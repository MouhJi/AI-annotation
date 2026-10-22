"""Inspect/recover one project quarantine after interrupted deletion. Dry-run default."""
import argparse
import os
import re
import shutil
from .database import SessionLocal
from .models import Project
from .services.image_service import STORAGE_PATH
from .services.project_delete_service import _project_folder

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quarantine',required=True,help='Exact project-ID-UUID directory basename')
    parser.add_argument('--apply',action='store_true');parser.add_argument('--confirm-quarantine')
    args=parser.parse_args()
    match=re.fullmatch(r'project-([1-9][0-9]*)-[a-f0-9]{32}',args.quarantine)
    if not match:parser.error('Invalid project quarantine name')
    source=STORAGE_PATH.resolve()/'.trash'/args.quarantine
    if (STORAGE_PATH.resolve()/'.trash').is_symlink() or source.is_symlink() or not source.resolve().is_relative_to(STORAGE_PATH.resolve()) or source.resolve().parent != (STORAGE_PATH.resolve()/'.trash').resolve() or not source.is_dir():parser.error('Unsafe or missing quarantine')
    project_id=int(match[1]);target=_project_folder(project_id)
    with SessionLocal() as db:
        exists=db.get(Project,project_id) is not None
        print('Proposed action:', 'restore project folder (DB row exists)' if exists else 'purge orphan quarantine (DB deletion committed)')
        if not args.apply:print('DRY RUN. No files changed.');return
        if args.confirm_quarantine!=args.quarantine:parser.error('Apply requires exact --confirm-quarantine')
        if exists:
            if target.exists():parser.error('Target already exists; refusing overwrite')
            target.parent.mkdir(parents=True,exist_ok=True);os.replace(source,target)
        else:shutil.rmtree(source)
        print('Applied quarantine recovery.')

if __name__=='__main__':main()
