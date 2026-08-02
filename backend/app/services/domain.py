from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.models import ActionTaskSettings, Dependency, Node, NodeType, Task


def not_found(kind: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{kind} not found")


def invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def get_node(db: Session, node_id: str) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise not_found("Node")
    return node


def descendants(db: Session, node_id: str) -> set[str]:
    result, pending = {node_id}, [node_id]
    while pending:
        children = db.scalars(select(Node.id).where(Node.parent_id.in_(pending))).all()
        pending = [child for child in children if child not in result]
        result.update(pending)
    return result


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
    if node.node_type == NodeType.GOAL and parent.parent_id is not None:
        raise invalid("Goals are limited to primary and secondary levels")
    if parent_id in descendants(db, node.id):
        raise invalid("Containment cannot form a cycle")


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


def validate_dependency(
    db: Session, project_id: str, predecessor_id: str, successor_id: str
) -> None:
    if predecessor_id == successor_id:
        raise invalid("A node cannot depend on itself")
    predecessor, successor = get_node(db, predecessor_id), get_node(db, successor_id)
    if predecessor.project_id != project_id or successor.project_id != project_id:
        raise invalid("Dependency nodes must belong to the project")
    if predecessor.node_type == NodeType.GOAL and successor.node_type == NodeType.GOAL:
        if (predecessor.parent_id is None) != (successor.parent_id is None):
            raise invalid("Goals can only depend on goals at the same level")
    elif (
        predecessor.node_type == NodeType.ACTION
        and successor.node_type == NodeType.ACTION
    ):
        if predecessor.parent_id != successor.parent_id:
            raise invalid("Actions can only connect when they share a parent goal")
    elif (
        predecessor.node_type == NodeType.ACTION
        and successor.node_type == NodeType.GOAL
    ):
        if predecessor.parent_id != successor.id:
            raise invalid("An action can only connect to its parent goal")
    elif (
        successor.node_type == NodeType.ACTION
        and predecessor.node_type == NodeType.GOAL
    ):
        if successor.parent_id != predecessor.id:
            raise invalid("An action can only connect to its parent goal")
    else:
        raise invalid(
            "Actions can only connect to their parent goal or sibling actions"
        )
    # Adding predecessor -> successor is cyclic when successor already reaches predecessor.
    visited, pending = {successor_id}, [successor_id]
    while pending:
        current = pending.pop()
        next_ids = db.scalars(
            select(Dependency.successor_id).where(
                Dependency.project_id == project_id,
                Dependency.predecessor_id == current,
            )
        ).all()
        for next_id in next_ids:
            if next_id == predecessor_id:
                raise invalid("Dependency would create a cycle")
            if next_id not in visited:
                visited.add(next_id)
                pending.append(next_id)


def delete_subtree(db: Session, node: Node) -> None:
    ids = descendants(db, node.id)
    db.execute(
        delete(Dependency).where(
            Dependency.predecessor_id.in_(ids) | Dependency.successor_id.in_(ids)
        )
    )
    db.execute(delete(Task).where(Task.action_id.in_(ids)))
    db.execute(delete(ActionTaskSettings).where(ActionTaskSettings.action_id.in_(ids)))
    # Delete leaves first so this works independently of FK cascade configuration.
    for node_id in sorted(
        ids, key=lambda item: len(descendants(db, item)), reverse=True
    ):
        db.execute(delete(Node).where(Node.id == node_id))
