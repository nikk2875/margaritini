from collections.abc import Generator

import pytest
from app.db.database import Base, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def isolated_database() -> Generator[None]:
    """Tests never create or modify the development SQLite database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)

    def override_get_db() -> Generator[Session]:
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def create_project(client: TestClient) -> str:
    return client.post("/api/projects", json={"name": "Test"}).json()["id"]


def create_node(
    client: TestClient, project_id: str, text: str, **extra: object
) -> dict:
    return client.post(
        f"/api/projects/{project_id}/nodes", json={"text": text, **extra}
    ).json()


def test_actions_cannot_have_children_or_goals_with_tasks() -> None:
    with TestClient(app) as client:
        project = create_project(client)
        parent = create_node(client, project, "Parent")
        action = create_node(
            client, project, "Action", node_type="action", parent_id=parent["id"]
        )
        response = client.post(
            f"/api/projects/{project}/nodes",
            json={"text": "Child", "parent_id": action["id"]},
        )
        assert response.status_code == 422
        goal = create_node(client, project, "Goal")
        assert (
            client.post(
                f"/api/actions/{goal['id']}/tasks", json={"text": "No"}
            ).status_code
            == 422
        )


def test_action_accepts_multiple_tasks_in_order() -> None:
    with TestClient(app) as client:
        project = create_project(client)
        parent = create_node(client, project, "Parent")
        action = create_node(
            client, project, "Action", node_type="action", parent_id=parent["id"]
        )
        first = client.post(
            f"/api/actions/{action['id']}/tasks", json={"text": "First"}
        )
        second = client.post(
            f"/api/actions/{action['id']}/tasks", json={"text": "Second"}
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert [
            task["position"]
            for task in client.get(f"/api/actions/{action['id']}/tasks").json()
        ] == [0, 1]


def test_actions_must_have_a_goal_parent() -> None:
    with TestClient(app) as client:
        project = create_project(client)
        assert (
            client.post(
                f"/api/projects/{project}/nodes",
                json={"text": "Orphan action", "node_type": "action"},
            ).status_code
            == 422
        )
        root_goal = create_node(client, project, "Root goal")
        assert (
            client.post(f"/api/nodes/{root_goal['id']}/convert-to-action").status_code
            == 422
        )


def test_goal_levels_and_dependency_connection_rules() -> None:
    with TestClient(app) as client:
        project = create_project(client)
        primary_one = create_node(client, project, "Primary one")
        primary_two = create_node(client, project, "Primary two")
        secondary_one = create_node(
            client, project, "Secondary one", parent_id=primary_one["id"]
        )
        secondary_two = create_node(
            client, project, "Secondary two", parent_id=primary_two["id"]
        )
        assert (
            client.post(
                f"/api/projects/{project}/nodes",
                json={"text": "Third level", "parent_id": secondary_one["id"]},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={
                    "predecessor_id": primary_one["id"],
                    "successor_id": primary_two["id"],
                },
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={
                    "predecessor_id": secondary_one["id"],
                    "successor_id": secondary_two["id"],
                },
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={
                    "predecessor_id": primary_one["id"],
                    "successor_id": secondary_one["id"],
                },
            ).status_code
            == 422
        )
        action = create_node(
            client, project, "Action", node_type="action", parent_id=primary_one["id"]
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={
                    "predecessor_id": action["id"],
                    "successor_id": primary_one["id"],
                },
            ).status_code
            == 201
        )
        sibling_action = create_node(
            client,
            project,
            "Sibling action",
            node_type="action",
            parent_id=primary_one["id"],
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={
                    "predecessor_id": action["id"],
                    "successor_id": sibling_action["id"],
                },
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={
                    "predecessor_id": action["id"],
                    "successor_id": secondary_one["id"],
                },
            ).status_code
            == 422
        )


def test_conversion_and_dependency_cycles_are_rejected() -> None:
    with TestClient(app) as client:
        project = create_project(client)
        parent = create_node(client, project, "Parent")
        create_node(client, project, "Child", parent_id=parent["id"])
        assert (
            client.post(f"/api/nodes/{parent['id']}/convert-to-action").status_code
            == 422
        )
        first = create_node(client, project, "First")
        second = create_node(client, project, "Second")
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={"predecessor_id": first["id"], "successor_id": second["id"]},
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={"predecessor_id": second["id"], "successor_id": first["id"]},
            ).status_code
            == 422
        )


def test_deleting_subtree_removes_dependencies() -> None:
    with TestClient(app) as client:
        project = create_project(client)
        parent = create_node(client, project, "Parent")
        child = create_node(client, project, "Child", parent_id=parent["id"])
        outside_parent = create_node(client, project, "Outside parent")
        outside = create_node(
            client, project, "Outside", parent_id=outside_parent["id"]
        )
        assert (
            client.post(
                f"/api/projects/{project}/dependencies",
                json={"predecessor_id": child["id"], "successor_id": outside["id"]},
            ).status_code
            == 201
        )
        assert client.delete(f"/api/nodes/{parent['id']}").status_code == 204
        remaining = client.get(f"/api/projects/{project}/nodes").json()
        assert {node["id"] for node in remaining} == {
            outside_parent["id"],
            outside["id"],
        }
        assert client.get(f"/api/projects/{project}/dependencies").json() == []
