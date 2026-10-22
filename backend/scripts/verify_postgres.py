"""Smoke test against a disposable PostgreSQL database ONLY, never the app DB.

DATABASE_URL must end in annotation_phase5_test_<suffix>. No database is dropped.
"""
import io
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command

url=os.environ['DATABASE_URL']
if not (make_url(url).database or '').startswith('annotation_phase5_test_'):
    raise RuntimeError('Refusing to test against a non-disposable database')
os.environ['STORAGE_PATH']='/tmp/annotation-phase5-smoke'
os.environ['EMAIL_BACKEND']='file'
os.environ['APP_ENV']='test'
os.environ['JWT_SECRET_KEY']=__import__('secrets').token_urlsafe(48)
config=Config('alembic.ini')
command.upgrade(config,'0001_legacy')
engine=create_engine(url)
with engine.begin() as connection:
    connection.execute(text("INSERT INTO projects(id,name,created_at,updated_at,annotation_mode) VALUES(9000,'Legacy preserved',NOW(),NOW(),'instance_segmentation')"))
    connection.execute(text("INSERT INTO classes(id,project_id,name,created_at) VALUES(9000,9000,'fox',NOW())"))
    connection.execute(text("INSERT INTO images(id,project_id,filename,filepath,width,height,created_at) VALUES(9000,9000,'legacy.png','/legacy/preserved.png',100,100,NOW())"))
    connection.execute(text("INSERT INTO annotations(id,image_id,class_id,x,y,width,height,annotation_type,points_json,created_at,updated_at) VALUES(9000,9000,9000,1,1,20,20,'polygon','[[1,1],[21,1],[1,21]]',NOW(),NOW())"))
    snapshot=connection.execute(text('SELECT * FROM annotations')).all()
    # Simulate the real unversioned Phase 4 DB before running the inspected baseline.
    connection.execute(text('DROP TABLE alembic_version'))
command.upgrade(config,'head')
command.upgrade(config,'head')
with engine.connect() as connection:
    assert connection.execute(text('SELECT * FROM annotations')).all()==snapshot
    assert connection.execute(text('SELECT owner_user_id FROM projects WHERE id=9000')).scalar() is None
print('PASS PostgreSQL populated unversioned baseline; rows unchanged and legacy unclaimed')

from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
ORIGIN={'Origin':'http://localhost:5173'}
password='test passphrase generated '+uuid.uuid4().hex
def register(email):
    with TestClient(app,headers=ORIGIN) as client:
        return client.post('/api/auth/register',json={'email':email,'password':password,'full_name':'Smoke User'}).status_code
email=uuid.uuid4().hex+'@example.com'
with ThreadPoolExecutor(max_workers=2) as executor:
    statuses=list(executor.map(register,[email,email]))
assert sorted(statuses)==[201,409],statuses
print('PASS concurrent PostgreSQL duplicate registration constraint')
owner=TestClient(app,headers=ORIGIN); other=TestClient(app,headers=ORIGIN)
login=owner.post('/api/auth/login',json={'email':email,'password':password}); assert login.status_code==200
access=login.json()['access_token']; owner.headers['Authorization']='Bearer '+access
register('other-'+email); other_login=other.post('/api/auth/login',json={'email':'other-'+email,'password':password}); other.headers['Authorization']='Bearer '+other_login.json()['access_token']
project=owner.post('/api/projects',json={'name':'Owned smoke project','annotation_mode':'instance_segmentation'}).json(); pid=project['id']
assert owner.get('/api/projects/9000').status_code==404
assert other.get(f'/api/projects/{pid}').status_code==404
label=owner.post(f'/api/projects/{pid}/classes',json={'name':'fox'}).json()
buffer=io.BytesIO(); Image.new('RGB',(100,80)).save(buffer,format='PNG')
image=owner.post(f'/api/projects/{pid}/images',files={'files':('smoke.png',buffer.getvalue(),'image/png')}).json()[0]
annotation=owner.post(f'/api/images/{image["id"]}/annotations',json={'class_id':label['id'],'annotation_type':'polygon','points':[[10,10],[50,10],[35,40]]}); assert annotation.status_code==201,annotation.text
assert owner.get(image['image_url']).status_code==200
assert other.get(image['image_url']).status_code==404
assert other.delete(f'/api/annotations/{annotation.json()["id"]}').status_code==404
assert owner.post(f'/api/projects/{pid}/dataset/export/yolo').status_code==200
print('PASS PostgreSQL owner isolation, image protection, polygon create and YOLO export')
old=owner.cookies.get('annotation_refresh')
def refresh_same(_):
    with TestClient(app,headers=ORIGIN) as client:
        client.cookies.set('annotation_refresh',old)
        return client.post('/api/auth/refresh').status_code
with ThreadPoolExecutor(max_workers=2) as executor:
    statuses=list(executor.map(refresh_same,range(2)))
assert sorted(statuses)==[200,401],statuses
assert owner.get('/api/auth/me').status_code==401
print('PASS concurrent rotation: one winner, replay revokes the session family')
print('All PostgreSQL smoke checks passed; disposable DB retained for inspection.')
