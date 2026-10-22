from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sql_delete, select, update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from ..auth_dependencies import get_active_user
from ..models.auth import utcnow
from ..services.auth_security import aware
from ..auth_dependencies import require_project_permission
from ..schemas.annotation import AnnotationBatch
from ..database import get_db
from ..models import Annotation, AutoLabelPrediction, Image
from ..schemas.annotation import AnnotationCreate, AnnotationOut, AnnotationUpdate
import json
from ..services.annotation_service import annotation_values, validate_payload
router=APIRouter(prefix="/api",tags=["annotations"])
def safe_points(value: str | None):
    if not value:
        return None
    try:
        points = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return points if isinstance(points, list) else None

def content_changed(annotation, values):
    return any((safe_points(annotation.points_json) != safe_points(value)) if key == "points_json"
               else getattr(annotation, key) != value for key, value in values.items())

def serialize(a:Annotation):
    author = lambda user: {"id": user.id, "full_name": user.full_name} if user else None
    return AnnotationOut(id=a.id,image_id=a.image_id,class_id=a.class_id,class_name=a.label_class.name,annotation_type=a.annotation_type or "bbox",x=a.x,y=a.y,width=a.width,height=a.height,points=safe_points(a.points_json), created_by=author(a.creator), updated_by=author(a.editor), created_at=aware(a.created_at), updated_at=aware(a.updated_at), source=a.source, version=a.version)
@router.get("/images/{image_id}/annotations",response_model=list[AnnotationOut])
def list_annotations(image_id:int,db:Session=Depends(get_db)):
    if not db.get(Image,image_id): raise HTTPException(404,"Image not found")
    return [serialize(a) for a in db.scalars(select(Annotation).options(joinedload(Annotation.creator), joinedload(Annotation.editor), joinedload(Annotation.label_class)).where(Annotation.image_id==image_id).order_by(Annotation.id))]
@router.post("/images/{image_id}/annotations",response_model=AnnotationOut,status_code=201)
def create(image_id:int,payload:AnnotationCreate,db:Session=Depends(get_db),user=Depends(get_active_user)):
    image=db.get(Image,image_id)
    if not image: raise HTTPException(404,"Image not found")
    if image.project.annotation_mode == "object_detection" and payload.annotation_type != "bbox": raise HTTPException(400,"Object detection projects accept bounding boxes only")
    if image.project.annotation_mode == "instance_segmentation" and payload.annotation_type != "polygon": raise HTTPException(400,"Instance segmentation projects accept polygons only")
    validate_payload(db,image,payload); a=Annotation(image_id=image_id,created_by=user.id,updated_by=user.id,**annotation_values(image,payload)); db.add(a); db.commit(); db.refresh(a); return serialize(a)
@router.put("/annotations/{annotation_id}",response_model=AnnotationOut)
def update(annotation_id:int,payload:AnnotationUpdate,db:Session=Depends(get_db),user=Depends(get_active_user)):
    a=db.scalar(select(Annotation).where(Annotation.id==annotation_id).with_for_update().execution_options(populate_existing=True))
    if not a: raise HTTPException(404,"Annotation not found")
    if a.image.project.annotation_mode == "object_detection" and payload.annotation_type != "bbox": raise HTTPException(400,"Object detection projects accept bounding boxes only")
    if a.image.project.annotation_mode == "instance_segmentation" and payload.annotation_type != "polygon": raise HTTPException(400,"Instance segmentation projects accept polygons only")
    validate_payload(db,a.image,payload)
    if payload.expected_version is not None and payload.expected_version != a.version:
        raise HTTPException(409, "This object was edited by another member. Reload the image before saving.")
    values = annotation_values(a.image,payload)
    if content_changed(a, values):
        for key,value in values.items(): setattr(a,key,value)
        a.updated_by = user.id
        a.updated_at = utcnow()
        a.version += 1
    db.commit(); db.refresh(a); return serialize(a)
@router.delete("/annotations/{annotation_id}",status_code=204)
def delete(annotation_id:int,db:Session=Depends(get_db)):
    a=db.get(Annotation,annotation_id)
    if not a: raise HTTPException(404,"Annotation not found")
    db.delete(a); db.commit()

@router.put("/images/{image_id}/annotations", response_model=list[AnnotationOut])
def save_batch(image_id: int, payload: AnnotationBatch, db: Session=Depends(get_db), user=Depends(get_active_user)):
    image = db.get(Image, image_id, with_for_update=True)
    if not image: raise HTTPException(404, "Image not found")
    existing = {a.id: a for a in db.scalars(select(Annotation).where(Annotation.image_id == image_id).with_for_update().execution_options(populate_existing=True))}
    if {key: a.version for key,a in existing.items()} != payload.expected_versions:
        raise HTTPException(409, "Annotations changed since you opened this image. Reload before saving.")
    ids = [a.id for a in payload.items if a.id is not None]
    if len(ids) != len(set(ids)) or any(key not in existing for key in ids):
        raise HTTPException(400, "Invalid or duplicate annotation IDs")
    removed = set(existing) - set(ids)
    if removed: require_project_permission(db, image.project_id, user, "annotation.delete")
    if any(a.id is None for a in payload.items): require_project_permission(db, image.project_id, user, "annotation.create")
    # Validate the entire request before changing any row; one commit for the image.
    values = []
    for item in payload.items:
        expected_type = "polygon" if image.project.annotation_mode == "instance_segmentation" else "bbox"
        if item.annotation_type != expected_type: raise HTTPException(400, "Geometry does not match project mode")
        validate_payload(db, image, item)
        values.append(annotation_values(image, item))
    for item, content in zip(payload.items, values):
        if item.id is None:
            db.add(Annotation(image_id=image_id, created_by=user.id, updated_by=user.id, **content))
        else:
            a = existing[item.id]
            if content_changed(a, content):
                for key,value in content.items(): setattr(a,key,value)
                a.updated_by = user.id; a.updated_at = utcnow(); a.version += 1
    if removed:
        db.execute(sql_update(AutoLabelPrediction).where(AutoLabelPrediction.annotation_id.in_(removed)).values(annotation_id=None, status="REJECTED"))
        for key in removed: db.delete(existing[key])
    db.commit()
    return list_annotations(image_id, db)
@router.delete("/images/{image_id}/annotations")
def delete_all(image_id:int,db:Session=Depends(get_db)):
    if not db.get(Image,image_id): raise HTTPException(404,"Image not found")
    annotation_ids = list(db.scalars(select(Annotation.id).where(Annotation.image_id == image_id)))
    if not annotation_ids:
        return {"deleted_count": 0}
    # Clear foreign keys before deleting annotations. This covers accepted AI predictions
    # without depending on ORM flush ordering or database-specific cascade settings.
    db.execute(sql_update(AutoLabelPrediction).where(AutoLabelPrediction.annotation_id.in_(annotation_ids)).values(annotation_id=None, status="REJECTED"))
    result = db.execute(sql_delete(Annotation).where(Annotation.id.in_(annotation_ids)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Unable to delete labels because they are referenced by another record")
    return {"deleted_count": result.rowcount or 0}
