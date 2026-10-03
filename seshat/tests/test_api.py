import asyncio
import threading

import httpx
import numpy as np
import pytest
from app.main import create_app
from app.recognition import Face
from fastapi.testclient import TestClient


def upload(client, path, data, mime="image/png"):
    return client.post(path, files={"file": ("photo.png", data, mime)})


def test_health_and_auth(client):
    assert client.get("/health").json()["model_loaded"]
    client.headers.pop("authorization")
    assert client.get("/people").status_code == 401
    assert client.delete("/people/Saad").status_code == 401
    assert client.get("/").status_code == 200


def test_ingress_cannot_spoof_forwarded_ip(runtime):
    with TestClient(create_app(runtime, ingress=True)) as client:
        assert client.get("/people", headers={"X-Forwarded-For": "172.30.32.2"}).status_code == 401
    with TestClient(create_app(runtime, ingress=True), client=("172.30.32.2", 123)) as client:
        assert client.get("/people").status_code == 200
        page = client.get("/", headers={"X-Ingress-Path": "/api/hassio_ingress/test-session"})
        assert '<base href="/api/hassio_ingress/test-session/">' in page.text


@pytest.mark.parametrize(
    "data,mime,status",
    [
        (b"bad", "image/png", 422),
        (b"bad", "text/plain", 415),
        (b"x" * (1024 * 1024 + 1), "image/png", 413),
        (b"x" * (1024 * 1024 + 70000), "image/png", 413),
    ],
    ids=["malformed", "mime", "oversized_file", "oversized_body"],
)
def test_invalid_upload(client, data, mime, status):
    assert upload(client, "/recognize", data, mime).status_code == status


def test_mime_mismatch_and_pixel_limit(client, runtime, png):
    assert upload(client, "/recognize", png(), "image/jpeg").status_code == 422
    runtime.settings.max_image_pixels = 100
    assert upload(client, "/recognize", png()).status_code == 422


def test_no_face(client, png):
    data = upload(client, "/recognize", png()).json()
    assert data["faces"] == [] and data["best_match"] is None
    assert upload(client, "/enroll/Saad", png()).status_code == 422


def test_enrollment_multiple_samples_duplicate_deletion(client, runtime, png, face):
    runtime.engine.output = [face]
    first = upload(client, "/enroll/Saad", png()).json()["sample_id"]
    assert upload(client, "/enroll/Saad", png()).json()["sample_id"] == first
    upload(client, "/enroll/Saad", png("blue"))
    assert client.get("/people").json()["people"][0]["samples"] == 2
    result = upload(client, "/recognize", png()).json()
    assert result["best_match"]["person"] == "Saad"
    assert result["best_match"]["similarity"] == pytest.approx(1)
    assert client.delete(f"/people/Saad/{first}").json() == {"deleted": 1}
    assert client.delete("/people/Saad").json() == {"deleted": 1}
    assert client.get("/people").json() == {"people": []}
    assert client.delete("/people/Saad").status_code == 404


def test_unknown_multiple_faces(client, runtime, png, face):
    runtime.engine.output = [face]
    upload(client, "/enroll/Saad", png())
    unknown = Face(face.bbox, np.array([0, 1], dtype=np.float32))
    runtime.engine.output = [unknown]
    result = upload(client, "/recognize", png()).json()
    assert result["best_match"]["person"] == "Unknown"
    assert result["best_match"]["distance"] == 1
    runtime.engine.output = [unknown, face]
    result = upload(client, "/recognize", png()).json()
    assert len(result["faces"]) == 2 and result["best_match"]["person"] == "Saad"
    assert upload(client, "/enroll/Saad", png()).status_code == 422


@pytest.mark.parametrize("name", ["Unknown", "No Face", "%2E%2E", "a%5Cb", "a%3Cb", "%20"])
def test_names(client, runtime, png, face, name):
    runtime.engine.output = [face]
    assert upload(client, f"/enroll/{name}", png()).status_code in (404, 422)


def test_raw_image_request(client, png):
    assert client.post("/recognize", content=png(), headers={"Content-Type": "image/png"}).status_code == 200


def test_capacity(client, runtime, png, face):
    runtime.engine.output = [face]
    runtime.settings.max_samples = 1
    assert upload(client, "/enroll/Saad", png()).status_code == 200
    assert upload(client, "/enroll/Saad", png("blue")).status_code == 422


async def test_single_worker_stays_busy_after_cancellation(runtime):
    entered, release = threading.Event(), threading.Event()

    def slow():
        entered.set()
        release.wait(5)

    task = asyncio.create_task(runtime.run(slow))
    try:
        await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(runtime)),
            base_url="http://seshat",
            headers={"Authorization": "Bearer " + runtime.settings.api_key.get_secret_value()},
        ) as client:
            assert (await client.get("/people")).status_code == 429
    finally:
        release.set()
        for _ in range(100):
            if not runtime.busy:
                break
            await asyncio.sleep(0.01)
    assert not runtime.busy
