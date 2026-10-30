from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth_dependencies import get_active_user
from ..models import Annotation, Image, Project, ImageRevision, CommentThread, ReviewComment
from ..schemas.quality import ReviewCommand, SubmitReview, ReviewState, ReviewSettings, ThreadCreate, CommentCreate, ThreadDecision, ActivityHeartbeat
from ..services.quality_service import lock_image, check_version, transition, review_detail
from ..services.comment_service import threads_for_image, create_thread, resolve_thread, text_body
from ..services.workspace_service import audit
from ..services.quality_metrics import heartbeat, metrics
from .annotations import apply_batch, list_annotations
from .images import serialize

router = APIRouter(prefix="/api", tags=["annotation-quality"])


@router.get("/images/{image_id}/review")
def get_review(image_id: int, db: Session = Depends(get_db), user=Depends(get_active_user)):
    return review_detail(db, db.get(Image, image_id), user)


@router.get("/images/{image_id}/revisions/{revision}")
def get_revision(image_id: int, revision: int, db: Session = Depends(get_db)):
    row = db.scalar(select(ImageRevision).where(ImageRevision.image_id == image_id, ImageRevision.revision == revision))
    if not row: raise HTTPException(404, "No snapshot was recorded for this revision. Historical data before this feature is unavailable.")
    return {"id": row.id, "revision": row.revision, "objects": row.objects, "contributors": row.contributors, "negative_confirmed": row.negative_confirmed}


@router.post("/images/{image_id}/review/submit")
def submit(image_id: int, payload: SubmitReview, db: Session = Depends(get_db), user=Depends(get_active_user)):
    image = lock_image(db, image_id)
    check_version(image, payload)
    apply_batch(image_id, payload.annotations, db, user)
    # The initial version has already been checked. Save and submit commit together.
    transition(db, image, user, "submit", payload.model_copy(update={"expected_revision": image.revision, "expected_review_version": image.review_version}))
    db.commit()
    return {"review": review_detail(db, image, user), "annotations": list_annotations(image_id, db, user)}


def decision(action):
    def handle(image_id: int, payload: ReviewCommand, db: Session = Depends(get_db), user=Depends(get_active_user)):
        image = lock_image(db, image_id)
        transition(db, image, user, action, payload)
        db.commit()
        return review_detail(db, image, user)
    handle.__name__ = action + "_image_review"
    return handle


for action in ("withdraw", "approve", "reject", "reopen"):
    router.add_api_route("/images/{image_id}/review/" + action, decision(action), methods=["POST"])


@router.get("/projects/{project_id}/review-queue")
def queue(project_id: int, state: ReviewState = "pending_review", split: str | None = None,
          offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    filters = [Image.project_id == project_id, Image.review_state == state]
    if split:
        if split not in {"train", "val", "test", "unassigned"}: raise HTTPException(422, "Unknown dataset split.")
        filters.append(Image.split.is_(None) if split == "unassigned" else Image.split == split)
    total = db.scalar(select(func.count(Image.id)).where(*filters)) or 0
    rows = list(db.scalars(select(Image).where(*filters).order_by(Image.id).offset(offset).limit(limit)))
    counts = dict(db.execute(select(Annotation.image_id, func.count(Annotation.id)).where(Annotation.image_id.in_([row.id for row in rows])).group_by(Annotation.image_id)).all())
    return {"total": total, "items": [serialize(row, db, counts.get(row.id, 0)) for row in rows]}


@router.patch("/projects/{project_id}/review-settings")
def settings(project_id: int, payload: ReviewSettings, db: Session = Depends(get_db), user=Depends(get_active_user)):
    project = db.get(Project, project_id)
    project.require_review = payload.require_review
    audit(db, project.workspace_id, user.id, "project.review_settings", "project", project.id, require_review=payload.require_review)
    db.commit()
    return {"require_review": project.require_review}


@router.get("/images/{image_id}/threads")
def get_threads(image_id: int, db: Session = Depends(get_db), user=Depends(get_active_user)):
    return threads_for_image(db, db.get(Image, image_id), user)


@router.post("/images/{image_id}/threads", status_code=201)
def add_thread(image_id: int, payload: ThreadCreate, db: Session = Depends(get_db), user=Depends(get_active_user)):
    return create_thread(db, db.get(Image, image_id), user, payload)


@router.post("/threads/{thread_id}/comments", status_code=201)
def reply(thread_id: int, payload: CommentCreate, db: Session = Depends(get_db), user=Depends(get_active_user)):
    thread = db.get(CommentThread, thread_id)
    db.add(ReviewComment(thread_id=thread.id, author_id=user.id, body=text_body(payload.body)))
    db.commit()
    return {"created": True}


@router.patch("/threads/{thread_id}")
def resolve(thread_id: int, payload: ThreadDecision, db: Session = Depends(get_db), user=Depends(get_active_user)):
    thread = db.scalar(select(CommentThread).where(CommentThread.id == thread_id).with_for_update().execution_options(populate_existing=True))
    return resolve_thread(db, thread, db.get(Image, thread.image_id), user, payload)


@router.post("/images/{image_id}/activity")
def record_activity(image_id: int, payload: ActivityHeartbeat, db: Session = Depends(get_db), user=Depends(get_active_user)):
    return heartbeat(db, db.get(Image, image_id), user, payload)


@router.get("/projects/{project_id}/quality")
def get_quality(project_id: int, start: datetime | None = None, end: datetime | None = None, user_id: UUID | None = None,
                split: str | None = None, db: Session = Depends(get_db), user=Depends(get_active_user)):
    return metrics(db, db.get(Project, project_id), user, start, end, user_id, split)
