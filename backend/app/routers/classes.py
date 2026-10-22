from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Annotation, AutoLabelPrediction, LabelClass, ProjectClassMapping
from ..schemas.class_schema import ClassCreate, ClassOut, ClassUpdate
from ..services.image_service import require_project
router=APIRouter(prefix="/api",tags=["classes"])
@router.post("/projects/{project_id}/classes",response_model=ClassOut,status_code=201)
def create(project_id:int,payload:ClassCreate,db:Session=Depends(get_db)):
    require_project(db,project_id)
    name = payload.name.strip()
    if not name: raise HTTPException(422,"Class name cannot be blank")
    existing = db.scalar(select(LabelClass).where(LabelClass.project_id == project_id, func.lower(func.trim(LabelClass.name)) == name.casefold()))
    if existing: raise HTTPException(409,"A class with this name already exists in the project")
    item=LabelClass(project_id=project_id,name=name); db.add(item); db.commit(); db.refresh(item); return item
@router.get("/projects/{project_id}/classes",response_model=list[ClassOut])
def list_classes(project_id:int,db:Session=Depends(get_db)):
    require_project(db,project_id); return db.scalars(select(LabelClass).where(LabelClass.project_id==project_id).order_by(LabelClass.name))
@router.put("/classes/{class_id}", response_model=ClassOut)
def rename(class_id: int, payload: ClassUpdate, db: Session = Depends(get_db)):
    item = db.get(LabelClass, class_id)
    if not item: raise HTTPException(404, "Class not found")
    name = payload.name.strip()
    if not name: raise HTTPException(422, "Class name cannot be blank")
    duplicate = db.scalar(select(LabelClass).where(LabelClass.project_id == item.project_id, func.lower(func.trim(LabelClass.name)) == name.casefold(), LabelClass.id != item.id))
    if duplicate: raise HTTPException(409, "A class with this name already exists in the project")
    item.name = name
    db.commit(); db.refresh(item)
    return item
@router.delete("/classes/{class_id}")
def delete(class_id:int,db:Session=Depends(get_db)):
    item=db.get(LabelClass,class_id)
    if not item: raise HTTPException(404,"Class not found")
    references = {
        "annotations": db.scalar(select(func.count(Annotation.id)).where(Annotation.class_id == class_id)) or 0,
        "predictions": db.scalar(select(func.count(AutoLabelPrediction.id)).where(AutoLabelPrediction.mapped_class_id == class_id)) or 0,
        "mappings": db.scalar(select(func.count(ProjectClassMapping.id)).where(ProjectClassMapping.class_id == class_id)) or 0,
    }
    if any(references.values()):
        parts = [f"{count} {name}" for name, count in references.items() if count]
        raise HTTPException(409, {"message": f'Cannot delete class "{item.name}" because it is used by ' + ", ".join(parts) + ".", "references": references})
    db.delete(item); db.commit()
    return {"deleted": True}
