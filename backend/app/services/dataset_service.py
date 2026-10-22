from __future__ import annotations
import io
import json
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..models import Annotation, Image, LabelClass, Project
from ..schemas.dataset import SplitConfig, SplitSummary
from .polygon_service import validate_polygon

SPLITS = ("train", "val", "test")

def split_summary(images: list[Image]) -> SplitSummary:
    counts = Counter(image.split for image in images)
    return SplitSummary(train=counts["train"], val=counts["val"], test=counts["test"], total=len(images), configured=all(image.split in SPLITS for image in images))

def _counts(total: int, config: SplitConfig) -> dict[str, int]:
    """Largest-remainder allocation; tiny datasets remain useful for training."""
    ratios = {"train": config.train, "val": config.val, "test": config.test}
    raw = {name: total * ratio / 100 for name, ratio in ratios.items()}
    counts = {name: int(value) for name, value in raw.items()}
    remainder = total - sum(counts.values())
    for name in sorted(SPLITS, key=lambda item: (raw[item] - counts[item], item == "train"), reverse=True)[:remainder]:
        counts[name] += 1
    if total and counts["train"] == 0:
        donor = max((name for name in SPLITS if counts[name]), key=lambda name: counts[name], default=None)
        if donor:
            counts[donor] -= 1
            counts["train"] += 1
    return counts

def assign_splits(db: Session, project_id: int, config: SplitConfig) -> SplitSummary:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    images = list(db.scalars(select(Image).where(Image.project_id == project_id).order_by(Image.id)))
    counts = _counts(len(images), config)
    cursor = 0
    for split in SPLITS:
        for image in images[cursor:cursor + counts[split]]:
            image.split = split
        cursor += counts[split]
    db.commit()
    return split_summary(images)

def _safe_dataset_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-") or "dataset"

def yolo_line(annotation: Annotation, image: Image, class_index: int) -> str:
    if (getattr(annotation, "annotation_type", "bbox") or "bbox") != "bbox":
        raise HTTPException(400, f"Invalid annotation {annotation.id}: expected a bounding box")
    if annotation.x < 0 or annotation.y < 0 or annotation.width <= 0 or annotation.height <= 0 or annotation.x + annotation.width > image.width or annotation.y + annotation.height > image.height:
        raise HTTPException(400, f"Invalid annotation {annotation.id}: bounding box exceeds image dimensions")
    x_center = (annotation.x + annotation.width / 2) / image.width
    y_center = (annotation.y + annotation.height / 2) / image.height
    return f"{class_index} {x_center:.6f} {y_center:.6f} {annotation.width / image.width:.6f} {annotation.height / image.height:.6f}"

def yolo_polygon_line(annotation: Annotation, image: Image, class_index: int) -> str:
    if annotation.annotation_type != "polygon" or not annotation.points_json:
        raise HTTPException(400, f"Invalid annotation {annotation.id}: instance segmentation export requires a polygon")
    try: points = validate_polygon(json.loads(annotation.points_json), image.width, image.height)
    except (ValueError, TypeError, json.JSONDecodeError): raise HTTPException(400, f"Invalid annotation {annotation.id}: malformed polygon geometry")
    return f"{class_index} " + " ".join(f"{coordinate:.6f}" for point in points for coordinate in (point[0] / image.width, point[1] / image.height))

def export_yolo_zip(db: Session, project_id: int) -> tuple[bytes, str]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    statement = select(Image).where(Image.project_id == project_id).options(selectinload(Image.annotations).selectinload(Annotation.label_class)).order_by(Image.id)
    images = list(db.scalars(statement))
    if not images:
        raise HTTPException(400, "Project has no images to export")
    if any(image.split not in SPLITS for image in images):
        assign_splits(db, project_id, SplitConfig())
        images = list(db.scalars(statement))
    classes = list(db.scalars(select(LabelClass).where(LabelClass.project_id == project_id).order_by(LabelClass.id)))
    if not classes:
        raise HTTPException(400, "Project must have at least one class before export")
    class_ids = {item.id: index for index, item in enumerate(classes)}
    root = _safe_dataset_name(project.name)
    with tempfile.TemporaryDirectory(prefix="annotation-export-") as temp_dir:
        workspace = Path(temp_dir) / root
        for split in SPLITS:
            (workspace / "images" / split).mkdir(parents=True)
            (workspace / "labels" / split).mkdir(parents=True)
        yaml = f"path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnc: {len(classes)}\nnames: [{', '.join(repr(item.name) for item in classes)}]\n"
        (workspace / "data.yaml").write_text(yaml, encoding="utf-8")
        for image in images:
            source = Path(image.filepath)
            if not source.is_file():
                raise HTTPException(400, f"Image file is missing: {image.filename}")
            target_stem = f"{image.id}_{Path(image.filename).stem}"
            shutil.copy2(source, workspace / "images" / image.split / f"{target_stem}{source.suffix.lower()}")
            lines: list[str] = []
            for annotation in image.annotations:
                if annotation.class_id not in class_ids or annotation.label_class.project_id != project_id:
                    raise HTTPException(400, f"Invalid annotation {annotation.id}: class does not belong to project")
                if project.annotation_mode == "instance_segmentation":
                    lines.append(yolo_polygon_line(annotation, image, class_ids[annotation.class_id]))
                else:
                    lines.append(yolo_line(annotation, image, class_ids[annotation.class_id]))
            (workspace / "labels" / image.split / f"{target_stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in workspace.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(workspace.parent).as_posix())
        return buffer.getvalue(), f"{root}-yolo.zip"
