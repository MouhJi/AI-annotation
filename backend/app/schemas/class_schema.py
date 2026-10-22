from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
class ClassCreate(BaseModel): name: str = Field(min_length=1, max_length=80)
class ClassUpdate(ClassCreate): pass
class ClassOut(ClassCreate):
    id: int
    project_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
