from fastapi import HTTPException
from sqlalchemy import select
from ..models import WorkspaceMember
from .workspace_service import audit
from ..models.auth import utcnow

RANK = {"viewer": 0, "annotator": 1, "reviewer": 2, "admin": 3, "owner": 4}

def role_map(db, workspace_id):
    return dict(db.execute(select(WorkspaceMember.user_id, WorkspaceMember.role).where(WorkspaceMember.workspace_id == workspace_id)).all())

def can_correct(annotation, actor_id, roles):
    actor = roles.get(actor_id)
    if actor not in RANK or actor == "viewer": return False
    if annotation.created_by == actor_id: return True
    creator = roles.get(annotation.created_by)
    # Missing/legacy authors are not guessed to be annotators.
    if creator is None: return actor in {"owner", "admin"}
    return RANK[actor] > RANK[creator]

def require_correction(annotation, user, roles):
    if not can_correct(annotation, user.id, roles):
        raise HTTPException(403, "You may only correct your own annotations or annotations created by a lower role.")

def snapshot(a):
    return {key: getattr(a,key) for key in ("class_id","annotation_type","x","y","width","height","points_json","version","source")}

def record_change(db, a, user, before, action="annotation.updated"):
    audit(db, a.image.project.workspace_id, user.id, action, "annotation", a.id, before=before, after=snapshot(a))

def soft_delete(db, a, user):
    before=snapshot(a); a.deleted_at=utcnow(); a.deleted_by=user.id; a.version+=1
    record_change(db,a,user,before,"annotation.deleted")
