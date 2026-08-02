from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import DisplayStyle, NodeType

Text = Annotated[str, Field(min_length=1, max_length=500)]


class ProjectCreate(BaseModel):
    name: Text


class ProjectUpdate(BaseModel):
    name: Text


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class NodeCreate(BaseModel):
    text: Text
    node_type: NodeType = NodeType.GOAL
    description: str = ""
    parent_id: str | None = None
    canvas_x: float = 0
    canvas_y: float = 0


class NodeUpdate(BaseModel):
    text: Text | None = None
    description: str | None = Field(default=None, max_length=5000)
    parent_id: str | None = None
    canvas_x: float | None = None
    canvas_y: float | None = None


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    parent_id: str | None
    node_type: NodeType
    text: str
    description: str
    canvas_x: float
    canvas_y: float
    created_at: datetime
    updated_at: datetime


class DependencyCreate(BaseModel):
    predecessor_id: str
    successor_id: str


class DependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    predecessor_id: str
    successor_id: str
    created_at: datetime


class TaskCreate(BaseModel):
    text: Text


class TaskUpdate(BaseModel):
    text: Text | None = None
    is_completed: bool | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action_id: str
    text: str
    is_completed: bool
    position: int


class TaskSettingsUpdate(BaseModel):
    display_style: DisplayStyle


class TaskSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    action_id: str
    display_style: DisplayStyle


class ReorderTasks(BaseModel):
    task_ids: list[str]


class ProjectExportNode(NodeCreate):
    id: str


class ProjectExportDependency(DependencyCreate):
    pass


class ProjectExportTask(TaskOut):
    pass


class ProjectExportSettings(TaskSettingsOut):
    pass


class ProjectExport(BaseModel):
    format_version: Literal[1] = 1
    name: Text
    nodes: list[ProjectExportNode]
    dependencies: list[ProjectExportDependency]
    tasks: list[ProjectExportTask]
    task_settings: list[ProjectExportSettings]
