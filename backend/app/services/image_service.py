import os, re, uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from PIL import Image as PillowImage
from sqlalchemy.orm import Session
from ..models import Image, Project

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 20 * 1024 * 1024
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./storage"))

def require_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project: raise HTTPException(404, "Project not found")
    return project

async def save_upload(db: Session, project_id: int, upload: UploadFile) -> Image:
    require_project(db, project_id)
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS: raise HTTPException(400, "Unsupported image type. Use jpg, jpeg, png, or webp.")
    content = await upload.read()
    if not content or len(content) > MAX_FILE_SIZE: raise HTTPException(400, "Image must be between 1 byte and 20 MB")
    folder = STORAGE_PATH / "projects" / str(project_id) / "images"; folder.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(upload.filename).name)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"; destination = folder / stored_name
    destination.write_bytes(content)
    try:
        with PillowImage.open(destination) as picture:
            width, height = picture.size
    except Exception:
        destination.unlink(missing_ok=True); raise HTTPException(400, "File is not a valid image")
    item = Image(project_id=project_id, filename=safe_name, filepath=str(destination.resolve()), width=width, height=height)
    db.add(item); db.commit(); db.refresh(item); return item
