import os, tempfile
from pathlib import Path
os.environ["DATABASE_URL"]="sqlite://"
os.environ["STORAGE_PATH"]=tempfile.mkdtemp()
from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app
Base.metadata.create_all(engine); client=TestClient(app, headers={"Origin":"http://localhost:5173"})
client.post("/api/auth/register", json={"email":"regression@example.com","password":"regression-passphrase-2026","full_name":"Regression Owner"})
client.headers["Authorization"]="Bearer "+client.post("/api/auth/login",json={"email":"regression@example.com","password":"regression-passphrase-2026"}).json()["access_token"]
def project(): return client.post("/api/projects",json={"name":"Test Project"}).json()
def test_project_and_class_crud():
    p=project(); assert client.get("/api/projects").status_code==200
    c=client.post(f"/api/projects/{p['id']}/classes",json={"name":"car"}).json(); assert c["name"]=="car"
    renamed=client.put(f"/api/classes/{c['id']}",json={"name":"vehicle"}); assert renamed.status_code==200 and renamed.json()["name"]=="vehicle"
    duplicate=client.post(f"/api/projects/{p['id']}/classes",json={"name":"truck"}).json()
    assert client.put(f"/api/classes/{c['id']}",json={"name":"truck"}).status_code==409
    assert client.delete(f"/api/classes/{c['id']}").status_code==200
def test_image_and_annotation_validation():
    p=project(); c=client.post(f"/api/projects/{p['id']}/classes",json={"name":"car"}).json()
    from PIL import Image
    path=Path(tempfile.mktemp(suffix=".png")); Image.new("RGB",(100,80)).save(path)
    with path.open("rb") as f: image=client.post(f"/api/projects/{p['id']}/images",files={"files":("a.png",f,"image/png")}).json()[0]
    response=client.post(f"/api/images/{image['id']}/annotations",json={"class_id":c["id"],"x":90,"y":0,"width":20,"height":10}); assert response.status_code==400
    response=client.post(f"/api/images/{image['id']}/annotations",json={"class_id":c["id"],"x":5,"y":5,"width":20,"height":10}); assert response.status_code==201
    assert len(client.get(f"/api/images/{image['id']}/annotations").json())==1

def test_delete_all_annotations_only_affects_requested_image():
    p=project(); c=client.post(f"/api/projects/{p['id']}/classes",json={"name":"car"}).json()
    from PIL import Image
    paths=[]
    for index in range(2):
        path=Path(tempfile.mktemp(suffix=".png")); Image.new("RGB",(100,80)).save(path); paths.append(path)
    images=[]
    for path in paths:
        with path.open("rb") as file: images.append(client.post(f"/api/projects/{p['id']}/images",files={"files":("a.png",file,"image/png")}).json()[0])
    for image in images:
        assert client.post(f"/api/images/{image['id']}/annotations",json={"class_id":c["id"],"x":5,"y":5,"width":20,"height":10}).status_code==201
    assert client.request("DELETE",f"/api/images/{images[0]['id']}/annotations",json={"expected_versions":{str(a["id"]):a["version"] for a in client.get(f"/api/images/{images[0]['id']}/annotations").json()}}).json()=={"deleted_count":1}
    assert client.get(f"/api/images/{images[0]['id']}/annotations").json()==[]
    assert len(client.get(f"/api/images/{images[1]['id']}/annotations").json())==1
    assert client.request("DELETE",f"/api/images/{images[0]['id']}/annotations",json={"expected_versions":{}}).json()=={"deleted_count":0}

def test_delete_single_image_cleans_annotations_predictions_and_file():
    p=project(); c=client.post(f"/api/projects/{p['id']}/classes",json={"name":"car"}).json()
    from PIL import Image as PillowImage
    path=Path(tempfile.mktemp(suffix=".png")); PillowImage.new("RGB",(100,80)).save(path)
    with path.open("rb") as file: image=client.post(f"/api/projects/{p['id']}/images",files={"files":("delete-me.png",file,"image/png")}).json()[0]
    assert client.post(f"/api/images/{image['id']}/annotations",json={"class_id":c["id"],"x":5,"y":5,"width":20,"height":10}).status_code==201
    detail=client.get(f"/api/images/{image['id']}").json(); stored=Path(detail["filepath"])
    response=client.delete(f"/api/images/{image['id']}")
    assert response.status_code==200 and response.json()["deleted_image_id"]==image["id"]
    assert not stored.exists() and client.get(f"/api/images/{image['id']}").status_code==404
    assert client.get(f"/api/projects/{p['id']}/classes").json()[0]["id"]==c["id"]

def test_bulk_delete_rejects_foreign_or_duplicate_ids_without_partial_delete():
    from PIL import Image as PillowImage
    one,two=project(),project(); ids=[]
    for index in range(2):
        path=Path(tempfile.mktemp(suffix=".png")); PillowImage.new("RGB",(30,30)).save(path)
        with path.open("rb") as file: ids.append(client.post(f"/api/projects/{one['id']}/images",files={"files":(f"bulk-{index}.png",file,"image/png")}).json()[0]["id"])
    path=Path(tempfile.mktemp(suffix=".png")); PillowImage.new("RGB",(30,30)).save(path)
    with path.open("rb") as file: foreign=client.post(f"/api/projects/{two['id']}/images",files={"files":("foreign.png",file,"image/png")}).json()[0]["id"]
    assert client.post("/api/images/bulk-delete",json={"project_id":one["id"],"image_ids":[ids[0],foreign]}).status_code==400
    assert len(client.get(f"/api/projects/{one['id']}/images").json())==2
    assert client.post("/api/images/bulk-delete",json={"project_id":one["id"],"image_ids":[ids[0],ids[0]]}).status_code==400
    response=client.post("/api/images/bulk-delete",json={"project_id":one["id"],"image_ids":ids})
    assert response.status_code==200 and set(response.json()["deleted_image_ids"])==set(ids)

def test_delete_project_removes_only_owned_rows_and_storage():
    from PIL import Image as PillowImage
    one,two=project(),project()
    class_one=client.post(f"/api/projects/{one['id']}/classes",json={"name":"car"}).json()
    class_two=client.post(f"/api/projects/{two['id']}/classes",json={"name":"dog"}).json()
    images=[]
    for project_item,label,name in [(one,class_one,"one.png"),(two,class_two,"two.png")]:
        path=Path(tempfile.mktemp(suffix=".png")); PillowImage.new("RGB",(60,50)).save(path)
        with path.open("rb") as file: image=client.post(f"/api/projects/{project_item['id']}/images",files={"files":(name,file,"image/png")}).json()[0]
        assert client.post(f"/api/images/{image['id']}/annotations",json={"class_id":label["id"],"x":4,"y":4,"width":20,"height":12}).status_code==201
        images.append(image)
    stored=Path(client.get(f"/api/images/{images[0]['id']}").json()["filepath"])
    response=client.delete(f"/api/projects/{one['id']}")
    assert response.status_code==200 and response.json()["deleted_project_id"]==one["id"]
    assert not stored.exists() and client.get(f"/api/projects/{one['id']}").status_code==404
    assert client.get(f"/api/images/{images[0]['id']}").status_code==404
    assert client.get(f"/api/images/{images[1]['id']}").status_code==200
    assert client.get(f"/api/projects/{two['id']}/classes").json()[0]["id"]==class_two["id"]

def test_delete_empty_project_and_repeated_delete():
    item=project(); assert client.delete(f"/api/projects/{item['id']}").status_code==200
    assert client.delete(f"/api/projects/{item['id']}").status_code==404
