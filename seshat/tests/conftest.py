import io

import numpy as np
import pytest
from app.config import Settings
from app.main import Runtime, create_app
from app.recognition import Face
from fastapi.testclient import TestClient
from PIL import Image

KEY = "test-only-key-not-a-secret-1234567890"


class FakeEngine:
    def __init__(self):
        self.output = []
        self.calls = 0

    def faces(self, image):
        self.calls += 1
        return self.output


@pytest.fixture
def face():
    return Face({"x": 1, "y": 2, "width": 30, "height": 30}, np.array([1, 0], dtype=np.float32))


@pytest.fixture
def png():
    def make(color="red"):
        output = io.BytesIO()
        Image.new("RGB", (64, 64), color).save(output, format="PNG")
        return output.getvalue()

    return make


@pytest.fixture
def runtime(tmp_path):
    runtime = Runtime(Settings(api_key=KEY, data_dir=tmp_path, max_image_size_mb=1), FakeEngine())
    yield runtime
    runtime.close()


@pytest.fixture
def client(runtime):
    with TestClient(create_app(runtime), headers={"Authorization": f"Bearer {KEY}"}) as client:
        yield client
