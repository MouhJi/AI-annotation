from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Annotation, Image
from ..schemas.image import BulkImageDelete, ImageDetail, ImageOut
from ..services.image_delete_service import delete_images
from ..services.image_service import save_upload, require_project, STORAGE_PATH
router=APIRouter(prefix="/api",tags=["images"])
def serialize(i:Image,db:Session):
    relative=Path(i.filepath).resolve().relative_to(STORAGE_PATH.resolve())
    return ImageOut(id=i.id,filename=i.filename,width=i.width,height=i.height,annotation_count=db.scalar(select(func.count(Annotation.id)).where(Annotation.image_id==i.id)) or 0,image_url=f"/storage/{relative.as_posix()}",split=i.split)
@router.post("/projects/{project_id}/images",response_model=list[ImageOut],status_code=201)
async def upload(project_id:int,files:list[UploadFile]=File(...),db:Session=Depends(get_db)):
    if not files: raise HTTPException(400,"At least one image is required")
    return [serialize(await save_upload(db,project_id,f),db) for f in files]
@router.get("/projects/{project_id}/images",response_model=list[ImageOut])
def list_images(project_id:int,db:Session=Depends(get_db)):
    require_project(db,project_id); return [serialize(i,db) for i in db.scalars(select(Image).where(Image.project_id==project_id).order_by(Image.created_at))]
@router.get("/images/{image_id}",response_model=ImageDetail)
def get_image(image_id:int,db:Session=Depends(get_db)):
    i=db.get(Image,image_id)
    if not i: raise HTTPException(404,"Image not found")
    basic=serialize(i,db).model_dump()
    return ImageDetail(**basic, project_id=i.project_id, filepath=i.filepath, created_at=i.created_at)

@router.delete("/images/{image_id}")
def delete_image(image_id: int, db: Session = Depends(get_db)):
    image = db.get(Image, image_id)
    if not image: raise HTTPException(404, "Image not found")
    result = delete_images(db, [image])
    return {"success": True, "deleted_image_id": image_id, "cleanup_warnings": result["cleanup_warnings"]}

@router.post("/images/bulk-delete")
def bulk_delete_images(payload: BulkImageDelete, db: Session = Depends(get_db)):
    require_project(db, payload.project_id)
    if len(set(payload.image_ids)) != len(payload.image_ids):
        raise HTTPException(400, "Image IDs must not contain duplicates")
    images = list(db.scalars(select(Image).where(Image.id.in_(payload.image_ids))))
    found = {image.id for image in images}
    missing = sorted(set(payload.image_ids) - found)
    foreign = sorted(image.id for image in images if image.project_id != payload.project_id)
    if missing: raise HTTPException(404, f"Images not found: {missing}")
    if foreign: raise HTTPException(400, f"Images do not belong to this project: {foreign}")
    result = delete_images(db, images)
    return {"success": True, "deleted_count": len(images), "deleted_image_ids": result["deleted_image_ids"], "cleanup_warnings": result["cleanup_warnings"]}
