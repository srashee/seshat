"""Offline smoke tests. Acquire pinned models explicitly before opting in."""

import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
from app.config import Settings
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
