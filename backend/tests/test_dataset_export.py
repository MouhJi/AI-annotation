import io
import zipfile
from pathlib import Path
from PIL import Image as PillowImage
import pytest
from fastapi import HTTPException
from app.services.dataset_service import _counts, yolo_line
from app.schemas.dataset import SplitConfig
from .test_api import client, project

def add_image(project_id: int, name: str = "sample.png") -> dict:
    source = Path(f"/tmp/{name}")
    PillowImage.new("RGB", (100, 80), "white").save(source)
    with source.open("rb") as file:
        response = client.post(f"/api/projects/{project_id}/images", files={"files": (name, file, "image/png")})
    return response.json()[0]

def test_split_counts_and_ratio_validation():
    assert _counts(1, SplitConfig()) == {"train": 1, "val": 0, "test": 0}
    assert _counts(10, SplitConfig()) == {"train": 8, "val": 1, "test": 1}
    p = project()
    assert client.put(f"/api/projects/{p['id']}/dataset/split", json={"train": 80, "val": 10, "test": 5}).status_code == 422

def test_yolo_coordinate_conversion():
    image = type("ImageStub", (), {"width": 100, "height": 80})()
    annotation = type("AnnotationStub", (), {"id": 1, "x": 10, "y": 20, "width": 40, "height": 20})()
    assert yolo_line(annotation, image, 2) == "2 0.300000 0.375000 0.400000 0.250000"
    invalid = type("AnnotationStub", (), {"id": 2, "x": 90, "y": 20, "width": 20, "height": 20})()
    with pytest.raises(HTTPException, match="exceeds image dimensions"):
        yolo_line(invalid, image, 0)

def test_export_contains_yolo_layout_labels_and_unannotated_images():
    p = project()
    car = client.post(f"/api/projects/{p['id']}/classes", json={"name": "car"}).json()
    bus = client.post(f"/api/projects/{p['id']}/classes", json={"name": "bus"}).json()
    annotated = add_image(p["id"], "annotated.png")
    empty = add_image(p["id"], "empty.png")
    response = client.post(f"/api/images/{annotated['id']}/annotations", json={"class_id": bus["id"], "x": 10, "y": 20, "width": 40, "height": 20})
    assert response.status_code == 201
    split = client.put(f"/api/projects/{p['id']}/dataset/split", json={"train": 100, "val": 0, "test": 0})
    assert split.json()["train"] == 2
    exported = client.post(f"/api/projects/{p['id']}/dataset/export/yolo")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names = archive.namelist(); root = "test-project"
        assert f"{root}/data.yaml" in names
        assert f"{root}/images/train/{annotated['id']}_annotated.png" in names
        assert f"{root}/images/train/{empty['id']}_empty.png" in names
        assert archive.read(f"{root}/labels/train/{empty['id']}_empty.txt") == b""
        label = archive.read(f"{root}/labels/train/{annotated['id']}_annotated.txt").decode()
        assert label.startswith("1 0.300000 0.375000 0.400000 0.250000")
        yaml = archive.read(f"{root}/data.yaml").decode()
        assert "nc: 2" in yaml and "'car', 'bus'" in yaml

def test_export_rejects_missing_project():
    assert client.post("/api/projects/999999/dataset/export/yolo").status_code == 404
