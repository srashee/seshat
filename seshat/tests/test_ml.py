"""Offline smoke tests. Acquire pinned models explicitly before opting in."""

import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
from app.config import Settings
from app.gestures import GestureEngine, classify_pose
from app.main import Runtime, create_app
from app.recognition import Engine
from fastapi.testclient import TestClient
from PIL import Image, ImageEnhance

pytestmark = pytest.mark.ml


def test_real_models_cpu_load_and_infer(tmp_path):
    directory = Path(__file__).resolve().parents[2] / "models"
    if not (directory / "sface.onnx").exists():
        pytest.skip("Run download_models.py first; tests never download artifacts")
    engine = Engine(Settings(api_key="x" * 32, model_dir=directory, data_dir=tmp_path))
    assert engine.faces(np.zeros((480, 640, 3), dtype=np.uint8)) == []
    vector = engine.recognizer.feature(np.zeros((112, 112, 3), dtype=np.uint8))
    assert vector.size == 128 and np.isfinite(vector).all()


def test_real_photo_enrollment_and_changed_image(tmp_path):
    directory = Path(__file__).resolve().parents[2] / "models"
    if not (directory / "sface.onnx").exists():
        pytest.skip("Acquire pinned models before ML tests")
    photo = (Path(__file__).parent / "fixtures/astronaut.png").read_bytes()
    assert (
        hashlib.sha256(photo).hexdigest()
        == "88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5"
    )
    key = "x" * 32
    runtime = Runtime(Settings(api_key=key, model_dir=directory, data_dir=tmp_path))
    try:
        with TestClient(create_app(runtime), headers={"Authorization": f"Bearer {key}"}) as client:
            original = {"file": ("fixture.png", photo, "image/png")}
            unknown = client.post("/recognize", files=original).json()
            assert unknown["best_match"]["person"] == "Unknown"
            response = client.post("/enroll/Fixture%20Person", files=original)
            assert response.status_code == 200, response.text
            with Image.open(io.BytesIO(photo)) as image:
                modified = io.BytesIO()
                ImageEnhance.Brightness(image).enhance(0.85).save(modified, format="JPEG", quality=90)
            known = client.post(
                "/recognize", files={"file": ("variant.jpg", modified.getvalue(), "image/jpeg")}
            )
            assert known.status_code == 200, known.text
            result = known.json()
            assert result["best_match"]["person"] == "Fixture Person"
            assert result["best_match"]["bbox"]["width"] > 30
            assert result["image_hash"] != unknown["image_hash"]
    finally:
        runtime.close()


def test_real_pose_models_and_partial_body(tmp_path):
    directory = Path(__file__).resolve().parents[2] / "models"
    if not all((directory / name).exists() for name in ("person.onnx", "pose.onnx")):
        pytest.skip("Acquire the pinned pose models before ML tests")
    import cv2

    settings = Settings(api_key="x" * 32, model_dir=directory, data_dir=tmp_path, gesture_enabled=True)
    engine = GestureEngine(settings)
    image = cv2.imread(str(Path(__file__).parent / "fixtures/astronaut.png"))
    batch = engine.infer(image)
    assert len(batch.poses) == 1
    assert batch.poses[0].landmarks.shape == (33, 5)
    assert np.isfinite(batch.poses[0].landmarks).all()
    # The fixture has a cropped/occluded arm: do not guess a positive gesture.
    assert classify_pose(batch.poses[0], 512, 512, 0.7)["label"] == "undetermined"
    assert engine.infer(np.zeros_like(image)).poses == []


def test_real_api_gestures_preserve_identity(tmp_path):
    directory = Path(__file__).resolve().parents[2] / "models"
    if not all((directory / name).exists() for name in ("person.onnx", "pose.onnx", "sface.onnx")):
        pytest.skip("Acquire the pinned models before ML tests")
    settings = Settings(api_key="x" * 32, model_dir=directory, data_dir=tmp_path, gesture_enabled=True)
    runtime = Runtime(settings)
    try:
        with TestClient(create_app(runtime), headers={"Authorization": "Bearer " + "x" * 32}) as client:
            assert client.get("/health").json()["gesture_model_loaded"]
            photo = (Path(__file__).parent / "fixtures/astronaut.png").read_bytes()
            upload = {"file": ("fixture.png", photo, "image/png")}
            assert client.post("/enroll/Fixture", files=upload).status_code == 200
            result = client.post("/recognize", files=upload).json()
            assert result["best_match"]["person"] == "Fixture"
            assert result["gesture"] == "undetermined"
            assert result["gesture_reason"] == "arm_not_visible_or_reliable"
            assert result["gesture_status"] == "ok"
            assert result["best_match"]["gesture"]["label"] == result["gesture"]
    finally:
        runtime.close()
