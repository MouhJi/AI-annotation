"""Immutable image content snapshots, shared by annotation writes and exports."""
import os
import uuid
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from ..models import Annotation, Image, ImageRevision, ReviewEvent, User, CommentThread
from .auth_security import aware
from .annotation_permissions import role_map
from .rbac import permissions

STATES = ("not_started", "in_progress", "pending_review", "changes_requested", "approved")
LOCKED = {"pending_review", "approved"}


def idle_seconds():
    return max(15, min(300, int(os.getenv("ANNOTATION_ACTIVITY_IDLE_SECONDS", "60"))))


def lock_image(db, image_id):
    image = db.scalar(select(Image).where(Image.id == image_id).with_for_update().execution_options(populate_existing=True))
    if image is None: raise HTTPException(404, "Image not found")
    return image


def require_editable(image):
    if image.review_state in LOCKED:
        raise HTTPException(409, "This image is locked for review. Withdraw the submission, request changes, or reopen the approved image before editing.")


def check_version(image, command):
    if image.revision != command.expected_revision or image.review_version != command.expected_review_version:
        raise HTTPException(409, "The image revision or review decision changed. Reload the image before continuing.")


def current_snapshot(db, image):
    return db.scalar(select(ImageRevision).where(ImageRevision.image_id == image.id, ImageRevision.revision == image.revision))


def capture(db, image, actor_id=None, extra_contributors=()):
    """Insert once. Opening an image never calls this function."""
    existing = current_snapshot(db, image)
    if existing: return existing
    rows = list(db.scalars(select(Annotation).where(Annotation.image_id == image.id).options(joinedload(Annotation.label_class)).order_by(Annotation.id)))
    previous = db.scalar(select(ImageRevision).where(ImageRevision.image_id == image.id).order_by(ImageRevision.revision.desc()))
    contributors = set(previous.contributors if previous else [])
    contributors.update(str(person) for person in extra_contributors if person)
    if actor_id: contributors.add(str(actor_id))
    objects = []
    for row in rows:
        for person in (row.created_by, row.updated_by):
            if person: contributors.add(str(person))
        objects.append({"id": row.id, "class_id": row.class_id, "class_name": row.label_class.name,
                        "annotation_type": row.annotation_type, "x": row.x, "y": row.y, "width": row.width, "height": row.height,
                        "points_json": row.points_json, "created_by": str(row.created_by) if row.created_by else None,
                        "updated_by": str(row.updated_by) if row.updated_by else None, "source": row.source, "version": row.version,
                        "created_at": aware(row.created_at).isoformat(), "updated_at": aware(row.updated_at).isoformat()})
    revision = ImageRevision(image_id=image.id, revision=image.revision, objects=objects,
                             contributors=sorted(contributors), negative_confirmed=image.negative_confirmed)
    db.add(revision); db.flush()
    return revision


def event(db, image, actor_id, action, **kwargs):
    row = ReviewEvent(image_id=image.id, revision=image.revision, actor_id=actor_id, action=action, **kwargs)
    db.add(row)
    return row


def content_changed(db, image, actor_id, extra_contributors=()):
    """Called once per atomic content mutation, after all object changes are staged."""
    require_editable(image)
    image.revision += 1
    image.review_version += 1
    image.approved_revision = None
    image.negative_confirmed = False
    if image.review_state != "changes_requested": image.review_state = "in_progress"
    db.flush()
    capture(db, image, actor_id, extra_contributors)
    event(db, image, actor_id, "content_changed")


def latest_submission(db, image):
    return db.scalar(select(ReviewEvent).where(ReviewEvent.image_id == image.id, ReviewEvent.action == "submitted").order_by(ReviewEvent.id.desc()))


def transition(db, image, user, action, command):
    check_version(image, command)
    allowed = permissions(role_map(db, image.project.workspace_id).get(user.id))
    required = {"submit": "review.submit", "withdraw": "review.submit", "approve": "review.approve", "reject": "review.reject", "reopen": "review.reopen"}[action]
    if required not in allowed: raise HTTPException(403, "Permission denied: " + required)
    submission = latest_submission(db, image)
    details = {}
    if action == "submit":
        require_editable(image)
        count = db.scalar(select(func.count(Annotation.id)).where(Annotation.image_id == image.id)) or 0
        if count == 0:
            if not command.negative_confirmed: raise HTTPException(422, "Confirm that this image contains no objects before submitting an empty annotation.")
            if not image.negative_confirmed:
                image.revision += 1; image.negative_confirmed = True
        elif command.negative_confirmed:
            raise HTTPException(422, "An image with objects cannot be confirmed as a negative image.")
        capture(db, image, user.id if count == 0 else None)
        image.review_state = "pending_review"
        details = {"submitter_id": user.id, "submission": (submission.submission if submission else 0) + 1}
        action_name = "submitted"
    elif action == "reopen":
        if image.review_state != "approved": raise HTTPException(409, "Only an approved image can be reopened.")
        image.review_state = "in_progress"; image.approved_revision = None
        action_name = "reopened"
    else:
        if image.review_state != "pending_review" or not submission or submission.revision != image.revision:
            raise HTTPException(409, "This revision is no longer waiting for review. Reload the image.")
        details = {"submitter_id": submission.submitter_id, "submission": submission.submission}
        if action == "withdraw":
            if submission.submitter_id != user.id and "review.reject" not in allowed:
                raise HTTPException(403, "Only the submitter or a reviewer can withdraw this submission.")
            image.review_state = "in_progress"; action_name = "withdrawn"
        elif action == "approve":
            revision = capture(db, image)
            if str(user.id) in revision.contributors:
                raise HTTPException(403, "You contributed to this image revision and cannot approve it. Add or ask another independent Reviewer, Admin or Owner to review it.")
            image.review_state = "approved"; image.approved_revision = image.revision; action_name = "approved"
        else:
            if not command.reason or not command.reason.strip(): raise HTTPException(422, "A reason is required when requesting changes.")
            if not command.error_category: raise HTTPException(422, "Choose an error category.")
            image.review_state = "changes_requested"; action_name = "changes_requested"
            details.update(reason=command.reason.strip(), error_category=command.error_category)
    image.review_version += 1
    event(db, image, user.id, action_name, **details)
    db.flush()


def review_detail(db, image, user):
    rows = list(db.scalars(select(ReviewEvent).where(ReviewEvent.image_id == image.id).order_by(ReviewEvent.id.desc()).limit(200)))
    revision = current_snapshot(db, image)
    contributors = set(revision.contributors if revision else [])
    if not revision:
        for created, updated in db.execute(select(Annotation.created_by, Annotation.updated_by).where(Annotation.image_id == image.id)):
            contributors.update(str(person) for person in (created, updated) if person)
    ids = {row.actor_id for row in rows} | {row.submitter_id for row in rows}
    ids.update(uuid.UUID(value) for value in contributors)
    people = {str(person.id): person.full_name for person in db.scalars(select(User).where(User.id.in_(ids - {None})))}
    author = lambda value: {"id": str(value), "full_name": people.get(str(value), "Deleted user")} if value else None
    allowed = permissions(role_map(db, image.project.workspace_id).get(user.id))
    submission = next((row for row in rows if row.action == "submitted"), None)
    return {"state": image.review_state, "revision": image.revision, "review_version": image.review_version,
            "approved_revision": image.approved_revision, "negative_confirmed": image.negative_confirmed,
            "snapshot_id": revision.id if revision else None,
            "contributors": [author(value) for value in sorted(contributors)],
            "can_approve": "review.approve" in allowed and str(user.id) not in contributors and image.review_state == "pending_review",
            "can_withdraw": image.review_state == "pending_review" and ("review.reject" in allowed or bool(submission and submission.submitter_id == user.id)),
            "independent_review_required": str(user.id) in contributors,
            "open_threads": db.scalar(select(func.count(CommentThread.id)).where(CommentThread.image_id == image.id, CommentThread.resolved.is_(False))) or 0,
            "idle_seconds": idle_seconds(),
            "history": [{"id": row.id, "revision": row.revision, "action": row.action, "actor": author(row.actor_id),
                         "submitter": author(row.submitter_id), "submission": row.submission, "reason": row.reason,
                         "error_category": row.error_category, "created_at": aware(row.created_at).isoformat()} for row in rows]}
