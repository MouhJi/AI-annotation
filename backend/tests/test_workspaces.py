import io
import json
import uuid
from datetime import timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image as PillowImage
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Workspace, WorkspaceMember, WorkspaceInvitation, User, Project, Image, Annotation, AuditLog
from app.models.auth import utcnow
from app.services.auth_security import token_hash
from app.services.rbac import ROLE_PERMISSIONS
from app.services.workspace_service import workspace_operation
from app.migrate_workspaces import migrate
from .test_auth import account, latest_token

@pytest.fixture(scope="module")
def people():
    return [account() for _ in range(4)]

@pytest.fixture
def team(people):
    owner, member, stranger, third = people
    response=owner[0].post('/api/workspaces',json={'name':'Team '+uuid.uuid4().hex,'slug':'team-'+uuid.uuid4().hex})
    assert response.status_code==201,response.text
    workspace=response.json()
    with SessionLocal() as db:
        db.add(WorkspaceMember(workspace_id=uuid.UUID(workspace['id']),user_id=uuid.UUID(member[2]['id']),role='viewer'))
        db.commit()
    project=owner[0].post('/api/projects',json={'name':'Shared','workspace_id':workspace['id']}).json()
    label=owner[0].post(f'/api/projects/{project["id"]}/classes',json={'name':'cat'}).json()
    buffer=io.BytesIO(); PillowImage.new('RGB',(100,80)).save(buffer,format='PNG')
    image=owner[0].post(f'/api/projects/{project["id"]}/images',files={'files':('team.png',buffer.getvalue(),'image/png')}).json()[0]
    annotation=owner[0].post(f'/api/images/{image["id"]}/annotations',json={'class_id':label['id'],'x':1,'y':1,'width':10,'height':10}).json()
    return owner,member,stranger,third,workspace,project,label,image,annotation

def role(team, value):
    owner,member,_,_,workspace,*_=team
    response=owner[0].patch(f'/api/workspaces/{workspace["id"]}/members/{member[2]["id"]}',json={'role':value})
    assert response.status_code==200,response.text

def test_workspace_creation_listing_settings_and_statistics(team):
    owner,member,stranger,_,workspace,project,label,image,annotation=team
    assert workspace['role']=='owner' and 'workspace.delete' in workspace['permissions']
    wid=workspace['id']
    assert any(row['id']==wid for row in member[0].get('/api/workspaces').json())
    assert all(row['id']!=wid for row in stranger[0].get('/api/workspaces').json())
    assert stranger[0].get(f'/api/workspaces/{wid}').status_code==404
    stats=owner[0].get(f'/api/workspaces/{wid}').json()
    assert [stats[key] for key in ['project_count','image_count','annotation_count','member_count']]==[1,1,1,2]
    assert owner[0].patch(f'/api/workspaces/{wid}',json={'name':'Renamed'}).json()['name']=='Renamed'
    assert owner[0].patch(f'/api/workspaces/{wid}',json={'created_by':member[2]['id']}).status_code==422
    assert owner[0].patch(f'/api/workspaces/{wid}',json={'name':None}).status_code==422
    assert owner[0].post('/api/workspaces',json={'name':'Collision','slug':workspace['slug'].upper()}).status_code==409

@pytest.mark.parametrize('role_name',list(ROLE_PERMISSIONS))
def test_permission_matrix_default_deny(role_name):
    allowed=ROLE_PERMISSIONS[role_name]
    assert 'project.read' in allowed and 'image.read' in allowed
    assert ('annotation.update' in allowed)==(role_name!='viewer')
    assert ('dataset.export' in allowed)==(role_name in {'admin','owner'})
    assert ('workspace.delete' in allowed)==(role_name=='owner')
    assert not ROLE_PERMISSIONS.get('super-admin',())

@pytest.mark.parametrize('operation',[
    'project-delete','project-update','project-create','image-delete','image-upload','bulk-delete','annotation-create','annotation-update','annotation-delete','all-labels',
    'class-create','class-rename','class-delete','export','split','infer','infer-batch','members','invite','settings',
])
def test_viewer_mutations_denied(team,operation):
    _,member,_,_,ws,p,c,i,a=team; client=member[0]; pid=p['id']; iid=i['id']
    calls={
        'project-delete':('delete',f'/api/projects/{pid}',{}),
        'project-update':('patch',f'/api/projects/{pid}',{'json':{'name':'Hacked'}}),
        'project-create':('post','/api/projects',{'json':{'name':'Hacked','workspace_id':ws['id']}}),
        'image-delete':('delete',f'/api/images/{iid}',{}),
        'image-upload':('post',f'/api/projects/{pid}/images',{}),
        'bulk-delete':('post','/api/images/bulk-delete',{'json':{'project_id':pid,'image_ids':[iid]}}),
        'annotation-create':('post',f'/api/images/{iid}/annotations',{'json':{'class_id':c['id'],'x':1,'y':1,'width':2,'height':2}}),
        'annotation-update':('put',f'/api/annotations/{a["id"]}',{'json':{}}),
        'annotation-delete':('delete',f'/api/annotations/{a["id"]}',{}),
        'all-labels':('delete',f'/api/images/{iid}/annotations',{}),
        'class-create':('post',f'/api/projects/{pid}/classes',{'json':{'name':'Hacked'}}),
        'class-rename':('put',f'/api/classes/{c["id"]}',{'json':{'name':'Hacked'}}),
        'class-delete':('delete',f'/api/classes/{c["id"]}',{}),
        'export':('post',f'/api/projects/{pid}/dataset/export/yolo',{}),
        'split':('put',f'/api/projects/{pid}/dataset/split',{'json':{'train':80,'val':10,'test':10}}),
        'infer':('post',f'/api/images/{iid}/auto-label',{'json':{}}),
        'infer-batch':('post',f'/api/projects/{pid}/auto-label-batch',{'json':{'image_ids':[iid]}}),
        'members':('get',f'/api/workspaces/{ws["id"]}/members',{}),
        'invite':('post',f'/api/workspaces/{ws["id"]}/invitations',{'json':{'email':'a@example.com','role':'viewer'}}),
        'settings':('patch',f'/api/workspaces/{ws["id"]}',{'json':{'name':'Hacked'}}),
    }
    method,path,kwargs=calls[operation]
    result=getattr(client,method)(path,**kwargs)
    assert result.status_code==403,result.text
    assert client.get(f'/api/projects/{pid}').status_code==200
    assert client.get(i['image_url']).status_code==200

@pytest.mark.parametrize('member_role',['annotator','reviewer','admin'])
def test_annotation_and_ai_assistance_roles(team,member_role,monkeypatch):
    _,member,_,_,ws,p,c,i,a=team; role(team,member_role); client=member[0]
    payload={'class_id':c['id'],'x':3,'y':3,'width':20,'height':10}
    assert client.post(f'/api/images/{i["id"]}/annotations',json=payload).status_code==201
    monkeypatch.setattr('app.services.auto_label_service.yolo_service.infer',lambda *_:('mock.pt',[{'model_class_id':7,'model_class_name':'new class','x':1,'y':1,'width':5,'height':5,'confidence':.9}]))
    predictions=client.post(f'/api/images/{i["id"]}/auto-label',json={}).json()['predictions']
    assert client.post(f'/api/predictions/{predictions[0]["id"]}/accept').status_code==200
    assert client.post(f'/api/projects/{p["id"]}/classes',json={'name':'manual'}).status_code==(201 if member_role=='admin' else 403)
    assert client.post(f'/api/projects/{p["id"]}/dataset/export/yolo').status_code==(200 if member_role=='admin' else 403)

def test_cross_workspace_and_switching_isolation(team):
    owner,member,stranger,_,ws,p,c,i,a=team
    for path in [f'/api/projects/{p["id"]}',f'/api/images/{i["id"]}',f'/api/images/{i["id"]}/annotations',i['image_url'],f'/api/classes/{c["id"]}']:
        method=stranger[0].put if '/classes/' in path else stranger[0].get
        response=method(path,json={'name':'changed'}) if '/classes/' in path else method(path)
        assert response.status_code==404,response.text
    assert stranger[0].delete(f'/api/annotations/{a["id"]}').status_code==404
    assert member[0].get('/api/projects',params={'workspace_id':ws['id']}).json()[0]['id']==p['id']
    foreign_ws=stranger[0].get('/api/workspaces').json()[0]['id']
    assert member[0].get('/api/projects',params={'workspace_id':foreign_ws}).status_code==404
    assert owner[0].post('/api/projects',json={'name':'forged','workspace_id':foreign_ws}).status_code==404
    assert owner[0].post('/api/projects',json={'name':'forged','owner_user_id':stranger[2]['id'],'workspace_id':ws['id']}).status_code==422

def test_role_change_removal_and_last_owner(team):
    owner,member,_,_,ws,p,*_=team; base=f'/api/workspaces/{ws["id"]}'
    assert owner[0].delete(f'{base}/members/{owner[2]["id"]}').status_code==409
    assert owner[0].patch(f'{base}/members/{owner[2]["id"]}',json={'role':'viewer'}).status_code==409
    role(team,'admin')
    assert member[0].patch(f'{base}/members/{member[2]["id"]}',json={'role':'owner'}).status_code==403
    assert member[0].patch(f'{base}/members/{owner[2]["id"]}',json={'role':'viewer'}).status_code==403
    assert member[0].delete(f'{base}/members/{owner[2]["id"]}').status_code==403
    role(team,'annotator')
    assert owner[0].delete(f'{base}/members/{member[2]["id"]}').status_code==200
    assert member[0].get(f'/api/projects/{p["id"]}').status_code==404
    assert member[0].get(base).status_code==404

def test_owner_transfer_two_step(team):
    owner,member,_,_,ws,*_=team; base=f'/api/workspaces/{ws["id"]}'
    role(team,'owner')
    assert owner[0].patch(f'{base}/members/{owner[2]["id"]}',json={'role':'viewer'}).status_code==200
    assert member[0].get(base).json()['role']=='owner'
    assert owner[0].delete(f'{base}/members/{member[2]["id"]}').status_code==403

def invitation(team,role_value='annotator'):
    owner,_,_,recipient,ws,*_=team
    response=owner[0].post(f'/api/workspaces/{ws["id"]}/invitations',json={'email':recipient[1].upper(),'role':role_value})
    assert response.status_code==201,response.text
    raw=latest_token(recipient[1],'invitations/accept')
    with SessionLocal() as db:
        person=db.get(User,uuid.UUID(recipient[2]['id']));person.email_verified_at=utcnow();db.commit()
    return response.json(),raw

def test_invitation_accept_verify_email_hash_single_use(team):
    owner,member,stranger,recipient,ws,*_=team
    inv,raw=invitation(team)
    assert 'token' not in json.dumps(inv)
    with SessionLocal() as db:
        row=db.get(WorkspaceInvitation,uuid.UUID(inv['id'])); assert row.token_hash==token_hash(raw) and row.token_hash!=raw
        person=db.get(User,uuid.UUID(recipient[2]['id']));person.email_verified_at=None;db.commit()
    assert recipient[0].post('/api/invitations/accept',json={'token':raw}).status_code==403
    with SessionLocal() as db:
        person=db.get(User,uuid.UUID(recipient[2]['id']));person.email_verified_at=utcnow();db.commit()
        person=db.get(User,uuid.UUID(stranger[2]['id']));person.email_verified_at=utcnow();db.commit()
    assert stranger[0].post('/api/invitations/accept',json={'token':raw}).status_code==400
    accepted=recipient[0].post('/api/invitations/accept',json={'token':raw})
    assert accepted.status_code==200 and accepted.json()['workspace_id']==ws['id']
    assert recipient[0].post('/api/invitations/accept',json={'token':raw}).status_code==400
    assert all('token' not in key for row in owner[0].get(f'/api/workspaces/{ws["id"]}/invitations').json() for key in row)

def test_in_app_invitations_list_accept_decline_and_privacy(team):
    owner,member,stranger,recipient,ws,*_=team
    invited,raw=invitation(team, 'reviewer')
    mine=recipient[0].get('/api/me/invitations')
    assert mine.status_code==200 and len(mine.json())==1
    row=mine.json()[0]
    assert row['invitation_id']==invited['id'] and row['workspace_id']==ws['id']
    assert row['workspace_name']==ws['name'] and row['invited_role']=='reviewer'
    assert 'token' not in json.dumps(row).lower() and row['status']=='pending'
    assert stranger[0].get('/api/me/invitations').json()==[]
    assert stranger[0].post(f"/api/me/invitations/{invited['id']}/accept").status_code==404
    accepted=recipient[0].post(f"/api/me/invitations/{invited['id']}/accept")
    assert accepted.status_code==200 and accepted.json()['workspace_id']==ws['id']
    with SessionLocal() as db:
        joined=db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id==uuid.UUID(ws['id']),WorkspaceMember.user_id==uuid.UUID(recipient[2]['id'])))
        assert joined and joined.role=='reviewer'
    assert recipient[0].get('/api/me/invitations').json()==[]
    assert recipient[0].post(f"/api/me/invitations/{invited['id']}/accept").status_code==409

    # A second invite can be declined and is neither reusable nor an active duplicate.
    second=owner[0].post(f"/api/workspaces/{ws['id']}/invitations",json={'email':stranger[1].upper(),'role':'viewer'}); assert second.status_code==201
    with SessionLocal() as db:
        person=db.get(User,uuid.UUID(stranger[2]['id'])); person.email_verified_at=utcnow(); db.commit()
    declined=stranger[0].post(f"/api/me/invitations/{second.json()['id']}/decline")
    assert declined.status_code==200 and declined.json()=={'declined':True}
    assert stranger[0].post(f"/api/me/invitations/{second.json()['id']}/accept").status_code==409
    again=owner[0].post(f"/api/workspaces/{ws['id']}/invitations",json={'email':stranger[1],'role':'viewer'})
    assert again.status_code==201
    logs=owner[0].get(f"/api/workspaces/{ws['id']}/audit-logs").json()
    assert 'invitation.declined' in {entry['action'] for entry in logs}

def test_in_app_invitation_rejects_unverified_expired_revoked_and_preserves_role(team):
    owner,member,stranger,recipient,ws,*_=team
    invited,raw=invitation(team, 'annotator')
    with SessionLocal() as db:
        person=db.get(User,uuid.UUID(recipient[2]['id'])); person.email_verified_at=None; db.commit()
    assert recipient[0].get('/api/me/invitations').status_code==403
    assert recipient[0].post(f"/api/me/invitations/{invited['id']}/accept").status_code==403
    with SessionLocal() as db:
        person=db.get(User,uuid.UUID(recipient[2]['id'])); person.email_verified_at=utcnow()
        row=db.get(WorkspaceInvitation,uuid.UUID(invited['id'])); row.expires_at=utcnow()-timedelta(seconds=1); db.commit()
    assert recipient[0].post(f"/api/me/invitations/{invited['id']}/accept").status_code==409
    fresh=owner[0].post(f"/api/workspaces/{ws['id']}/invitations",json={'email':recipient[1],'role':'viewer'}); assert fresh.status_code==201
    assert owner[0].delete(f"/api/workspaces/{ws['id']}/invitations/{fresh.json()['id']}").status_code==200
    assert recipient[0].post(f"/api/me/invitations/{fresh.json()['id']}/accept").status_code==409

def test_resend_pending_invitation_keeps_one_active_invitation(team):
    owner,_,_,recipient,ws,*_=team
    invited,raw=invitation(team)
    response=owner[0].post(f"/api/workspaces/{ws['id']}/invitations/{invited['id']}/resend")
    assert response.status_code==200 and response.json()['status']=='pending'
    newer=latest_token(recipient[1], 'invitations/accept')
    assert newer != raw
    assert recipient[0].post('/api/invitations/accept',json={'token':raw}).status_code==400

@pytest.mark.parametrize('invalid_state',['expired','revoked','inviter-demoted'])
def test_invalid_invitations(team,invalid_state):
    owner,member,_,recipient,ws,*_=team
    inv,raw=invitation(team)
    with SessionLocal() as db:
        row=db.get(WorkspaceInvitation,uuid.UUID(inv['id']))
        if invalid_state=='expired': row.expires_at=utcnow()-timedelta(seconds=1)
        elif invalid_state=='revoked': row.revoked_at=utcnow()
        else:
            # First add another owner so workspace remains valid.
            target=db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id==uuid.UUID(ws['id']),WorkspaceMember.user_id==uuid.UUID(owner[2]['id'])));target.role='viewer'
            target=db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id==uuid.UUID(ws['id']),WorkspaceMember.user_id==uuid.UUID(member[2]['id'])));target.role='owner'
        db.commit()
    assert recipient[0].post('/api/invitations/accept',json={'token':raw}).status_code==400

def test_duplicate_expired_reinvite_and_admin_invite_policy(team):
    owner,member,_,recipient,ws,*_=team
    inv,raw=invitation(team);path=f'/api/workspaces/{ws["id"]}/invitations';payload={'email':recipient[1],'role':'viewer'}
    assert owner[0].post(path,json=payload).status_code==409
    with SessionLocal() as db:
        row=db.get(WorkspaceInvitation,uuid.UUID(inv['id']));row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert owner[0].post(path,json=payload).status_code==201
    role(team,'admin')
    assert member[0].post(path,json={'email':'new@example.com','role':'owner'}).status_code==403
    assert member[0].post(path,json={'email':'new@example.com','role':'admin'}).status_code==403
    assert member[0].post(path,json={'email':'new@example.com','role':'viewer'}).status_code==201
    assert owner[0].post(path,json={'email':member[1],'role':'viewer'}).status_code==409

def test_revoke_invitation_and_audit_privacy(team):
    owner,member,_,recipient,ws,*_=team;inv,raw=invitation(team)
    base=f'/api/workspaces/{ws["id"]}'
    assert owner[0].delete(f'{base}/invitations/{inv["id"]}').status_code==200
    assert recipient[0].post('/api/invitations/accept',json={'token':raw}).status_code==400
    logs=owner[0].get(base+'/audit-logs').json()
    assert {'workspace.created','project.created','member.invited','invitation.revoked'}<={row['action'] for row in logs}
    assert raw not in json.dumps(logs) and 'password' not in json.dumps(logs)
    assert member[0].get(base+'/audit-logs').status_code==403

@pytest.mark.parametrize('segmentation',[False,True])
def test_workspace_delete_atomic_cleanup_and_other_tenant_preserved(team,segmentation):
    owner,member,stranger,_,ws,p,c,i,a=team; base=f'/api/workspaces/{ws["id"]}'
    if segmentation:
        seg=owner[0].post('/api/projects',json={'name':'Masks','annotation_mode':'instance_segmentation','workspace_id':ws['id']}).json()
        buffer=io.BytesIO();PillowImage.new('RGB',(100,80)).save(buffer,format='PNG')
        img=owner[0].post(f'/api/projects/{seg["id"]}/images',files={'files':('mask.png',buffer.getvalue(),'image/png')}).json()[0]
        cl=owner[0].post(f'/api/projects/{seg["id"]}/classes',json={'name':'dog'}).json()
        assert owner[0].post(f'/api/images/{img["id"]}/annotations',json={'class_id':cl['id'],'annotation_type':'polygon','points':[[1,1],[50,1],[20,50]]}).status_code==201
    role(team,'admin')
    assert member[0].request('DELETE',base,json={'confirmation':ws['name']}).status_code==403
    assert owner[0].request('DELETE',base,json={'confirmation':'wrong'}).status_code==400
    folder=Path(owner[0].get(f'/api/images/{i["id"]}').json()['filepath']).parent.parent
    response=owner[0].request('DELETE',base,json={'confirmation':ws['name']}); assert response.status_code==200,response.text
    assert not folder.exists()
    assert owner[0].get(f'/api/projects/{p["id"]}').status_code==404
    assert stranger[0].get('/api/workspaces').status_code==200
    with SessionLocal() as db:
        assert db.get(Workspace,uuid.UUID(ws['id'])) is None
        assert db.scalar(select(AuditLog).where(AuditLog.workspace_id==uuid.UUID(ws['id']),AuditLog.action=='workspace.deleted'))

def test_active_ai_operation_blocks_delete_and_member_removal(team):
    owner,member,_,_,ws,p,*_=team; wid=uuid.UUID(ws['id'])
    with SessionLocal() as db, workspace_operation(db,wid):
        assert owner[0].request('DELETE',f'/api/workspaces/{wid}',json={'confirmation':ws['name']}).status_code==409
        assert owner[0].delete(f'/api/workspaces/{wid}/members/{member[2]["id"]}').status_code==409
    assert owner[0].get(f'/api/projects/{p["id"]}').status_code==200

def test_legacy_workspace_dry_run_idempotence_and_orphan_lock(people):
    owner=people[0]
    with SessionLocal() as db:
        owned=Project(name='Preserve ownership',owner_user_id=uuid.UUID(owner[2]['id']));orphan=Project(name='Unclaimed');db.add_all([owned,orphan]);db.commit();ids=[owned.id,orphan.id]
        report=migrate(db,False,ids);assert len(report['mapped'])==1 and report['locked']==[orphan.id]
        assert db.get(Project,owned.id).workspace_id is None
        original_updated_at=owned.updated_at
        migrate(db,True,ids); db.refresh(owned)
        assert owned.updated_at==original_updated_at
        assert owned.workspace_id is not None and owned.owner_user_id==uuid.UUID(owner[2]['id'])
        second=migrate(db,True,ids);assert second['already_mapped']==[owned.id]
        assert db.get(Project,orphan.id).workspace_id is None
    assert owner[0].get(f'/api/projects/{ids[1]}').status_code==404

def test_every_resource_route_has_explicit_policy():
    from app.main import app
    from app.auth_dependencies import RESOURCE_PERMISSIONS
    for route in app.routes:
        if not (set(getattr(route,'tags',[])) & {'projects','classes','images','annotations','dataset','auto-labeling'}): continue
        if route.path=='/api/projects': continue
        for method in route.methods:
            assert (method,route.path) in RESOURCE_PERMISSIONS,(method,route.path)

def test_project_quarantine_restores_on_database_commit_failure(team,monkeypatch):
    from app.services.project_delete_service import delete_projects
    owner,_,_,_,ws,p,c,i,a=team
    filepath=Path(owner[0].get(f'/api/images/{i["id"]}').json()['filepath'])
    with SessionLocal() as db:
        project=db.get(Project,p['id'])
        def fail():raise RuntimeError('Simulated commit failure')
        monkeypatch.setattr(db,'commit',fail)
        with pytest.raises(RuntimeError,match='Simulated'):
            delete_projects(db,[project])
        assert filepath.is_file() and db.get(Project,p['id']) is not None
        assert db.get(Annotation,a['id']) is not None

def test_cross_workspace_bulk_ids_never_partially_delete(team):
    owner,_,stranger,_,ws,p,c,i,a=team
    other_project=stranger[0].post('/api/projects',json={'name':'Other tenant'}).json()
    buffer=io.BytesIO();PillowImage.new('RGB',(20,20)).save(buffer,format='PNG')
    other_image=stranger[0].post(f'/api/projects/{other_project["id"]}/images',files={'files':('other.png',buffer.getvalue(),'image/png')}).json()[0]
    result=owner[0].post('/api/images/bulk-delete',json={'project_id':p['id'],'image_ids':[i['id'],other_image['id']]})
    assert result.status_code==400
    assert owner[0].get(f'/api/images/{i["id"]}').status_code==200
    assert stranger[0].get(f'/api/images/{other_image["id"]}').status_code==200
