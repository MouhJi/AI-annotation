import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..auth_config import settings
from ..auth_dependencies import get_active_user
from ..database import get_db
from ..models import Workspace, WorkspaceMember, WorkspaceInvitation, AuditLog, User, Project, Image, Annotation
from ..models.auth import utcnow
from ..rate_limit import limiter
from ..schemas.workspace import WorkspaceCreate, WorkspaceUpdate, RoleInput, InviteInput, DeleteWorkspaceInput, AcceptInvitationInput
from ..services.auth_security import opaque_token, token_hash, aware
from ..services.email_service import prepare_delivery, deliver_email
from ..services.email_templates import action_email
from ..services.rbac import permissions, assignable_roles
from ..services.workspace_service import audit, membership, require_workspace_permission, normalize_slug, workspace_operation
from ..services.project_delete_service import delete_projects

router = APIRouter(prefix="/api", tags=["workspaces"])

def workspace_out(db, workspace, member):
    project_ids = select(Project.id).where(Project.workspace_id == workspace.id)
    image_ids = select(Image.id).where(Image.project_id.in_(project_ids))
    return {"id": workspace.id, "name": workspace.name, "slug": workspace.slug, "description": workspace.description,
            "created_by": workspace.created_by, "created_at": workspace.created_at, "updated_at": workspace.updated_at,
            "role": member.role, "permissions": permissions(member.role), "assignable_roles": assignable_roles(member.role),
            "project_count": db.scalar(select(func.count()).select_from(Project).where(Project.workspace_id == workspace.id)),
            "image_count": db.scalar(select(func.count()).select_from(Image).where(Image.project_id.in_(project_ids))),
            "annotation_count": db.scalar(select(func.count()).select_from(Annotation).where(Annotation.image_id.in_(image_ids))),
            "member_count": db.scalar(select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id))}

def invitation_out(row):
    return {"id": row.id, "email": row.email, "role": row.role, "expires_at": row.expires_at, "accepted_at": row.accepted_at, "declined_at": row.declined_at, "revoked_at": row.revoked_at, "created_at": row.created_at,
            "status": invitation_status(row)}

def invitation_status(row):
    return "accepted" if row.accepted_at else "declined" if row.declined_at else "revoked" if row.revoked_at else "expired" if aware(row.expires_at) <= utcnow() else "pending"

def send_invitation_email(db, invitation, raw_token, attempt):
    workspace = db.get(Workspace, invitation.workspace_id)
    subject, text_body, html_body = action_email("invitation", f"{settings()['frontend']}/invitations/accept#token={raw_token}", workspace=workspace.name)
    status = deliver_email(db, attempt, invitation.email, subject, text_body, html_body)
    return {"sent": "smtp", "development": "development_file", "failed": "failed"}[status]

def accept_row(db, row, user):
    """Atomically consume an invitation after caller proved it belongs to user."""
    unavailable = HTTPException(409, "Invitation is no longer available")
    with workspace_operation(db, row.workspace_id):
        row = db.get(WorkspaceInvitation, row.id)
        if not row or row.email != user.email or invitation_status(row) != "pending" or not db.get(Workspace, row.workspace_id):
            raise unavailable
        # If inviter lost authority, an old invitation must not grant a role they
        # could no longer assign.
        inviter = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == row.workspace_id, WorkspaceMember.user_id == row.invited_by))
        if not inviter or db.get(User, row.invited_by).status != "active" or row.role not in assignable_roles(inviter.role):
            raise unavailable
        if db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == row.workspace_id, WorkspaceMember.user_id == user.id)):
            raise HTTPException(409, "Already a workspace member")
        changed = db.execute(update(WorkspaceInvitation).where(
            WorkspaceInvitation.id == row.id,
            WorkspaceInvitation.accepted_at.is_(None), WorkspaceInvitation.declined_at.is_(None),
            WorkspaceInvitation.revoked_at.is_(None), WorkspaceInvitation.expires_at > utcnow(),
        ).values(accepted_at=utcnow()).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise unavailable
        db.add(WorkspaceMember(workspace_id=row.workspace_id, user_id=user.id, role=row.role, invited_by=row.invited_by))
        audit(db, row.workspace_id, user.id, "member.joined", "member", user.id, role=row.role, invitation_id=str(row.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Already a workspace member")
        return {"workspace_id": row.workspace_id, "message": "Invitation accepted"}

@router.post("/workspaces", status_code=201)
def create_workspace(payload: WorkspaceCreate, request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    limiter.check(request, "workspace-create", str(user.id), limit=20)
    workspace = Workspace(**{**payload.model_dump(), "slug": normalize_slug(payload.slug)}, created_by=user.id)
    try:
        db.add(workspace); db.flush()
        member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"); db.add(member)
        audit(db, workspace.id, user.id, "workspace.created", "workspace", workspace.id)
        db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Workspace slug is already in use")
    return workspace_out(db, workspace, member)

@router.get("/workspaces")
def list_workspaces(user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Workspace, WorkspaceMember).join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id).where(WorkspaceMember.user_id == user.id).order_by(Workspace.created_at))
    return [workspace_out(db, workspace, member) for workspace, member in rows]

@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: uuid.UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    member = require_workspace_permission(db, workspace_id, user, "workspace.read")
    return workspace_out(db, db.get(Workspace, workspace_id), member)

@router.patch("/workspaces/{workspace_id}")
def update_workspace(workspace_id: uuid.UUID, payload: WorkspaceUpdate, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.update")
    with workspace_operation(db, workspace_id):
        member = require_workspace_permission(db, workspace_id, user, "workspace.update")
        workspace = db.get(Workspace, workspace_id)
        changes = payload.model_dump(exclude_unset=True)
        if "slug" in changes: changes["slug"] = normalize_slug(changes["slug"])
        for key, value in changes.items(): setattr(workspace, key, value)
        audit(db, workspace_id, user.id, "workspace.updated", "workspace", workspace_id, fields=sorted(changes))
        try: db.commit()
        except IntegrityError:
            db.rollback(); raise HTTPException(409, "Workspace slug is already in use")
        return workspace_out(db, workspace, member)

@router.get("/workspaces/{workspace_id}/members")
def members(workspace_id: uuid.UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.members.read")
    return [{"user_id": row.user_id, "full_name": person.full_name, "email": person.email, "role": row.role, "joined_at": row.joined_at, "status": person.status}
            for row, person in db.execute(select(WorkspaceMember, User).join(User, User.id == WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == workspace_id).order_by(WorkspaceMember.joined_at))]

def manageable(actor, target, new_role=None):
    if actor.role == "admin" and (target.role in {"owner", "admin"} or new_role not in {None, "annotator", "reviewer", "viewer"}):
        raise HTTPException(403, "Admins may manage only annotators, reviewers and viewers")

def protect_last_owner(db, workspace_id, target):
    if target.role != "owner": return
    count = db.scalar(select(func.count()).select_from(WorkspaceMember).join(User, User.id == WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "owner", User.status == "active"))
    if count <= 1: raise HTTPException(409, "Cannot remove or downgrade the last active owner")

@router.patch("/workspaces/{workspace_id}/members/{user_id}")
def change_role(workspace_id: uuid.UUID, user_id: uuid.UUID, payload: RoleInput, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.members.manage")
    with workspace_operation(db, workspace_id):
        actor = require_workspace_permission(db, workspace_id, user, "workspace.members.manage")
        target = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id).with_for_update())
        if not target: raise HTTPException(404, "Member not found")
        manageable(actor, target, payload.role)
        if payload.role == "owner" and actor.role != "owner": raise HTTPException(403, "Only owners can grant ownership")
        if payload.role == "owner" and db.get(User, user_id).status != "active": raise HTTPException(409, "New owner must be active")
        if target.role == "owner" and payload.role != "owner": protect_last_owner(db, workspace_id, target)
        old = target.role; target.role = payload.role
        audit(db, workspace_id, user.id, "member.role_changed", "member", user_id, previous_role=old, role=payload.role)
        db.commit()
        return {"user_id": user_id, "role": payload.role}

@router.delete("/workspaces/{workspace_id}/members/{user_id}")
def remove_member(workspace_id: uuid.UUID, user_id: uuid.UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.members.manage")
    with workspace_operation(db, workspace_id):
        actor = require_workspace_permission(db, workspace_id, user, "workspace.members.manage")
        target = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id).with_for_update())
        if not target: raise HTTPException(404, "Member not found")
        manageable(actor, target); protect_last_owner(db, workspace_id, target)
        db.delete(target)
        # Outstanding invitations for a removed account cannot silently restore access.
        email = db.get(User, user_id).email
        db.execute(update(WorkspaceInvitation).where(WorkspaceInvitation.workspace_id == workspace_id, WorkspaceInvitation.email == email, WorkspaceInvitation.accepted_at.is_(None), WorkspaceInvitation.revoked_at.is_(None)).values(revoked_at=utcnow()))
        audit(db, workspace_id, user.id, "member.removed", "member", user_id); db.commit()
        return {"removed": True}

@router.post("/workspaces/{workspace_id}/invitations", status_code=201)
def invite(workspace_id: uuid.UUID, payload: InviteInput, request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.members.invite")
    limiter.check(request, "workspace-invite", str(user.id), limit=20)
    with workspace_operation(db, workspace_id):
        actor = require_workspace_permission(db, workspace_id, user, "workspace.members.invite")
        if payload.role not in assignable_roles(actor.role): raise HTTPException(403, "Cannot invite this role")
        email = str(payload.email)
        existing = db.scalar(select(User).where(User.email == email))
        if existing and db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == existing.id)): raise HTTPException(409, "User is already a member")
        now = utcnow()
        db.execute(update(WorkspaceInvitation).where(WorkspaceInvitation.workspace_id == workspace_id, WorkspaceInvitation.email == email, WorkspaceInvitation.accepted_at.is_(None), WorkspaceInvitation.revoked_at.is_(None), WorkspaceInvitation.expires_at <= now).values(revoked_at=now).execution_options(synchronize_session=False))
        raw = opaque_token()
        invitation = WorkspaceInvitation(workspace_id=workspace_id, email=email, role=payload.role, token_hash=token_hash(raw), invited_by=user.id, expires_at=now+timedelta(days=7))
        db.add(invitation)
        audit(db, workspace_id, user.id, "member.invited", "workspace", workspace_id, role=payload.role)
        try:
            db.flush()
            attempt = prepare_delivery(db, "invitation", invitation.id)
            db.commit()
        except IntegrityError:
            db.rollback(); raise HTTPException(409, "A pending invitation already exists for this email")
        return {**invitation_out(invitation), "in_app": bool(existing), "delivery": send_invitation_email(db, invitation, raw, attempt)}

@router.get("/workspaces/{workspace_id}/invitations")
def invitations(workspace_id: uuid.UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.members.invite")
    return [invitation_out(row) for row in db.scalars(select(WorkspaceInvitation).where(WorkspaceInvitation.workspace_id == workspace_id).order_by(WorkspaceInvitation.created_at.desc()).limit(200))]

@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}")
def revoke_invitation(workspace_id: uuid.UUID, invitation_id: uuid.UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.members.invite")
    with workspace_operation(db, workspace_id):
        actor = require_workspace_permission(db, workspace_id, user, "workspace.members.invite")
        row = db.get(WorkspaceInvitation, invitation_id)
        if not row or row.workspace_id != workspace_id: raise HTTPException(404, "Invitation not found")
        if actor.role == "admin" and row.role in {"owner", "admin"}: raise HTTPException(403, "Cannot revoke this invitation")
        if row.accepted_at: raise HTTPException(409, "Invitation already accepted")
        row.revoked_at = utcnow(); audit(db, workspace_id, user.id, "invitation.revoked", "invitation", row.id); db.commit()
        return {"revoked": True}

@router.post("/workspaces/{workspace_id}/invitations/{invitation_id}/resend")
def resend_invitation(workspace_id: uuid.UUID, invitation_id: uuid.UUID, request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    limiter.check(request, "workspace-invite-resend", str(user.id), limit=3, window=300)
    require_workspace_permission(db, workspace_id, user, "workspace.members.invite")
    with workspace_operation(db, workspace_id):
        actor = require_workspace_permission(db, workspace_id, user, "workspace.members.invite")
        row = db.get(WorkspaceInvitation, invitation_id)
        if not row or row.workspace_id != workspace_id: raise HTTPException(404, "Invitation not found")
        if actor.role == "admin" and row.role in {"owner", "admin"}: raise HTTPException(403, "Cannot resend this invitation")
        if invitation_status(row) != "pending": raise HTTPException(409, "Only pending invitations can be resent")
        raw = opaque_token(); row.token_hash = token_hash(raw); row.expires_at = utcnow() + timedelta(days=7)
        audit(db, workspace_id, user.id, "invitation.resent", "invitation", row.id)
        attempt = prepare_delivery(db, "invitation", row.id)
        db.commit()
        return {**invitation_out(row), "delivery": send_invitation_email(db, row, raw, attempt)}

@router.get("/me/invitations")
def my_invitations(user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    if not user.email_verified_at: raise HTTPException(403, "Verify your email before viewing invitations")
    rows = db.execute(select(WorkspaceInvitation, Workspace, User).join(Workspace, Workspace.id == WorkspaceInvitation.workspace_id).join(User, User.id == WorkspaceInvitation.invited_by).where(
        WorkspaceInvitation.email == user.email, WorkspaceInvitation.accepted_at.is_(None),
        WorkspaceInvitation.declined_at.is_(None), WorkspaceInvitation.revoked_at.is_(None),
        WorkspaceInvitation.expires_at > utcnow(),
    ).order_by(WorkspaceInvitation.created_at.desc())).all()
    return [{"invitation_id": row.id, "workspace_id": workspace.id, "workspace_name": workspace.name,
             "invited_role": row.role, "invited_by_name": inviter.full_name, "created_at": row.created_at,
             "expires_at": row.expires_at, "status": "pending"} for row, workspace, inviter in rows]

@router.post("/me/invitations/{invitation_id}/accept")
def accept_my_invitation(invitation_id: uuid.UUID, request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    limiter.check(request, "invitation-accept", str(user.id), limit=20)
    if not user.email_verified_at: raise HTTPException(403, "Verify your email before accepting an invitation")
    row = db.get(WorkspaceInvitation, invitation_id)
    if not row or row.email != user.email: raise HTTPException(404, "Invitation not found")
    return accept_row(db, row, user)

@router.post("/me/invitations/{invitation_id}/decline")
def decline_my_invitation(invitation_id: uuid.UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    if not user.email_verified_at: raise HTTPException(403, "Verify your email before declining an invitation")
    row = db.get(WorkspaceInvitation, invitation_id)
    if not row or row.email != user.email: raise HTTPException(404, "Invitation not found")
    with workspace_operation(db, row.workspace_id):
        row = db.get(WorkspaceInvitation, invitation_id)
        if not row or row.email != user.email: raise HTTPException(404, "Invitation not found")
        if invitation_status(row) != "pending": raise HTTPException(409, "Invitation is no longer available")
        changed = db.execute(update(WorkspaceInvitation).where(
            WorkspaceInvitation.id == row.id, WorkspaceInvitation.accepted_at.is_(None),
            WorkspaceInvitation.declined_at.is_(None), WorkspaceInvitation.revoked_at.is_(None),
            WorkspaceInvitation.expires_at > utcnow(),
        ).values(declined_at=utcnow()).execution_options(synchronize_session=False))
        if changed.rowcount != 1: raise HTTPException(409, "Invitation is no longer available")
        audit(db, row.workspace_id, user.id, "invitation.declined", "invitation", row.id)
        db.commit()
    return {"declined": True}

@router.post("/invitations/accept")
def accept_invitation(payload: AcceptInvitationInput, request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    limiter.check(request, "invitation-accept", str(user.id), limit=20)
    if not user.email_verified_at: raise HTTPException(403, "Verify your email before accepting an invitation")
    row = db.scalar(select(WorkspaceInvitation).where(WorkspaceInvitation.token_hash == token_hash(payload.token)))
    invalid = HTTPException(400, "Invitation is invalid, unavailable or expired")
    if not row or row.email != user.email: raise invalid
    try:
        return accept_row(db, row, user)
    except HTTPException as error:
        if error.status_code == 409 and error.detail != "Already a workspace member": raise invalid
        raise

@router.get("/workspaces/{workspace_id}/audit-logs")
def audit_logs(workspace_id: uuid.UUID, limit: int = 50, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.audit.read")
    rows = db.scalars(select(AuditLog).where(AuditLog.workspace_id == workspace_id).order_by(AuditLog.created_at.desc()).limit(max(1, min(limit, 200))))
    return [{"id": row.id, "actor_user_id": row.actor_user_id, "action": row.action, "resource_type": row.resource_type, "resource_id": row.resource_id, "metadata": row.details, "created_at": row.created_at} for row in rows]

@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: uuid.UUID, payload: DeleteWorkspaceInput, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    require_workspace_permission(db, workspace_id, user, "workspace.delete")
    with workspace_operation(db, workspace_id):
        require_workspace_permission(db, workspace_id, user, "workspace.delete")
        workspace = db.get(Workspace, workspace_id)
        if payload.confirmation != workspace.name: raise HTTPException(400, "Type the exact workspace name to confirm deletion")
        projects = list(db.scalars(select(Project).where(Project.workspace_id == workspace_id)))
        audit(db, workspace_id, user.id, "workspace.deleted", "workspace", workspace_id, project_count=len(projects))
        def final_rows():
            db.execute(delete(WorkspaceInvitation).where(WorkspaceInvitation.workspace_id == workspace_id))
            db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
            db.execute(delete(Workspace).where(Workspace.id == workspace_id))
        result = delete_projects(db, projects, before_commit=final_rows)
        return {"deleted": True, "deleted_project_count": len(projects), **result}
