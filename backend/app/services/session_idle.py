import os
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import update
from ..models import UserSession
from ..models.auth import utcnow
from .auth_security import aware


def policy():
    timeout = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "60"))
    warning = int(os.getenv("IDLE_WARNING_MINUTES", "5"))
    if not 0 < warning < timeout: raise RuntimeError("Idle warning must be positive and less than timeout")
    return timeout * 60, warning * 60


def enforce_idle(db, session):
    seconds, _ = policy()
    if aware(session.last_activity_at) + timedelta(seconds=seconds) <= utcnow():
        db.execute(update(UserSession).where(UserSession.id == session.id, UserSession.revoked_at.is_(None),
                   UserSession.last_activity_at <= utcnow()-timedelta(seconds=seconds)).values(revoked_at=utcnow()).execution_options(synchronize_session=False))
        db.commit(); db.refresh(session)
        if session.revoked_at: raise HTTPException(401, "Your session expired due to inactivity.")


def session_out(session):
    seconds, warning = policy()
    return {"id": str(session.id), "server_time": utcnow(), "idle_expires_at": min(aware(session.expires_at), aware(session.last_activity_at)+timedelta(seconds=seconds)),
            "idle_timeout_seconds": seconds, "warning_seconds": warning}
