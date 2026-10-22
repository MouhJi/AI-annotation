import io
import json
import re
import uuid
from datetime import timedelta
from pathlib import Path
import jwt
import pytest
from PIL import Image as PillowImage
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal
from app.models import User, UserSession, PasswordResetToken, Project
from app.models.auth import utcnow
from app.auth_config import settings
from app.services.auth_security import token_hash
from .test_api import client as regression_client

PASSWORD="long secure passphrase 2026"
def browser(): return TestClient(app, headers={"Origin":"http://localhost:5173"})
def account(client=None):
    client=client or browser(); email=f"{uuid.uuid4().hex}@example.com"
    response=client.post("/api/auth/register",json={"email":email,"password":PASSWORD,"full_name":"Test User"})
    assert response.status_code==201, response.text
    login=client.post("/api/auth/login",json={"email":email,"password":PASSWORD})
    assert login.status_code==200, login.text
    client.headers["Authorization"]="Bearer "+login.json()["access_token"]
    return client,email,response.json(),login.json()
def latest_token(email,action):
    paths=sorted((Path(__import__('os').environ['STORAGE_PATH'])/'.emails').glob('*.eml'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
    from email import message_from_string, policy
    for path in paths:
        message=message_from_string(path.read_text(encoding='utf-8'),policy=policy.default)
        part=message.get_body(preferencelist=('plain',)) if message.is_multipart() else message
        body=part.get_content()
        if message['To']==email and action in body:
            return re.search(r'#token=([A-Za-z0-9_-]+)',body).group(1)
    raise AssertionError("Development email not delivered")

def test_register_normalization_duplicate_and_password_rules():
    client=browser(); email=f"{uuid.uuid4().hex}@example.com"; payload={"email":"  "+email.upper()+"  ","password":PASSWORD,"full_name":"  User  "}
    first=client.post('/api/auth/register',json=payload); assert first.status_code==201
    assert first.json()['email']==email and first.json()['full_name']=='User' and 'password_hash' not in first.text
    assert client.post('/api/auth/register',json={**payload,'email':email}).status_code==409
    assert client.post('/api/auth/register',json={**payload,'password':'short'}).status_code==422

def test_login_me_profile_and_mass_assignment():
    client,email,user,_=account()
    assert client.get('/api/auth/me').json()['id']==user['id']
    assert client.patch('/api/users/me',json={'full_name':'New Name'}).json()['full_name']=='New Name'
    assert client.patch('/api/users/me',json={'full_name':'Bad','status':'active'}).status_code==422
    bad=browser().post('/api/auth/login',json={'email':email,'password':'wrong'})
    missing=browser().post('/api/auth/login',json={'email':'absent@example.com','password':'wrong'})
    assert bad.status_code==missing.status_code==401 and bad.json()==missing.json()
    with SessionLocal() as db:
        row=db.get(User,uuid.UUID(user['id'])); row.status='disabled'; db.commit()
    assert browser().post('/api/auth/login',json={'email':email,'password':PASSWORD}).status_code==401
    assert client.get('/api/auth/me').status_code==403

@pytest.mark.parametrize('change',[{'exp':1},{'iss':'other'},{'aud':'other'},{'type':'refresh'}])
def test_invalid_access_claims(change):
    client,_,_,login=account(); config=settings()
    claims=jwt.decode(login['access_token'],config['secret'],algorithms=['HS256'],audience=config['audience']); claims.update(change)
    client.headers['Authorization']='Bearer '+jwt.encode(claims,config['secret'],algorithm='HS256')
    assert client.get('/api/projects').status_code==401

def test_bad_signature_and_anonymous_private_endpoints():
    client,_,_,login=account(); claims=jwt.decode(login['access_token'],options={'verify_signature':False})
    client.headers['Authorization']='Bearer '+jwt.encode(claims,'wrong-secret-with-at-least-32-characters',algorithm='HS256')
    assert client.get('/api/auth/me').status_code==401
    for url in ['/api/projects','/api/images/1','/api/images/1/predictions','/storage/projects/1/images/a.png']:
        assert browser().get(url).status_code==401
    assert browser().get('/health').status_code==200

def test_rotation_reuse_revokes_family_and_access():
    client,_,_,_=account(); old=client.cookies.get('annotation_refresh')
    response=client.post('/api/auth/refresh'); assert response.status_code==200
    assert client.cookies.get('annotation_refresh')!=old
    replay=browser(); replay.cookies.set('annotation_refresh',old)
    assert replay.post('/api/auth/refresh').status_code==401
    assert client.post('/api/auth/refresh').status_code==401
    assert client.get('/api/auth/me').status_code==401

def test_expired_refresh_session_invalidates_access():
    client,_,user,_=account()
    with SessionLocal() as db:
        session=db.scalar(select(UserSession).where(UserSession.user_id==uuid.UUID(user['id']))); session.expires_at=utcnow()-timedelta(seconds=1); db.commit()
    assert client.post('/api/auth/refresh').status_code==401
    assert client.get('/api/auth/me').status_code==401

def test_required_verification_blocks_login_until_verified(monkeypatch):
    monkeypatch.setitem(settings(),'verify_required',True)
    client=browser(); email=f'{uuid.uuid4().hex}@example.com'
    registered=client.post('/api/auth/register',json={'email':email,'password':PASSWORD,'full_name':'Pending User'})
    assert registered.status_code==201 and registered.json()['status']=='pending_verification'
    assert client.post('/api/auth/login',json={'email':email,'password':PASSWORD}).status_code==401
    raw=latest_token(email,'verify-email')
    assert client.post('/api/auth/verify-email',json={'token':raw}).status_code==200
    assert client.post('/api/auth/login',json={'email':email,'password':PASSWORD}).status_code==200

def test_logout_and_logout_all_and_session_revoke():
    client,email,user,_=account(); second=browser(); login=second.post('/api/auth/login',json={'email':email,'password':PASSWORD}).json(); second.headers['Authorization']='Bearer '+login['access_token']
    sessions=client.get('/api/auth/sessions').json(); assert len(sessions)==2 and sum(row['current'] for row in sessions)==1
    other=next(row for row in sessions if not row['current']); assert client.delete('/api/auth/sessions/'+other['id']).status_code==200
    assert second.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/logout').status_code==200 and not client.cookies.get('annotation_refresh')
    assert client.get('/api/auth/me').status_code==401
    client.headers['Authorization']='Bearer '+client.post('/api/auth/login',json={'email':email,'password':PASSWORD}).json()['access_token']
    assert client.post('/api/auth/logout-all').status_code==200
    assert client.get('/api/auth/me').status_code==401

def test_change_password_revokes_all_sessions():
    client,email,_,_=account()
    assert client.post('/api/auth/change-password',json={'current_password':'wrong','new_password':'another password long'}).status_code==400
    assert client.post('/api/auth/change-password',json={'current_password':PASSWORD,'new_password':'another password long'}).status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert browser().post('/api/auth/login',json={'email':email,'password':PASSWORD}).status_code==401
    assert browser().post('/api/auth/login',json={'email':email,'password':'another password long'}).status_code==200

def test_reset_generic_single_use_expiration_and_verification():
    client,email,_,_=account()
    known=client.post('/api/auth/forgot-password',json={'email':email}); unknown=client.post('/api/auth/forgot-password',json={'email':'missing@example.com'})
    assert known.json()==unknown.json() and 'token' not in known.text
    raw=latest_token(email,'reset-password')
    assert client.post('/api/auth/reset-password',json={'token':raw,'new_password':'new passphrase for reset'}).status_code==200
    assert client.post('/api/auth/reset-password',json={'token':raw,'new_password':'new passphrase for reset'}).status_code==400
    assert client.get('/api/auth/me').status_code==401
    client.post('/api/auth/forgot-password',json={'email':email}); raw=latest_token(email,'reset-password')
    with SessionLocal() as db:
        row=db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash==token_hash(raw))); row.expires_at=utcnow()-timedelta(seconds=1); db.commit()
    assert client.post('/api/auth/reset-password',json={'token':raw,'new_password':PASSWORD}).status_code==400
    verification=latest_token(email,'verify-email')
    # Password reset invalidates existing one-time tokens. Resend generates a fresh verification.
    client.post('/api/auth/resend-verification',json={'email':email}); verification=latest_token(email,'verify-email')
    assert client.post('/api/auth/verify-email',json={'token':verification}).status_code==200
    assert client.post('/api/auth/verify-email',json={'token':verification}).status_code==400

def test_csrf_rate_limits_and_cookie_flags():
    client,email,_,_=account()
    assert client.post('/api/auth/refresh',headers={'Origin':'https://evil.example'}).status_code==403
    client.headers.pop('Origin'); assert client.post('/api/auth/refresh').status_code==403
    response=browser().post('/api/auth/login',json={'email':email,'password':PASSWORD})
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=lax' in response.headers['set-cookie'] and 'Path=/api/auth' in response.headers['set-cookie']
    client=browser()
    responses=[client.post('/api/auth/login',json={'email':email,'password':'bad'}).status_code for _ in range(12)]
    assert 429 in responses

def test_project_image_annotation_prediction_split_and_export_isolation():
    owner,_,_,_=account(); stranger,_,_,_=account()
    project=owner.post('/api/projects',json={'name':'Private'}).json(); pid=project['id']
    label=owner.post(f'/api/projects/{pid}/classes',json={'name':'cat'}).json()
    buffer=io.BytesIO(); PillowImage.new('RGB',(40,30)).save(buffer,format='PNG')
    image=owner.post(f'/api/projects/{pid}/images',files={'files':('private.png',buffer.getvalue(),'image/png')}).json()[0]; iid=image['id']
    annotation=owner.post(f'/api/images/{iid}/annotations',json={'class_id':label['id'],'x':1,'y':1,'width':10,'height':10}).json()
    assert owner.get(image['image_url']).status_code==200
    assert stranger.get(image['image_url']).status_code==404
    assert all(row['id']!=pid for row in stranger.get('/api/projects').json())
    for method,path in [('get',f'/api/projects/{pid}'),('delete',f'/api/projects/{pid}'),('get',f'/api/images/{iid}'),('delete',f'/api/annotations/{annotation["id"]}'),('get',f'/api/images/{iid}/predictions'),('get',f'/api/projects/{pid}/dataset/split'),('post',f'/api/projects/{pid}/dataset/export/yolo')]:
        assert getattr(stranger,method)(path).status_code==404
    assert stranger.post('/api/images/bulk-delete',json={'project_id':pid,'image_ids':[iid]}).status_code==404
    assert owner.get(f'/api/images/{iid}/annotations').json()[0]['id']==annotation['id']
    assert owner.post(f'/api/projects/{pid}/dataset/export/yolo').status_code==200
    with SessionLocal() as db:
        legacy=Project(name='Unclaimed'); db.add(legacy); db.commit(); db.refresh(legacy); legacy_id=legacy.id
    assert owner.get(f'/api/projects/{legacy_id}').status_code==404
    with SessionLocal() as db: assert db.get(Project,legacy_id).name=='Unclaimed'
