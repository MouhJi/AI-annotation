"""Separate quality measures, never a score or a ranking."""
from collections import Counter, defaultdict
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from ..models import Annotation, Image, ReviewEvent, AnnotationActivity, ActivityCursor, User, WorkspaceMember
from ..models.auth import utcnow
from .auth_security import aware
from .quality_service import idle_seconds
from .workspace_service import membership
from .rbac import permissions

ERROR_CATEGORIES = ("wrong_class", "missing_object", "extra_object", "inaccurate_bbox", "inaccurate_polygon", "other")


def heartbeat(db, image, user, payload, now=None):
    now = now or utcnow()
    # Serialize across workspaces as well as tabs for this user in PostgreSQL.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    cursor = db.get(ActivityCursor, user.id, with_for_update=True, populate_existing=True)
    credited = 0.0
    client = str(payload.client_id)
    if not cursor:
        cursor = ActivityCursor(user_id=user.id, client_id=client, sequence=payload.sequence, seen_at=now)
        db.add(cursor)
    else:
        elapsed = (now - aware(cursor.seen_at)).total_seconds()
        if cursor.client_id != client and elapsed < 25:
            return {"credited_seconds": 0, "idle_seconds": idle_seconds(), "another_tab_active": True}
        if cursor.client_id == client and payload.sequence <= cursor.sequence:
            return {"credited_seconds": 0, "idle_seconds": idle_seconds(), "duplicate": True}
        if cursor.client_id == client and 0 < elapsed <= 25:
            credited = min(15.0, elapsed, payload.elapsed_seconds)
        cursor.client_id = client; cursor.sequence = payload.sequence; cursor.seen_at = now
    if credited:
        db.add(AnnotationActivity(image_id=image.id, user_id=user.id, seconds=credited,
                                  started_at=now - timedelta(seconds=credited), ended_at=now))
    db.commit()
    return {"credited_seconds": credited, "idle_seconds": idle_seconds(), "another_tab_active": False}


def metrics(db, project, user, start=None, end=None, user_id=None, split=None):
    end = aware(end) if end else utcnow()
    start = aware(start) if start else end - timedelta(days=30)
    if start >= end or end - start > timedelta(days=366): raise HTTPException(422, "Choose a valid date range of up to 366 days.")
    manager = "quality.project.read" in permissions(membership(db, project.workspace_id, user).role)
    if not manager:
        if user_id and user_id != user.id: raise HTTPException(403, "You may only view your own quality metrics.")
        user_id = user.id
    image_query = select(Image.id).where(Image.project_id == project.id)
    if split:
        if split not in {"train", "val", "test", "unassigned"}: raise HTTPException(422, "Unknown dataset split.")
        image_query = image_query.where(Image.split.is_(None) if split == "unassigned" else Image.split == split)
    # Constant query count: events are grouped in memory; no per-image/member lookups.
    all_events = list(db.scalars(select(ReviewEvent).where(ReviewEvent.image_id.in_(image_query)).order_by(ReviewEvent.id)))
    scoped = [row for row in all_events if start <= aware(row.created_at) < end and (not user_id or (row.actor_id if row.action == "submitted" else row.submitter_id) == user_id)]
    submitted = [row for row in scoped if row.action == "submitted"]
    approved = [row for row in scoped if row.action == "approved"]
    returned = [row for row in scoped if row.action == "changes_requested"]
    first = [row for row in scoped if row.submission == 1 and row.action in {"approved", "changes_requested"}]
    latest_approved = {row.image_id: row for row in approved}
    rounds = [sum(row.action == "changes_requested" and row.image_id == image_id and row.id < approval.id for row in all_events) for image_id, approval in latest_approved.items()]
    activity_query = select(AnnotationActivity).where(AnnotationActivity.image_id.in_(image_query), AnnotationActivity.ended_at > start, AnnotationActivity.started_at < end)
    if user_id: activity_query = activity_query.where(AnnotationActivity.user_id == user_id)
    activity = list(db.scalars(activity_query))
    contributions = defaultdict(lambda: {"seconds": 0.0, "content_changes": 0})
    for row in activity:
        overlap = max(0, (min(end, aware(row.ended_at)) - max(start, aware(row.started_at))).total_seconds())
        contributions[row.user_id]["seconds"] += min(row.seconds, overlap)
    for row in all_events:
        if row.action == "content_changed" and start <= aware(row.created_at) < end and (not user_id or row.actor_id == user_id):
            contributions[row.actor_id]["content_changes"] += 1
    object_query = select(Annotation.source).where(Annotation.image_id.in_(image_query))
    if user_id: object_query = object_query.where((Annotation.created_by == user_id) | (Annotation.updated_by == user_id))
    source_counts = Counter({"manual": 0, "ai": 0, "ai_edited": 0, "unknown": 0})
    for source in db.scalars(object_query): source_counts[{"manual": "manual", "ai_accepted": "ai", "ai_edited": "ai_edited"}.get(source, "unknown")] += 1
    people_query = select(User).join(WorkspaceMember, WorkspaceMember.user_id == User.id).where(WorkspaceMember.workspace_id == project.workspace_id)
    if not manager: people_query = people_query.where(User.id == user.id)
    people = {person.id: person.full_name for person in db.scalars(people_query)}
    errors = Counter(row.error_category for row in returned)
    return {"start": start.isoformat(), "end": end.isoformat(), "user_id": str(user_id) if user_id else None, "can_view_project": manager,
            "split": split, "unique_submitted_images": len({row.image_id for row in submitted}), "submissions": len(submitted),
            "approved_images": len(latest_approved), "returns": len(returned),
            "first_pass_approved": sum(row.action == "approved" for row in first), "first_pass_decided": len(first),
            "first_pass_rate": sum(row.action == "approved" for row in first) / len(first) if first else None,
            "average_rework_rounds": sum(rounds) / len(rounds) if rounds else None,
            "active_seconds": sum(row["seconds"] for row in contributions.values()),
            "errors": [{"category": key, "count": errors[key]} for key in ERROR_CATEGORIES],
            "contributors": [{"id": str(key) if key else None, "full_name": people.get(key, "Former or deleted member"), **value} for key, value in contributions.items()],
            "people": [{"id": str(key), "full_name": name} for key, name in people.items()], "object_sources": dict(source_counts),
            "tracking_started_at": min((aware(row.created_at) for row in all_events), default=None),
            "time_note": "Estimated visible, active annotation time. Heartbeats are capped at 15 seconds and shared across tabs; this is not an absolute performance measure.",
            "history_note": "Review and activity metrics only cover events recorded since this feature was installed. Older work is not estimated."}
