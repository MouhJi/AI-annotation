from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update as sql_update
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
from ..services.annotation_permissions import role_map, can_correct, require_correction, snapshot, record_change, soft_delete
from ..services.quality_service import LOCKED, lock_image, require_editable, capture, content_changed as image_content_changed
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

def serialize(a:Annotation, db=None, user=None, roles=None):
    allowed = a.image.review_state not in LOCKED and can_correct(a, user.id, roles if roles is not None else role_map(db,a.image.project.workspace_id)) if user else False
    author = lambda user: {"id": user.id, "full_name": user.full_name} if user else None
    return AnnotationOut(id=a.id,image_id=a.image_id,class_id=a.class_id,class_name=a.label_class.name,annotation_type=a.annotation_type or "bbox",x=a.x,y=a.y,width=a.width,height=a.height,points=safe_points(a.points_json), created_by=author(a.creator), updated_by=author(a.editor), created_at=aware(a.created_at), updated_at=aware(a.updated_at), source=a.source, version=a.version, can_edit=allowed, can_delete=allowed)
@router.get("/images/{image_id}/annotations",response_model=list[AnnotationOut])
def list_annotations(image_id:int,db:Session=Depends(get_db),user=Depends(get_active_user)):
    if not db.get(Image,image_id): raise HTTPException(404,"Image not found")
    roles=role_map(db,db.get(Image,image_id).project.workspace_id)
    return [serialize(a,db,user,roles) for a in db.scalars(select(Annotation).options(joinedload(Annotation.creator), joinedload(Annotation.editor), joinedload(Annotation.label_class)).where(Annotation.image_id==image_id).order_by(Annotation.id))]
@router.post("/images/{image_id}/annotations",response_model=AnnotationOut,status_code=201)
def create(image_id:int,payload:AnnotationCreate,db:Session=Depends(get_db),user=Depends(get_active_user)):
    image=lock_image(db,image_id); require_editable(image); capture(db,image)
    if image.project.annotation_mode == "object_detection" and payload.annotation_type != "bbox": raise HTTPException(400,"Object detection projects accept bounding boxes only")
    if image.project.annotation_mode == "instance_segmentation" and payload.annotation_type != "polygon": raise HTTPException(400,"Instance segmentation projects accept polygons only")
    validate_payload(db,image,payload); a=Annotation(image_id=image_id,created_by=user.id,updated_by=user.id,**annotation_values(image,payload)); db.add(a); image_content_changed(db,image,user.id); db.commit(); db.refresh(a); return serialize(a,db,user)
@router.put("/annotations/{annotation_id}",response_model=AnnotationOut)
def update(annotation_id:int,payload:AnnotationUpdate,db:Session=Depends(get_db),user=Depends(get_active_user)):
    a=db.scalar(select(Annotation).where(Annotation.id==annotation_id).with_for_update().execution_options(populate_existing=True))
    if not a: raise HTTPException(404,"Annotation not found")
    image=lock_image(db,a.image_id); require_editable(image)
    if a.image.project.annotation_mode == "object_detection" and payload.annotation_type != "bbox": raise HTTPException(400,"Object detection projects accept bounding boxes only")
    if a.image.project.annotation_mode == "instance_segmentation" and payload.annotation_type != "polygon": raise HTTPException(400,"Instance segmentation projects accept polygons only")
    require_correction(a,user,role_map(db,a.image.project.workspace_id))
    validate_payload(db,a.image,payload)
    if payload.expected_version is not None and payload.expected_version != a.version:
        raise HTTPException(409, "This object was edited by another member. Reload the image before saving.")
    values = annotation_values(a.image,payload)
    if content_changed(a, values):
        if payload.expected_version is None: raise HTTPException(428, "Reload and supply expected_version before editing this object.")
        capture(db,image)
        before=snapshot(a)
        for key,value in values.items(): setattr(a,key,value)
        a.updated_by = user.id
        a.updated_at = utcnow()
        a.version += 1
        if a.source == "ai_accepted": a.source = "ai_edited"
        record_change(db,a,user,before)
        image_content_changed(db,image,user.id)
    db.commit(); db.refresh(a); return serialize(a,db,user)
@router.delete("/annotations/{annotation_id}",status_code=204)
def delete(annotation_id:int,expected_version:int,db:Session=Depends(get_db),user=Depends(get_active_user)):
    a=db.scalar(select(Annotation).where(Annotation.id==annotation_id).with_for_update().execution_options(populate_existing=True))
    if not a: raise HTTPException(404,"Annotation not found")
    image=lock_image(db,a.image_id); require_editable(image); capture(db,image)
    require_correction(a,user,role_map(db,a.image.project.workspace_id))
    if a.version != expected_version: raise HTTPException(409,"Annotation changed. Reload before deleting.")
    db.execute(sql_update(AutoLabelPrediction).where(AutoLabelPrediction.annotation_id==a.id).values(annotation_id=None,status="REJECTED"))
    soft_delete(db,a,user);image_content_changed(db,image,user.id);db.commit()

@router.put("/images/{image_id}/annotations", response_model=list[AnnotationOut])
def save_batch(image_id: int, payload: AnnotationBatch, db: Session=Depends(get_db), user=Depends(get_active_user)):
    apply_batch(image_id,payload,db,user)
    db.commit()
    return list_annotations(image_id, db, user)

def apply_batch(image_id, payload, db, user):
    """Stage a whole image without committing; submit uses this same transaction."""
    image = lock_image(db,image_id); require_editable(image)
    require_project_permission(db,image.project_id,user,"annotation.update")
    if payload.expected_revision is not None and image.revision != payload.expected_revision:
        raise HTTPException(409, "Image revision changed. Reload before saving.")
    existing = {a.id: a for a in db.scalars(select(Annotation).where(Annotation.image_id == image_id).with_for_update().execution_options(populate_existing=True))}
    if {key: a.version for key,a in existing.items()} != payload.expected_versions:
        raise HTTPException(409, "Annotations changed since you opened this image. Reload before saving.")
    ids = [a.id for a in payload.items if a.id is not None]
    if len(ids) != len(set(ids)) or any(key not in existing for key in ids):
        raise HTTPException(400, "Invalid or duplicate annotation IDs")
    removed = set(existing) - set(ids)
    if removed: require_project_permission(db, image.project_id, user, "annotation.delete")
    if any(a.id is None for a in payload.items): require_project_permission(db, image.project_id, user, "annotation.create")
    roles=role_map(db,image.project.workspace_id)
    for key in removed: require_correction(existing[key],user,roles)
    # Validate the entire request before changing any row; one commit for the image.
    values = []
    for item in payload.items:
        expected_type = "polygon" if image.project.annotation_mode == "instance_segmentation" else "bbox"
        if item.annotation_type != expected_type: raise HTTPException(400, "Geometry does not match project mode")
        validate_payload(db, image, item)
        content=annotation_values(image,item)
        if item.id is not None and content_changed(existing[item.id],content): require_correction(existing[item.id],user,roles)
        values.append(content)
    changed = bool(removed) or any(item.id is None or content_changed(existing[item.id],content) for item,content in zip(payload.items,values))
    if changed: capture(db,image)
    for item, content in zip(payload.items, values):
        if item.id is None:
            db.add(Annotation(image_id=image_id, created_by=user.id, updated_by=user.id, **content))
        else:
            a = existing[item.id]
            if content_changed(a, content):
                before=snapshot(a)
                for key,value in content.items(): setattr(a,key,value)
                a.updated_by = user.id; a.updated_at = utcnow(); a.version += 1
                if a.source == "ai_accepted": a.source = "ai_edited"
                record_change(db,a,user,before)
    if removed:
        db.execute(sql_update(AutoLabelPrediction).where(AutoLabelPrediction.annotation_id.in_(removed)).values(annotation_id=None, status="REJECTED"))
        for key in removed: soft_delete(db,existing[key],user)
    if changed: image_content_changed(db,image,user.id)
    return image
@router.delete("/images/{image_id}/annotations")
def delete_all(image_id:int,payload:dict,db:Session=Depends(get_db),user=Depends(get_active_user)):
    image=lock_image(db,image_id); require_editable(image)
    rows=list(db.scalars(select(Annotation).where(Annotation.image_id==image_id).with_for_update()))
    expected={str(a.id):a.version for a in rows}
    if payload.get("expected_versions")!=expected: raise HTTPException(409,"Annotations changed. Reload before deleting.")
    roles=role_map(db,image.project.workspace_id)
    for a in rows: require_correction(a,user,roles)
    if rows: capture(db,image)
    ids=[a.id for a in rows]
    if ids: db.execute(sql_update(AutoLabelPrediction).where(AutoLabelPrediction.annotation_id.in_(ids)).values(annotation_id=None,status="REJECTED"))
    for a in rows: soft_delete(db,a,user)
    if rows: image_content_changed(db,image,user.id)
    db.commit()
    return {"deleted_count":len(rows)}

