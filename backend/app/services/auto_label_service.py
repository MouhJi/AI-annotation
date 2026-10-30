import json
import os
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from ..models import Annotation, AutoLabelPrediction, Image, LabelClass, Project, ProjectClassMapping, AuditLog
from ..schemas.annotation import AnnotationCreate
from ..schemas.prediction import AutoLabelRequest, PredictionUpdate
from .annotation_service import annotation_values, validate_payload
from .image_service import STORAGE_PATH
from .yolo_service import yolo_service
from .quality_service import lock_image, require_editable, capture, content_changed
from .workspace_service import audit
from .auth_security import aware

def _points_from_json(value: str | None):
    if not value:
        return None
    try:
        points = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return points if isinstance(points, list) else None

def prediction_out(item: AutoLabelPrediction) -> dict:
    return {"id": item.id, "image_id": item.image_id, "model_class_id": item.model_class_id, "model_class_name": item.model_class_name, "mapped_class_id": item.mapped_class_id, "mapped_class_name": item.mapped_class.name if item.mapped_class else None, "prediction_type": item.prediction_type or "bbox", "x": item.x, "y": item.y, "width": item.width, "height": item.height, "points": _points_from_json(item.points_json), "confidence": item.confidence, "status": item.status}

def _image_path(image: Image) -> Path:
    path = Path(image.filepath).resolve()
    try: path.relative_to(STORAGE_PATH.resolve())
    except ValueError: raise HTTPException(400, "Image path is outside configured storage")
    return path

def _run_inference(db: Session, image: Image, request: AutoLabelRequest, inference, prediction_type: str) -> tuple[str, list[AutoLabelPrediction], list[str]]:
    require_editable(lock_image(db,image.id))
    # A new inference run replaces only unreviewed proposals; decisions remain auditable.
    for stale in db.scalars(select(AutoLabelPrediction).where(AutoLabelPrediction.image_id == image.id, AutoLabelPrediction.status == "PENDING")):
        db.delete(stale)
    mappings = {row.model_class_id: row.class_id for row in db.scalars(select(ProjectClassMapping).where(ProjectClassMapping.project_id == image.project_id))}
    classes_by_name = {label.name.strip().casefold(): label.id for label in db.scalars(select(LabelClass).where(LabelClass.project_id == image.project_id))}
    model_name, raw = inference(_image_path(image), request.confidence_threshold)
    predictions, unmapped = [], set()
    for item in raw:
        # Explicit mapping wins. An exact normalized name is the only automatic match.
        mapped = mappings.get(item["model_class_id"]) or classes_by_name.get(item["model_class_name"].strip().casefold())
        if mapped is None: unmapped.add(item["model_class_name"])
        points = item.pop("points", None)
        prediction = AutoLabelPrediction(image_id=image.id, mapped_class_id=mapped, prediction_type=prediction_type, points_json=json.dumps(points) if points is not None else None, status="PENDING", **item)
        db.add(prediction); predictions.append(prediction)
    db.commit()
    for prediction in predictions: db.refresh(prediction)
    warnings = [f"No project mapping for model class: {name}" for name in sorted(unmapped)]
    return model_name, predictions, warnings

def run_auto_label(db: Session, image: Image, request: AutoLabelRequest) -> tuple[str, list[AutoLabelPrediction], list[str]]:
    return _run_inference(db, image, request, yolo_service.infer, "bbox")

def run_auto_segment(db: Session, image: Image, request: AutoLabelRequest) -> tuple[str, list[AutoLabelPrediction], list[str]]:
    # API callers that omit a threshold get the segmentation-specific deployment default.
    if "confidence_threshold" not in request.model_fields_set:
        try: request = request.model_copy(update={"confidence_threshold": float(os.getenv("YOLO_SEG_CONFIDENCE_THRESHOLD", "0.25"))})
        except ValueError: raise HTTPException(500, "YOLO_SEG_CONFIDENCE_THRESHOLD must be a number between 0 and 1")
    if not 0 <= request.confidence_threshold <= 1: raise HTTPException(500, "YOLO_SEG_CONFIDENCE_THRESHOLD must be between 0 and 1")
    return _run_inference(db, image, request, yolo_service.infer_segmentation, "polygon")

def _resolve_or_create_class(db: Session, prediction: AutoLabelPrediction) -> LabelClass:
    """Create a project class only at acceptance time, under a project-row lock."""
    image = prediction.image
    # Serializes competing accept requests for the same project in PostgreSQL.
    db.get(Project, image.project_id, with_for_update=True)
    if prediction.mapped_class_id is not None:
        label = db.get(LabelClass, prediction.mapped_class_id)
        if label and label.project_id == image.project_id: return label
    normalized = prediction.model_class_name.strip()
    if not normalized or len(normalized) > 80:
        raise HTTPException(400, "Prediction has an invalid model class name")
    label = db.scalar(select(LabelClass).where(LabelClass.project_id == image.project_id).where(func.lower(func.trim(LabelClass.name)) == normalized.casefold()))
    if label is None:
        label = LabelClass(project_id=image.project_id, name=normalized)
        db.add(label); db.flush()
    prediction.mapped_class_id = label.id
    mapping = db.scalar(select(ProjectClassMapping).where(ProjectClassMapping.project_id == image.project_id, ProjectClassMapping.model_class_id == prediction.model_class_id))
    if mapping is None:
        db.add(ProjectClassMapping(project_id=image.project_id, model_class_id=prediction.model_class_id, model_class_name=prediction.model_class_name, class_id=label.id))
    return label

def update_prediction(db: Session, prediction: AutoLabelPrediction, payload: PredictionUpdate, actor_id=None) -> AutoLabelPrediction:
    require_editable(lock_image(db,prediction.image_id))
    if prediction.status != "PENDING": raise HTTPException(400, "Only pending predictions can be edited")
    image = prediction.image
    expected_type = "polygon" if image.project.annotation_mode == "instance_segmentation" else "bbox"
    if payload.prediction_type != expected_type: raise HTTPException(400, "Prediction geometry does not match the project annotation mode")
    if payload.mapped_class_id is not None:
        label = db.get(LabelClass, payload.mapped_class_id)
        if not label: raise HTTPException(404, "Class not found")
        if label.project_id != image.project_id: raise HTTPException(400, "Class belongs to a different project")
    geometry = AnnotationCreate(class_id=payload.mapped_class_id or 1, annotation_type=payload.prediction_type, x=payload.x, y=payload.y, width=payload.width, height=payload.height, points=payload.points)
    values = annotation_values(image, geometry)
    if prediction.mapped_class_id != payload.mapped_class_id or prediction.prediction_type != payload.prediction_type or any(getattr(prediction,field) != values[field] for field in ("x", "y", "width", "height")) or _points_from_json(prediction.points_json) != _points_from_json(values["points_json"]):
        prediction.human_edited = True
        if actor_id:
            audit(db,image.project.workspace_id,actor_id,"prediction.edited","prediction",prediction.id,
                  image_id=image.id,prediction_created_at=aware(prediction.created_at).isoformat())
    # Do not overwrite the user-selected class while updating geometry; a null mapping means "create on accept".
    prediction.mapped_class_id = payload.mapped_class_id
    prediction.prediction_type = payload.prediction_type
    prediction.points_json = values["points_json"]
    for field in ("x", "y", "width", "height"): setattr(prediction, field, values[field])
    db.commit(); db.refresh(prediction); return prediction

def accept_prediction(db: Session, prediction: AutoLabelPrediction, actor_id) -> Annotation:
    image=lock_image(db,prediction.image_id); require_editable(image)
    if prediction.status == "ACCEPTED":
        if prediction.annotation: return prediction.annotation
        raise HTTPException(409, "Prediction is already accepted")
    if prediction.status != "PENDING": raise HTTPException(400, "Only pending predictions can be accepted")
    image = prediction.image
    expected_type = "polygon" if image.project.annotation_mode == "instance_segmentation" else "bbox"
    if (prediction.prediction_type or "bbox") != expected_type:
        raise HTTPException(400, "Prediction geometry does not match the project annotation mode")
    label = _resolve_or_create_class(db, prediction)
    points = _points_from_json(prediction.points_json)
    if prediction.prediction_type == "polygon" and points is None:
        raise HTTPException(400, "Prediction polygon data is invalid")
    payload = AnnotationCreate(class_id=label.id, annotation_type=prediction.prediction_type or "bbox", x=prediction.x, y=prediction.y, width=prediction.width, height=prediction.height, points=points)
    validate_payload(db, image, payload)
    capture(db,image)
    annotation = Annotation(image_id=image.id, created_by=actor_id, updated_by=actor_id, source="ai_edited" if prediction.human_edited else "ai_accepted", **annotation_values(image, payload))
    db.add(annotation); db.flush()
    prediction.annotation_id = annotation.id; prediction.status = "ACCEPTED"
    # Carry actual proposal editors into the accepted image's contributor lineage.
    # Creation identity prevents reused pending-prediction IDs inheriting old edits.
    identity=aware(prediction.created_at).isoformat()
    proposal_editors=[row.actor_user_id for row in db.scalars(select(AuditLog).where(
        AuditLog.workspace_id==image.project.workspace_id,AuditLog.action=="prediction.edited",
        AuditLog.resource_type=="prediction",AuditLog.resource_id==str(prediction.id)))
        if row.details.get("image_id")==image.id and row.details.get("prediction_created_at")==identity]
    content_changed(db,image,actor_id,proposal_editors)
    db.commit(); db.refresh(annotation); return annotation

def reject_prediction(db: Session, prediction: AutoLabelPrediction) -> AutoLabelPrediction:
    if prediction.status == "ACCEPTED": raise HTTPException(400, "Accepted predictions cannot be rejected")
    prediction.status = "REJECTED"; db.commit(); db.refresh(prediction); return prediction
