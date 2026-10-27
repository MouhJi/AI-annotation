import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User,UserSession,Workspace,WorkspaceMember,AuditLog,Annotation
from app.models.auth import utcnow
from app.services.platform_admin import change_platform_role
from .test_auth import account,browser,PASSWORD
from .test_workspaces import team,role

@pytest.fixture(scope='module')
def people():
    from app.rate_limit import limiter
    limiter.buckets.clear()
    return [account() for _ in range(4)]

@pytest.fixture
def admin():
    result=account()
    with SessionLocal() as db:
        user=db.get(User,uuid.UUID(result[2]['id']));user.email_verified_at=utcnow();db.commit()
        change_platform_role(db,result[1],True,True)
    return result

@pytest.mark.parametrize('path',['dashboard/summary','dashboard/activity','users','workspaces','projects','audit-logs'])
def test_admin_endpoints_default_deny(admin,path):
    assert browser().get('/api/admin/'+path).status_code==401
    user=account();assert user[0].get('/api/admin/'+path).status_code==403
    response=admin[0].get('/api/admin/'+path);assert response.status_code==200,response.text

@pytest.mark.parametrize('role_name',['owner','admin'])
def test_workspace_roles_cannot_access_platform(team,role_name):
    role(team,role_name);assert team[1][0].get('/api/admin/users').status_code==403

def test_self_promotion_forbidden():
    c=browser();r=c.post('/api/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':PASSWORD,'full_name':'Bad','is_platform_admin':True});assert r.status_code==422
    user=account();assert user[0].patch('/api/users/me',json={'full_name':'Bad','is_platform_admin':True}).status_code==422

def test_bootstrap_verified_dryrun_revoke_and_last_admin():
    a=account();b=account()
    with SessionLocal() as db:
        with pytest.raises(ValueError):change_platform_role(db,'absent@example.com',True,True)
        with pytest.raises(ValueError):change_platform_role(db,a[1],True,True)
        for result in (a,b):db.get(User,uuid.UUID(result[2]['id'])).email_verified_at=utcnow()
        db.commit();before=len(list(db.scalars(select(User))))
        assert not change_platform_role(db,a[1],True)['applied']
        assert not db.get(User,uuid.UUID(a[2]['id'])).is_platform_admin
        change_platform_role(db,a[1],True,True)
        assert len(list(db.scalars(select(User))))==before
        # Use a transaction-local fixture state so other admin tests cannot hide the last-admin case.
        others=list(db.scalars(select(User).where(User.id!=uuid.UUID(a[2]['id']),User.is_platform_admin.is_(True))))
        for row in others:row.is_platform_admin=False
        db.commit()
        with pytest.raises(HTTPException) as error:change_platform_role(db,a[1],False,True)
        assert error.value.status_code==409
        change_platform_role(db,b[1],True,True);change_platform_role(db,a[1],False,True)
        assert not db.get(User,uuid.UUID(a[2]['id'])).is_platform_admin

def test_user_list_search_filter_pagination_and_secrets(admin):
    target=account();c=admin[0]
    response=c.get('/api/admin/users',params={'q':target[1],'verified':'false','status':'active','page_size':1,'sort':'email','direction':'asc'})
    assert response.status_code==200,response.text
    result=response.json();assert result['total']==1 and result['items'][0]['id']==target[2]['id']
    assert c.get('/api/admin/users?page_size=101').status_code==422
    assert c.get('/api/admin/users?sort=password_hash').status_code==422
    detail=c.get('/api/admin/users/'+target[2]['id']);assert detail.status_code==200
    assert set(detail.json()['user'])=={'id','full_name','email','status','email_verified','is_platform_admin','created_at','last_login_at','workspace_count'}
    assert not any(word in detail.text for word in ['password_hash','refresh_token','verification_token','smtp','points_json','filepath'])
    assert target[0].get('/api/admin/users/'+target[2]['id']).status_code==403

def test_disable_enable_revoke_and_audit(admin):
    target=account();tid=target[2]['id'];c=admin[0];body={'confirm_user_id':tid}
    assert c.post(f'/api/admin/users/{tid}/disable',json={'confirm_user_id':str(uuid.uuid4())}).status_code==422
    assert c.post(f'/api/admin/users/{tid}/disable',json=body,headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post(f'/api/admin/users/{tid}/disable',json=body).status_code==200
    assert target[0].get('/api/auth/me').status_code in (401,403)
    assert browser().post('/api/auth/login',json={'email':target[1],'password':PASSWORD}).status_code==401
    assert c.post(f'/api/admin/users/{tid}/enable',json=body).status_code==200
    assert browser().post('/api/auth/login',json={'email':target[1],'password':PASSWORD}).status_code==200
    assert c.post(f'/api/admin/users/{tid}/revoke-sessions',json=body).status_code==200
    with SessionLocal() as db:
        assert all(s.revoked_at for s in db.scalars(select(UserSession).where(UserSession.user_id==uuid.UUID(tid))))
        assert len(list(db.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id==uuid.UUID(tid)))))==1
    logs=c.get('/api/admin/audit-logs',params={'resource_type':'user','resource_id':tid}).json()['items']
    assert {r['action'] for r in logs}>={'user.disabled','user.enabled','user.sessions_revoked'}
    assert c.get('/api/admin/audit-logs/'+logs[0]['id']).status_code==200
    assert c.delete('/api/admin/audit-logs/'+logs[0]['id']).status_code==405

def test_no_self_lock_and_live_role_revocation(admin):
    c,_,u,_=admin
    assert c.post('/api/admin/users/'+u['id']+'/disable',json={'confirm_user_id':u['id']}).status_code==409
    with SessionLocal() as db:
        db.get(User,uuid.UUID(u['id'])).is_platform_admin=False;db.commit()
    assert c.get('/api/admin/dashboard/summary').status_code==403

def test_metadata_not_private_contents_and_audit_redaction(admin,team):
    owner,_,_,_,w,p,label,image,a=team;c=admin[0]
    assert c.get('/api/admin/workspaces/'+w['id']).status_code==200
    project=c.get('/api/admin/projects',params={'workspace_id':w['id']}).json()['items'][0]
    assert project['id']==p['id'] and project['annotation_count']==1
    for path in [f'/api/projects/{p["id"]}',f'/api/images/{image["id"]}/annotations',f'/api/images/{image["id"]}']:
        assert c.get(path).status_code==404
    assert c.post(f'/api/projects/{p["id"]}/dataset/export/yolo').status_code==404
    with SessionLocal() as db:
        db.add(AuditLog(workspace_id=uuid.UUID(w['id']),actor_user_id=uuid.UUID(owner[2]['id']),action='annotation.updated',resource_type='annotation',resource_id=str(a['id']),details={'before':{'points_json':'SECRET GEOMETRY','x':1,'version':1},'password':'SECRET PASSWORD','after':{'version':2,'source':'manual'}}));db.commit()
    logs=c.get('/api/admin/audit-logs',params={'action':'annotation.updated','resource_id':a['id']}).json()
    assert 'SECRET' not in str(logs) and 'points_json' not in str(logs)
    summary=c.get('/api/admin/dashboard/summary').json()
    with SessionLocal() as db:
        row=db.get(Annotation,a['id']);row.deleted_at=utcnow();db.commit()
    assert c.get('/api/admin/dashboard/summary').json()['total_annotations']==summary['total_annotations']-1
    assert c.get('/api/admin/projects',params={'workspace_id':w['id']}).json()['items'][0]['annotation_count']==0
