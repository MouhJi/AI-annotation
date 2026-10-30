from fastapi import HTTPException
from sqlalchemy import select
from ..models import Annotation, CommentThread, ReviewComment, User
from ..models.auth import utcnow
from .auth_security import aware
from .annotation_permissions import role_map


def text_body(body):
    if not body.strip(): raise HTTPException(422, "Comment cannot be blank.")
    return body.strip()


def threads_for_image(db, image, user):
    threads = list(db.scalars(select(CommentThread).where(CommentThread.image_id == image.id).order_by(CommentThread.id)))
    comments = list(db.scalars(select(ReviewComment).where(ReviewComment.thread_id.in_([row.id for row in threads])).order_by(ReviewComment.id)))
    ids = {row.author_id for row in comments} | {row.created_by for row in threads} | {row.resolved_by for row in threads}
    people = {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(ids - {None})))}
    objects = {row.id: row for row in db.scalars(select(Annotation).where(Annotation.image_id == image.id).execution_options(include_deleted=True))}
    role = role_map(db, image.project.workspace_id).get(user.id)
    author = lambda key: {"id": str(key), "full_name": people.get(key, "Deleted user")} if key else None
    grouped = {}
    for row in comments:
        grouped.setdefault(row.thread_id, []).append({"id": row.id, "author": author(row.author_id), "body": row.body, "created_at": aware(row.created_at).isoformat()})
    return [{"id": row.id, "object_id": row.object_id,
             "object_deleted": row.object_id is not None and (row.object_id not in objects or objects[row.object_id].deleted_at is not None),
             "resolved": row.resolved, "version": row.version, "resolved_by": author(row.resolved_by),
             "resolved_at": aware(row.resolved_at).isoformat() if row.resolved_at else None,
             "can_resolve": role in {"owner", "admin", "reviewer"} or (role == "annotator" and row.created_by == user.id),
             "comments": grouped.get(row.id, [])} for row in threads]


def create_thread(db, image, user, payload):
    if payload.object_id is not None:
        annotation = db.get(Annotation, payload.object_id)
        if not annotation or annotation.deleted_at or annotation.image_id != image.id:
            raise HTTPException(404, "Object not found in this image. Save new objects before commenting.")
    thread = CommentThread(image_id=image.id, object_id=payload.object_id, created_by=user.id)
    db.add(thread); db.flush()
    db.add(ReviewComment(thread_id=thread.id, author_id=user.id, body=text_body(payload.body)))
    db.commit()
    return {"id": thread.id}


def resolve_thread(db, thread, image, user, payload):
    role = role_map(db, image.project.workspace_id).get(user.id)
    if role not in {"owner", "admin", "reviewer"} and not (role == "annotator" and thread.created_by == user.id):
        raise HTTPException(403, "Only the thread creator or a reviewer can resolve or reopen this thread.")
    if payload.expected_version != thread.version: raise HTTPException(409, "This thread changed. Reload comments before continuing.")
    if thread.resolved != payload.resolved:
        thread.resolved = payload.resolved; thread.version += 1
        if payload.resolved:
            thread.resolved_by = user.id
            thread.resolved_at = utcnow()
    db.commit()
    return {"id": thread.id}
