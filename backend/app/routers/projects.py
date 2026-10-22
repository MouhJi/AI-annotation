from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from uuid import UUID
from ..database import get_db
from ..models import Image, LabelClass, Project, User
from ..auth_dependencies import get_active_user
from ..models import WorkspaceMember
from ..services.workspace_service import personal_workspace, require_workspace_permission, membership, workspace_operation, audit
from ..services.rbac import permissions
from ..schemas.project import ProjectCreate, ProjectOut
from ..services.project_delete_service import delete_project
router = APIRouter(prefix="/api/projects", tags=["projects"])

def serialize(p: Project, db: Session, user: User):
    return ProjectOut(id=p.id, name=p.name, description=p.description, annotation_mode=p.annotation_mode, created_at=p.created_at, updated_at=p.updated_at, workspace_id=p.workspace_id, permissions=permissions(membership(db,p.workspace_id,user).role),
      image_count=db.scalar(select(func.count(Image.id)).where(Image.project_id == p.id)) or 0,
      class_count=db.scalar(select(func.count(LabelClass.id)).where(LabelClass.project_id == p.id)) or 0)
@router.post("", response_model=ProjectOut, status_code=201)
def create(payload: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_active_user)):
    workspace_id = payload.workspace_id
    if workspace_id is None:
        workspace_id = personal_workspace(db, user).id
        db.commit()
    require_workspace_permission(db, workspace_id, user, "project.create")
    with workspace_operation(db, workspace_id):
        require_workspace_permission(db, workspace_id, user, "project.create")
        p=Project(**{**payload.model_dump(), "workspace_id":workspace_id}, owner_user_id=user.id)
        db.add(p); db.flush(); audit(db,workspace_id,user.id,"project.created","project",p.id)
        db.commit(); db.refresh(p); return serialize(p,db,user)
@router.get("", response_model=list[ProjectOut])
def list_projects(workspace_id: UUID | None = None, db: Session = Depends(get_db), user: User = Depends(get_active_user)):
    # Compatibility for older clients: aggregate only current memberships, never owner metadata.
    query=select(Project).join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id).where(WorkspaceMember.user_id == user.id)
    if workspace_id:
        require_workspace_permission(db,workspace_id,user,"project.read")
        query=query.where(Project.workspace_id == workspace_id)
    return [serialize(p,db,user) for p in db.scalars(query.order_by(Project.created_at.desc()))]
@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id:int, db: Session=Depends(get_db), user: User=Depends(get_active_user)):
    p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Project not found")
    return serialize(p,db,user)

@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id:int, payload: dict, db:Session=Depends(get_db), user:User=Depends(get_active_user)):
    # No project movement or owner mass assignment in this phase.
    if set(payload) - {"name", "description"}: raise HTTPException(422,"Only name and description can be updated")
    p=db.get(Project,project_id)
    if "name" in payload:
        if not isinstance(payload["name"],str) or not 1 <= len(payload["name"].strip()) <= 120: raise HTTPException(422,"Invalid project name")
        p.name=payload["name"].strip()
    if "description" in payload:
        if payload["description"] is not None and (not isinstance(payload["description"],str) or len(payload["description"]) > 5000): raise HTTPException(422,"Invalid description")
        p.description=payload["description"]
    audit(db,p.workspace_id,user.id,"project.updated","project",p.id,fields=sorted(payload))
    db.commit(); return serialize(p,db,user)

@router.delete("/{project_id}")
def delete(project_id: int, db: Session = Depends(get_db), user: User=Depends(get_active_user)):
    project = db.get(Project, project_id)
    if not project: raise HTTPException(404, "Project not found")
    audit(db,project.workspace_id,user.id,"project.deleted","project",project_id)
    result = delete_project(db, project)
    return {"success": True, "deleted_project_id": project_id, "cleanup_warnings": result["cleanup_warnings"]}
