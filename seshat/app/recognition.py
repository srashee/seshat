"""CPU inference and explicit cosine scoring."""

import hashlib
import io
import logging
import time
import warnings
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import Settings
from .database import Database

LOGGER = logging.getLogger(__name__)
MODEL_ID = "sface-2021dec-0ba9fbfa-yunet-2023mar-8f2383e4-v1"


@dataclass
class Face:
    bbox: dict[str, int]
    embedding: np.ndarray


def decode(data: bytes, mime: str, settings: Settings) -> np.ndarray:
    if mime not in ("image/jpeg", "image/png"):
        raise ValueError("Only image/jpeg and image/png are accepted")
    if len(data) > settings.upload_limit:
        raise ValueError("Image exceeds upload limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                expected = {"image/jpeg": "JPEG", "image/png": "PNG"}[mime]
                if image.format != expected or image.width * image.height > settings.max_image_pixels:
                    raise ValueError("Invalid format or image pixel limit exceeded")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Animated images are not accepted")
                image.load()
                rgb = np.array(ImageOps.exif_transpose(image).convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as err:
        raise ValueError("Malformed or oversized image") from err


class Engine:
    def __init__(self, settings: Settings):
        self.settings = settings
        cv2.setNumThreads(settings.cpu_threads)
        cv2.ocl.setUseOpenCL(False)
        self.detector = cv2.FaceDetectorYN.create(
            str(settings.model_dir / "yunet.onnx"), "", (320, 320), settings.detection_threshold, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(settings.model_dir / "sface.onnx"), "")
        LOGGER.info("model_initialized model=%s threads=%d", MODEL_ID, settings.cpu_threads)

    def faces(self, image: np.ndarray) -> list[Face]:
        started = time.perf_counter()
        h, w = image.shape[:2]
        scale = min(1.0, self.settings.detection_size / max(h, w))
        small = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))))
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, detections = self.detector.detect(small)
        rows = [] if detections is None else list(detections)
        if len(rows) > self.settings.max_faces:
            raise ValueError("Too many faces; crop the image")
        LOGGER.debug("detection faces=%d duration_ms=%.1f", len(rows), (time.perf_counter() - started) * 1000)
        faces = []
        for row in rows:
            row = row.copy()
            row[:14] /= scale
            x, y, fw, fh = row[:4]
            if min(fw, fh) < self.settings.min_face_size:
                continue
            aligned = self.recognizer.alignCrop(image, row)
            vector = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
            norm = np.linalg.norm(vector)
            if not np.isfinite(vector).all() or norm <= 0:
                raise RuntimeError("Invalid model output")
            left, top = max(0, int(x)), max(0, int(y))
            right, bottom = min(w, int(x + fw)), min(h, int(y + fh))
            faces.append(
                Face(
                    {"x": left, "y": top, "width": max(0, right - left), "height": max(0, bottom - top)},
                    vector / norm,
                )
            )
        LOGGER.debug("embedding faces=%d total_ms=%.1f", len(faces), (time.perf_counter() - started) * 1000)
        return sorted(faces, key=lambda face: (face.bbox["x"], face.bbox["y"]))


def match(vector: np.ndarray, samples: list[tuple[str, np.ndarray]], settings: Settings) -> dict:
    # Max over references per person preserves distinct poses; margin rejects near ties.
    scores: dict[str, float] = {}
    for name, sample in samples:
        if sample.shape != vector.shape:
            raise RuntimeError("Embedding dimensions do not match model")
        score = float(np.clip(np.dot(vector, sample), -1, 1))
        scores[name] = max(scores.get(name, -1.0), score)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    similarity = ranked[0][1] if ranked else None
    margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else None
    known = bool(
        ranked
        and similarity >= settings.recognition_threshold
        and (margin is None or margin >= settings.ambiguity_margin)
    )
    return {
        "person": ranked[0][0] if known else "Unknown",
        "matched": known,
        "similarity": similarity,
        "distance": 1 - similarity if similarity is not None else None,
        "confidence": max(0.0, similarity) if known else 0.0,
        "margin": margin,
    }


class Recognizer:
    def __init__(self, settings: Settings, db: Database, engine: Engine):
        self.settings, self.db, self.engine = settings, db, engine

    def recognize(self, data: bytes, mime: str) -> dict:
        start = time.perf_counter()
        image = decode(data, mime, self.settings)
        detected = self.engine.faces(image)
        matching_start = time.perf_counter()
        samples = self.db.embeddings(MODEL_ID)
        faces = [dict(match(face.embedding, samples, self.settings), bbox=face.bbox) for face in detected]
        best = max(
            faces,
            key=lambda face: (face["matched"], face["similarity"] if face["similarity"] is not None else -2),
            default=None,
        )
        LOGGER.debug(
            "matching samples=%d threshold=%.3f duration_ms=%.1f",
            len(samples),
            self.settings.recognition_threshold,
            (time.perf_counter() - matching_start) * 1000,
        )
        result = {
            "faces": faces,
            "best_match": best,
            "processing_ms": round((time.perf_counter() - start) * 1000, 2),
            "model": MODEL_ID,
            "threshold": self.settings.recognition_threshold,
            "image_hash": hashlib.sha256(data).hexdigest(),
        }
        LOGGER.info(
            "recognition_complete faces=%d matched=%s total_ms=%.2f",
            len(faces),
            bool(best and best["matched"]),
            result["processing_ms"],
        )
        return result
