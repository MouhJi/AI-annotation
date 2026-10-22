from pydantic import BaseModel, ConfigDict, Field, model_validator
from .annotation import Point

class AutoLabelRequest(BaseModel):
    confidence_threshold: float = Field(default=0.25, ge=0, le=1)
    model_key: str = "default"

class PredictionUpdate(BaseModel):
    mapped_class_id: int | None = None
    prediction_type: str = "bbox"
    x: float | None = Field(default=None, ge=0); y: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, gt=0); height: float | None = Field(default=None, gt=0)
    points: list[Point] | None = None
    @model_validator(mode="after")
    def require_geometry(self):
        if self.prediction_type not in {"bbox", "polygon"}: raise ValueError("Unsupported prediction type")
        if self.prediction_type == "bbox" and None in (self.x,self.y,self.width,self.height): raise ValueError("Bounding box requires x, y, width and height")
        if self.prediction_type == "polygon" and self.points is None: raise ValueError("Polygon requires points")
        return self

class PredictionOut(BaseModel):
    id: int; image_id: int; model_class_id: int; model_class_name: str
    mapped_class_id: int | None; mapped_class_name: str | None = None
    prediction_type: str = "bbox"
    x: float; y: float; width: float; height: float
    points: list[Point] | None = None
    confidence: float; status: str
    model_config = ConfigDict(from_attributes=True)

class AutoLabelResponse(BaseModel):
    image_id: int
    status: str
    model: str
    predictions: list[PredictionOut]
    warnings: list[str] = []

class MappingInput(BaseModel):
    model_class_id: int = Field(ge=0)
    model_class_name: str = Field(min_length=1, max_length=120)
    class_id: int

class MappingOut(MappingInput):
    id: int
    class_name: str
    model_config = ConfigDict(from_attributes=True)

class BatchAutoLabelRequest(AutoLabelRequest):
    image_ids: list[int] = Field(min_length=1, max_length=20)

class BatchAutoLabelResult(BaseModel):
    image_id: int
    status: str
    detail: str | None = None
