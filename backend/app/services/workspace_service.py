import re
import threading
import uuid
from contextlib import contextmanager
from fastapi import HTTPException
from sqlalchemy import select, text
from ..models import Workspace, WorkspaceMember, User, AuditLog
from .rbac import ROLE_PERMISSIONS

def audit(db, workspace_id, actor_id, action, resource_type, resource_id, **details):
    # Callers supply only explicit allowlisted scalar fields, never request bodies.
    db.add(AuditLog(workspace_id=workspace_id, actor_user_id=actor_id, action=action, resource_type=resource_type, resource_id=str(resource_id), details=details))

def normalize_slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not value or len(value) > 160: raise HTTPException(422, "Slug must contain letters/numbers and be at most 160 characters")
    return value

def membership(db, workspace_id, user):
    row = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id).execution_options(populate_existing=True))
    if not row or not db.get(Workspace, workspace_id): raise HTTPException(404, "Workspace not found or access revoked")
    return row

def require_workspace_permission(db, workspace_id, user, permission):
    row = membership(db, workspace_id, user)
    if permission not in ROLE_PERMISSIONS.get(row.role, ()): raise HTTPException(403, "Permission denied: " + permission)
    return row

_locks = {}
_locks_guard = threading.Lock()

@contextmanager
def workspace_operation(db, workspace_id):
    """Serialize workspace mutations across workers, spanning legacy service commits.

    Dedicated PostgreSQL session advisory lock survives transaction commits. Never
    wait behind a long inference: return 409 so deletion/removal can be retried safely.
    SQLite test fallback is process-local; production uses PostgreSQL only.
    """
    key = int.from_bytes(workspace_id.bytes[:8], "big", signed=True)
    if db.bind.dialect.name == "postgresql":
        with db.bind.connect() as connection:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            connection.commit()
            if not acquired: raise HTTPException(409, "Workspace has an active operation or AI job. Retry when it finishes.")
            try: yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key}); connection.commit()
    else:
        with _locks_guard: lock = _locks.setdefault(workspace_id, threading.Lock())
        if not lock.acquire(blocking=False): raise HTTPException(409, "Workspace has an active operation or AI job. Retry when it finishes.")
        try: yield
        finally: lock.release()

def personal_workspace(db, user):
    # User row lock + UNIQUE(personal_user_id) make concurrent creation safe.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    workspace = db.scalar(select(Workspace).where(Workspace.personal_user_id == user.id))
    if workspace: return workspace
    workspace = Workspace(name=(user.full_name[:120] + "'s workspace"), slug=f"personal-{user.id.hex}", created_by=user.id, personal_user_id=user.id)
    db.add(workspace); db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    audit(db, workspace.id, user.id, "workspace.created", "workspace", workspace.id, personal=True)
    db.flush()
    return workspace
