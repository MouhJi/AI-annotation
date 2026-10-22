"""Safe, best-effort filesystem cleanup for image deletion."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ..models import Annotation, AutoLabelPrediction, Image
from .image_service import STORAGE_PATH


def _safe_path(image: Image) -> Path:
    path = Path(image.filepath).resolve()
    try:
        path.relative_to(STORAGE_PATH.resolve())
    except ValueError:
        raise HTTPException(400, f"Image {image.id} has a file path outside configured storage")
    return path


def _stage(image: Image) -> tuple[Path, Path] | None:
    source = _safe_path(image)
    if not source.exists():
        return None
    trash = STORAGE_PATH.resolve() / ".trash" / f"{uuid.uuid4().hex}-{source.name}"
    trash.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, trash)
    except OSError as exc:
        raise HTTPException(500, f"Unable to stage image file for deletion: {exc.strerror or 'filesystem error'}")
    return source, trash


def delete_images(db: Session, images: list[Image]) -> dict:
    """Delete related DB rows transactionally and clean staged storage files after commit."""
    if not images:
        return {"deleted_image_ids": [], "cleanup_warnings": []}
    image_ids = [image.id for image in images]
    staged: list[tuple[Path, Path]] = []
    warnings: list[str] = []
    try:
        for image in images:
            shared = db.scalar(select(Image.id).where(Image.filepath == image.filepath, Image.id != image.id))
            if shared is not None:
                raise HTTPException(409, f"Image file for {image.id} is shared with image {shared}; deletion was blocked")
            result = _stage(image)
            if result is None:
                warnings.append(f"Image file was already missing for image {image.id}")
            else:
                staged.append(result)
        # Predictions reference annotations, so remove them before annotations/image rows.
        db.execute(delete(AutoLabelPrediction).where(AutoLabelPrediction.image_id.in_(image_ids)))
        db.execute(delete(Annotation).where(Annotation.image_id.in_(image_ids)))
        db.execute(delete(Image).where(Image.id.in_(image_ids)))
        db.commit()
    except Exception:
        db.rollback()
        for source, trash in staged:
            try:
                if trash.exists(): os.replace(trash, source)
            except OSError:
                warnings.append(f"Could not restore staged image file {source.name}")
        raise
    for _, trash in staged:
        try:
            trash.unlink(missing_ok=True)
        except OSError:
            warnings.append(f"Database row was deleted, but storage cleanup is pending for {trash.name}")
    return {"deleted_image_ids": image_ids, "cleanup_warnings": warnings}
