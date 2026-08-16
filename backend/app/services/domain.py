from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.models import (
    ActionTaskSettings,
    Dependency,
    Node,
    NodeType,
    Project,
    Task,
)

# SQLite caps the number of bound parameters per statement.
QUERY_CHUNK_SIZE = 500
MAX_GOAL_LEVELS = 2


class NodeLike(Protocol):
    """Shared shape of stored nodes and imported node documents."""

    id: str
    parent_id: str | None
    node_type: NodeType


def not_found(kind: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{kind} not found")


def invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def chunked(values: Sequence[str]) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), QUERY_CHUNK_SIZE):
        yield values[start : start + QUERY_CHUNK_SIZE]


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project")
    return project


def touch_project(db: Session, project_id: str) -> None:
    """Keep projects.updated_at meaningful for "most recently changed" order."""
    project = db.get(Project, project_id)
    if project is not None:
        project.updated_at = datetime.now(UTC).replace(tzinfo=None)


def get_node(db: Session, node_id: str) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise not_found("Node")
    return node


def get_project_node(db: Session, project_id: str, node_id: str) -> Node:
    """Every node lookup is scoped so ids from other projects stay invisible."""
    node = db.get(Node, node_id)
    if node is None or node.project_id != project_id:
        raise not_found("Node")
    return node


def get_project_action(db: Session, project_id: str, action_id: str) -> Node:
    action = get_project_node(db, project_id, action_id)
    if action.node_type != NodeType.ACTION:
        raise invalid("Tasks are only available on actions")
    return action


def get_project_task(db: Session, project_id: str, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task")
    action = db.get(Node, task.action_id)
    if action is None or action.project_id != project_id:
        raise not_found("Task")
    return task


def get_project_dependency(
    db: Session, project_id: str, dependency_id: str
) -> Dependency:
    edge = db.get(Dependency, dependency_id)
    if edge is None or edge.project_id != project_id:
        raise not_found("Dependency")
    return edge


def subtree_levels(db: Session, node_id: str) -> list[list[str]]:
    """Ids of a subtree grouped by depth, walked with a single query per level."""
    levels, visited = [[node_id]], {node_id}
    while True:
        children: list[str] = []
        for batch in chunked(levels[-1]):
            children.extend(
                db.scalars(select(Node.id).where(Node.parent_id.in_(batch))).all()
            )
        children = [child for child in children if child not in visited]
        if not children:
            return levels
        visited.update(children)
        levels.append(children)


def descendants(db: Session, node_id: str) -> set[str]:
    return {node_id for level in subtree_levels(db, node_id) for node_id in level}


def subtree_goal_depth(db: Session, node_id: str) -> int:
    """Goal levels stored below a node (0 when it contains no goals)."""
    depth, level, visited = 0, [node_id], {node_id}
    while level:
        children: list[str] = []
        for batch in chunked(level):
            children.extend(
                db.scalars(
                    select(Node.id).where(
                        Node.parent_id.in_(batch), Node.node_type == NodeType.GOAL
                    )
                ).all()
            )
        level = [child for child in children if child not in visited]
        visited.update(level)
        if level:
            depth += 1
    return depth


def validate_parent(db: Session, node: Node, parent_id: str | None) -> None:
    if parent_id is None:
        if node.node_type == NodeType.ACTION:
            raise invalid("An action must belong to a goal")
        return
    parent = get_node(db, parent_id)
    if parent.project_id != node.project_id:
        raise invalid("Parent must belong to the same project")
    if parent.node_type == NodeType.ACTION:
        raise invalid("An action cannot contain children")
    if parent_id == node.id or parent_id in descendants(db, node.id):
        raise invalid("Containment cannot form a cycle")
    if node.node_type == NodeType.GOAL:
        parent_level = 1 if parent.parent_id is None else 2
        # The whole moved subtree has to stay within the allowed goal levels.
        deepest = parent_level + 1 + subtree_goal_depth(db, node.id)
        if deepest > MAX_GOAL_LEVELS:
            raise invalid("Goals are limited to primary and secondary levels")


def validate_node_type(db: Session, node: Node, node_type: NodeType) -> None:
    if node_type == NodeType.ACTION:
        if node.parent_id is None:
            raise invalid("An action must belong to a goal")
        if db.scalar(select(Node.id).where(Node.parent_id == node.id).limit(1)):
            raise invalid("A goal with children cannot become an action")
    else:
        if db.scalar(select(Task.id).where(Task.action_id == node.id).limit(1)):
            raise invalid("An action with tasks cannot become a goal")


def validate_action(db: Session, action_id: str) -> Node:
    action = get_node(db, action_id)
    if action.node_type != NodeType.ACTION:
        raise invalid("Tasks are only available on actions")
    return action


def dependency_rule_error(
    predecessor: NodeLike, successor: NodeLike
) -> str | None:
    """Connection rules shared by the interactive API and project import."""
    if predecessor.id == successor.id:
        return "A node cannot depend on itself"
    if (
        predecessor.node_type == NodeType.GOAL
        and successor.node_type == NodeType.GOAL
    ):
        if (predecessor.parent_id is None) != (successor.parent_id is None):
            return "Goals can only depend on goals at the same level"
        return None
    if (
        predecessor.node_type == NodeType.ACTION
        and successor.node_type == NodeType.ACTION
    ):
        if predecessor.parent_id != successor.parent_id:
            return "Actions can only connect when they share a parent goal"
        return None
    action, goal = (
        (predecessor, successor)
        if predecessor.node_type == NodeType.ACTION
        else (successor, predecessor)
    )
    if action.parent_id != goal.id:
        return "An action can only connect to its parent goal"
    return None


def dependency_cycle_error(
    reachable_from: dict[str, list[str]], predecessor_id: str, successor_id: str
) -> str | None:
    """Adding predecessor -> successor is cyclic when successor reaches it."""
    visited, pending = {successor_id}, [successor_id]
    while pending:
        current = pending.pop()
        for next_id in reachable_from.get(current, []):
            if next_id == predecessor_id:
                return "Dependency would create a cycle"
            if next_id not in visited:
                visited.add(next_id)
                pending.append(next_id)
    return None


def validate_dependency(
    db: Session, project_id: str, predecessor_id: str, successor_id: str
) -> None:
    if predecessor_id == successor_id:
        raise invalid("A node cannot depend on itself")
    predecessor = db.get(Node, predecessor_id)
    successor = db.get(Node, successor_id)
    if (
        predecessor is None
        or successor is None
        or predecessor.project_id != project_id
        or successor.project_id != project_id
    ):
        raise invalid("Dependency nodes must belong to the project")
    error = dependency_rule_error(predecessor, successor)
    if error:
        raise invalid(error)
    edges: dict[str, list[str]] = defaultdict(list)
    for stored_predecessor, stored_successor in db.execute(
        select(Dependency.predecessor_id, Dependency.successor_id).where(
            Dependency.project_id == project_id
        )
    ).all():
        edges[stored_predecessor].append(stored_successor)
    cycle = dependency_cycle_error(edges, predecessor_id, successor_id)
    if cycle:
        raise invalid(cycle)


def revalidate_dependencies(db: Session, node: Node) -> None:
    """Reject a node change that would leave an existing dependency invalid.

    Re-parenting a goal or converting a node can break connection rules for
    edges that were valid when they were drawn, so the change is rejected
    rather than silently deleting the user's connections.
    """
    edges = db.scalars(
        select(Dependency).where(
            (Dependency.predecessor_id == node.id)
            | (Dependency.successor_id == node.id)
        )
    ).all()
    for edge in edges:
        predecessor = (
            node
            if edge.predecessor_id == node.id
            else get_node(db, edge.predecessor_id)
        )
        successor = (
            node if edge.successor_id == node.id else get_node(db, edge.successor_id)
        )
        error = dependency_rule_error(predecessor, successor)
        if error:
            raise invalid(f"An existing dependency would become invalid: {error}")


def delete_subtree(db: Session, node: Node) -> None:
    levels = subtree_levels(db, node.id)
    ids = [node_id for level in levels for node_id in level]
    for batch in chunked(ids):
        db.execute(
            delete(Dependency).where(
                Dependency.predecessor_id.in_(batch)
                | Dependency.successor_id.in_(batch)
            )
        )
        db.execute(delete(Task).where(Task.action_id.in_(batch)))
        db.execute(
            delete(ActionTaskSettings).where(ActionTaskSettings.action_id.in_(batch))
        )
    # Delete leaves first so this works independently of FK cascade configuration.
    for level in reversed(levels):
        for batch in chunked(level):
            db.execute(delete(Node).where(Node.id.in_(batch)))


def validate_import_hierarchy(nodes: Sequence[NodeLike]) -> dict[str, NodeLike]:
    """Apply the interactive containment rules to an imported document."""
    by_id: dict[str, NodeLike] = {}
    for node in nodes:
        if node.id in by_id:
            raise invalid(f"Import contains a duplicate node id: {node.id}")
        by_id[node.id] = node
    children: dict[str, list[NodeLike]] = defaultdict(list)
    for node in nodes:
        if node.parent_id is not None:
            if node.parent_id not in by_id:
                raise invalid(f"Import references an unknown node: {node.parent_id}")
            children[node.parent_id].append(node)
    for node in nodes:
        seen, current = {node.id}, node
        while current.parent_id is not None:
            if current.parent_id in seen:
                raise invalid("Containment cannot form a cycle")
            seen.add(current.parent_id)
            current = by_id[current.parent_id]
        if node.node_type == NodeType.ACTION:
            if node.parent_id is None:
                raise invalid("An action must belong to a goal")
            if children[node.id]:
                raise invalid("An action cannot contain children")
            if by_id[node.parent_id].node_type != NodeType.GOAL:
                raise invalid("An action cannot contain children")
        else:
            if len(seen) > MAX_GOAL_LEVELS:
                raise invalid("Goals are limited to primary and secondary levels")
    return by_id


class DependencyLike(Protocol):
    predecessor_id: str
    successor_id: str


def validate_import_dependencies(
    by_id: dict[str, NodeLike], dependencies: Sequence[DependencyLike]
) -> None:
    edges: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for edge in dependencies:
        for node_id in (edge.predecessor_id, edge.successor_id):
            if node_id not in by_id:
                raise invalid(f"Import references an unknown node: {node_id}")
        pair = (edge.predecessor_id, edge.successor_id)
        if pair in seen:
            raise invalid("Import contains a duplicate dependency")
        seen.add(pair)
        error = dependency_rule_error(
            by_id[edge.predecessor_id], by_id[edge.successor_id]
        )
        if error:
            raise invalid(error)
        cycle = dependency_cycle_error(edges, edge.predecessor_id, edge.successor_id)
        if cycle:
            raise invalid(cycle)
        edges[edge.predecessor_id].append(edge.successor_id)


def validate_import_action_targets(
    by_id: dict[str, NodeLike], action_ids: Iterable[str], kind: str
) -> None:
    for action_id in action_ids:
        node = by_id.get(action_id)
        if node is None:
            raise invalid(f"Import references an unknown node: {action_id}")
        if node.node_type != NodeType.ACTION:
            raise invalid(f"{kind} are only available on actions")
