"""Integration checks restricted to an existing, disposable quality PostgreSQL DB.

Run with DATABASE_URL pointing to annotation_phase6_test_quality_* only. Does not
create/drop databases, touch the production storage mount, or print credentials.
"""
import io
import os
import secrets
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not (make_url(os.environ['DATABASE_URL']).database or '').startswith('annotation_phase6_test_quality_'):
    raise RuntimeError('Refusing a non-disposable quality database')
os.environ.update(STORAGE_PATH='/tmp/quality-integration', APP_ENV='test', EMAIL_PROVIDER='file', EMAIL_BACKEND='file',
                  JWT_SECRET_KEY=secrets.token_urlsafe(48), EMAIL_VERIFICATION_REQUIRED='false')
from alembic import command
from alembic.config import Config
command.upgrade(Config('alembic.ini'), 'head')
from fastapi.testclient import TestClient
from PIL import Image as PILImage
from app.main import app
from app.database import SessionLocal
from app.models import WorkspaceMember, ImageRevision, ReviewEvent, Annotation, Image
from sqlalchemy import select


def account(name):
    client = TestClient(app, headers={'Origin':'http://localhost:5173'})
    email = uuid.uuid4().hex + '@example.com'; password = secrets.token_urlsafe(24)
    result = client.post('/api/auth/register', json={'email':email, 'password':password, 'full_name':name})
    assert result.status_code == 201, result.text
    client.headers['Authorization'] = 'Bearer ' + client.post('/api/auth/login', json={'email':email,'password':password}).json()['access_token']
    return client, result.json()


owner, owner_user = account('Quality fixture owner')
actor, actor_user = account('Quality fixture annotator')
r1, r1_user = account('Quality fixture reviewer one')
r2, r2_user = account('Quality fixture reviewer two')
workspace = owner.post('/api/workspaces', json={'name':'Quality integration','slug':'quality-'+uuid.uuid4().hex}).json()
with SessionLocal() as db:
    for person, role in [(actor_user,'annotator'),(r1_user,'reviewer'),(r2_user,'reviewer')]:
        db.add(WorkspaceMember(workspace_id=uuid.UUID(workspace['id']),user_id=uuid.UUID(person['id']),role=role))
    db.commit()
project = owner.post('/api/projects',json={'name':'Quality integration','workspace_id':workspace['id']}).json()
label = owner.post(f'/api/projects/{project["id"]}/classes',json={'name':'Car'}).json()
buffer=io.BytesIO();PILImage.new('RGB',(100,80)).save(buffer,format='PNG')
image=owner.post(f'/api/projects/{project["id"]}/images',files={'files':('fixture.png',buffer.getvalue(),'image/png')}).json()[0]
url=f'/api/images/{image["id"]}'
annotation=actor.post(url+'/annotations',json={'class_id':label['id'],'x':5,'y':5,'width':20,'height':20}).json()


def versions(client):
    state=client.get(url+'/review').json()
    return {'expected_revision':state['revision'],'expected_review_version':state['review_version']}


def submit(client):
    rows=client.get(url+'/annotations').json()
    body={'items':[{key:row[key] for key in ['id','class_id','annotation_type','x','y','width','height','points']} for row in rows],
          'expected_versions':{str(row['id']):row['version'] for row in rows}}
    response=client.post(url+'/review/submit',json={**versions(client),'annotations':body})
    assert response.status_code==200,response.text


submit(actor)
body=versions(r1)
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(lambda client:client.post(url+'/review/approve',json=body).status_code,[r1,r2]))
assert sorted(results)==[200,409],results
with SessionLocal() as db:
    assert len(list(db.scalars(select(ReviewEvent).where(ReviewEvent.image_id==image['id'],ReviewEvent.action=='approved'))))==1
assert r1.post(url+'/review/reopen',json=versions(r1)).status_code==200
payload={'class_id':label['id'],'x':6,'y':5,'width':20,'height':20,'expected_version':1}
assert r1.put(f'/api/annotations/{annotation["id"]}',json=payload).status_code==200
submit(r1)
assert r1.post(url+'/review/approve',json=versions(r1)).status_code==403
assert r2.post(url+'/review/approve',json=versions(r2)).status_code==200
assert owner.patch(f'/api/projects/{project["id"]}/review-settings',json={'require_review':True}).status_code==200
assert owner.get(f'/api/projects/{project["id"]}/dataset/export-preview').json()['eligible']==1
assert owner.post(f'/api/projects/{project["id"]}/dataset/export/yolo').status_code==200
assert r2.post(url+'/review/reopen',json=versions(r2)).status_code==200
assert owner.get(f'/api/projects/{project["id"]}/dataset/export-preview').json()['eligible']==0
thread=actor.post(url+'/threads',json={'object_id':annotation['id'],'body':'Check this object.'}).json()
assert r1.post(f'/api/threads/{thread["id"]}/comments',json={'body':'Reviewed.'}).status_code==201
assert owner.delete(f'/api/images/{image["id"]}').status_code==200
with SessionLocal() as db:
    assert all(row.image_id is None for row in db.scalars(select(ImageRevision).where(ImageRevision.original_image_id==image['id'])))
print('PASS PostgreSQL quality: migration, atomic submit, concurrent review 200/409, no self approval, reopen/export gate, comments and retained history')
