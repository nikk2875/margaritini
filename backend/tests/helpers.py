from typing import Any

from fastapi.testclient import TestClient


def create_project(client: TestClient, name: str = "Test") -> str:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    project_id: str = response.json()["id"]
    return project_id


def create_node(
    client: TestClient, project_id: str, text: str, **extra: object
) -> dict[str, Any]:
    response = client.post(
        f"/api/projects/{project_id}/nodes", json={"text": text, **extra}
    )
    body: dict[str, Any] = response.json()
    return body


def create_dependency(
    client: TestClient, project_id: str, predecessor_id: str, successor_id: str
) -> Any:
    return client.post(
        f"/api/projects/{project_id}/dependencies",
        json={"predecessor_id": predecessor_id, "successor_id": successor_id},
    )


def export_document(client: TestClient, project_id: str) -> dict[str, Any]:
    response = client.get(f"/api/projects/{project_id}/export")
    assert response.status_code == 200, response.text
    document: dict[str, Any] = response.json()
    return document


def empty_document(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "format_version": 1,
        "name": "Imported",
        "nodes": [],
        "dependencies": [],
        "tasks": [],
        "task_settings": [],
    }
    document.update(overrides)
    return document


def node_document(
    node_id: str,
    text: str = "Node",
    node_type: str = "goal",
    parent_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "text": text,
        "node_type": node_type,
        "description": "",
        "parent_id": parent_id,
        "canvas_x": 0,
        "canvas_y": 0,
    }
