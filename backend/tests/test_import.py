from typing import Any

from fastapi.testclient import TestClient
from helpers import (
    create_dependency,
    create_node,
    create_project,
    empty_document,
    export_document,
    node_document,
)


def import_document(client: TestClient, document: dict[str, Any]) -> Any:
    return client.post("/api/projects/import", json=document)


def test_export_import_round_trip_preserves_data(client: TestClient) -> None:
    project = create_project(client, "Original")
    primary = create_node(client, project, "Primary", description="Ambition")
    secondary = create_node(client, project, "Secondary", parent_id=primary["id"])
    action = create_node(
        client,
        project,
        "Action",
        node_type="action",
        parent_id=secondary["id"],
        canvas_x=12.5,
        canvas_y=-3.5,
    )
    other_action = create_node(
        client, project, "Other action", node_type="action", parent_id=primary["id"]
    )
    create_dependency(client, project, action["id"], secondary["id"])
    tasks_url = f"/api/projects/{project}/actions/{action['id']}/tasks"
    client.post(tasks_url, json={"text": "First"})
    done = client.post(tasks_url, json={"text": "Second"}).json()
    client.patch(
        f"/api/projects/{project}/tasks/{done['id']}", json={"is_completed": True}
    )
    client.put(
        f"/api/projects/{project}/actions/{action['id']}/task-settings",
        json={"display_style": "numbered"},
    )

    document = export_document(client, project)
    created = import_document(client, document)
    assert created.status_code == 201, created.text
    imported = created.json()["id"]

    nodes = client.get(f"/api/projects/{imported}/nodes").json()
    assert {node["text"] for node in nodes} == {
        "Primary",
        "Secondary",
        "Action",
        "Other action",
    }
    by_text = {node["text"]: node for node in nodes}
    assert by_text["Secondary"]["parent_id"] == by_text["Primary"]["id"]
    assert by_text["Action"]["parent_id"] == by_text["Secondary"]["id"]
    assert by_text["Primary"]["description"] == "Ambition"
    assert by_text["Action"]["canvas_x"] == 12.5
    assert all(node["project_id"] == imported for node in nodes)
    assert by_text["Action"]["id"] != action["id"]
    assert by_text["Other action"]["id"] != other_action["id"]

    edges = client.get(f"/api/projects/{imported}/dependencies").json()
    assert [(edge["predecessor_id"], edge["successor_id"]) for edge in edges] == [
        (by_text["Action"]["id"], by_text["Secondary"]["id"])
    ]

    imported_action = by_text["Action"]["id"]
    imported_tasks = client.get(
        f"/api/projects/{imported}/actions/{imported_action}/tasks"
    ).json()
    assert [(task["text"], task["is_completed"], task["position"]) for task in
            imported_tasks] == [("First", False, 0), ("Second", True, 1)]
    assert (
        client.get(
            f"/api/projects/{imported}/actions/{imported_action}/task-settings"
        ).json()["display_style"]
        == "numbered"
    )


def test_import_rejects_containment_cycles(client: TestClient) -> None:
    document = empty_document(
        nodes=[
            node_document("a", "A", parent_id="b"),
            node_document("b", "B", parent_id="a"),
        ]
    )
    response = import_document(client, document)
    assert response.status_code == 422
    assert client.get("/api/projects").json() == []


def test_import_rejects_a_third_goal_level(client: TestClient) -> None:
    document = empty_document(
        nodes=[
            node_document("a", "A"),
            node_document("b", "B", parent_id="a"),
            node_document("c", "C", parent_id="b"),
        ]
    )
    response = import_document(client, document)
    assert response.status_code == 422
    assert "primary and secondary" in response.json()["detail"]
    assert client.get("/api/projects").json() == []


def test_import_rejects_actions_with_children_or_no_parent(
    client: TestClient,
) -> None:
    with_child = empty_document(
        nodes=[
            node_document("a", "A"),
            node_document("b", "B", node_type="action", parent_id="a"),
            node_document("c", "C", node_type="action", parent_id="b"),
        ]
    )
    assert import_document(client, with_child).status_code == 422
    orphan = empty_document(nodes=[node_document("a", "A", node_type="action")])
    assert import_document(client, orphan).status_code == 422
    assert client.get("/api/projects").json() == []


def test_import_rejects_duplicate_node_ids(client: TestClient) -> None:
    document = empty_document(
        nodes=[node_document("a", "A"), node_document("a", "Also A")]
    )
    response = import_document(client, document)
    assert response.status_code == 422
    assert "duplicate node id" in response.json()["detail"]


def test_import_rejects_unknown_references(client: TestClient) -> None:
    document = empty_document(
        nodes=[node_document("a", "A")],
        dependencies=[{"predecessor_id": "a", "successor_id": "missing"}],
    )
    assert import_document(client, document).status_code == 422
    document = empty_document(
        nodes=[node_document("a", "A")],
        tasks=[
            {
                "id": "t1",
                "action_id": "missing",
                "text": "Task",
                "is_completed": False,
                "position": 0,
            }
        ],
    )
    assert import_document(client, document).status_code == 422


def test_import_rejects_tasks_on_goals(client: TestClient) -> None:
    document = empty_document(
        nodes=[node_document("a", "A")],
        tasks=[
            {
                "id": "t1",
                "action_id": "a",
                "text": "Task",
                "is_completed": False,
                "position": 0,
            }
        ],
    )
    response = import_document(client, document)
    assert response.status_code == 422
    assert "only available on actions" in response.json()["detail"]


def test_import_rejects_invalid_and_cyclic_dependencies(client: TestClient) -> None:
    cross_level = empty_document(
        nodes=[node_document("a", "A"), node_document("b", "B", parent_id="a")],
        dependencies=[{"predecessor_id": "a", "successor_id": "b"}],
    )
    assert import_document(client, cross_level).status_code == 422
    cyclic = empty_document(
        nodes=[node_document("a", "A"), node_document("b", "B")],
        dependencies=[
            {"predecessor_id": "a", "successor_id": "b"},
            {"predecessor_id": "b", "successor_id": "a"},
        ],
    )
    response = import_document(client, cyclic)
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"]
    assert client.get("/api/projects").json() == []


def test_import_normalises_duplicate_task_positions(client: TestClient) -> None:
    document = empty_document(
        nodes=[
            node_document("a", "A"),
            node_document("b", "B", node_type="action", parent_id="a"),
        ],
        tasks=[
            {
                "id": f"t{index}",
                "action_id": "b",
                "text": f"Task {index}",
                "is_completed": False,
                "position": 0,
            }
            for index in range(3)
        ],
    )
    response = import_document(client, document)
    assert response.status_code == 201, response.text
    imported = response.json()["id"]
    action = next(
        node
        for node in client.get(f"/api/projects/{imported}/nodes").json()
        if node["node_type"] == "action"
    )
    tasks = client.get(
        f"/api/projects/{imported}/actions/{action['id']}/tasks"
    ).json()
    assert [task["position"] for task in tasks] == [0, 1, 2]


def test_import_rejects_oversized_and_unknown_fields(client: TestClient) -> None:
    oversized = empty_document(
        nodes=[node_document(f"n{index}", f"Node {index}") for index in range(2001)]
    )
    assert import_document(client, oversized).status_code == 422
    unexpected = empty_document(nodes=[], surprise="payload")
    assert import_document(client, unexpected).status_code == 422
    long_description = empty_document(
        nodes=[node_document("a", "A") | {"description": "x" * 5001}]
    )
    assert import_document(client, long_description).status_code == 422
    assert client.get("/api/projects").json() == []
