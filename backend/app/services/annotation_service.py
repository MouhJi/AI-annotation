import json
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..models import Image, LabelClass
from ..schemas.annotation import AnnotationBase
from .polygon_service import polygon_bbox, validate_polygon

def annotation_values(image: Image, payload: AnnotationBase) -> dict:
    """Canonical storage values; polygons retain a bbox for old readers and indexes."""
    if payload.annotation_type == "polygon":
        points = validate_polygon(payload.points or [], image.width, image.height)
        return {"class_id": payload.class_id, "annotation_type": "polygon", "points_json": json.dumps(points), **polygon_bbox(points)}
    assert None not in (payload.x, payload.y, payload.width, payload.height)
    return {"class_id": payload.class_id, "annotation_type": "bbox", "points_json": None, "x": payload.x, "y": payload.y, "width": payload.width, "height": payload.height}

def validate_payload(db: Session, image: Image, payload: AnnotationBase) -> LabelClass:
    label_class = db.get(LabelClass, payload.class_id)
    if not label_class: raise HTTPException(404, "Class not found")
    if label_class.project_id != image.project_id: raise HTTPException(400, "Class belongs to a different project")
    values = annotation_values(image, payload)
    if values["x"] + values["width"] > image.width or values["y"] + values["height"] > image.height:
        raise HTTPException(400, "Bounding box exceeds image dimensions")
    return label_class
