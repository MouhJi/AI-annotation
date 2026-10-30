import io
import uuid
import zipfile
from datetime import timedelta
import pytest
from PIL import Image as PILImage
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Annotation, Image, ImageRevision, ReviewEvent, CommentThread, ReviewComment, AutoLabelPrediction, WorkspaceMember, User, AnnotationActivity
from app.models.auth import utcnow
from app.schemas.quality import ActivityHeartbeat
from app.services.quality_metrics import heartbeat
from .test_workspaces import people, team, role


@pytest.fixture
def quality(team):
    owner, annotator, reviewer, reviewer2, ws, project, label, *_ = team
    role(team, 'annotator')
    with SessionLocal() as db:
        for person in (reviewer, reviewer2):
            db.add(WorkspaceMember(workspace_id=uuid.UUID(ws['id']), user_id=uuid.UUID(person[2]['id']), role='reviewer'))
        db.commit()
    buffer=io.BytesIO(); PILImage.new('RGB',(100,80)).save(buffer,format='PNG')
    image=owner[0].post(f'/api/projects/{project["id"]}/images',files={'files':('quality.png',buffer.getvalue(),'image/png')}).json()[0]
    annotation=annotator[0].post(f'/api/images/{image["id"]}/annotations',json={'class_id':label['id'],'x':2,'y':2,'width':20,'height':20}).json()
    return owner,annotator,reviewer,reviewer2,project,label,image,annotation


def status(person, image): return person[0].get(f'/api/images/{image["id"]}/review').json()
def command(person,image):
    detail=status(person,image)
    return {'expected_revision':detail['revision'],'expected_review_version':detail['review_version']}
def batch(person,image):
    rows=person[0].get(f'/api/images/{image["id"]}/annotations').json()
    return {'expected_versions':{str(row['id']):row['version'] for row in rows},'items':[
        {key:row[key] for key in ['id','class_id','annotation_type','x','y','width','height','points']} for row in rows]}
def submit(person,image,**extra):
    return person[0].post(f'/api/images/{image["id"]}/review/submit',json={**command(person,image),'annotations':batch(person,image),**extra})
def decision(person,image,action,**extra):
    return person[0].post(f'/api/images/{image["id"]}/review/{action}',json={**command(person,image),**extra})


def test_drafts_noop_revisions_and_full_review_cycle(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    before=status(actor,i)
    assert before['state']=='in_progress'
    assert actor[0].put(f'/api/images/{i["id"]}/annotations',json=batch(actor,i)).status_code==200
    assert status(actor,i)['revision']==before['revision']
    assert submit(actor,i).status_code==200
    pending=command(r1,i)
    assert status(actor,i)['state']=='pending_review'
    for method,path,payload in [
        ('put',f'/api/annotations/{a["id"]}',{'class_id':c['id'],'x':3,'y':2,'width':20,'height':20,'expected_version':1}),
        ('post',f'/api/images/{i["id"]}/annotations',{'class_id':c['id'],'x':1,'y':1,'width':2,'height':2}),
        ('put',f'/api/images/{i["id"]}/annotations',batch(actor,i)),
        ('delete',f'/api/images/{i["id"]}/annotations',{'expected_versions':{str(a['id']):1}}),
    ]:
        assert actor[0].request(method,path,json=payload).status_code==409
    assert actor[0].delete(f'/api/annotations/{a["id"]}?expected_version=1').status_code==409
    assert decision(r1,i,'reject',reason='  ',error_category='wrong_class').status_code==422
    assert decision(r1,i,'reject',reason='Tighten the box',error_category='inaccurate_bbox').status_code==200
    stale=r2[0].post(f'/api/images/{i["id"]}/review/approve',json=pending)
    assert stale.status_code==409
    payload=batch(actor,i);payload['items'][0]['x']=3
    assert actor[0].put(f'/api/images/{i["id"]}/annotations',json=payload).status_code==200
    assert submit(actor,i).status_code==200
    assert decision(r1,i,'approve').status_code==200
    assert decision(r2,i,'approve').status_code==409
    assert status(actor,i)['state']=='approved'
    assert decision(r2,i,'reopen').status_code==200
    assert status(actor,i)['approved_revision'] is None
    assert submit(actor,i).status_code==200
    assert decision(r2,i,'approve').status_code==200
    history=status(actor,i)['history']
    assert {'content_changed','submitted','changes_requested','approved','reopened'} <= {row['action'] for row in history}


def test_no_self_approval_even_admin_and_reviewer_corrections(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    assert submit(actor,i).status_code==200
    assert decision(actor,i,'approve').status_code==403
    assert decision(r1,i,'withdraw').status_code==200
    payload=batch(r1,i);payload['items'][0]['x']=4
    assert r1[0].put(f'/api/images/{i["id"]}/annotations',json=payload).status_code==200
    assert submit(r1,i).status_code==200
    assert decision(r1,i,'approve').status_code==403
    assert status(r1,i)['independent_review_required'] is True
    assert decision(r2,i,'approve').status_code==200
    assert decision(owner,i,'reopen').status_code==200
    payload=batch(owner,i);payload['items'][0]['x']=5
    assert owner[0].put(f'/api/images/{i["id"]}/annotations',json=payload).status_code==200
    assert submit(owner,i).status_code==200
    assert decision(owner,i,'approve').status_code==403
    assert decision(r2,i,'approve').status_code==200


def test_atomic_submit_failure_and_negative_confirmation_export(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    payload=batch(actor,i);payload['items']=[]
    before=status(actor,i)
    response=actor[0].post(f'/api/images/{i["id"]}/review/submit',json={**command(actor,i),'annotations':payload})
    assert response.status_code==422
    assert len(actor[0].get(f'/api/images/{i["id"]}/annotations').json())==1
    assert status(actor,i)['revision']==before['revision']
    response=actor[0].post(f'/api/images/{i["id"]}/review/submit',json={**command(actor,i),'annotations':payload,'negative_confirmed':True})
    assert response.status_code==200,response.text
    assert decision(r1,i,'approve').status_code==200
    assert owner[0].patch(f'/api/projects/{p["id"]}/review-settings',json={'require_review':True}).status_code==200
    preview=owner[0].get(f'/api/projects/{p["id"]}/dataset/export-preview').json()
    assert preview['total_selected']==2 and preview['eligible']==1
    response=owner[0].post(f'/api/projects/{p["id"]}/dataset/export/yolo')
    assert response.status_code==200,response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        labels=[name for name in archive.namelist() if name.endswith('.txt')]
        assert len(labels)==1 and archive.read(labels[0])==b''
    assert decision(r1,i,'reopen').status_code==200
    assert owner[0].get(f'/api/projects/{p["id"]}/dataset/export-preview').json()['eligible']==0
    assert owner[0].post(f'/api/projects/{p["id"]}/dataset/export/yolo').status_code==400
    assert owner[0].patch(f'/api/projects/{p["id"]}/review-settings',json={'require_review':False}).status_code==200
    assert owner[0].post(f'/api/projects/{p["id"]}/dataset/export/yolo').status_code==200


def test_export_snapshot_and_image_revision_conflict(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    assert submit(actor,i).status_code==200
    assert decision(r1,i,'approve').status_code==200
    owner[0].patch(f'/api/projects/{p["id"]}/review-settings',json={'require_review':True})
    revision=status(actor,i)['revision']
    frozen=actor[0].get(f'/api/images/{i["id"]}/revisions/{revision}').json()
    # Simulate a corrupt/out-of-band live row: approved export must use the snapshot.
    with SessionLocal() as db:
        db.get(Annotation,a['id']).x=50;db.commit()
    response=owner[0].post(f'/api/projects/{p["id"]}/dataset/export/yolo')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        labels=[name for name in archive.namelist() if name.endswith('.txt')]
        assert '0.120000' in archive.read(labels[0]).decode()
    assert frozen['objects'][0]['x']==2
    assert decision(r1,i,'reopen').status_code==200
    payload=batch(actor,i);payload['expected_revision']=revision-1
    assert actor[0].put(f'/api/images/{i["id"]}/annotations',json=payload).status_code==409


def test_comments_stable_object_deleted_history_and_no_revision_changes(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    before=status(actor,i)
    url=f'/api/images/{i["id"]}/threads'
    thread=actor[0].post(url,json={'object_id':a['id'],'body':'Please check this edge.'}).json()
    assert r1[0].post(f'/api/threads/{thread["id"]}/comments',json={'body':'Checked.'}).status_code==201
    assert r1[0].patch(f'/api/threads/{thread["id"]}',json={'resolved':True,'expected_version':1}).status_code==200
    row=actor[0].get(url).json()[0]
    assert row['resolved_by']['id']==r1[2]['id'] and row['resolved_at'] and len(row['comments'])==2
    assert r2[0].patch(f'/api/threads/{thread["id"]}',json={'resolved':False,'expected_version':1}).status_code==409
    assert actor[0].patch(f'/api/threads/{thread["id"]}',json={'resolved':False,'expected_version':2}).status_code==200
    assert status(actor,i)['revision']==before['revision']
    assert submit(actor,i).status_code==200
    assert decision(r1,i,'approve').status_code==200  # Open threads are informative, not a gate.
    assert actor[0].post(url,json={'body':'Image discussion.'}).status_code==201
    assert status(actor,i)['state']=='approved'
    assert decision(r1,i,'reopen').status_code==200
    assert actor[0].delete(f'/api/annotations/{a["id"]}?expected_version=1').status_code==204
    assert actor[0].get(url).json()[0]['object_deleted'] is True


def test_cross_project_permissions_and_personal_metrics(quality,people):
    owner,actor,r1,r2,p,c,i,a=quality
    foreign=owner[0].post('/api/projects',json={'name':'Private'}).json()
    for suffix in ['review-queue','quality','dataset/export-preview']:
        assert actor[0].get(f'/api/projects/{foreign["id"]}/{suffix}').status_code==404
    assert actor[0].patch(f'/api/projects/{p["id"]}/review-settings',json={'require_review':True}).status_code==403
    assert actor[0].get(f'/api/projects/{p["id"]}/quality',params={'user_id':r1[2]['id']}).status_code==403
    empty=actor[0].get(f'/api/projects/{p["id"]}/quality').json()
    assert empty['first_pass_rate'] is None and empty['average_rework_rounds'] is None
    assert submit(actor,i).status_code==200
    assert actor[0].get(f'/api/projects/{p["id"]}/quality').json()['first_pass_decided']==0
    assert decision(r1,i,'reject',reason='Wrong class',error_category='wrong_class').status_code==200
    assert submit(actor,i).status_code==200
    assert decision(r2,i,'approve').status_code==200
    data=actor[0].get(f'/api/projects/{p["id"]}/quality').json()
    assert data['unique_submitted_images']==1 and data['submissions']==2 and data['returns']==1
    assert data['first_pass_decided']==1 and data['first_pass_rate']==0 and data['average_rework_rounds']==1
    assert data['approved_images']==1


def test_activity_bounded_deduplication_across_tabs_and_idle(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    now=utcnow();client=uuid.uuid4();other=uuid.uuid4()
    with SessionLocal() as db:
        user=db.get(User,uuid.UUID(actor[2]['id']));image=db.get(Image,i['id'])
        def pulse(client_id,sequence,at,elapsed=15): return heartbeat(db,image,user,ActivityHeartbeat(client_id=client_id,sequence=sequence,elapsed_seconds=elapsed),now+timedelta(seconds=at))
        assert pulse(client,1,0)['credited_seconds']==0
        assert pulse(client,2,10)['credited_seconds']==10
        assert pulse(client,2,11)['credited_seconds']==0
        assert pulse(other,1,15)['credited_seconds']==0
        assert pulse(client,3,20)['credited_seconds']==10
        assert pulse(client,4,100)['credited_seconds']==0
        assert pulse(other,2,130)['credited_seconds']==0
        assert pulse(other,3,140)['credited_seconds']==10
        assert sum(row.seconds for row in db.scalars(select(AnnotationActivity).where(AnnotationActivity.user_id==user.id)))==30


def test_ai_acceptance_obeys_lock_revision_and_source(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    with SessionLocal() as db:
        prediction=AutoLabelPrediction(image_id=i['id'],model_class_id=1,model_class_name='cat',mapped_class_id=c['id'],x=1,y=1,width=10,height=10,confidence=.9)
        db.add(prediction);db.commit();pid=prediction.id
    before=status(actor,i)['revision']
    assert submit(actor,i).status_code==200
    assert actor[0].post(f'/api/predictions/{pid}/accept').status_code==409
    assert actor[0].post(f'/api/images/{i["id"]}/predictions/accept-all').status_code==409
    assert decision(actor,i,'withdraw').status_code==200
    edited=r1[0].put(f'/api/predictions/{pid}',json={'mapped_class_id':c['id'],'prediction_type':'bbox','x':2,'y':1,'width':10,'height':10})
    assert edited.status_code==200,edited.text
    assert actor[0].post(f'/api/predictions/{pid}/accept').status_code==200
    assert status(actor,i)['revision']==before+1
    rows=actor[0].get(f'/api/images/{i["id"]}/annotations').json()
    assert next(row for row in rows if row['id']!=a['id'])['source']=='ai_edited'
    assert submit(actor,i).status_code==200
    assert r1[2]['id'] in {person['id'] for person in status(actor,i)['contributors']}
    assert decision(r1,i,'approve').status_code==403  # Editing an AI proposal cannot bypass independent review.
    assert decision(r2,i,'approve').status_code==200


def test_history_retained_and_detached_when_image_deleted(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    thread=actor[0].post(f'/api/images/{i["id"]}/threads',json={'body':'Retain this discussion.'}).json()
    assert submit(actor,i).status_code==200
    assert owner[0].delete(f'/api/images/{i["id"]}').status_code==200
    with SessionLocal() as db:
        for model in (ImageRevision,ReviewEvent,CommentThread):
            rows=list(db.scalars(select(model).where(model.original_image_id==i['id'])))
            assert rows and all(row.image_id is None for row in rows)
        assert db.scalar(select(ReviewComment).where(ReviewComment.thread_id==thread['id'])).body=='Retain this discussion.'
    assert actor[0].post(f'/api/threads/{thread["id"]}/comments',json={'body':'Cannot reattach'}).status_code==404


def test_approved_segmentation_uses_polygon_snapshot(quality):
    owner,actor,r1,r2,p,c,i,a=quality
    # Only fixture setup changes project mode; all annotation writes use the API.
    with SessionLocal() as db:
        image=db.get(Image,i['id']);image.project.annotation_mode='instance_segmentation';db.commit()
    payload=batch(actor,i)
    payload['items']=[{'id':a['id'],'class_id':c['id'],'annotation_type':'polygon','points':[[10,10],[30,10],[30,30],[10,30]]}]
    assert actor[0].put(f'/api/images/{i["id"]}/annotations',json=payload).status_code==200
    assert submit(actor,i).status_code==200
    assert decision(r1,i,'approve').status_code==200
    owner[0].patch(f'/api/projects/{p["id"]}/review-settings',json={'require_review':True})
    response=owner[0].post(f'/api/projects/{p["id"]}/dataset/export/yolo')
    assert response.status_code==200,response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        labels=[name for name in archive.namelist() if name.endswith('.txt')]
        assert len(labels)==1
        assert archive.read(labels[0]).decode().strip()=='0 0.100000 0.125000 0.300000 0.125000 0.300000 0.375000 0.100000 0.375000'
