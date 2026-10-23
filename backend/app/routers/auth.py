import uuid
from datetime import timedelta
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update, case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..auth_config import settings
from ..auth_dependencies import get_active_user
from ..database import get_db
from ..models import User, UserSession, UsedRefreshToken, PasswordResetToken, EmailVerificationToken
from ..models.auth import utcnow
from ..rate_limit import limiter
from ..schemas.auth import RegisterInput, LoginInput, ProfileInput, EmailInput, ChangePasswordInput, ResetInput, TokenInput
from ..services.auth_security import hash_password, verify_password, opaque_token, token_hash, access_token, aware
from ..services.email_service import prepare_delivery, deliver_email
from ..services.email_templates import action_email
from ..services.workspace_service import personal_workspace
from ..services.session_idle import enforce_idle, session_out, policy

COOKIE = "annotation_refresh"
COOKIE_PATH = "/api/auth"
GENERIC = {"message": "Request processed. If the account is eligible, check your inbox and spam folder. If no email arrives, retry later or contact support."}

def generic_email_response():
    # Provider availability is installation-wide, never account-specific.
    return {**GENERIC, "email_delivery": "unavailable" if settings()["email_backend"] == "file" else "requested"}

def check_origin(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}: return
    origin = request.headers.get("origin")
    if not origin and request.headers.get("referer"):
        parsed = urlsplit(request.headers["referer"]); origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in settings()["origins"]: raise HTTPException(403, "Untrusted request origin")

router = APIRouter(prefix="/api/auth", tags=["authentication"], dependencies=[Depends(check_origin)])
users_router = APIRouter(prefix="/api/users", tags=["account"])

def user_out(user):
    return {"id": str(user.id), "email": user.email, "full_name": user.full_name, "status": user.status, "email_verified": user.email_verified_at is not None, "created_at": aware(user.created_at)}
def set_cookie(response, raw):
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings()["secure"], samesite="lax", path=COOKIE_PATH, max_age=settings()["refresh_days"]*86400)
def clear_cookie(response):
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, secure=settings()["secure"], samesite="lax")
def auth_out(user, session):
    return {"access_token": access_token(user, session), "token_type": "bearer", "expires_in": settings()["access_minutes"]*60, "user": user_out(user), "session": session_out(session)}
def device_name(user_agent):
    browser = next((name for marker, name in [("Edg/", "Microsoft Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")] if marker in user_agent), "Browser")
    platform = next((name for marker, name in [("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"), ("Macintosh", "macOS"), ("Linux", "Linux")] if marker in user_agent), "Device")
    return f"{browser} · {platform}"
def invalidate_tokens(db, user_id):
    for model in (PasswordResetToken, EmailVerificationToken): db.execute(update(model).where(model.user_id == user_id, model.used_at.is_(None)).values(used_at=utcnow()))
def revoke_sessions(db, user_id):
    db.execute(update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
def send_action(db, user, model):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    raw = opaque_token(); now = utcnow()
    db.execute(update(model).where(model.user_id == user.id, model.used_at.is_(None)).values(used_at=now))
    token = model(user_id=user.id, token_hash=token_hash(raw), expires_at=now+timedelta(minutes=30 if model is PasswordResetToken else 1440))
    db.add(token); db.flush()
    kind = "password_reset" if model is PasswordResetToken else "verification"
    attempt = prepare_delivery(db, kind, token.id)
    db.commit()
    action = "reset-password" if model is PasswordResetToken else "verify-email"
    # Fragment tokens do not reach frontend access logs or Referer headers.
    subject, text_body, html_body = action_email(kind, f"{settings()['frontend']}/{action}#token={raw}", name=user.full_name)
    return deliver_email(db, attempt, user.email, subject, text_body, html_body)

@router.post("/register", status_code=201)
def register(payload: RegisterInput, request: Request, db: Session = Depends(get_db)):
    limiter.check(request, "register", str(payload.email), limit=5)
    user = User(email=str(payload.email), full_name=payload.full_name, password_hash=hash_password(payload.password), status="pending_verification" if settings()["verify_required"] else "active")
    db.add(user)
    try: db.commit(); db.refresh(user)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Unable to register this email. Sign in or reset your password.")
    personal_workspace(db,user); db.commit()
    delivery = send_action(db, user, EmailVerificationToken)
    return {**user_out(user), "email_delivery": delivery}

@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    limiter.check(request, "login", str(payload.email))
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    # Hash even unknown emails to reduce timing differences.
    valid = verify_password(payload.password, user.password_hash) if user else (hash_password(payload.password) and False)
    if not valid or user.status != "active": raise HTTPException(401, "Invalid email or password, or account unavailable")
    raw = opaque_token(); now = utcnow()
    session = UserSession(user_id=user.id, refresh_token_hash=token_hash(raw), expires_at=now+timedelta(days=settings()["refresh_days"]), last_used_at=now, user_agent=request.headers.get("user-agent", "")[:500], device_name=device_name(request.headers.get("user-agent", "")))
    user.last_login_at = now; db.add(session); db.commit(); db.refresh(session)
    set_cookie(response, raw); return auth_out(user, session)

@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    limiter.check(request, "refresh", limit=60)
    raw = request.cookies.get(COOKIE, ""); digest = token_hash(raw)
    session = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == digest).with_for_update())
    if not session:
        spent = db.get(UsedRefreshToken, digest)
        if spent:
            db.execute(update(UserSession).where(UserSession.id == spent.session_id).values(revoked_at=utcnow())); db.commit()
        raise HTTPException(401, "Session expired or invalid")
    user = db.get(User, session.user_id)
    if session.revoked_at or aware(session.expires_at) <= utcnow() or not user or user.status != "active": raise HTTPException(401, "Session expired or invalid")
    enforce_idle(db, session)
    next_raw = opaque_token()
    changed = db.execute(update(UserSession).where(UserSession.id == session.id, UserSession.refresh_token_hash == digest, UserSession.revoked_at.is_(None)).values(refresh_token_hash=token_hash(next_raw), last_used_at=utcnow()))
    if changed.rowcount != 1: db.rollback(); raise HTTPException(401, "Session expired or invalid")
    db.add(UsedRefreshToken(token_hash=digest, session_id=session.id)); db.commit(); db.refresh(session)
    set_cookie(response, next_raw); return auth_out(user, session)

@router.post("/logout")
def logout(request: Request, response: Response, payload: dict | None = None, db: Session = Depends(get_db)):
    digest = token_hash(request.cookies.get(COOKIE, ""))
    session = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == digest))
    spent = db.get(UsedRefreshToken, digest)
    target = str(session.id) if session else str(spent.session_id) if spent else None
    if payload and payload.get("session_id") and payload["session_id"] != target:
        return {"message": "Session already ended"}
    if session: session.revoked_at = utcnow()
    elif spent: db.execute(update(UserSession).where(UserSession.id == spent.session_id).values(revoked_at=utcnow()))
    db.commit(); clear_cookie(response); return {"message": "Signed out"}

@router.get("/session")
def session_status(request: Request, user=Depends(get_active_user), db: Session=Depends(get_db)):
    return session_out(db.get(UserSession, request.state.session_id))

@router.post("/activity")
def activity(request: Request, user=Depends(get_active_user), db: Session=Depends(get_db)):
    limiter.check(request, "session-activity", str(request.state.session_id), limit=120)
    now = utcnow(); seconds, _ = policy()
    changed = db.execute(update(UserSession).where(UserSession.id == request.state.session_id,
        UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now,
        UserSession.last_activity_at > now-timedelta(seconds=seconds)).values(last_activity_at=case((UserSession.last_activity_at < now, now), else_=UserSession.last_activity_at)).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback(); raise HTTPException(401, "Your session expired due to inactivity.")
    db.commit()
    return session_out(db.get(UserSession, request.state.session_id))

@router.post("/logout-all")
def logout_all(response: Response, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    revoke_sessions(db, user.id); db.commit(); clear_cookie(response); return {"message": "All sessions revoked"}

@router.get("/me")
def me(user: User = Depends(get_active_user)): return user_out(user)

@users_router.patch("/me")
def profile(payload: ProfileInput, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    user.full_name = payload.full_name; db.commit(); db.refresh(user); return user_out(user)

@router.post("/change-password")
def change_password(payload: ChangePasswordInput, response: Response, request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    limiter.check(request, "change-password", str(user.id), limit=5)
    if not verify_password(payload.current_password, user.password_hash): raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password); revoke_sessions(db, user.id); invalidate_tokens(db, user.id); db.commit(); clear_cookie(response)
    return {"message": "Password changed. Sign in again on all devices."}

@router.post("/forgot-password")
def forgot(payload: EmailInput, request: Request, db: Session = Depends(get_db)):
    limiter.check(request, "forgot-password", str(payload.email), limit=5, window=300)
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    if user and user.status != "disabled": send_action(db, user, PasswordResetToken)
    return generic_email_response()

def consume_token(db, model, raw):
    now = utcnow(); row = db.scalar(select(model).where(model.token_hash == token_hash(raw)).with_for_update())
    if model is EmailVerificationToken:
        if not row: raise HTTPException(400, "Verification link is invalid")
        if row.used_at: raise HTTPException(400, "Verification link has already been used or replaced. Request a new link.")
        if aware(row.expires_at) <= now: raise HTTPException(400, "Verification link has expired. Request a new link.")
    if not row or row.used_at or aware(row.expires_at) <= now: raise HTTPException(400, "Token is invalid or expired")
    result = db.execute(update(model).where(model.id == row.id, model.used_at.is_(None), model.expires_at > now).values(used_at=now).execution_options(synchronize_session=False))
    if result.rowcount != 1: raise HTTPException(400, "Token is invalid or expired")
    user = db.get(User, row.user_id)
    if not user or user.status == "disabled": raise HTTPException(400, "Token is invalid or expired")
    return user

@router.post("/reset-password")
def reset(payload: ResetInput, request: Request, db: Session = Depends(get_db)):
    limiter.check(request, "reset-password", limit=10, window=300)
    user = consume_token(db, PasswordResetToken, payload.token); user.password_hash = hash_password(payload.new_password); revoke_sessions(db, user.id); invalidate_tokens(db, user.id); db.commit()
    return {"message": "Password reset. You can sign in now."}

@router.post("/verify-email")
def verify_email(payload: TokenInput, request: Request, db: Session = Depends(get_db)):
    limiter.check(request, "verify-email", limit=10, window=300)
    user = consume_token(db, EmailVerificationToken, payload.token); user.email_verified_at = utcnow()
    if user.status == "pending_verification": user.status = "active"
    db.commit(); return {"message": "Email verified. You can sign in now."}

@router.post("/resend-verification")
def resend(payload: EmailInput, request: Request, db: Session = Depends(get_db)):
    limiter.check(request, "resend-verification", str(payload.email), limit=3, window=300)
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    if user and not user.email_verified_at and user.status != "disabled": send_action(db, user, EmailVerificationToken)
    return generic_email_response()

@router.post("/me/resend-verification")
def resend_own_verification(request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    limiter.check(request, "resend-verification", user.email, limit=3, window=300)
    if user.email_verified_at:
        return {"email_delivery": "already_verified", "message": "Email is already verified."}
    delivery = send_action(db, user, EmailVerificationToken)
    return {"email_delivery": delivery, "message": "Verification request processed."}

@router.get("/sessions")
def sessions(request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > utcnow()).order_by(UserSession.created_at.desc()))
    return [{"id": str(row.id), "device_name": row.device_name, "created_at": aware(row.created_at), "last_used_at": aware(row.last_used_at) if row.last_used_at else None, "current": row.id == request.state.session_id} for row in rows]

@router.delete("/sessions/{session_id}")
def revoke(session_id: uuid.UUID, request: Request, response: Response, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    row = db.get(UserSession, session_id)
    if not row or row.user_id != user.id: raise HTTPException(404, "Session not found")
    row.revoked_at = utcnow(); db.commit()
    if row.id == request.state.session_id: clear_cookie(response)
    return {"message": "Session revoked"}
