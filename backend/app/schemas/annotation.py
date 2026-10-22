from typing import Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

Point = tuple[float, float]

class AnnotationBase(BaseModel):
    """Extensible geometry payload; legacy bbox fields stay supported."""
    class_id: int
    annotation_type: Literal["bbox", "polygon"] = "bbox"
    x: float | None = Field(default=None, ge=0); y: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, gt=0); height: float | None = Field(default=None, gt=0)
    points: list[Point] | None = None

    @model_validator(mode="after")
    def require_geometry(self):
        if self.annotation_type == "bbox":
            if None in (self.x, self.y, self.width, self.height): raise ValueError("Bounding box requires x, y, width and height")
            if self.points is not None: raise ValueError("Bounding box must not include polygon points")
        elif self.points is None: raise ValueError("Polygon requires points")
        return self

class AnnotationCreate(AnnotationBase): pass
class AnnotationUpdate(AnnotationBase):
    expected_version: int | None = Field(default=None, ge=1)

class AnnotatorOut(BaseModel):
    id: UUID
    full_name: str

class BatchAnnotation(AnnotationBase):
    id: int | None = None

class AnnotationBatch(BaseModel):
    items: list[BatchAnnotation]
    expected_versions: dict[int, int]

class AnnotationOut(AnnotationBase):
    id: int; image_id: int; class_name: str
    created_by: AnnotatorOut | None = None
    updated_by: AnnotatorOut | None = None
    created_at: datetime
    updated_at: datetime
    source: str
    version: int
    model_config = ConfigDict(from_attributes=True)
