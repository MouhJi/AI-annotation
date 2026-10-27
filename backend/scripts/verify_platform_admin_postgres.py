"""Platform-admin checks ONLY in an empty disposable PostgreSQL test database."""
import os,sys,uuid,secrets
from pathlib import Path
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine,text,select
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if not (make_url(os.environ['DATABASE_URL']).database or '').startswith('annotation_phase6_test_'):
    raise RuntimeError('Refusing non-disposable database')
os.environ.update(APP_ENV='test',EMAIL_PROVIDER='file',STORAGE_PATH='/tmp/platform-admin-pg',JWT_SECRET_KEY=secrets.token_urlsafe(48))
from alembic import command
from alembic.config import Config
config=Config('alembic.ini');command.upgrade(config,'0008_annotation_correction')
engine=create_engine(os.environ['DATABASE_URL']);legacy=uuid.uuid4()
with engine.begin() as connection:
    connection.execute(text("INSERT INTO users(id,email,full_name,password_hash,status,email_verified_at,created_at,updated_at) VALUES(:id,'legacy-admin-test@example.com','Existing verified user','unused','active',NOW(),NOW(),NOW())"),{'id':legacy})
command.upgrade(config,'head');command.upgrade(config,'head')
with engine.connect() as connection:
    assert connection.execute(text('SELECT count(*) FROM users')).scalar()==1
    assert connection.execute(text('SELECT is_platform_admin FROM users WHERE id=:id'),{'id':legacy}).scalar() is False
from app.database import SessionLocal
from app.models import User,UserSession,AuditLog
from app.models.auth import utcnow
from app.services.platform_admin import change_platform_role,usable_admins
from app.services.auth_security import access_token,opaque_token,token_hash
from app.main import app
from fastapi.testclient import TestClient

def client(uid):
    with SessionLocal() as db:
        user=db.get(User,uid);raw=opaque_token();session=UserSession(user_id=uid,refresh_token_hash=token_hash(raw),expires_at=utcnow()+timedelta(days=1))
        db.add(session);db.commit();token=access_token(user,session)
    return TestClient(app,headers={'Origin':'http://localhost:5173','Authorization':'Bearer '+token})
with SessionLocal() as db:
    b=User(email='second-admin-test@example.com',full_name='Second test admin',password_hash='unused',email_verified_at=utcnow());db.add(b);db.commit();bid=b.id
    change_platform_role(db,'legacy-admin-test@example.com',True,True);change_platform_role(db,b.email,True,True)
a=client(legacy);b=client(bid)
assert a.get('/api/admin/dashboard/summary').status_code==200
assert a.get('/api/admin/dashboard/activity').status_code==200
for route in ('users','workspaces','projects','audit-logs'):assert a.get('/api/admin/'+route).status_code==200
def disable(args):
    c,target=args
    return c.post(f'/api/admin/users/{target}/disable',json={'confirm_user_id':str(target)}).status_code
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(disable,[(a,bid),(b,legacy)]))
assert 200 in results and all(code in (200,403,409) for code in results),results
with SessionLocal() as db:
    assert usable_admins(db)==1
    target=db.scalar(select(User).where(User.status=='disabled'))
    assert target is not None
    assert all(s.revoked_at for s in db.scalars(select(UserSession).where(UserSession.user_id==target.id)))
    assert db.scalar(select(AuditLog).where(AuditLog.action=='user.disabled')) is not None
print('PASS PostgreSQL: additive migration, no automatic promotion, admin APIs, concurrent disable retains an administrator, session revocation and audit')
