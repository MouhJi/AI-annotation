import io
import zipfile
from pathlib import Path
from PIL import Image as PillowImage
from fastapi import HTTPException
from .test_api import client
from app.services.polygon_service import validate_polygon


def _project():
    return client.post("/api/projects", json={"name": "Segmentation Project", "annotation_mode": "instance_segmentation"}).json()


def _upload(project_id: int):
    source = Path("/tmp/segmentation.png")
    PillowImage.new("RGB", (100, 80), "white").save(source)
    with source.open("rb") as file:
        return client.post(f"/api/projects/{project_id}/images", files={"files": ("segmentation.png", file, "image/png")}).json()[0]


def test_polygon_create_update_delete_and_validation():
    project = _project(); label = client.post(f"/api/projects/{project['id']}/classes", json={"name": "dog"}).json(); image = _upload(project["id"])
    payload = {"class_id": label["id"], "annotation_type": "polygon", "points": [[10, 10], [50, 10], [35, 40]]}
    created = client.post(f"/api/images/{image['id']}/annotations", json=payload)
    assert created.status_code == 201 and created.json()["annotation_type"] == "polygon"
    assert created.json()["x"] == 10 and created.json()["width"] == 40
    updated = client.put(f"/api/annotations/{created.json()['id']}", json={**payload, "expected_version":1, "points": [[20, 10], [60, 10], [40, 45]]})
    assert updated.status_code == 200 and updated.json()["points"][0] == [20.0, 10.0]
    invalid = client.post(f"/api/images/{image['id']}/annotations", json={**payload, "points": [[1, 1], [2, 2], [3, 3]]})
    assert invalid.status_code == 400
    assert client.delete(f"/api/annotations/{created.json()['id']}?expected_version=2").status_code == 204

def test_polygon_accepts_duplicate_closing_point_from_double_click():
    project = _project(); label = client.post(f"/api/projects/{project['id']}/classes", json={"name": "dog"}).json(); image = _upload(project["id"])
    response = client.post(f"/api/images/{image['id']}/annotations", json={"class_id": label["id"], "annotation_type": "polygon", "points": [[10, 10], [50, 10], [35, 40], [35, 40]]})
    assert response.status_code == 201
    assert response.json()["points"] == [[10.0, 10.0], [50.0, 10.0], [35.0, 40.0]]

def test_polygon_validation_allows_separated_collinear_edges_but_rejects_a_bow_tie():
    # This is a valid concave step shape. Its two right-side vertical edges are
    # collinear but separated, which occurs frequently in YOLO mask contours.
    valid = [[0, 0], [6, 0], [6, 2], [2, 2], [2, 4], [6, 4], [6, 6], [0, 6]]
    assert validate_polygon(valid, 10, 10) == [(float(x), float(y)) for x, y in valid]
    try:
        validate_polygon([[0, 0], [5, 5], [0, 5], [5, 0]], 10, 10)
    except HTTPException as error:
        assert error.detail == "Polygon must not self-intersect"
    else:
        raise AssertionError("bow-tie polygon should be rejected")


def test_segmentation_export_and_detection_mode_rejection():
    project = _project(); label = client.post(f"/api/projects/{project['id']}/classes", json={"name": "dog"}).json(); image = _upload(project["id"])
    assert client.post(f"/api/images/{image['id']}/annotations", json={"class_id": label["id"], "annotation_type": "polygon", "points": [[10, 10], [50, 10], [35, 40]]}).status_code == 201
    assert client.put(f"/api/projects/{project['id']}/dataset/split", json={"train": 100, "val": 0, "test": 0}).status_code == 200
    result = client.post(f"/api/projects/{project['id']}/dataset/export/yolo")
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        label_file = f"segmentation-project/labels/train/{image['id']}_segmentation.txt"
        assert archive.read(label_file).decode().strip() == "0 0.100000 0.125000 0.500000 0.125000 0.350000 0.500000"


def test_auto_segment_accept_creates_the_missing_class(monkeypatch):
    monkeypatch.setattr("app.services.auto_label_service.yolo_service.infer_segmentation", lambda *_: ("mock-seg.pt", [{"model_class_id": 16, "model_class_name": "dog", "x": 10, "y": 10, "width": 40, "height": 30, "points": [[10, 10], [50, 10], [35, 40]], "confidence": .9}]))
    project = _project(); image = _upload(project["id"])
    result = client.post(f"/api/images/{image['id']}/auto-segment", json={})
    assert result.status_code == 200 and result.json()["predictions"][0]["mapped_class_id"] is None
    prediction = result.json()["predictions"][0]
    assert client.post(f"/api/predictions/{prediction['id']}/accept").status_code == 200
    annotation = client.get(f"/api/images/{image['id']}/annotations").json()[0]
    assert annotation["annotation_type"] == "polygon" and annotation["class_name"] == "dog"
