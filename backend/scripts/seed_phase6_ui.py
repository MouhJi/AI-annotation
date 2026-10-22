"""Browser fixtures in a disposable phase6 database only. No production credentials."""
import io
import os
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
if not (make_url(os.environ['DATABASE_URL']).database or '').startswith('annotation_phase6_test_'):raise RuntimeError('Disposable database required')
from fastapi.testclient import TestClient
from PIL import Image as PillowImage, ImageDraw
from app.main import app
from app.database import SessionLocal
from app.models import User,WorkspaceMember
from app.models.auth import utcnow
PASSWORD='Phase6-UI-only-passphrase-2026'
client=TestClient(app,headers={'Origin':os.environ['CORS_ORIGINS']})
for email,name in [('owner-phase6@example.com','Demo Owner'),('viewer-phase6@example.com','Demo Viewer')]:
    result=client.post('/api/auth/register',json={'email':email,'full_name':name,'password':PASSWORD})
    assert result.status_code==201,result.text
    with SessionLocal() as db:
        from sqlalchemy import select
        user=db.scalar(select(User).where(User.email==email));user.email_verified_at=utcnow();db.commit()
        if name=='Demo Viewer':viewer_id=user.id
response=client.post('/api/auth/login',json={'email':'owner-phase6@example.com','password':PASSWORD})
client.headers['Authorization']='Bearer '+response.json()['access_token']
ws=client.post('/api/workspaces',json={'name':'Demo Vision Team','slug':'demo-vision-'+uuid.uuid4().hex,'description':'Isolated Phase 6 browser verification'}).json()
with SessionLocal() as db:
    db.add(WorkspaceMember(workspace_id=uuid.UUID(ws['id']),user_id=viewer_id,role='viewer'));db.commit()
for name,mode in [('Demo Masks','instance_segmentation'),('Demo Traffic','object_detection')]:
    project=client.post('/api/projects',json={'name':name,'workspace_id':ws['id'],'annotation_mode':mode}).json()
    label=client.post(f'/api/projects/{project["id"]}/classes',json={'name':'object'}).json()
    image=PillowImage.new('RGB',(640,400),'#e0f2fe');ImageDraw.Draw(image).polygon([(180,80),(460,100),(380,330),(140,260)],fill='#38bdf8')
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    item=client.post(f'/api/projects/{project["id"]}/images',files={'files':('demo-object.png',buffer.getvalue(),'image/png')}).json()[0]
    geometry={'class_id':label['id'],'annotation_type':'polygon','points':[[180,80],[460,100],[380,330],[140,260]]} if mode=='instance_segmentation' else {'class_id':label['id'],'x':140,'y':80,'width':320,'height':250}
    assert client.post(f'/api/images/{item["id"]}/annotations',json=geometry).status_code==201
    print(name,'project',project['id'],'image',item['id'])
print('Demo Vision Team:',ws['id'])
