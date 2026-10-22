"""Attribution integration checks ONLY in an existing disposable PostgreSQL test DB."""
import io
import os
import sys
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not (make_url(os.environ['DATABASE_URL']).database or '').startswith('annotation_phase6_test_'):
    raise RuntimeError('Refusing non-disposable database')
os.environ.update(STORAGE_PATH='/tmp/attribution-tests', APP_ENV='test', EMAIL_PROVIDER='file',
                  EMAIL_BACKEND='file', JWT_SECRET_KEY=__import__('secrets').token_urlsafe(48))
from fastapi.testclient import TestClient
from PIL import Image as PillowImage
from app.main import app
from app.database import SessionLocal
from app.models import User, WorkspaceMember
from app.models.auth import utcnow


def account(name):
    client = TestClient(app, headers={'Origin': 'http://localhost:5173'})
    email = uuid.uuid4().hex + '@example.com'
    password = uuid.uuid4().hex
    response = client.post('/api/auth/register', json={'email': email, 'password': password, 'full_name': name})
    assert response.status_code == 201, response.text
    user = response.json()
    client.headers['Authorization'] = 'Bearer ' + client.post('/api/auth/login', json={'email': email, 'password': password}).json()['access_token']
    with SessionLocal() as db:
        db.get(User, uuid.UUID(user['id'])).email_verified_at = utcnow(); db.commit()
    return client, user


a, ua = account('Nguyễn An')
b, ub = account('Trần Bình')
workspace = a.post('/api/workspaces', json={'name': 'Attribution concurrency test', 'slug': 'attr-' + uuid.uuid4().hex}).json()
with SessionLocal() as db:
    db.add(WorkspaceMember(workspace_id=uuid.UUID(workspace['id']), user_id=uuid.UUID(ub['id']), role='annotator')); db.commit()
project = a.post('/api/projects', json={'name': 'Attribution', 'workspace_id': workspace['id']}).json()
label = a.post(f'/api/projects/{project["id"]}/classes', json={'name': 'Car'}).json()
buffer = io.BytesIO(); PillowImage.new('RGB', (100, 100)).save(buffer, format='PNG')
image = a.post(f'/api/projects/{project["id"]}/images', files={'files': ('a.png', buffer.getvalue(), 'image/png')}).json()[0]
url = f'/api/images/{image["id"]}/annotations'
box = dict(class_id=label['id'], x=1, y=1, width=10, height=10)
saved = a.post(url, json=box).json()
assert b.get(url).json()[0]['created_by']['id'] == ua['id']
body = {'expected_versions': {str(saved['id']): 1}, 'items': [{**box, 'id': saved['id'], 'width': 15}]}
with ThreadPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(lambda client: client.put(url, json=body).status_code, [a, b]))
assert sorted(results) == [200, 409], results
official = a.get(url).json()[0]
assert official['created_by']['id'] == ua['id'] and official['version'] == 2
assert official['updated_by']['id'] == (ua['id'] if results[0] == 200 else ub['id'])
body['expected_versions'] = {str(saved['id']): 2}
assert b.put(url, json=body).json()[0] == official  # no-op preserves editor and time
body['items'][0]['width'] = 20
edited = b.put(url, json=body).json()[0]
assert edited['created_by']['id'] == ua['id'] and edited['updated_by']['id'] == ub['id']
a.patch('/api/users/me', json={'full_name': 'Nguyễn An renamed'})
assert b.get(url).json()[0]['created_by']['full_name'] == 'Nguyễn An renamed'
a.delete(f'/api/workspaces/{workspace["id"]}/members/{ub["id"]}')
assert a.get(url).json()[0]['updated_by']['id'] == ub['id']
assert b.get(url).status_code == 404
print('PASS PostgreSQL attribution: creator/editor, no-op, rename, removal retention, atomic concurrent batch 200/409')
