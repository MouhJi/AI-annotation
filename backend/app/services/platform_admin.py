import uuid
from fastapi import Depends, HTTPException
from sqlalchemy import select, func
from ..auth_dependencies import get_active_user
from ..models import User
from .auth_security import aware
from .workspace_service import workspace_operation, audit

# One cross-worker lock shared by CLI privilege changes and account mutations.
ADMIN_LOCK_ID=uuid.UUID("3ce2c095-0555-401d-8308-8ef93d6b3db1")

def require_platform_admin(user=Depends(get_active_user)):
    if not user or user.status != "active" or not user.is_platform_admin or user.email_verified_at is None:
        raise HTTPException(403,"Platform administrator access required")
    return user

def admin_operation(db): return workspace_operation(db, ADMIN_LOCK_ID)

def usable_admins(db):
    return db.scalar(select(func.count()).select_from(User).where(User.is_platform_admin.is_(True),User.status=="active",User.email_verified_at.is_not(None))) or 0

def protect_last_admin(db,user):
    if user.is_platform_admin and user.status=="active" and user.email_verified_at and usable_admins(db)<=1:
        raise HTTPException(409,"Cannot remove or disable the last active verified platform administrator")

def change_platform_role(db,email,grant,apply=False):
    with admin_operation(db):
        user=db.scalar(select(User).where(User.email==email).execution_options(populate_existing=True))
        if not user: raise ValueError("User must already exist")
        if grant and (user.status!="active" or user.email_verified_at is None):
            raise ValueError("Grant requires an active user with a verified email")
        if user.is_platform_admin==grant: return {"user_id":str(user.id),"changed":False,"applied":False}
        if not grant: protect_last_admin(db,user)
        if apply:
            user.is_platform_admin=grant
            audit(db,None,None,"platform_admin.granted" if grant else "platform_admin.revoked","user",user.id,origin="backend_cli")
            db.commit()
        return {"user_id":str(user.id),"changed":True,"applied":apply}

def safe_audit(row):
    # Existing correction logs contain geometry: never expose it through admin metadata APIs.
    allowed={"role","previous_role","status","previous_status","count","origin","personal","fields"}
    details={key:value for key,value in (row.details or {}).items() if key in allowed and isinstance(value,(str,int,bool,type(None),list))}
    for side in ("before","after"):
        value=(row.details or {}).get(side)
        if isinstance(value,dict):details[side]={k:v for k,v in value.items() if k in {"version","source"} and isinstance(v,(str,int))}
    return {"id":row.id,"actor_user_id":row.actor_user_id,"action":row.action,"resource_type":row.resource_type,
            "resource_id":row.resource_id,"workspace_id":row.workspace_id,"created_at":aware(row.created_at),"details":details}
