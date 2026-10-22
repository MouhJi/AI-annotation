import uuid
import pytest
from sqlalchemy import event, select
from app.database import SessionLocal, engine
from app.models import Annotation, User
from .test_workspaces import team, people, role


def geometry(label, **changes):
    return dict(class_id=label['id'], annotation_type='bbox', x=1, y=1, width=10, height=10, **changes)


def test_creator_editor_noop_spoof_and_rename(team):
    owner,member,stranger,_,ws,p,c,i,a=team
    assert a['created_by']==a['updated_by']=={'id':owner[2]['id'],'full_name':owner[2]['full_name']}
    assert a['created_at'].endswith('Z')
    role(team,'annotator')
    url=f'/api/annotations/{a["id"]}'
    noop=member[0].put(url,json=geometry(c)).json()
    assert noop['updated_by']==a['updated_by'] and noop['updated_at']==a['updated_at']
    edited=member[0].put(url,json={**geometry(c),'width':12,'created_by':stranger[2]['id'],'updated_by':stranger[2]['id'],'expected_version':1}).json()
    assert edited['created_by']==a['created_by'] and edited['updated_by']['id']==member[2]['id']
    assert edited['id']==a['id'] and edited['version']==2
    assert member[0].put(url,json={**geometry(c),'expected_version':1}).status_code==409
    owner[0].patch('/api/users/me',json={'full_name':'Nguyễn An'})
    listed=member[0].get(f'/api/images/{i["id"]}/annotations').json()[0]
    assert listed['created_by']['full_name']=='Nguyễn An'
    assert 'email' not in listed['created_by'] and 'password_hash' not in listed['created_by']
    assert stranger[0].get(f'/api/images/{i["id"]}/annotations').status_code==404
    assert stranger[0].put(url,json=geometry(c)).status_code==404
    owner[0].delete(f'/api/workspaces/{ws["id"]}/members/{member[2]["id"]}')
    assert owner[0].get(f'/api/images/{i["id"]}/annotations').json()[0]['updated_by']['id']==member[2]['id']


def test_atomic_batch_identity_authors_conflict_and_validation(team):
    owner,member,_,_,_,p,c,i,a=team
    role(team,'annotator')
    url=f'/api/images/{i["id"]}/annotations'
    payload={'expected_versions':{str(a['id']):1},'items':[{**geometry(c),'id':a['id']},geometry(c)]}
    result=member[0].put(url,json=payload)
    assert result.status_code==200,result.text
    old,new=result.json()
    assert old==a and new['created_by']['id']==member[2]['id']
    assert member[0].put(url,json=payload).status_code==409
    versions={str(x['id']):x['version'] for x in result.json()}
    invalid={'expected_versions':versions,'items':[{**geometry(c),'id':a['id'],'width':15},{**geometry(c),'x':1000}]}
    assert member[0].put(url,json=invalid).status_code==400
    assert owner[0].get(url).json()==result.json()
    saved=member[0].put(url,json={'expected_versions':versions,'items':[{**geometry(c),'id':a['id'],'width':15}]}).json()
    assert len(saved)==1 and saved[0]['created_by']==a['created_by'] and saved[0]['updated_by']['id']==member[2]['id']


def test_polygon_legacy_and_constant_author_query_count(team):
    owner,member,_,_,_,p,c,i,a=team
    with SessionLocal() as db:
        annotation=db.get(Annotation,a['id']); annotation.created_by=None; annotation.updated_by=None; annotation.source='legacy'
        project=annotation.image.project; project.annotation_mode='instance_segmentation'; db.commit()
    payload={'class_id':c['id'],'annotation_type':'polygon','points':[[5,5],[30,5],[30,25],[5,25]],'created_by':member[2]['id']}
    polygon=owner[0].post(f'/api/images/{i["id"]}/annotations',json=payload).json()
    assert polygon['created_by']['id']==owner[2]['id'] and polygon['points']==payload['points']
    role(team,'reviewer')
    edited=member[0].put(f'/api/annotations/{polygon["id"]}',json={**payload,'points':[[6,5],[30,5],[30,25],[6,25]]}).json()
    assert edited['created_by']==polygon['created_by'] and edited['updated_by']['id']==member[2]['id']
    statements=[]
    def count(conn,cursor,statement,*args): statements.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try: rows=member[0].get(f'/api/images/{i["id"]}/annotations').json()
    finally: event.remove(engine,'before_cursor_execute',count)
    assert rows[0]['created_by'] is None and rows[0]['updated_by'] is None
    author_queries=[sql for sql in statements if 'JOIN users' in sql]
    assert len(author_queries)==1
    with SessionLocal() as db:
        for _ in range(20): db.add(Annotation(image_id=i['id'],class_id=c['id'],x=1,y=1,width=2,height=2,created_by=uuid.UUID(member[2]['id'])))
        db.commit()
    statements.clear(); event.listen(engine,'before_cursor_execute',count)
    try: assert len(member[0].get(f'/api/images/{i["id"]}/annotations').json())==22
    finally: event.remove(engine,'before_cursor_execute',count)
    assert len([sql for sql in statements if 'JOIN users' in sql])==1


@pytest.mark.parametrize('polygon',[False,True])
def test_ai_accepting_user_and_proposals_remain_distinct(team,monkeypatch,polygon):
    owner,member,_,_,_,p,c,i,a=team
    role(team,'annotator')
    if polygon:
        with SessionLocal() as db:
            db.get(Annotation,a['id']).image.project.annotation_mode='instance_segmentation'; db.commit()
    def infer(*args):
        box={'model_class_id':3,'model_class_name':'New AI class','confidence':.9,'x':1,'y':1,'width':10,'height':10}
        if polygon: box['points']=[[1,1],[11,1],[11,11],[1,11]]
        return 'mock-yolo.pt',[box]
    monkeypatch.setattr('app.services.auto_label_service.yolo_service.'+('infer_segmentation' if polygon else 'infer'),infer)
    pending=owner[0].post(f'/api/images/{i["id"]}/'+('auto-segment' if polygon else 'auto-label'),json={}).json()['predictions'][0]
    assert 'created_by' not in pending
    result=member[0].post(f'/api/predictions/{pending["id"]}/accept')
    assert result.status_code==200,result.text
    member[0].post(f'/api/images/{i["id"]}/predictions/accept-all')
    rows=owner[0].get(f'/api/images/{i["id"]}/annotations').json()
    official=next(x for x in rows if x['id']==result.json()['annotation_id'])
    assert official['created_by']['id']==official['updated_by']['id']==member[2]['id']
    assert official['source']=='ai_accepted'
    assert official['annotation_type']==('polygon' if polygon else 'bbox')
