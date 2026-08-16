import pytest
from app.core.config import settings
from app.core.security import API_TOKEN_HEADER
from app.main import app
from fastapi.testclient import TestClient
from helpers import create_dependency, create_node, create_project


def test_resources_are_scoped_to_their_project(client: TestClient) -> None:
    owner = create_project(client, "Owner")
    other = create_project(client, "Other")
    goal = create_node(client, owner, "Goal")
    action = create_node(
        client, owner, "Action", node_type="action", parent_id=goal["id"]
    )
    task = client.post(
        f"/api/projects/{owner}/actions/{action['id']}/tasks", json={"text": "Task"}
    ).json()
    sibling = create_node(
        client, owner, "Sibling", node_type="action", parent_id=goal["id"]
    )
    edge = create_dependency(client, owner, action["id"], sibling["id"]).json()

    assert client.get(f"/api/projects/{other}/nodes/{goal['id']}").status_code == 404
    assert (
        client.patch(
            f"/api/projects/{other}/nodes/{goal['id']}", json={"text": "Stolen"}
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/projects/{other}/nodes/{goal['id']}").status_code == 404
    )
    assert (
        client.post(
            f"/api/projects/{other}/nodes/{goal['id']}/convert-to-action"
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/projects/{other}/actions/{action['id']}/tasks").status_code
        == 404
    )
    assert (
        client.get(
            f"/api/projects/{other}/actions/{action['id']}/task-settings"
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/projects/{other}/tasks/{task['id']}", json={"text": "Stolen"}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/projects/{other}/tasks/{task['id']}").status_code == 404
    assert (
        client.delete(
            f"/api/projects/{other}/dependencies/{edge['id']}"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/projects/{other}/dependencies/{edge['id']}/reverse"
        ).status_code
        == 404
    )
    # Nothing was changed by the cross-project attempts.
    assert client.get(f"/api/projects/{owner}/nodes/{goal['id']}").json()["text"] == (
        "Goal"
    )


def test_nodes_cannot_be_parented_across_projects(client: TestClient) -> None:
    owner = create_project(client, "Owner")
    other = create_project(client, "Other")
    goal = create_node(client, owner, "Goal")
    response = client.post(
        f"/api/projects/{other}/nodes",
        json={"text": "Child", "parent_id": goal["id"]},
    )
    assert response.status_code == 404
    child = create_node(client, other, "Child")
    assert (
        client.patch(
            f"/api/projects/{other}/nodes/{child['id']}",
            json={"parent_id": goal["id"]},
        ).status_code
        == 404
    )


def test_dependencies_cannot_span_projects(client: TestClient) -> None:
    owner = create_project(client, "Owner")
    other = create_project(client, "Other")
    goal = create_node(client, owner, "Goal")
    foreign = create_node(client, other, "Foreign")
    assert create_dependency(client, other, goal["id"], foreign["id"]).status_code == (
        422
    )


def test_unknown_host_is_rejected() -> None:
    with TestClient(app, base_url="http://evil.example") as hostile:
        assert hostile.get("/health").status_code == 400


def test_oversized_body_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/projects",
        content=b'{"name": "' + b"x" * settings.max_request_bytes + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_api_token_is_enforced_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "api_token", "secret-token")
    assert client.get("/api/projects").status_code == 401
    assert (
        client.get("/api/projects", headers={API_TOKEN_HEADER: "wrong"}).status_code
        == 401
    )
    assert (
        client.get(
            "/api/projects", headers={API_TOKEN_HEADER: "secret-token"}
        ).status_code
        == 200
    )


def test_cors_is_limited_to_the_local_web_app(client: TestClient) -> None:
    allowed = client.options(
        "/api/projects",
        headers={
            "Origin": "http://localhost:6002",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:6002"
    assert "access-control-allow-credentials" not in allowed.headers
    blocked = client.options(
        "/api/projects",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in blocked.headers
