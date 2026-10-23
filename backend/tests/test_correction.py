import io,json,uuid,zipfile
import pytest
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Annotation,WorkspaceMember,AuditLog
from .test_workspaces import team,people,role

RANK={'viewer':0,'annotator':1,'reviewer':2,'admin':3,'owner':4}
def prepare(team,actor_role='reviewer',creator_role='annotator',polygon=False):
    owner,actor,_,creator,ws,p,c,i,a=team
    role(team,actor_role)
    with SessionLocal() as db:
        db.add(WorkspaceMember(workspace_id=uuid.UUID(ws['id']),user_id=uuid.UUID(creator[2]['id']),role=creator_role))
        row=db.get(Annotation,a['id']);row.created_by=uuid.UUID(creator[2]['id']);row.updated_by=row.created_by
        if polygon:
            row.image.project.annotation_mode='instance_segmentation';row.annotation_type='polygon';row.points_json='[[1,1],[11,1],[11,11],[1,11]]'
        db.commit()
    return owner,actor,creator,c,i,a

@pytest.mark.parametrize('actor_role',RANK)
@pytest.mark.parametrize('creator_role',RANK)
def test_strict_hierarchy_single_batch_delete(team,actor_role,creator_role):
    owner,actor,creator,c,i,a=prepare(team,actor_role,creator_role)
    payload={'class_id':c['id'],'x':2,'y':2,'width':12,'height':12,'expected_version':1}
    allowed=RANK[actor_role]>RANK[creator_role]
    result=actor[0].put(f'/api/annotations/{a["id"]}',json=payload)
    assert result.status_code==(200 if allowed else 403),result.text
    if not allowed:
        batch=actor[0].put(f'/api/images/{i["id"]}/annotations',json={'expected_versions':{str(a['id']):1},'items':[{**payload,'id':a['id']}]})
        assert batch.status_code==403
        assert actor[0].delete(f'/api/annotations/{a["id"]}?expected_version=1').status_code==403
    else:
        edited=result.json();assert edited['id']==a['id'] and edited['created_by']['id']==creator[2]['id'] and edited['updated_by']['id']==actor[2]['id']
        assert actor[0].delete(f'/api/annotations/{a["id"]}?expected_version=1').status_code==409
        assert actor[0].delete(f'/api/annotations/{a["id"]}?expected_version=2').status_code==204

@pytest.mark.parametrize('polygon',[False,True])
def test_inplace_export_audit_and_soft_delete(team,polygon):
    owner,actor,creator,c,i,a=prepare(team,polygon=polygon)
    newclass=owner[0].post(f'/api/projects/{c["project_id"]}/classes',json={'name':'Corrected'}).json()
    payload={'class_id':newclass['id'],'annotation_type':'polygon' if polygon else 'bbox','x':20,'y':10,'width':20,'height':20}
    if polygon:payload['points']=[[20,10],[40,10],[40,30],[20,30]]
    response=actor[0].put(f'/api/images/{i["id"]}/annotations',json={'expected_versions':{str(a['id']):1},'items':[{**payload,'id':a['id']}]})
    assert response.status_code==200,response.text
    edited=response.json()[0];assert edited['id']==a['id'] and edited['created_by']['id']==creator[2]['id'] and edited['version']==2
    reloaded=actor[0].get(f'/api/images/{i["id"]}/annotations').json();assert len(reloaded)==1 and reloaded[0]['x']==20
    exported=owner[0].post(f'/api/projects/{c["project_id"]}/dataset/export/yolo')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        text=z.read(next(name for name in z.namelist() if name.endswith('.txt'))).decode();assert text.startswith('1 ')
        assert ('0.200000 0.125000' in text) if polygon else ('0.300000 0.250000' in text)
    assert actor[0].delete(f'/api/annotations/{a["id"]}?expected_version=2').status_code==204
    assert actor[0].get(f'/api/images/{i["id"]}/annotations').json()==[]
    with SessionLocal() as db:
        row=db.scalar(select(Annotation).where(Annotation.id==a['id']).execution_options(include_deleted=True))
        assert row.deleted_by==uuid.UUID(actor[2]['id']) and row.created_by==uuid.UUID(creator[2]['id'])
        logs=list(db.scalars(select(AuditLog).where(AuditLog.resource_type=='annotation',AuditLog.resource_id==str(a['id']))))
        assert {log.action for log in logs}=={'annotation.updated','annotation.deleted'}
    exported=owner[0].post(f'/api/projects/{c["project_id"]}/dataset/export/yolo')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:assert z.read(next(name for name in z.namelist() if name.endswith('.txt')))==b''

def test_own_annotation_and_locked_objects_noop(team):
    owner,actor,creator,c,i,a=prepare(team)
    own=actor[0].post(f'/api/images/{i["id"]}/annotations',json={'class_id':c['id'],'x':1,'y':1,'width':5,'height':5}).json()
    assert own['can_edit'] and own['can_delete']
    assert actor[0].put(f'/api/annotations/{own["id"]}',json={'class_id':c['id'],'x':2,'y':1,'width':5,'height':5}).status_code==428
