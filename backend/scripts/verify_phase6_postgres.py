"""Destructive fixtures ONLY in an empty annotation_phase6_test_* PostgreSQL DB.

Run inside a disposable backend container with no real storage mount. Never drops DBs.
"""
import io
import os
import sys
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config

url=os.environ['DATABASE_URL']
if not (make_url(url).database or '').startswith('annotation_phase6_test_'): raise RuntimeError('Refusing non-disposable database')
os.environ.update(STORAGE_PATH='/tmp/annotation-phase6-test',APP_ENV='test',EMAIL_PROVIDER='file',EMAIL_BACKEND='file',JWT_SECRET_KEY=__import__('secrets').token_urlsafe(48))
config=Config('alembic.ini'); command.upgrade(config,'0002_auth')
engine=create_engine(url)
with engine.begin() as connection:
    owner_id=uuid.uuid4()
    connection.execute(text("INSERT INTO users(id,email,password_hash,full_name,status,created_at,updated_at) VALUES(:id,'legacy@example.com','unused','Legacy owner','active',NOW(),NOW())"),{'id':owner_id})
    connection.execute(text("INSERT INTO projects(id,name,owner_user_id,created_at,updated_at,annotation_mode) VALUES(9000,'Legacy masks',:owner,NOW(),NOW(),'instance_segmentation'),(9001,'Orphan',NULL,NOW(),NOW(),'object_detection')"),{'owner':owner_id})
    connection.execute(text("INSERT INTO classes(id,project_id,name,created_at) VALUES(9000,9000,'dog',NOW())"))
    connection.execute(text("INSERT INTO images(id,project_id,filename,filepath,width,height,created_at,split) VALUES(9000,9000,'legacy.png','/legacy/keep.png',100,80,NOW(),'train')"))
    connection.execute(text("INSERT INTO annotations(id,image_id,class_id,x,y,width,height,annotation_type,points_json,created_at,updated_at) VALUES(9000,9000,9000,1,1,20,20,'polygon','[[1,1],[21,1],[1,21]]',NOW(),NOW())"))
    snapshot=connection.execute(text('SELECT id,image_id,class_id,x,y,width,height,annotation_type,points_json FROM annotations')).all()
command.upgrade(config,'head');command.upgrade(config,'head')
from app.database import SessionLocal
from app.migrate_workspaces import migrate
with SessionLocal() as db:
    assert migrate(db,False,[9000,9001])['locked']==[9001]
    assert db.execute(text('SELECT workspace_id FROM projects WHERE id=9000')).scalar() is None
    first=migrate(db,True,[9000,9001]);assert len(first['mapped'])==1
    assert migrate(db,True,[9000,9001])['already_mapped']==[9000]
    assert db.execute(text('SELECT id,image_id,class_id,x,y,width,height,annotation_type,points_json FROM annotations')).all()==snapshot
print('PASS populated PostgreSQL migration + explicit dry-run/backfill/idempotence + orphan isolation')

from fastapi.testclient import TestClient
from PIL import Image as PillowImage
from app.main import app
from app.models import User,WorkspaceMember,WorkspaceInvitation
from app.models.auth import utcnow
from app.services.auto_label_service import yolo_service
from app.services.auth_security import token_hash

def account():
    client=TestClient(app,headers={'Origin':'http://localhost:5173'});email=uuid.uuid4().hex+'@example.com';password=uuid.uuid4().hex+'password'
    user=client.post('/api/auth/register',json={'email':email,'password':password,'full_name':'PG tester'}).json()
    login=client.post('/api/auth/login',json={'email':email,'password':password});assert login.status_code==200,login.text
    client.headers['Authorization']='Bearer '+login.json()['access_token']
    with SessionLocal() as db:
        db.get(User,uuid.UUID(user['id'])).email_verified_at=utcnow();db.commit()
    return client,user
owner,owner_user=account();other,other_user=account();third,third_user=account()
workspace=owner.post('/api/workspaces',json={'name':'Concurrent PG team','slug':'pg-'+uuid.uuid4().hex}).json();wid=workspace['id']
base=f'/api/workspaces/{wid}'
with SessionLocal() as db:
    db.add(WorkspaceMember(workspace_id=uuid.UUID(wid),user_id=uuid.UUID(other_user['id']),role='owner'));db.commit()

def demote(client,user_id):return client.patch(f'{base}/members/{user_id}',json={'role':'viewer'}).status_code
with ThreadPoolExecutor(max_workers=2) as executor:
    results=[executor.submit(demote,owner,owner_user['id']),executor.submit(demote,other,other_user['id'])]
    statuses=[future.result() for future in results]
assert statuses.count(200)==1 and all(status in {200,409} for status in statuses),statuses
with SessionLocal() as db:
    owners=list(db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id==uuid.UUID(wid),WorkspaceMember.role=='owner')))
    assert len(owners)==1
    survivor=owner if str(owners[0].user_id)==owner_user['id'] else other
print('PASS PostgreSQL concurrent owner demotion preserves at least one active owner')

def invite():return survivor.post(base+'/invitations',json={'email':third_user['email'],'role':'annotator'}).status_code
with ThreadPoolExecutor(max_workers=2) as executor: statuses=list(executor.map(lambda _:invite(),range(2)))
assert statuses.count(201)==1 and all(status in {201,409} for status in statuses),statuses
from email import message_from_string, policy
raw=None
for path in (Path(os.environ['STORAGE_PATH'])/'.emails').glob('*.eml'):
    msg=message_from_string(path.read_text(),policy=policy.default);body=msg.get_body(preferencelist=('plain',)).get_content()
    if msg['To']==third_user['email'] and '/invitations/accept#token=' in body:raw=body.split('#token=')[1].split()[0]
assert raw
def accept():return third.post('/api/invitations/accept',json={'token':raw}).status_code
with ThreadPoolExecutor(max_workers=2) as executor: statuses=list(executor.map(lambda _:accept(),range(2)))
assert statuses.count(200)==1 and all(status in {200,400,409} for status in statuses),statuses
with SessionLocal() as db:
    assert len(list(db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id==uuid.UUID(wid),WorkspaceMember.user_id==uuid.UUID(third_user['id'])))))==1
print('PASS PostgreSQL concurrent invite uniqueness and single-use atomic acceptance')

project=survivor.post('/api/projects',json={'name':'Live AI masks','workspace_id':wid,'annotation_mode':'instance_segmentation'}).json();pid=project['id']
buffer=io.BytesIO();PillowImage.new('RGB',(100,80)).save(buffer,format='PNG')
image=survivor.post(f'/api/projects/{pid}/images',files={'files':('mask.png',buffer.getvalue(),'image/png')}).json()[0];iid=image['id']
started,release=Event(),Event()
original=yolo_service.infer_segmentation
def infer(*_):
    started.set();assert release.wait(20)
    return 'mock-seg.pt',[{'model_class_id':7,'model_class_name':'new dog','x':1,'y':1,'width':40,'height':39,'points':[[1,1],[41,1],[20,40]],'confidence':.9}]
yolo_service.infer_segmentation=infer
try:
    with ThreadPoolExecutor(max_workers=2) as executor:
        running=executor.submit(third.post,f'/api/images/{iid}/auto-segment',json={})
        assert started.wait(10)
        assert survivor.request('DELETE',base,json={'confirmation':workspace['name']}).status_code==409
        assert survivor.delete(f'{base}/members/{third_user["id"]}').status_code==409
        release.set();result=running.result();assert result.status_code==200,result.text
finally:
    release.set();yolo_service.infer_segmentation=original
prediction=result.json()['predictions'][0]
assert third.post(f'/api/predictions/{prediction["id"]}/accept').status_code==200
assert third.post(f'/api/projects/{pid}/dataset/export/yolo').status_code==403
assert survivor.post(f'/api/projects/{pid}/dataset/export/yolo').status_code==200
assert survivor.delete(f'{base}/members/{third_user["id"]}').status_code==200
assert third.get(image['image_url']).status_code==404
assert third.get(f'/api/images/{iid}').status_code==404
assert third.delete(f'/api/images/{iid}/annotations').status_code==404
assert survivor.request('DELETE',base,json={'confirmation':workspace['name']}).status_code==200
assert survivor.get(f'/api/projects/{pid}').status_code==404
with engine.connect() as connection:
    assert connection.execute(text('SELECT id,image_id,class_id,x,y,width,height,annotation_type,points_json FROM annotations WHERE id=9000')).all()==snapshot
print('PASS live synchronous AI tenant lock, segmentation accept, export RBAC, stale JWT membership, workspace cascade cleanup')
print('All Phase 6 PostgreSQL checks passed. Disposable database retained; real app DB/storage untouched.')
