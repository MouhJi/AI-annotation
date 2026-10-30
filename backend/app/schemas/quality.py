from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from .annotation import AnnotationBatch

ReviewState = Literal["not_started", "in_progress", "pending_review", "changes_requested", "approved"]
ErrorCategory = Literal["wrong_class", "missing_object", "extra_object", "inaccurate_bbox", "inaccurate_polygon", "other"]


class ReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    expected_review_version: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=4000)
    error_category: ErrorCategory | None = None


class SubmitReview(ReviewCommand):
    annotations: AnnotationBatch
    negative_confirmed: bool = False


class ReviewSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_review: bool


class ThreadCreate(BaseModel):
    object_id: int | None = None
    body: str = Field(min_length=1, max_length=4000)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ThreadDecision(BaseModel):
    resolved: bool
    expected_version: int = Field(ge=1)


class ActivityHeartbeat(BaseModel):
    client_id: UUID
    sequence: int = Field(ge=1)
    elapsed_seconds: float = Field(ge=0, le=15, allow_inf_nan=False)
