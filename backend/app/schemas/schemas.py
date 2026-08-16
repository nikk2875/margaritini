from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.models.models import DisplayStyle, NodeType

Text = Annotated[str, Field(min_length=1, max_length=500)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Description = Annotated[str, Field(max_length=5000)]

STRICT = ConfigDict(extra="forbid")
STRICT_FROM_ATTRIBUTES = ConfigDict(from_attributes=True, extra="forbid")


class ProjectCreate(BaseModel):
    name: Name


class ProjectUpdate(BaseModel):
    name: Name


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class NodeCreate(BaseModel):
    text: Text
    node_type: NodeType = NodeType.GOAL
    description: Description = ""
    parent_id: str | None = None
    canvas_x: float = 0
    canvas_y: float = 0


class NodeUpdate(BaseModel):
    text: Text | None = None
    description: Description | None = None
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
    task_ids: Annotated[list[str], Field(max_length=settings.max_import_tasks)]


class ProjectExportNode(NodeCreate):
    model_config = STRICT
    id: str


class ProjectExportDependency(DependencyCreate):
    model_config = STRICT


class ProjectExportTask(TaskOut):
    model_config = STRICT_FROM_ATTRIBUTES
    text: Text
    position: Annotated[int, Field(ge=0)]


class ProjectExportSettings(TaskSettingsOut):
    model_config = STRICT_FROM_ATTRIBUTES


class ProjectExport(BaseModel):
    """Import payloads are untrusted, so every list is explicitly bounded."""

    model_config = STRICT
    format_version: Literal[1] = 1
    name: Name
    nodes: Annotated[
        list[ProjectExportNode], Field(max_length=settings.max_import_nodes)
    ]
    dependencies: Annotated[
        list[ProjectExportDependency], Field(max_length=settings.max_import_nodes * 4)
    ]
    tasks: Annotated[
        list[ProjectExportTask], Field(max_length=settings.max_import_tasks)
    ]
    task_settings: Annotated[
        list[ProjectExportSettings], Field(max_length=settings.max_import_nodes)
    ]
