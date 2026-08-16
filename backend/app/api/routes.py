from collections import defaultdict
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_api_token
from app.db.database import get_db
from app.models.models import (
    ActionTaskSettings,
    Dependency,
    DisplayStyle,
    Node,
    NodeType,
    Project,
    Task,
    new_id,
)
from app.schemas.schemas import (
    DependencyCreate,
    DependencyOut,
    NodeCreate,
    NodeOut,
    NodeUpdate,
    ProjectCreate,
    ProjectExport,
    ProjectExportDependency,
    ProjectExportNode,
    ProjectExportSettings,
    ProjectExportTask,
    ProjectOut,
    ProjectUpdate,
    ReorderTasks,
    TaskCreate,
    TaskOut,
    TaskSettingsOut,
    TaskSettingsUpdate,
    TaskUpdate,
)
from app.services.domain import (
    delete_subtree,
    get_project,
    get_project_action,
    get_project_dependency,
    get_project_node,
    get_project_task,
    invalid,
    revalidate_dependencies,
    touch_project,
    validate_dependency,
    validate_import_action_targets,
    validate_import_dependencies,
    validate_import_hierarchy,
    validate_node_type,
    validate_parent,
)

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_token)])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> Sequence[Project]:
    return db.scalars(select(Project).order_by(Project.updated_at.desc())).all()


@router.post(
    "/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED
)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(name=body.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post(
    "/projects/import", response_model=ProjectOut, status_code=status.HTTP_201_CREATED
)
def import_project(body: ProjectExport, db: Session = Depends(get_db)) -> Project:
    """Import an untrusted document under the interactive domain rules."""
    by_id = validate_import_hierarchy(body.nodes)
    validate_import_dependencies(by_id, body.dependencies)
    validate_import_action_targets(
        by_id, (task.action_id for task in body.tasks), "Tasks"
    )
    validate_import_action_targets(
        by_id,
        (settings.action_id for settings in body.task_settings),
        "Task settings",
    )
    styled_actions = [settings.action_id for settings in body.task_settings]
    if len(styled_actions) != len(set(styled_actions)):
        raise invalid("Import contains duplicate task settings for an action")

    project = Project(id=new_id(), name=body.name)
    db.add(project)
    # Rows are flushed in dependency order: the models carry no relationships,
    # so the unit of work cannot order the inserts for the foreign keys.
    db.flush()
    id_map = {source.id: new_id() for source in body.nodes}
    db.add_all(
        Node(
            id=id_map[source.id],
            project_id=project.id,
            parent_id=id_map[source.parent_id] if source.parent_id else None,
            text=source.text,
            description=source.description,
            node_type=source.node_type,
            canvas_x=source.canvas_x,
            canvas_y=source.canvas_y,
        )
        for source in body.nodes
    )
    db.flush()
    db.add_all(
        Dependency(
            project_id=project.id,
            predecessor_id=id_map[source.predecessor_id],
            successor_id=id_map[source.successor_id],
        )
        for source in body.dependencies
    )
    tasks_by_action: dict[str, list[ProjectExportTask]] = defaultdict(list)
    for source_task in body.tasks:
        tasks_by_action[source_task.action_id].append(source_task)
    for action_id, action_tasks in tasks_by_action.items():
        # Positions are renumbered so a crafted document cannot collide.
        for position, source_task in enumerate(
            sorted(action_tasks, key=lambda item: item.position)
        ):
            db.add(
                Task(
                    action_id=id_map[action_id],
                    text=source_task.text,
                    is_completed=source_task.is_completed,
                    position=position,
                )
            )
    styles = {
        settings.action_id: settings.display_style for settings in body.task_settings
    }
    for source in body.nodes:
        if source.node_type == NodeType.ACTION:
            db.add(
                ActionTaskSettings(
                    action_id=id_map[source.id],
                    display_style=styles.get(source.id, DisplayStyle.BULLETED),
                )
            )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise invalid("Import contains conflicting data") from error
    db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project_detail(project_id: str, db: Session = Depends(get_db)) -> Project:
    return get_project(db, project_id)


@router.get("/projects/{project_id}/export", response_model=ProjectExport)
def export_project(project_id: str, db: Session = Depends(get_db)) -> ProjectExport:
    project = get_project(db, project_id)
    nodes = db.scalars(select(Node).where(Node.project_id == project_id)).all()
    node_ids = [node.id for node in nodes]
    return ProjectExport(
        name=project.name,
        nodes=[
            ProjectExportNode(
                id=node.id,
                text=node.text,
                description=node.description,
                node_type=node.node_type,
                parent_id=node.parent_id,
                canvas_x=node.canvas_x,
                canvas_y=node.canvas_y,
            )
            for node in nodes
        ],
        dependencies=[
            ProjectExportDependency(
                predecessor_id=edge.predecessor_id, successor_id=edge.successor_id
            )
            for edge in db.scalars(
                select(Dependency).where(Dependency.project_id == project_id)
            )
        ],
        tasks=[
            ProjectExportTask.model_validate(task)
            for task in db.scalars(select(Task).where(Task.action_id.in_(node_ids)))
        ],
        task_settings=[
            ProjectExportSettings.model_validate(settings)
            for settings in db.scalars(
                select(ActionTaskSettings).where(
                    ActionTaskSettings.action_id.in_(node_ids)
                )
            )
        ],
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str, body: ProjectUpdate, db: Session = Depends(get_db)
) -> Project:
    project = get_project(db, project_id)
    project.name = body.name
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> Response:
    db.delete(get_project(db, project_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/nodes", response_model=list[NodeOut])
def list_nodes(project_id: str, db: Session = Depends(get_db)) -> Sequence[Node]:
    get_project(db, project_id)
    return db.scalars(select(Node).where(Node.project_id == project_id)).all()


@router.post(
    "/projects/{project_id}/nodes",
    response_model=NodeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_node(
    project_id: str, body: NodeCreate, db: Session = Depends(get_db)
) -> Node:
    get_project(db, project_id)
    node = Node(
        id=new_id(),
        project_id=project_id,
        text=body.text,
        description=body.description,
        node_type=body.node_type,
        canvas_x=body.canvas_x,
        canvas_y=body.canvas_y,
    )
    if body.parent_id is not None:
        get_project_node(db, project_id, body.parent_id)
    validate_parent(db, node, body.parent_id)
    node.parent_id = body.parent_id
    db.add(node)
    if node.node_type == NodeType.ACTION:
        # The node row has to exist before its settings row references it.
        db.flush()
        db.add(ActionTaskSettings(action_id=node.id))
    touch_project(db, project_id)
    db.commit()
    db.refresh(node)
    return node


@router.get("/projects/{project_id}/nodes/{node_id}", response_model=NodeOut)
def read_node(project_id: str, node_id: str, db: Session = Depends(get_db)) -> Node:
    return get_project_node(db, project_id, node_id)


@router.patch("/projects/{project_id}/nodes/{node_id}", response_model=NodeOut)
def update_node(
    project_id: str, node_id: str, body: NodeUpdate, db: Session = Depends(get_db)
) -> Node:
    node = get_project_node(db, project_id, node_id)
    if "parent_id" in body.model_fields_set:
        if body.parent_id is not None:
            get_project_node(db, project_id, body.parent_id)
        validate_parent(db, node, body.parent_id)
        node.parent_id = body.parent_id
        revalidate_dependencies(db, node)
    for field in ("text", "description", "canvas_x", "canvas_y"):
        value = getattr(body, field)
        if value is not None:
            setattr(node, field, value)
    touch_project(db, project_id)
    db.commit()
    db.refresh(node)
    return node


@router.delete(
    "/projects/{project_id}/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_node(
    project_id: str, node_id: str, db: Session = Depends(get_db)
) -> Response:
    delete_subtree(db, get_project_node(db, project_id, node_id))
    touch_project(db, project_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/nodes/{node_id}/convert-to-action", response_model=NodeOut
)
def convert_to_action(
    project_id: str, node_id: str, db: Session = Depends(get_db)
) -> Node:
    node = get_project_node(db, project_id, node_id)
    validate_node_type(db, node, NodeType.ACTION)
    node.node_type = NodeType.ACTION
    revalidate_dependencies(db, node)
    # A previous action/goal round trip may have left settings behind.
    if db.get(ActionTaskSettings, node.id) is None:
        db.add(ActionTaskSettings(action_id=node.id))
    touch_project(db, project_id)
    db.commit()
    db.refresh(node)
    return node


@router.post(
    "/projects/{project_id}/nodes/{node_id}/convert-to-goal", response_model=NodeOut
)
def convert_to_goal(
    project_id: str, node_id: str, db: Session = Depends(get_db)
) -> Node:
    node = get_project_node(db, project_id, node_id)
    validate_node_type(db, node, NodeType.GOAL)
    node.node_type = NodeType.GOAL
    revalidate_dependencies(db, node)
    settings = db.get(ActionTaskSettings, node.id)
    if settings is not None:
        db.delete(settings)
    touch_project(db, project_id)
    db.commit()
    db.refresh(node)
    return node


@router.get("/projects/{project_id}/dependencies", response_model=list[DependencyOut])
def list_dependencies(
    project_id: str, db: Session = Depends(get_db)
) -> Sequence[Dependency]:
    get_project(db, project_id)
    return db.scalars(
        select(Dependency).where(Dependency.project_id == project_id)
    ).all()


@router.post(
    "/projects/{project_id}/dependencies",
    response_model=DependencyOut,
    status_code=status.HTTP_201_CREATED,
)
def create_dependency(
    project_id: str, body: DependencyCreate, db: Session = Depends(get_db)
) -> Dependency:
    get_project(db, project_id)
    validate_dependency(db, project_id, body.predecessor_id, body.successor_id)
    edge = Dependency(project_id=project_id, **body.model_dump())
    db.add(edge)
    touch_project(db, project_id)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise invalid("Dependency already exists") from error
    db.refresh(edge)
    return edge


@router.post(
    "/projects/{project_id}/dependencies/{dependency_id}/reverse",
    response_model=DependencyOut,
)
def reverse_dependency(
    project_id: str, dependency_id: str, db: Session = Depends(get_db)
) -> Dependency:
    """Swap direction in one transaction so no edge can be lost on failure."""
    edge = get_project_dependency(db, project_id, dependency_id)
    edge.predecessor_id, edge.successor_id = edge.successor_id, edge.predecessor_id
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise invalid("Dependency already exists") from error
    validate_dependency(db, project_id, edge.predecessor_id, edge.successor_id)
    touch_project(db, project_id)
    db.commit()
    db.refresh(edge)
    return edge


@router.delete(
    "/projects/{project_id}/dependencies/{dependency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dependency(
    project_id: str, dependency_id: str, db: Session = Depends(get_db)
) -> Response:
    db.delete(get_project_dependency(db, project_id, dependency_id))
    touch_project(db, project_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects/{project_id}/actions/{action_id}/tasks", response_model=list[TaskOut]
)
def list_tasks(
    project_id: str, action_id: str, db: Session = Depends(get_db)
) -> Sequence[Task]:
    get_project_action(db, project_id, action_id)
    return db.scalars(
        select(Task).where(Task.action_id == action_id).order_by(Task.position)
    ).all()


@router.post(
    "/projects/{project_id}/actions/{action_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    project_id: str, action_id: str, body: TaskCreate, db: Session = Depends(get_db)
) -> Task:
    get_project_action(db, project_id, action_id)
    for attempt in range(3):
        max_position = db.scalar(
            select(func.max(Task.position)).where(Task.action_id == action_id)
        )
        task = Task(
            action_id=action_id,
            text=body.text,
            position=0 if max_position is None else max_position + 1,
        )
        db.add(task)
        touch_project(db, project_id)
        try:
            db.commit()
        except IntegrityError as error:
            # Another writer claimed the position; recompute and retry.
            db.rollback()
            if attempt == 2:
                raise invalid("Could not add the task, please try again") from error
            continue
        db.refresh(task)
        return task
    raise invalid("Could not add the task, please try again")


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=TaskOut)
def update_task(
    project_id: str, task_id: str, body: TaskUpdate, db: Session = Depends(get_db)
) -> Task:
    task = get_project_task(db, project_id, task_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    touch_project(db, project_id)
    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/projects/{project_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_task(
    project_id: str, task_id: str, db: Session = Depends(get_db)
) -> Response:
    db.delete(get_project_task(db, project_id, task_id))
    touch_project(db, project_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects/{project_id}/actions/{action_id}/task-settings",
    response_model=TaskSettingsOut,
)
def get_task_settings(
    project_id: str, action_id: str, db: Session = Depends(get_db)
) -> ActionTaskSettings | TaskSettingsOut:
    get_project_action(db, project_id, action_id)
    settings = db.get(ActionTaskSettings, action_id)
    # Reads never write: report the default instead of creating a row.
    if settings is None:
        return TaskSettingsOut(
            action_id=action_id, display_style=DisplayStyle.BULLETED
        )
    return settings


@router.put(
    "/projects/{project_id}/actions/{action_id}/task-settings",
    response_model=TaskSettingsOut,
)
def update_task_settings(
    project_id: str,
    action_id: str,
    body: TaskSettingsUpdate,
    db: Session = Depends(get_db),
) -> ActionTaskSettings:
    get_project_action(db, project_id, action_id)
    settings = db.get(ActionTaskSettings, action_id) or ActionTaskSettings(
        action_id=action_id
    )
    settings.display_style = body.display_style
    db.add(settings)
    touch_project(db, project_id)
    db.commit()
    db.refresh(settings)
    return settings


@router.put(
    "/projects/{project_id}/actions/{action_id}/tasks/reorder",
    response_model=list[TaskOut],
)
def reorder_tasks(
    project_id: str, action_id: str, body: ReorderTasks, db: Session = Depends(get_db)
) -> list[Task]:
    get_project_action(db, project_id, action_id)
    tasks = db.scalars(select(Task).where(Task.action_id == action_id)).all()
    if set(body.task_ids) != {task.id for task in tasks} or len(body.task_ids) != len(
        set(body.task_ids)
    ):
        raise invalid("task_ids must contain every task exactly once")
    # Temporary positions avoid the per-action uniqueness constraint mid-reorder.
    task_by_id = {task.id: task for task in tasks}
    for index, task_id in enumerate(body.task_ids):
        task_by_id[task_id].position = -(index + 1)
    db.flush()
    for index, task_id in enumerate(body.task_ids):
        task_by_id[task_id].position = index
    touch_project(db, project_id)
    db.commit()
    return [task_by_id[task_id] for task_id in body.task_ids]
