from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    annotation_mode: Literal["object_detection", "instance_segmentation"] = "object_detection"
    workspace_id: UUID | None = None
class ProjectOut(ProjectCreate):
    require_review: bool = False
    id: int
    created_at: datetime
    updated_at: datetime
    image_count: int = 0
    class_count: int = 0
    permissions: list[str] = []
    model_config = ConfigDict(from_attributes=True)
