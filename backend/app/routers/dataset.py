import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Image
from ..schemas.dataset import SplitConfig, SplitSummary
from ..services.dataset_service import assign_splits, export_yolo_zip, split_summary
from ..services.image_service import require_project
from ..services.export_scope import export_selection
from ..auth_dependencies import get_active_user, require_project_permission

router = APIRouter(prefix="/api/projects/{project_id}/dataset", tags=["dataset"])

@router.get("/split", response_model=SplitSummary)
def get_split(project_id: int, db: Session = Depends(get_db)):
    require_project(db, project_id)
    return split_summary(list(db.scalars(select(Image).where(Image.project_id == project_id))))

@router.put("/split", response_model=SplitSummary)
def configure_split(project_id: int, config: SplitConfig, db: Session = Depends(get_db)):
    return assign_splits(db, project_id, config)

@router.post("/export/yolo")
def export_yolo(project_id: int, split: str | None = None, image_ids: list[int] | None = Query(None), db: Session = Depends(get_db), user=Depends(get_active_user)):
    if require_project(db, project_id).require_review: require_project_permission(db,project_id,user,"export.approved")
    content, filename = export_yolo_zip(db, project_id, split, image_ids)
    return StreamingResponse(io.BytesIO(content), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.get("/export-preview")
def preview_export(project_id: int, split: str | None = None, image_ids: list[int] | None = Query(None), db: Session = Depends(get_db)):
    return export_selection(db, require_project(db, project_id), split, image_ids)[2]
