import uuid
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
import jwt
from .database import get_db
from .models import User, UserSession, Project, Image, Annotation, LabelClass, AutoLabelPrediction
from .models.auth import utcnow
from .models import CommentThread
from .services.auth_security import decode_access, aware
from .services.workspace_service import require_workspace_permission, workspace_operation

bearer = HTTPBearer(auto_error=False)
def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    error = HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    if not credentials: raise error
    try:
        claims = decode_access(credentials.credentials)
        user = db.get(User, uuid.UUID(claims["sub"]))
        session = db.get(UserSession, uuid.UUID(claims["sid"]))
    except (jwt.InvalidTokenError, ValueError, KeyError): raise error
    if not user or not session or session.user_id != user.id or session.revoked_at or aware(session.expires_at) <= utcnow(): raise error
    from .services.session_idle import enforce_idle
    enforce_idle(db, session)
    request.state.session_id = session.id
    return user

def get_active_user(user: User = Depends(get_current_user)) -> User:
    if user.status != "active": raise HTTPException(403, "Account is not active")
    return user

require_authenticated_user = get_active_user

def owned_project(db: Session, project_id: int, user: User) -> Project:
    return require_project_permission(db, project_id, user, "project.read")

def require_project_permission(db, project_id, user, permission):
    project = db.get(Project, project_id, populate_existing=True)
    if not project or project.workspace_id is None: raise HTTPException(404, "Project not found")
    require_workspace_permission(db, project.workspace_id, user, permission)
    return project

def require_image_permission(db, image_id, user, permission):
    image = db.get(Image, image_id)
    if not image: raise HTTPException(404, "Image not found")
    require_project_permission(db, image.project_id, user, permission)
    return image

def require_annotation_permission(db, annotation_id, user, permission):
    annotation = db.get(Annotation, annotation_id)
    if not annotation: raise HTTPException(404, "Annotation not found")
    require_image_permission(db, annotation.image_id, user, permission)
    return annotation

# Explicit route-template registry: adding a new mutation without policy is denied.
RESOURCE_PERMISSIONS = {
    ("GET", "/api/images/{image_id}/review"): "review.read",
    ("GET", "/api/images/{image_id}/revisions/{revision}"): "review.read",
    ("POST", "/api/images/{image_id}/review/submit"): "review.submit",
    ("POST", "/api/images/{image_id}/review/withdraw"): "review.submit",
    ("POST", "/api/images/{image_id}/review/approve"): "review.approve",
    ("POST", "/api/images/{image_id}/review/reject"): "review.reject",
    ("POST", "/api/images/{image_id}/review/reopen"): "review.reopen",
    ("GET", "/api/projects/{project_id}/review-queue"): "review.read",
    ("PATCH", "/api/projects/{project_id}/review-settings"): "project.review_settings.manage",
    ("GET", "/api/images/{image_id}/threads"): "comment.read",
    ("POST", "/api/images/{image_id}/threads"): "comment.create",
    ("POST", "/api/threads/{thread_id}/comments"): "comment.create",
    ("PATCH", "/api/threads/{thread_id}"): "comment.resolve",
    ("POST", "/api/images/{image_id}/activity"): "activity.record",
    ("GET", "/api/projects/{project_id}/quality"): "quality.read",
    ("GET", "/api/projects/{project_id}/dataset/export-preview"): "dataset.read",
    ("GET", "/api/projects/{project_id}"): "project.read",
    ("GET", "/api/projects/{project_id}/images"): "image.read",
    ("GET", "/api/images/{image_id}"): "image.read",
    ("GET", "/api/projects/{project_id}/classes"): "class.read",
    ("GET", "/api/images/{image_id}/annotations"): "annotation.read",
    ("GET", "/api/projects/{project_id}/class-mappings"): "class.read",
    ("GET", "/api/images/{image_id}/predictions"): "prediction.read",
    ("GET", "/api/projects/{project_id}/dataset/split"): "dataset.read",
    ("POST", "/api/projects/{project_id}/images"): "image.upload",
    ("DELETE", "/api/images/{image_id}"): "image.delete",
    ("POST", "/api/images/bulk-delete"): "image.delete",
    ("POST", "/api/projects/{project_id}/classes"): "class.create",
    ("PUT", "/api/classes/{class_id}"): "class.update",
    ("DELETE", "/api/classes/{class_id}"): "class.delete",
    ("POST", "/api/images/{image_id}/annotations"): "annotation.create",
    ("PUT", "/api/annotations/{annotation_id}"): "annotation.update",
    ("PUT", "/api/images/{image_id}/annotations"): "annotation.update",
    ("DELETE", "/api/annotations/{annotation_id}"): "annotation.delete",
    ("DELETE", "/api/images/{image_id}/annotations"): "annotation.delete",
    ("DELETE", "/api/projects/{project_id}"): "project.delete",
    ("PATCH", "/api/projects/{project_id}"): "project.update",
    ("PUT", "/api/projects/{project_id}/dataset/split"): "dataset.split",
    ("POST", "/api/projects/{project_id}/dataset/export/yolo"): "dataset.export",
    ("PUT", "/api/projects/{project_id}/class-mappings"): "class.mapping",
    ("POST", "/api/images/{image_id}/auto-label"): "prediction.run",
    ("POST", "/api/images/{image_id}/auto-segment"): "prediction.run",
    ("POST", "/api/projects/{project_id}/auto-label-batch"): "prediction.run",
    ("POST", "/api/projects/{project_id}/auto-segment-batch"): "prediction.run",
    ("PUT", "/api/predictions/{prediction_id}"): "prediction.review",
    ("POST", "/api/predictions/{prediction_id}/accept"): "prediction.review",
    ("POST", "/api/predictions/{prediction_id}/reject"): "prediction.review",
    ("POST", "/api/images/{image_id}/predictions/accept-all"): "prediction.review",
    ("POST", "/api/images/{image_id}/predictions/reject-all"): "prediction.review",
}

async def require_resource_access(request: Request, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    """Resolve IDs through the DB, then authorize. JWT never contains tenant roles."""
    params = request.path_params
    template = request.scope["route"].path
    if template == "/api/projects":
        yield  # Collection handlers validate the selected workspace explicitly.
        return
    permission = RESOURCE_PERMISSIONS.get((request.method, template))
    if not permission: raise HTTPException(403, "Operation has no permission policy")
    project = None
    if "project_id" in params: project = require_project_permission(db, int(params["project_id"]), user, permission)
    if "thread_id" in params:
        thread = db.get(CommentThread, int(params["thread_id"]))
        if not thread or thread.image_id is None: raise HTTPException(404, "Thread not found")
        image = require_image_permission(db, thread.image_id, user, permission)
        project = image.project
    for key, model in [("image_id", Image), ("annotation_id", Annotation), ("class_id", LabelClass), ("prediction_id", AutoLabelPrediction)]:
        if key not in params: continue
        row = db.get(model, int(params[key]))
        if row is None: raise HTTPException(404, "Resource not found")
        project_id = row.project_id if model in (Image, LabelClass) else row.image.project_id
        project = require_project_permission(db, project_id, user, permission)
    if request.url.path.endswith("/images/bulk-delete"):
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("project_id"), int): raise HTTPException(422, "project_id required")
        project = require_project_permission(db, payload["project_id"], user, permission)
    if not project: raise HTTPException(403, "No project access policy")
    request.state.actor_id = user.id
    request.state.workspace_id = project.workspace_id
    if request.method == "GET":
        yield
    else:
        with workspace_operation(db, project.workspace_id):
            # Re-read after acquiring the cross-worker lock. Permission removal/deletion
            # and inference/save cannot pass each other even across service commits.
            require_project_permission(db, project.id, user, permission)
            yield
