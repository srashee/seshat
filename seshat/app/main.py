"""Bounded authenticated API; model work always runs in one executor thread."""

import asyncio
import hashlib
import hmac
import logging
import re
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.datastructures import UploadFile

from .config import Settings
from .database import Database
from .recognition import MODEL_ID, Engine, Recognizer, decode

LOGGER = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings: Settings, engine=None):
        self.settings = settings
        self.db = Database(settings.data_dir / "faces.db")
        self.engine = engine if engine is not None else Engine(settings)
        self.recognizer = Recognizer(settings, self.db, self.engine)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="seshat")
        self.busy = False

    async def run(self, function, *args):
        # No unbounded executor queue, including after client cancellation/timeouts.
        if self.busy:
            raise HTTPException(429, "Seshat is busy; retry shortly", headers={"Retry-After": "1"})
        self.busy = True
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self.executor, function, *args)
        future.add_done_callback(lambda _: setattr(self, "busy", False))
        return await asyncio.shield(future)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


class Boundary:
    """Authenticate and bound the entire body BEFORE multipart parsing/spooling."""

    def __init__(self, app, runtime: Runtime, ingress: bool):
        self.app, self.runtime, self.ingress = app, runtime, ingress
        self.inflight = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        peer = (scope.get("client") or ("", 0))[0]
        if self.ingress:
            allowed = peer == "172.30.32.2"
        else:
            expected = b"Bearer " + self.runtime.settings.api_key.get_secret_value().encode()
            allowed = hmac.compare_digest(headers.get(b"authorization", b""), expected)
            # Static shell contains no private data; API still requires a token.
            allowed |= scope["method"] == "GET" and scope["path"] in ("/", "/ui.js", "/style.css")
            allowed |= scope["method"] == "GET" and scope["path"] == "/health"
        if not allowed:
            return await JSONResponse({"detail": "Unauthorized"}, status_code=401)(scope, receive, send)
        if self.inflight >= 4:
            return await JSONResponse({"detail": "Too many requests"}, status_code=429)(scope, receive, send)
        self.inflight += 1
        try:
            body = bytearray()
            limit = self.runtime.settings.upload_limit + 65536
            try:
                async with asyncio.timeout(30):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > limit:
                            return await JSONResponse({"detail": "Upload too large"}, status_code=413)(
                                scope, receive, send
                            )
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await JSONResponse({"detail": "Upload timeout"}, status_code=408)(scope, receive, send)
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            async def secure_send(message):
                if message["type"] == "http.response.start":
                    message["headers"] += [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'",
                        ),
                    ]
                await send(message)

            await self.app(scope, bounded_receive, secure_send)
        finally:
            self.inflight -= 1


def person_name(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if (
        not 1 <= len(value) <= 64
        or value.casefold() in ("unknown", "no face", "unavailable")
        or not all(c.isalnum() or c in " -_'" for c in value)
        or not any(c.isalnum() for c in value)
    ):
        raise HTTPException(422, "Use a name of 1–64 letters, numbers, spaces, hyphens or apostrophes")
    return value


async def uploaded(request: Request, settings: Settings) -> tuple[bytes, str]:
    mime = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if mime == "multipart/form-data":
        async with request.form(max_files=1, max_fields=0, max_part_size=settings.upload_limit) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise HTTPException(422, "Upload a file in the 'file' field")
            data = await file.read(settings.upload_limit + 1)
            mime = (file.content_type or "").lower()
    else:
        data = await request.body()
    if len(data) > settings.upload_limit:
        raise HTTPException(413, "Upload too large")
    if mime not in ("image/jpeg", "image/png"):
        raise HTTPException(415, "Only JPEG/PNG images are supported")
    return data, mime


def create_app(runtime: Runtime, ingress: bool = False) -> FastAPI:
    app = FastAPI(title="Seshat", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Boundary, runtime=runtime, ingress=ingress)

    @app.exception_handler(ValueError)
    async def bad_image(_request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def database_error(_request, error):
        LOGGER.error("database_failure type=%s", type(error).__name__)
        return JSONResponse({"detail": "Database unavailable"}, status_code=503)

    @app.exception_handler(Exception)
    async def unexpected(_request, error):
        LOGGER.error("request_failure type=%s", type(error).__name__)
        return JSONResponse({"detail": "Recognition service failure; inspect logs"}, status_code=503)

    @app.get("/health")
    def health():
        runtime.db.health()
        return {"status": "ok", "model_loaded": runtime.engine is not None, "model": MODEL_ID}

    @app.get("/settings")
    async def settings():
        return {
            "threshold": runtime.settings.recognition_threshold,
            "model": MODEL_ID,
            "max_image_size_mb": runtime.settings.max_image_size_mb,
        }

    @app.post("/recognize")
    async def recognize(request: Request):
        data, mime = await uploaded(request, runtime.settings)
        return await runtime.run(runtime.recognizer.recognize, data, mime)

    def enroll_sync(name: str, data: bytes, mime: str):
        image = decode(data, mime, runtime.settings)
        faces = runtime.engine.faces(image)
        if len(faces) != 1:
            raise ValueError("Enrollment needs exactly one usable face")
        sample = runtime.db.add(
            name, faces[0].embedding, MODEL_ID, hashlib.sha256(data).hexdigest(), runtime.settings.max_samples
        )
        return {"person": name, "sample_id": sample, "model": MODEL_ID}

    @app.post("/enroll/{name}")
    async def enroll(name: str, request: Request):
        name = person_name(name)
        data, mime = await uploaded(request, runtime.settings)
        return await runtime.run(enroll_sync, name, data, mime)

    @app.get("/people")
    async def people():
        return {"people": await runtime.run(runtime.db.people)}

    @app.delete("/people/{name}")
    @app.delete("/people/{name}/{sample_id}")
    async def delete(name: str, sample_id: str | None = None):
        name = person_name(name)
        if sample_id is not None and not re.fullmatch(r"[a-f0-9-]{36}", sample_id):
            raise HTTPException(422, "Invalid sample ID")
        count = await runtime.run(runtime.db.delete, name, sample_id)
        if not count:
            raise HTTPException(404, "Enrollment not found")
        return {"deleted": count}

    static = Path(__file__).parent / "static"

    @app.get("/")
    def index(request: Request):
        document = (static / "index.html").read_text(encoding="utf-8")
        prefix = request.headers.get("x-ingress-path", "").rstrip("/") if ingress else ""
        if prefix and re.fullmatch(r"/[A-Za-z0-9_/-]+", prefix) and not prefix.startswith("//"):
            document = document.replace("<head>", f'<head><base href="{prefix}/">', 1)
        return HTMLResponse(document)

    @app.get("/ui.js")
    async def javascript():
        return FileResponse(static / "ui.js", media_type="application/javascript")

    @app.get("/style.css")
    async def stylesheet():
        return FileResponse(static / "style.css", media_type="text/css")

    return app
