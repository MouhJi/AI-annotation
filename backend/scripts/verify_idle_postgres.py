"""Isolated PostgreSQL idle/concurrency test. Never run on the application DB."""
import os, sys, uuid
from pathlib import Path
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if not (make_url(os.environ['DATABASE_URL']).database or '').startswith('annotation_phase6_test_'):
    raise RuntimeError('Refusing non-disposable database')
os.environ.update(APP_ENV='test',EMAIL_PROVIDER='file',STORAGE_PATH='/tmp/idle-pg-test',JWT_SECRET_KEY=__import__('secrets').token_urlsafe(48))
from alembic import command
from alembic.config import Config
command.upgrade(Config('alembic.ini'),'head')
from app.database import SessionLocal
from app.models import User,UserSession
from app.models.auth import utcnow
from app.services.auth_security import access_token,opaque_token,token_hash
from app.main import app
from fastapi.testclient import TestClient

with SessionLocal() as db:
    user=User(email=uuid.uuid4().hex+'@example.com',full_name='Idle test',password_hash='unused')
    db.add(user);db.flush()
    raw=opaque_token();session=UserSession(user_id=user.id,refresh_token_hash=token_hash(raw),expires_at=utcnow()+timedelta(days=1))
    db.add(session);db.commit();db.refresh(session);sid=session.id;token=access_token(user,session)
def client():
    c=TestClient(app,headers={'Origin':'http://localhost:5173','Authorization':'Bearer '+token});c.cookies.set('annotation_refresh',raw,path='/api/auth');return c
def touch(_):return client().post('/api/auth/activity').status_code
with ThreadPoolExecutor(max_workers=4) as pool: assert list(pool.map(touch,range(4)))==[200]*4
with SessionLocal() as db:
    before=db.get(UserSession,sid).last_activity_at
assert client().post('/api/auth/refresh').status_code==200
with SessionLocal() as db:
    row=db.get(UserSession,sid);assert row.last_activity_at==before
    row.last_activity_at=utcnow()-timedelta(minutes=60);db.commit()
with ThreadPoolExecutor(max_workers=4) as pool: assert list(pool.map(touch,range(4)))==[401]*4
with SessionLocal() as db: assert db.get(UserSession,sid).revoked_at is not None
print('PASS PostgreSQL migration, concurrent activity, refresh without idle extension, boundary expiry, no resurrection')
