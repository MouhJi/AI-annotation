from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
class ImageOut(BaseModel):
    id: int; filename: str; width: int; height: int; annotation_count: int = 0; image_url: str | None = None; split: str | None = None
    review_state: str = "not_started"
    revision: int = 0
    review_version: int = 0
    model_config = ConfigDict(from_attributes=True)
class ImageDetail(ImageOut):
    project_id: int; filepath: str; image_url: str; created_at: datetime

class BulkImageDelete(BaseModel):
    project_id: int
    image_ids: list[int] = Field(min_length=1, max_length=200)
