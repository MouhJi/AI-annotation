from pathlib import Path
from fastapi import HTTPException
from PIL import Image as PillowImage
from .test_api import client, project

def upload(project_id: int, name: str) -> dict:
    path = Path(f"/tmp/{name}"); PillowImage.new("RGB", (100, 80), "white").save(path)
    with path.open("rb") as file:
        return client.post(f"/api/projects/{project_id}/images", files={"files": (name, file, "image/png")}).json()[0]

def mock_infer(_, __):
    return "mock-yolo.pt", [
        {"model_class_id": 2, "model_class_name": "car", "x": 10, "y": 20, "width": 40, "height": 20, "confidence": .91},
        {"model_class_id": 0, "model_class_name": "person", "x": 1, "y": 1, "width": 5, "height": 5, "confidence": .95},
    ]

def test_yolo_output_is_normalized_and_thresholded(monkeypatch, tmp_path):
    from app.services.yolo_service import yolo_service
    class Value:
        def __init__(self, value): self.value = value
        def item(self): return self.value
    class Vector:
        def __init__(self, values): self.values = values
        def __getitem__(self, _): return Value(self.values[0]) if len(self.values) == 1 else self
        def tolist(self): return self.values
    class Box:
        def __init__(self, confidence, cls, xyxy): self.conf = Vector([confidence]); self.cls = Vector([cls]); self.xyxy = Vector(xyxy)
    class Model:
        def predict(self, **_): return [type("Result", (), {"names": {2: "car", 0: "person"}, "boxes": [Box(.91, 2, [10, 20, 50, 40]), Box(.1, 0, [0, 0, 2, 2])]})()]
    monkeypatch.setattr(yolo_service, "_load", lambda: (Model(), "cpu"))
    image = tmp_path / "input.jpg"; image.write_bytes(b"x")
    _, output = yolo_service.infer(image, .25)
    assert output == [{"model_class_id": 2, "model_class_name": "car", "x": 10.0, "y": 20.0, "width": 40.0, "height": 20.0, "confidence": .91}]

def test_auto_label_mapping_review_accept_and_idempotency(monkeypatch):
    monkeypatch.setattr("app.services.auto_label_service.yolo_service.infer", mock_infer)
    p = project(); car = client.post(f"/api/projects/{p['id']}/classes", json={"name": "car"}).json(); image = upload(p["id"], "auto.png")
    mapping = client.put(f"/api/projects/{p['id']}/class-mappings", json={"model_class_id": 2, "model_class_name": "car", "class_id": car["id"]})
    assert mapping.status_code == 200 and mapping.json()["class_id"] == car["id"]
    response = client.post(f"/api/images/{image['id']}/auto-label", json={"confidence_threshold": .25})
    assert response.status_code == 200
    body = response.json(); assert len(body["predictions"]) == 2 and "person" in body["warnings"][0]
    car_prediction = next(item for item in body["predictions"] if item["model_class_name"] == "car")
    accepted = client.post(f"/api/predictions/{car_prediction['id']}/accept"); assert accepted.status_code == 200
    repeated = client.post(f"/api/predictions/{car_prediction['id']}/accept"); assert repeated.status_code == 200
    assert repeated.json()["annotation_id"] == accepted.json()["annotation_id"]
    annotations = client.get(f"/api/images/{image['id']}/annotations").json(); assert len(annotations) == 1 and annotations[0]["class_id"] == car["id"]

def test_unmapped_classes_are_created_only_when_accepted(monkeypatch):
    monkeypatch.setattr("app.services.auto_label_service.yolo_service.infer", mock_infer)
    p = project(); image = upload(p["id"], "unmapped.png")
    predictions = client.post(f"/api/images/{image['id']}/auto-label", json={}).json()["predictions"]
    assert all(item["mapped_class_id"] is None for item in predictions)
    rejected = client.post(f"/api/predictions/{predictions[0]['id']}/reject"); assert rejected.json()["status"] == "REJECTED"
    assert client.get(f"/api/projects/{p['id']}/classes").json() == []
    summary = client.post(f"/api/images/{image['id']}/predictions/accept-all").json(); assert summary == {"accepted": 1, "skipped": 0, "failed": 0}
    assert [item["class_name"] for item in client.get(f"/api/images/{image['id']}/annotations").json()] == ["person"]

    image = upload(p["id"], "accept-unmapped.png")
    predictions = client.post(f"/api/images/{image['id']}/auto-label", json={}).json()["predictions"]
    result = client.post(f"/api/images/{image['id']}/predictions/accept-all").json()
    assert result == {"accepted": 2, "skipped": 0, "failed": 0}
    names = {item["name"] for item in client.get(f"/api/projects/{p['id']}/classes").json()}
    assert names == {"car", "person"}
    annotations = client.get(f"/api/images/{image['id']}/annotations").json()
    assert {item["class_name"] for item in annotations} == {"car", "person"}

def test_same_model_class_id_never_falls_back_to_a_database_id(monkeypatch):
    monkeypatch.setattr("app.services.auto_label_service.yolo_service.infer", mock_infer)
    p=project(); first=client.post(f"/api/projects/{p['id']}/classes",json={"name":"a"}).json(); image=upload(p["id"],"no-fallback.png")
    predictions=client.post(f"/api/images/{image['id']}/auto-label",json={}).json()["predictions"]
    assert all(item["mapped_class_id"] != first["id"] for item in predictions)

def test_mapping_rejects_class_from_another_project_and_batch_continues(monkeypatch):
    monkeypatch.setattr("app.services.auto_label_service.yolo_service.infer", mock_infer)
    one, two = project(), project(); foreign = client.post(f"/api/projects/{two['id']}/classes", json={"name": "foreign"}).json()
    assert client.put(f"/api/projects/{one['id']}/class-mappings", json={"model_class_id": 2, "model_class_name": "car", "class_id": foreign["id"]}).status_code == 400
    good = upload(one["id"], "good.png")
    batch = client.post(f"/api/projects/{one['id']}/auto-label-batch", json={"image_ids": [good["id"], 999999], "confidence_threshold": .25})
    assert [item["status"] for item in batch.json()] == ["COMPLETED", "FAILED"]

def test_class_cannot_be_deleted_when_referenced_by_mapping_or_prediction(monkeypatch):
    monkeypatch.setattr("app.services.auto_label_service.yolo_service.infer", mock_infer)
    p=project(); car=client.post(f"/api/projects/{p['id']}/classes",json={"name":"car"}).json(); image=upload(p["id"],"mapped.png")
    client.put(f"/api/projects/{p['id']}/class-mappings",json={"model_class_id":2,"model_class_name":"car","class_id":car["id"]})
    client.post(f"/api/images/{image['id']}/auto-label",json={})
    response=client.delete(f"/api/classes/{car['id']}")
    assert response.status_code==409
    assert response.json()["detail"]["references"]=={"annotations":0,"predictions":1,"mappings":1}

def test_missing_weights_is_reported(monkeypatch):
    p = project(); image = upload(p["id"], "missing.png")
    def unavailable(*_): raise HTTPException(503, "YOLO model weights not found: missing.pt")
    monkeypatch.setattr("app.services.auto_label_service.yolo_service.infer", unavailable)
    response = client.post(f"/api/images/{image['id']}/auto-label", json={})
    assert response.status_code == 503 and "weights not found" in response.json()["detail"]
