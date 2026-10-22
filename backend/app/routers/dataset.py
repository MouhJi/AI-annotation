import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Image
from ..schemas.dataset import SplitConfig, SplitSummary
from ..services.dataset_service import assign_splits, export_yolo_zip, split_summary
from ..services.image_service import require_project

router = APIRouter(prefix="/api/projects/{project_id}/dataset", tags=["dataset"])

@router.get("/split", response_model=SplitSummary)
def get_split(project_id: int, db: Session = Depends(get_db)):
    require_project(db, project_id)
    return split_summary(list(db.scalars(select(Image).where(Image.project_id == project_id))))

@router.put("/split", response_model=SplitSummary)
def configure_split(project_id: int, config: SplitConfig, db: Session = Depends(get_db)):
    return assign_splits(db, project_id, config)

@router.post("/export/yolo")
def export_yolo(project_id: int, db: Session = Depends(get_db)):
    content, filename = export_yolo_zip(db, project_id)
    return StreamingResponse(io.BytesIO(content), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
