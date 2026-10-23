import os
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .database import get_db
from sqlalchemy.orm import Session
from .auth_config import settings
from .auth_dependencies import get_active_user, require_resource_access, owned_project
from . import models
from .routers import projects, classes, images, annotations, dataset, auto_label, auth, workspaces

storage=Path(os.getenv("STORAGE_PATH","./storage")); storage.mkdir(parents=True,exist_ok=True)
(storage / "models").mkdir(exist_ok=True)
config = settings()
from .services.session_idle import policy
policy()
app=FastAPI(title="Annotation Platform API",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=config["origins"],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type"],expose_headers=["Content-Disposition"])
for router in (projects.router, classes.router, images.router, annotations.router, dataset.router, auto_label.router):
    app.include_router(router, dependencies=[Depends(require_resource_access)])
app.include_router(auth.router); app.include_router(auth.users_router)
app.include_router(workspaces.router)

@app.middleware("http")
async def response_security(request, call_next):
    response = await call_next(request)
    if response.status_code == 401 and request.url.path in {"/api/auth/refresh", "/api/auth/activity"}:
        auth.clear_cookie(response)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith(("/api", "/storage")): response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/storage/{relative:path}")
def protected_image(relative: str, user=Depends(get_active_user), db: Session=Depends(get_db)):
    parts = Path(relative).parts
    if len(parts) != 4 or parts[0] != "projects" or not parts[1].isdigit() or parts[2] != "images": raise HTTPException(404, "Image not found")
    owned_project(db, int(parts[1]), user)
    path = (storage / relative).resolve()
    project_images = (storage / "projects" / parts[1] / "images").resolve()
    if not project_images.is_relative_to(storage.resolve()) or not path.is_relative_to(project_images) or not path.is_file(): raise HTTPException(404, "Image not found")
    return FileResponse(path)
@app.get("/health")
def health(): return {"status":"ok"}
