import uuid
from datetime import timedelta
import pytest
from app.database import SessionLocal
from app.models import UserSession
from app.models.auth import utcnow
from sqlalchemy import select
from .test_auth import account, browser

def session(user):
    with SessionLocal() as db: return db.scalar(select(UserSession).where(UserSession.user_id==uuid.UUID(user['id'])))

@pytest.mark.parametrize('path',['/api/auth/refresh','/api/auth/me','/api/auth/activity'])
def test_exact_deadline_rejected_and_revoked(path):
    client,_,user,login=account(); row=session(user)
    with SessionLocal() as db:
        item=db.get(UserSession,row.id);item.last_activity_at=utcnow()-timedelta(minutes=60);db.commit()
    response=client.get(path) if path.endswith('/me') else client.post(path)
    assert response.status_code==401,response.text
    with SessionLocal() as db: assert db.get(UserSession,row.id).revoked_at is not None
    assert client.post('/api/auth/activity').status_code==401
    assert client.post('/api/auth/refresh').status_code==401

def test_polling_refresh_dont_extend_activity():
    client,_,user,login=account();before=session(user).last_activity_at
    assert client.get('/api/auth/me').status_code==200
    assert client.get('/api/auth/session').status_code==200
    refreshed=client.post('/api/auth/refresh');assert refreshed.status_code==200
    assert session(user).last_activity_at==before
    client.headers['Authorization']='Bearer '+refreshed.json()['access_token']
    result=client.post('/api/auth/activity',json={'last_activity_at':'2099-01-01T00:00:00Z','session_id':str(uuid.uuid4())})
    assert result.status_code==200,result.text
    assert result.json()['id']==str(session(user).id)
    assert session(user).last_activity_at>before
    assert result.json()['idle_timeout_seconds']==3600 and result.json()['warning_seconds']==300

def test_activity_csrf_other_user_and_revoked():
    a,_,ua,_=account();b,_,ub,_=account();before=session(ua).last_activity_at
    assert b.post('/api/auth/activity',json={'session_id':str(session(ua).id)}).status_code==200
    assert session(ua).last_activity_at==before
    assert a.post('/api/auth/activity',headers={'Origin':'https://untrusted.example'}).status_code==403
    assert a.post('/api/auth/logout').status_code==200
    assert a.post('/api/auth/activity').status_code==401

def test_session_at_59_minutes_can_extend():
    client,_,user,_=account();row=session(user)
    with SessionLocal() as db:
        db.get(UserSession,row.id).last_activity_at=utcnow()-timedelta(minutes=59);db.commit()
    assert client.post('/api/auth/activity').status_code==200
    assert session(user).last_activity_at>utcnow().replace(tzinfo=None)-timedelta(seconds=5)
