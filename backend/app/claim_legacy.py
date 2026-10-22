"""Explicit operator-only legacy assignment. Dry-run unless --apply --confirm-email match."""
import argparse
from sqlalchemy import select
from .database import SessionLocal
from .models import Project, User

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--project-ids", type=int, nargs="+")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-email")
    args = parser.parse_args(); email = args.email.strip().casefold()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if not user or user.status != "active": parser.error("An active registered owner is required")
        query = select(Project).where(Project.owner_user_id.is_(None)).with_for_update()
        if args.project_ids: query = query.where(Project.id.in_(args.project_ids))
        projects = list(db.scalars(query))
        print(f"Unclaimed projects selected: {len(projects)}")
        for project in projects: print(f"  {project.id}: {project.name}")
        print(f"Proposed owner: {email}")
        if not args.apply: print("DRY RUN. No ownership changed."); return
        if not args.project_ids or args.confirm_email != email: parser.error("Apply requires explicit --project-ids and --confirm-email matching --email")
        if {row.id for row in projects} != set(args.project_ids): parser.error("Some selected projects are missing or already claimed; no changes applied")
        for project in projects: project.owner_user_id = user.id
        db.commit(); print(f"Assigned {len(projects)} projects. Annotation and image data preserved.")

if __name__ == "__main__": main()
