from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import (
    ActionTaskSettings,
    Dependency,
    Node,
    NodeType,
    Project,
    Task,
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
    get_node,
    invalid,
    not_found,
    validate_action,
    validate_dependency,
    validate_node_type,
    validate_parent,
)

router = APIRouter(prefix="/api")


def project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project")
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.updated_at.desc())).all()


@router.post(
    "/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED
)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post(
    "/projects/import", response_model=ProjectOut, status_code=status.HTTP_201_CREATED
)
def import_project(body: ProjectExport, db: Session = Depends(get_db)):
    project = Project(name=body.name)
    db.add(project)
    db.flush()
    node_ids: dict[str, str] = {}
    for source in body.nodes:
        node = Node(
            project_id=project.id,
            text=source.text,
            description=source.description,
            node_type=source.node_type,
            canvas_x=source.canvas_x,
            canvas_y=source.canvas_y,
        )
        db.add(node)
        db.flush()
        node_ids[source.id] = node.id
    try:
        for source_node in body.nodes:
            if source_node.parent_id:
                imported_node = db.get(Node, node_ids[source_node.id])
                assert imported_node is not None
                imported_node.parent_id = node_ids[source_node.parent_id]
        for source_dependency in body.dependencies:
            db.add(
                Dependency(
                    project_id=project.id,
                    predecessor_id=node_ids[source_dependency.predecessor_id],
                    successor_id=node_ids[source_dependency.successor_id],
                )
            )
        for source_task in body.tasks:
            db.add(
                Task(
                    action_id=node_ids[source_task.action_id],
                    text=source_task.text,
                    is_completed=source_task.is_completed,
                    position=source_task.position,
                )
            )
        for source_settings in body.task_settings:
            db.add(
                ActionTaskSettings(
                    action_id=node_ids[source_settings.action_id],
                    display_style=source_settings.display_style,
                )
            )
    except KeyError as error:
        raise invalid(f"Import references an unknown node: {error.args[0]}")
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    return project_or_404(db, project_id)


@router.get("/projects/{project_id}/export", response_model=ProjectExport)
def export_project(project_id: str, db: Session = Depends(get_db)):
    project_or_404(db, project_id)
    nodes = db.scalars(select(Node).where(Node.project_id == project_id)).all()
    node_ids = [node.id for node in nodes]
    return ProjectExport(
        name=project_or_404(db, project_id).name,
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
            ProjectExportTask(
                id=task.id,
                action_id=task.action_id,
                text=task.text,
                is_completed=task.is_completed,
                position=task.position,
            )
            for task in db.scalars(select(Task).where(Task.action_id.in_(node_ids)))
        ],
        task_settings=[
            ProjectExportSettings(
                action_id=settings.action_id, display_style=settings.display_style
            )
            for settings in db.scalars(
                select(ActionTaskSettings).where(
                    ActionTaskSettings.action_id.in_(node_ids)
                )
            )
        ],
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, db: Session = Depends(get_db)):
    project = project_or_404(db, project_id)
    project.name = body.name
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    db.delete(project_or_404(db, project_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/nodes", response_model=list[NodeOut])
def list_nodes(project_id: str, db: Session = Depends(get_db)):
    project_or_404(db, project_id)
    return db.scalars(select(Node).where(Node.project_id == project_id)).all()


@router.post(
    "/projects/{project_id}/nodes",
    response_model=NodeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_node(project_id: str, body: NodeCreate, db: Session = Depends(get_db)):
    project_or_404(db, project_id)
    node = Node(
        project_id=project_id,
        text=body.text,
        description=body.description,
        node_type=body.node_type,
        canvas_x=body.canvas_x,
        canvas_y=body.canvas_y,
    )
    db.add(node)
    db.flush()
    validate_parent(db, node, body.parent_id)
    node.parent_id = body.parent_id
    if node.node_type == NodeType.ACTION:
        db.add(ActionTaskSettings(action_id=node.id))
    db.commit()
    db.refresh(node)
    return node


@router.get("/nodes/{node_id}", response_model=NodeOut)
def read_node(node_id: str, db: Session = Depends(get_db)):
    return get_node(db, node_id)


@router.patch("/nodes/{node_id}", response_model=NodeOut)
def update_node(node_id: str, body: NodeUpdate, db: Session = Depends(get_db)):
    node = get_node(db, node_id)
    if "parent_id" in body.model_fields_set:
        validate_parent(db, node, body.parent_id)
        node.parent_id = body.parent_id
    for field in ("text", "description", "canvas_x", "canvas_y"):
        value = getattr(body, field)
        if value is not None:
            setattr(node, field, value)
    db.commit()
    db.refresh(node)
    return node


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_node(node_id: str, db: Session = Depends(get_db)):
    delete_subtree(db, get_node(db, node_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/nodes/{node_id}/convert-to-action", response_model=NodeOut)
def convert_to_action(node_id: str, db: Session = Depends(get_db)):
    node = get_node(db, node_id)
    validate_node_type(db, node, NodeType.ACTION)
    node.node_type = NodeType.ACTION
    db.add(ActionTaskSettings(action_id=node.id))
    db.commit()
    db.refresh(node)
    return node


@router.post("/nodes/{node_id}/convert-to-goal", response_model=NodeOut)
def convert_to_goal(node_id: str, db: Session = Depends(get_db)):
    node = get_node(db, node_id)
    validate_node_type(db, node, NodeType.GOAL)
    node.node_type = NodeType.GOAL
    settings = db.get(ActionTaskSettings, node.id)
    if settings is not None:
        db.delete(settings)
    db.commit()
    db.refresh(node)
    return node


@router.get("/projects/{project_id}/dependencies", response_model=list[DependencyOut])
def list_dependencies(project_id: str, db: Session = Depends(get_db)):
    project_or_404(db, project_id)
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
):
    project_or_404(db, project_id)
    validate_dependency(db, project_id, body.predecessor_id, body.successor_id)
    edge = Dependency(project_id=project_id, **body.model_dump())
    db.add(edge)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise invalid("Dependency already exists")
    db.refresh(edge)
    return edge


@router.delete("/dependencies/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dependency(dependency_id: str, db: Session = Depends(get_db)):
    edge = db.get(Dependency, dependency_id)
    if edge is None:
        raise not_found("Dependency")
    db.delete(edge)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/actions/{action_id}/tasks", response_model=list[TaskOut])
def list_tasks(action_id: str, db: Session = Depends(get_db)):
    validate_action(db, action_id)
    return db.scalars(
        select(Task).where(Task.action_id == action_id).order_by(Task.position)
    ).all()


@router.post(
    "/actions/{action_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
)
def create_task(action_id: str, body: TaskCreate, db: Session = Depends(get_db)):
    validate_action(db, action_id)
    max_position = db.scalar(
        select(func.max(Task.position)).where(Task.action_id == action_id)
    )
    position = 0 if max_position is None else max_position + 1
    task = Task(action_id=action_id, text=body.text, position=position)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: str, body: TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task")
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/actions/{action_id}/task-settings", response_model=TaskSettingsOut)
def get_task_settings(action_id: str, db: Session = Depends(get_db)):
    validate_action(db, action_id)
    settings = db.get(ActionTaskSettings, action_id)
    if settings is None:
        settings = ActionTaskSettings(action_id=action_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.put("/actions/{action_id}/task-settings", response_model=TaskSettingsOut)
def task_settings(
    action_id: str, body: TaskSettingsUpdate, db: Session = Depends(get_db)
):
    validate_action(db, action_id)
    settings = db.get(ActionTaskSettings, action_id) or ActionTaskSettings(
        action_id=action_id
    )
    settings.display_style = body.display_style
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


@router.put("/actions/{action_id}/tasks/reorder", response_model=list[TaskOut])
def reorder_tasks(action_id: str, body: ReorderTasks, db: Session = Depends(get_db)):
    validate_action(db, action_id)
    tasks = db.scalars(select(Task).where(Task.action_id == action_id)).all()
    if set(body.task_ids) != {task.id for task in tasks} or len(body.task_ids) != len(
        set(body.task_ids)
    ):
        raise invalid("task_ids must contain every task exactly once")
    # Use temporary positions to avoid the per-action uniqueness constraint during reorder.
    task_by_id = {task.id: task for task in tasks}
    for index, task_id in enumerate(body.task_ids):
        task_by_id[task_id].position = -(index + 1)
    db.flush()
    for index, task_id in enumerate(body.task_ids):
        task_by_id[task_id].position = index
    db.commit()
    return [task_by_id[task_id] for task_id in body.task_ids]
