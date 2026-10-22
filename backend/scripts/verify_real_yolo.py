"""Optional real-model API smoke against isolated Phase 6 browser fixtures only."""
import io
import os
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
if not (make_url(os.environ['DATABASE_URL']).database or '').startswith('annotation_phase6_test_'):raise RuntimeError('Disposable database required')
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app,headers={'Origin':os.environ['CORS_ORIGINS']})
login=client.post('/api/auth/login',json={'email':'owner-phase6@example.com','password':'Phase6-UI-only-passphrase-2026'})
assert login.status_code==200,login.text
client.headers['Authorization']='Bearer '+login.json()['access_token']
projects=client.get('/api/projects').json()
for name,endpoint in [('Demo Traffic','auto-label'),('Demo Masks','auto-segment')]:
    project=next(row for row in projects if row['name']==name)
    image=client.get(f'/api/projects/{project["id"]}/images').json()[0]
    result=client.post(f'/api/images/{image["id"]}/{endpoint}',json={})
    assert result.status_code==200,result.text
    accepted=client.post(f'/api/images/{image["id"]}/predictions/accept-all')
    assert accepted.status_code==200 and accepted.json()['failed']==0,accepted.text
    exported=client.post(f'/api/projects/{project["id"]}/dataset/export/yolo')
    assert exported.status_code==200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive: assert any(path.endswith('data.yaml') for path in archive.namelist())
    print('PASS REAL YOLO',endpoint,':',len(result.json()['predictions']),'predictions; accept-all + ZIP export OK')
