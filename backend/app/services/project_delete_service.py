"""Coordinated project deletion with a safe filesystem quarantine."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ..models import Annotation, AutoLabelPrediction, Image, LabelClass, Project, ProjectClassMapping
from .image_service import STORAGE_PATH


def _project_folder(project_id: int) -> Path:
    root = STORAGE_PATH.resolve()
    expected = root / "projects" / str(project_id)
    folder = expected.resolve()
    if expected.is_symlink() or folder != expected or (root / "projects").is_symlink():
        raise HTTPException(400, "Unsafe project storage symlink; deletion blocked")
    try:
        folder.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Project storage path is outside configured storage")
    return folder


def delete_project(db: Session, project: Project) -> dict:
    return delete_projects(db, [project])

def delete_projects(db: Session, projects: list[Project], before_commit=None) -> dict:
    """Stage all folders first; one DB transaction, restore all on rollback.

    Only project-ID folders are touched, never shared weights or another tenant.
    .trash/project-ID-UUID is a recoverable quarantine if the process crashes.
    """
    project_ids = [project.id for project in projects]
    image_ids = select(Image.id).where(Image.project_id.in_(project_ids))
    staged: list[tuple[Path, Path]] = []
    warnings: list[str] = []
    try:
        for project in projects:
            folder = _project_folder(project.id)
            if folder.exists():
                trash = STORAGE_PATH.resolve() / ".trash" / f"project-{project.id}-{uuid.uuid4().hex}"
                if trash.parent.is_symlink() or not trash.resolve().is_relative_to(STORAGE_PATH.resolve()):
                    raise HTTPException(400, "Unsafe storage quarantine path; deletion blocked")
                trash.parent.mkdir(parents=True, exist_ok=True)
                os.replace(folder, trash); staged.append((folder, trash))
        # Explicit order keeps PostgreSQL foreign keys valid even without DB cascades.
        db.execute(delete(AutoLabelPrediction).where(AutoLabelPrediction.image_id.in_(image_ids)))
        db.execute(delete(Annotation).where(Annotation.image_id.in_(image_ids)))
        db.execute(delete(ProjectClassMapping).where(ProjectClassMapping.project_id.in_(project_ids)))
        db.execute(delete(Image).where(Image.project_id.in_(project_ids)))
        db.execute(delete(LabelClass).where(LabelClass.project_id.in_(project_ids)))
        db.execute(delete(Project).where(Project.id.in_(project_ids)))
        if before_commit: before_commit()
        db.commit()
    except Exception:
        db.rollback()
        for folder, trash in reversed(staged):
            if trash.exists():
                try: os.replace(trash, folder)
                except OSError:
                    import logging
                    logging.getLogger(__name__).critical("Project folder restore failed; recover quarantine %s", trash.name)
        raise
    for folder, trash in staged:
        try: shutil.rmtree(trash)
        except OSError: warnings.append(f"Storage cleanup is pending for {trash.name}")
    return {"cleanup_warnings": warnings}
