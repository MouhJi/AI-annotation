"""Idempotent, operator-only legacy-to-personal-workspace mapping. Dry-run by default."""
import argparse
from contextlib import ExitStack
from sqlalchemy import select, update
from .database import SessionLocal
from .models import Project, User, Workspace
from .services.workspace_service import personal_workspace, audit, workspace_operation

def migrate(db, apply=False, project_ids=None):
    with ExitStack() as operations:
        return _migrate(db, apply, project_ids, operations)

def _migrate(db, apply, project_ids, operations):
    locked_workspaces = set()
    query = select(Project).where(Project.workspace_id.is_(None)).order_by(Project.id)
    if project_ids: query = query.where(Project.id.in_(project_ids))
    if apply: query = query.with_for_update()
    rows = list(db.scalars(query)); report = {"mapped": [], "locked": [], "already_mapped": []}
    if project_ids:
        found = {row.id for row in db.scalars(select(Project).where(Project.id.in_(project_ids)))}
        if found != set(project_ids): raise ValueError("Some selected project IDs do not exist")
        report["already_mapped"] = sorted(found - {row.id for row in rows})
    for row in rows:
        owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
        if not owner or owner.status != "active":
            report["locked"].append(row.id); continue
        workspace = db.scalar(select(Workspace).where(Workspace.personal_user_id == owner.id))
        if workspace:
            if apply and workspace.id not in locked_workspaces:
                operations.enter_context(workspace_operation(db, workspace.id))
                locked_workspaces.add(workspace.id)
            # Never backfill into a personal workspace whose original owner was removed.
            from .models import WorkspaceMember
            if not db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == owner.id, WorkspaceMember.role == "owner")):
                report["locked"].append(row.id); continue
        report["mapped"].append({"project_id": row.id, "name": row.name, "owner": owner.email, "workspace": str(workspace.id) if workspace else "new personal workspace"})
        if apply:
            workspace = workspace or personal_workspace(db, owner)
            # Backfill is not an edit: preserve the project's original timestamps too.
            db.execute(update(Project).where(Project.id == row.id).values(workspace_id=workspace.id, updated_at=row.updated_at))
            audit(db, workspace.id, owner.id, "project.workspace_migrated", "project", row.id)
    if apply: db.commit()
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-ids", type=int, nargs="+")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-project-ids", type=int, nargs="+")
    args=parser.parse_args()
    if args.apply and (not args.project_ids or set(args.confirm_project_ids or []) != set(args.project_ids)): parser.error("Apply requires explicit --project-ids and matching --confirm-project-ids")
    with SessionLocal() as db:
        result=migrate(db,args.apply,args.project_ids)
        print(result)
        print("APPLIED. IDs, owner metadata, images, classes and annotations unchanged." if args.apply else "DRY RUN. No data changed.")

if __name__ == "__main__": main()
