"""Lazy, process-local Ultralytics YOLO inference service."""
import os
from pathlib import Path
from threading import Lock
from fastapi import HTTPException

class YoloService:
    def __init__(self) -> None:
        self._model = None
        self._model_path: str | None = None
        self._seg_model = None
        self._seg_model_path: str | None = None
        self._lock = Lock()

    def _load(self):
        model_path = os.getenv("YOLO_MODEL_PATH", "yolo11n.pt")
        device = os.getenv("YOLO_DEVICE", "cpu")
        if device not in {"cpu", "cuda"}:
            raise HTTPException(400, "YOLO_DEVICE must be cpu or cuda")
        if device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available(): raise HTTPException(503, "CUDA was requested but is not available")
            except ImportError: raise HTTPException(503, "CUDA was requested but PyTorch is unavailable")
        with self._lock:
            if self._model is not None and self._model_path == model_path:
                return self._model, device
            try:
                from ultralytics import YOLO
                self._model = YOLO(model_path)
                self._model_path = model_path
            except FileNotFoundError:
                raise HTTPException(503, f"YOLO model weights not found: {model_path}")
            except Exception as exc:
                raise HTTPException(503, f"Unable to load YOLO model: {str(exc)[:180]}")
        return self._model, device

    def infer(self, image_path: Path, confidence: float) -> tuple[str, list[dict]]:
        if not image_path.is_file(): raise HTTPException(400, "Image file is missing")
        model, device = self._load()
        try:
            results = model.predict(source=str(image_path), conf=confidence, iou=float(os.getenv("YOLO_IOU_THRESHOLD", "0.45")), device=device, verbose=False)
            result = results[0]; names = result.names
            detections = []
            for box in result.boxes:
                score = float(box.conf[0].item())
                if score < confidence: continue
                class_id = int(box.cls[0].item())
                xyxy = [float(value) for value in box.xyxy[0].tolist()]
                name = names[class_id] if isinstance(names, dict) else names[class_id]
                detections.append({"model_class_id": class_id, "model_class_name": str(name), "x": xyxy[0], "y": xyxy[1], "width": xyxy[2] - xyxy[0], "height": xyxy[3] - xyxy[1], "confidence": score})
            return self._model_path or "default", detections
        except HTTPException: raise
        except Exception as exc: raise HTTPException(500, f"YOLO inference failed: {str(exc)[:180]}")

    def _load_segmentation(self):
        model_path = os.getenv("YOLO_SEG_MODEL_PATH", "yolo11n-seg.pt")
        device = os.getenv("YOLO_SEG_DEVICE", os.getenv("YOLO_DEVICE", "cpu"))
        if device not in {"cpu", "cuda"}: raise HTTPException(400, "YOLO_SEG_DEVICE must be cpu or cuda")
        if device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available(): raise HTTPException(503, "CUDA was requested but is not available")
            except ImportError: raise HTTPException(503, "CUDA was requested but PyTorch is unavailable")
        with self._lock:
            if self._seg_model is not None and self._seg_model_path == model_path: return self._seg_model, device
            try:
                from ultralytics import YOLO
                self._seg_model = YOLO(model_path); self._seg_model_path = model_path
            except FileNotFoundError: raise HTTPException(503, f"YOLO segmentation model weights not found: {model_path}")
            except Exception as exc: raise HTTPException(503, f"Unable to load YOLO segmentation model: {str(exc)[:180]}")
        return self._seg_model, device

    def infer_segmentation(self, image_path: Path, confidence: float) -> tuple[str, list[dict]]:
        if not image_path.is_file(): raise HTTPException(400, "Image file is missing")
        model, device = self._load_segmentation()
        try:
            results = model.predict(source=str(image_path), conf=confidence, iou=float(os.getenv("YOLO_SEG_IOU_THRESHOLD", "0.45")), device=device, verbose=False)
            result = results[0]
            if result.masks is None: return self._seg_model_path or "default", []
            names, detections = result.names, []
            polygons = result.masks.xy
            for index, box in enumerate(result.boxes):
                score = float(box.conf[0].item())
                if score < confidence or index >= len(polygons): continue
                points = [(float(x), float(y)) for x, y in polygons[index].tolist()]
                if len(points) < 3: continue
                class_id = int(box.cls[0].item()); xyxy = [float(value) for value in box.xyxy[0].tolist()]
                name = names[class_id] if isinstance(names, dict) else names[class_id]
                detections.append({"model_class_id": class_id, "model_class_name": str(name), "x": xyxy[0], "y": xyxy[1], "width": xyxy[2]-xyxy[0], "height": xyxy[3]-xyxy[1], "points": points, "confidence": score})
            return self._seg_model_path or "default", detections
        except HTTPException: raise
        except Exception as exc: raise HTTPException(500, f"YOLO segmentation inference failed: {str(exc)[:180]}")

yolo_service = YoloService()
