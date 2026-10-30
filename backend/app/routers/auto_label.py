from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth_dependencies import get_active_user
from ..models import AutoLabelPrediction, Image, LabelClass, ProjectClassMapping
from ..schemas.prediction import AutoLabelRequest, AutoLabelResponse, BatchAutoLabelRequest, BatchAutoLabelResult, MappingInput, MappingOut, PredictionOut, PredictionUpdate
from ..services.annotation_service import validate_payload
from ..services.auto_label_service import accept_prediction, prediction_out, reject_prediction, run_auto_label, run_auto_segment, update_prediction
from ..services.image_service import require_project
from ..services.quality_service import lock_image, require_editable

router = APIRouter(prefix="/api", tags=["auto-labeling"])

def mapping_out(item: ProjectClassMapping) -> MappingOut:
    return MappingOut(id=item.id, model_class_id=item.model_class_id, model_class_name=item.model_class_name, class_id=item.class_id, class_name=item.label_class.name)

@router.get("/projects/{project_id}/class-mappings", response_model=list[MappingOut])
def get_mappings(project_id: int, db: Session = Depends(get_db)):
    require_project(db, project_id)
    return [mapping_out(item) for item in db.scalars(select(ProjectClassMapping).where(ProjectClassMapping.project_id == project_id).order_by(ProjectClassMapping.model_class_id))]

@router.put("/projects/{project_id}/class-mappings", response_model=MappingOut)
def upsert_mapping(project_id: int, payload: MappingInput, db: Session = Depends(get_db)):
    require_project(db, project_id)
    label = db.get(LabelClass, payload.class_id)
    if not label: raise HTTPException(404, "Class not found")
    if label.project_id != project_id: raise HTTPException(400, "Class belongs to a different project")
    item = db.scalar(select(ProjectClassMapping).where(ProjectClassMapping.project_id == project_id, ProjectClassMapping.model_class_id == payload.model_class_id))
    if item is None:
        item = ProjectClassMapping(project_id=project_id, **payload.model_dump()); db.add(item)
    else:
        item.model_class_name = payload.model_class_name; item.class_id = payload.class_id
    db.commit(); db.refresh(item); return mapping_out(item)

@router.post("/images/{image_id}/auto-label", response_model=AutoLabelResponse)
def auto_label(image_id: int, payload: AutoLabelRequest, db: Session = Depends(get_db)):
    image = db.get(Image, image_id)
    if not image: raise HTTPException(404, "Image not found")
    if image.project.annotation_mode != "object_detection": raise HTTPException(400, "Use Auto Segment for an instance segmentation project")
    model, predictions, warnings = run_auto_label(db, image, payload)
    return AutoLabelResponse(image_id=image.id, status="COMPLETED", model=model, predictions=[prediction_out(item) for item in predictions], warnings=warnings)

@router.post("/projects/{project_id}/auto-label-batch", response_model=list[BatchAutoLabelResult])
def auto_label_batch(project_id: int, payload: BatchAutoLabelRequest, db: Session = Depends(get_db)):
    project = require_project(db, project_id); results = []
    if project.annotation_mode != "object_detection": raise HTTPException(400, "Use Auto Segment from an instance segmentation image")
    for image_id in payload.image_ids:
        image = db.get(Image, image_id)
        if not image or image.project_id != project_id:
            results.append(BatchAutoLabelResult(image_id=image_id, status="FAILED", detail="Image not found in project")); continue
        try:
            run_auto_label(db, image, payload); results.append(BatchAutoLabelResult(image_id=image_id, status="COMPLETED"))
        except HTTPException as error:
            db.rollback(); results.append(BatchAutoLabelResult(image_id=image_id, status="FAILED", detail=str(error.detail)))
    return results

@router.post("/projects/{project_id}/auto-segment-batch", response_model=list[BatchAutoLabelResult])
def auto_segment_batch(project_id: int, payload: BatchAutoLabelRequest, db: Session = Depends(get_db)):
    project = require_project(db, project_id); results = []
    if project.annotation_mode != "instance_segmentation": raise HTTPException(400, "Auto Segment is available only for instance segmentation projects")
    for image_id in payload.image_ids:
        image = db.get(Image, image_id)
        if not image or image.project_id != project_id:
            results.append(BatchAutoLabelResult(image_id=image_id, status="FAILED", detail="Image not found in project")); continue
        try:
            run_auto_segment(db, image, payload); results.append(BatchAutoLabelResult(image_id=image_id, status="COMPLETED"))
        except HTTPException as error:
            db.rollback(); results.append(BatchAutoLabelResult(image_id=image_id, status="FAILED", detail=str(error.detail)))
    return results

@router.post("/images/{image_id}/auto-segment", response_model=AutoLabelResponse)
def auto_segment(image_id: int, payload: AutoLabelRequest, db: Session = Depends(get_db)):
    image = db.get(Image, image_id)
    if not image: raise HTTPException(404, "Image not found")
    if image.project.annotation_mode != "instance_segmentation": raise HTTPException(400, "Auto Segment is available only for instance segmentation projects")
    model, predictions, warnings = run_auto_segment(db, image, payload)
    return AutoLabelResponse(image_id=image.id, status="COMPLETED", model=model, predictions=[prediction_out(item) for item in predictions], warnings=warnings)

@router.get("/images/{image_id}/predictions", response_model=list[PredictionOut])
def get_predictions(image_id: int, db: Session = Depends(get_db)):
    if not db.get(Image, image_id): raise HTTPException(404, "Image not found")
    return [prediction_out(item) for item in db.scalars(select(AutoLabelPrediction).where(AutoLabelPrediction.image_id == image_id).order_by(AutoLabelPrediction.id))]

@router.put("/predictions/{prediction_id}", response_model=PredictionOut)
def edit_prediction(prediction_id: int, payload: PredictionUpdate, db: Session = Depends(get_db), user=Depends(get_active_user)):
    item = db.get(AutoLabelPrediction, prediction_id)
    if not item: raise HTTPException(404, "Prediction not found")
    return prediction_out(update_prediction(db, item, payload, user.id))

@router.post("/predictions/{prediction_id}/accept")
def accept(prediction_id: int, db: Session = Depends(get_db), user=Depends(get_active_user)):
    item = db.get(AutoLabelPrediction, prediction_id)
    if not item: raise HTTPException(404, "Prediction not found")
    annotation = accept_prediction(db, item, user.id)
    return {"prediction_id": item.id, "annotation_id": annotation.id, "status": "ACCEPTED"}

@router.post("/predictions/{prediction_id}/reject", response_model=PredictionOut)
def reject(prediction_id: int, db: Session = Depends(get_db)):
    item = db.get(AutoLabelPrediction, prediction_id)
    if not item: raise HTTPException(404, "Prediction not found")
    return prediction_out(reject_prediction(db, item))

@router.post("/images/{image_id}/predictions/accept-all")
def accept_all(image_id: int, db: Session = Depends(get_db), user=Depends(get_active_user)):
    require_editable(lock_image(db,image_id))
    if not db.get(Image, image_id): raise HTTPException(404, "Image not found")
    accepted = failed = 0
    items = list(db.scalars(select(AutoLabelPrediction).where(AutoLabelPrediction.image_id == image_id, AutoLabelPrediction.status == "PENDING")))
    for item in items:
        try: accept_prediction(db, item, user.id); accepted += 1
        except HTTPException:
            db.rollback(); failed += 1
    return {"accepted": accepted, "skipped": 0, "failed": failed}

@router.post("/images/{image_id}/predictions/reject-all")
def reject_all(image_id: int, db: Session = Depends(get_db)):
    if not db.get(Image, image_id): raise HTTPException(404, "Image not found")
    items = list(db.scalars(select(AutoLabelPrediction).where(AutoLabelPrediction.image_id == image_id, AutoLabelPrediction.status == "PENDING")))
    for item in items: item.status = "REJECTED"
    db.commit(); return {"rejected": len(items)}
