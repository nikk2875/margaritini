from fastapi.testclient import TestClient
from helpers import create_dependency, create_node, create_project


def test_actions_cannot_have_children_or_goals_with_tasks(client: TestClient) -> None:
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
            f"/api/projects/{project}/actions/{goal['id']}/tasks", json={"text": "No"}
        ).status_code
        == 422
    )


def test_action_accepts_multiple_tasks_in_order(client: TestClient) -> None:
    project = create_project(client)
    parent = create_node(client, project, "Parent")
    action = create_node(
        client, project, "Action", node_type="action", parent_id=parent["id"]
    )
    tasks_url = f"/api/projects/{project}/actions/{action['id']}/tasks"
    first = client.post(tasks_url, json={"text": "First"})
    second = client.post(tasks_url, json={"text": "Second"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert [task["position"] for task in client.get(tasks_url).json()] == [0, 1]


def test_actions_must_have_a_goal_parent(client: TestClient) -> None:
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
        client.post(
            f"/api/projects/{project}/nodes/{root_goal['id']}/convert-to-action"
        ).status_code
        == 422
    )


def test_goal_levels_and_dependency_connection_rules(client: TestClient) -> None:
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
        create_dependency(client, project, primary_one["id"], primary_two["id"])
    ).status_code == 201
    assert (
        create_dependency(client, project, secondary_one["id"], secondary_two["id"])
    ).status_code == 201
    assert (
        create_dependency(client, project, primary_one["id"], secondary_one["id"])
    ).status_code == 422
    action = create_node(
        client, project, "Action", node_type="action", parent_id=primary_one["id"]
    )
    assert (
        create_dependency(client, project, action["id"], primary_one["id"])
    ).status_code == 201
    sibling_action = create_node(
        client,
        project,
        "Sibling action",
        node_type="action",
        parent_id=primary_one["id"],
    )
    assert (
        create_dependency(client, project, action["id"], sibling_action["id"])
    ).status_code == 201
    assert (
        create_dependency(client, project, action["id"], secondary_one["id"])
    ).status_code == 422


def test_conversion_and_dependency_cycles_are_rejected(client: TestClient) -> None:
    project = create_project(client)
    parent = create_node(client, project, "Parent")
    create_node(client, project, "Child", parent_id=parent["id"])
    assert (
        client.post(
            f"/api/projects/{project}/nodes/{parent['id']}/convert-to-action"
        ).status_code
        == 422
    )
    first = create_node(client, project, "First")
    second = create_node(client, project, "Second")
    assert (
        create_dependency(client, project, first["id"], second["id"])
    ).status_code == 201
    assert (
        create_dependency(client, project, second["id"], first["id"])
    ).status_code == 422


def test_deleting_subtree_removes_dependencies(client: TestClient) -> None:
    project = create_project(client)
    parent = create_node(client, project, "Parent")
    child = create_node(client, project, "Child", parent_id=parent["id"])
    outside_parent = create_node(client, project, "Outside parent")
    outside = create_node(client, project, "Outside", parent_id=outside_parent["id"])
    assert (
        create_dependency(client, project, child["id"], outside["id"])
    ).status_code == 201
    delete_url = f"/api/projects/{project}/nodes/{parent['id']}"
    assert client.delete(delete_url).status_code == 204
    remaining = client.get(f"/api/projects/{project}/nodes").json()
    assert {node["id"] for node in remaining} == {
        outside_parent["id"],
        outside["id"],
    }
    assert client.get(f"/api/projects/{project}/dependencies").json() == []


def test_reparenting_a_goal_cannot_create_a_third_level(client: TestClient) -> None:
    project = create_project(client)
    primary_one = create_node(client, project, "Primary one")
    primary_two = create_node(client, project, "Primary two")
    create_node(client, project, "Secondary", parent_id=primary_one["id"])
    response = client.patch(
        f"/api/projects/{project}/nodes/{primary_one['id']}",
        json={"parent_id": primary_two["id"]},
    )
    assert response.status_code == 422
    assert "primary and secondary" in response.json()["detail"]
    # A goal without goal children may still move to the secondary level.
    assert (
        client.patch(
            f"/api/projects/{project}/nodes/{primary_two['id']}",
            json={"parent_id": primary_one["id"]},
        ).status_code
        == 200
    )


def test_reparenting_is_rejected_when_it_invalidates_a_dependency(
    client: TestClient,
) -> None:
    project = create_project(client)
    primary_one = create_node(client, project, "Primary one")
    primary_two = create_node(client, project, "Primary two")
    spare = create_node(client, project, "Primary three")
    assert (
        create_dependency(client, project, primary_one["id"], primary_two["id"])
    ).status_code == 201
    response = client.patch(
        f"/api/projects/{project}/nodes/{primary_one['id']}",
        json={"parent_id": spare["id"]},
    )
    assert response.status_code == 422
    assert "existing dependency" in response.json()["detail"]
    assert len(client.get(f"/api/projects/{project}/dependencies").json()) == 1


def test_conversion_is_rejected_when_it_invalidates_a_dependency(
    client: TestClient,
) -> None:
    project = create_project(client)
    goal = create_node(client, project, "Goal")
    action = create_node(
        client, project, "Action", node_type="action", parent_id=goal["id"]
    )
    sibling = create_node(
        client, project, "Sibling", node_type="action", parent_id=goal["id"]
    )
    assert (
        create_dependency(client, project, action["id"], sibling["id"])
    ).status_code == 201
    response = client.post(
        f"/api/projects/{project}/nodes/{action['id']}/convert-to-goal"
    )
    assert response.status_code == 422
    assert "existing dependency" in response.json()["detail"]


def test_conversion_round_trip_keeps_task_settings_usable(client: TestClient) -> None:
    project = create_project(client)
    goal = create_node(client, project, "Goal")
    node = create_node(
        client, project, "Action", node_type="action", parent_id=goal["id"]
    )
    node_url = f"/api/projects/{project}/nodes/{node['id']}"
    assert client.post(f"{node_url}/convert-to-goal").status_code == 200
    assert client.post(f"{node_url}/convert-to-action").status_code == 200
    assert client.post(f"{node_url}/convert-to-goal").status_code == 200
    assert client.post(f"{node_url}/convert-to-action").status_code == 200
    settings_url = f"/api/projects/{project}/actions/{node['id']}/task-settings"
    assert client.get(settings_url).json()["display_style"] == "bulleted"


def test_reading_task_settings_does_not_write(client: TestClient) -> None:
    project = create_project(client)
    goal = create_node(client, project, "Goal")
    action = create_node(
        client, project, "Action", node_type="action", parent_id=goal["id"]
    )
    settings_url = f"/api/projects/{project}/actions/{action['id']}/task-settings"
    before = client.get(f"/api/projects/{project}").json()["updated_at"]
    assert client.get(settings_url).json() == {
        "action_id": action["id"],
        "display_style": "bulleted",
    }
    assert client.get(f"/api/projects/{project}").json()["updated_at"] == before
    assert (
        client.put(settings_url, json={"display_style": "numbered"}).status_code == 200
    )
    assert client.get(settings_url).json()["display_style"] == "numbered"


def test_project_modification_time_tracks_content_changes(client: TestClient) -> None:
    project = create_project(client)
    before = client.get(f"/api/projects/{project}").json()["updated_at"]
    goal = create_node(client, project, "Goal")
    after_node = client.get(f"/api/projects/{project}").json()["updated_at"]
    assert after_node >= before
    action = create_node(
        client, project, "Action", node_type="action", parent_id=goal["id"]
    )
    client.post(
        f"/api/projects/{project}/actions/{action['id']}/tasks", json={"text": "Task"}
    )
    assert client.get(f"/api/projects/{project}").json()["updated_at"] >= after_node


def test_tasks_can_be_reordered(client: TestClient) -> None:
    project = create_project(client)
    goal = create_node(client, project, "Goal")
    action = create_node(
        client, project, "Action", node_type="action", parent_id=goal["id"]
    )
    tasks_url = f"/api/projects/{project}/actions/{action['id']}/tasks"
    ids = [
        client.post(tasks_url, json={"text": text}).json()["id"]
        for text in ("First", "Second", "Third")
    ]
    response = client.put(
        f"{tasks_url}/reorder", json={"task_ids": [ids[2], ids[0], ids[1]]}
    )
    assert response.status_code == 200
    assert [task["id"] for task in client.get(tasks_url).json()] == [
        ids[2],
        ids[0],
        ids[1],
    ]
    partial = client.put(f"{tasks_url}/reorder", json={"task_ids": ids[:2]})
    assert partial.status_code == 422


def test_dependency_can_be_reversed_atomically(client: TestClient) -> None:
    project = create_project(client)
    first = create_node(client, project, "First")
    second = create_node(client, project, "Second")
    edge = create_dependency(client, project, first["id"], second["id"]).json()
    reversed_edge = client.post(
        f"/api/projects/{project}/dependencies/{edge['id']}/reverse"
    )
    assert reversed_edge.status_code == 200
    assert reversed_edge.json()["predecessor_id"] == second["id"]
    assert reversed_edge.json()["successor_id"] == first["id"]
    assert len(client.get(f"/api/projects/{project}/dependencies").json()) == 1


def test_reversing_an_invalid_dependency_keeps_the_original(
    client: TestClient,
) -> None:
    project = create_project(client)
    first = create_node(client, project, "First")
    second = create_node(client, project, "Second")
    third = create_node(client, project, "Third")
    create_dependency(client, project, first["id"], second["id"])
    create_dependency(client, project, second["id"], third["id"])
    edge = create_dependency(client, project, first["id"], third["id"]).json()
    # third -> first would close the first -> second -> third chain.
    response = client.post(
        f"/api/projects/{project}/dependencies/{edge['id']}/reverse"
    )
    assert response.status_code == 422
    stored = client.get(f"/api/projects/{project}/dependencies").json()
    assert sorted(
        (item["predecessor_id"], item["successor_id"]) for item in stored
    ) == sorted(
        [
            (first["id"], second["id"]),
            (second["id"], third["id"]),
            (first["id"], third["id"]),
        ]
    )
