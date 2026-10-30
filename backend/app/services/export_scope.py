from collections import Counter
from fastapi import HTTPException
from sqlalchemy import select
from ..models import Image, ImageRevision
from .quality_service import STATES


def export_selection(db, project, split=None, image_ids=None):
    query = select(Image).where(Image.project_id == project.id).order_by(Image.id)
    if split:
        if split not in {"train", "val", "test", "unassigned"}: raise HTTPException(422, "Unknown dataset split.")
        query = query.where(Image.split.is_(None) if split == "unassigned" else Image.split == split)
    if image_ids is not None:
        existing = set(db.scalars(select(Image.id).where(Image.project_id == project.id, Image.id.in_(image_ids))))
        if existing != set(image_ids): raise HTTPException(404, "Selected images are not all in this project.")
        query = query.where(Image.id.in_(image_ids))
    images = list(db.scalars(query))
    snapshots = {row.image_id: row for row in db.scalars(select(ImageRevision).join(Image, Image.id == ImageRevision.image_id).where(
        Image.project_id == project.id, ImageRevision.revision == Image.revision, Image.id.in_([row.id for row in images])))}
    excluded = Counter({key: 0 for key in STATES})
    eligible = []
    for image in images:
        snapshot = snapshots.get(image.id)
        if not project.require_review or (image.review_state == "approved" and image.approved_revision == image.revision and snapshot is not None and snapshot.revision == image.revision):
            eligible.append(image)
        else: excluded[image.review_state] += 1
    return eligible, snapshots, {"total_selected": len(images), "eligible": len(eligible), "excluded_by_state": dict(excluded), "require_review": project.require_review}
