"""Validated Supervisor options and local development settings."""

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=32)
    recognition_threshold: float = Field(default=0.363, ge=-1, le=1)
    ambiguity_margin: float = Field(default=0.05, ge=0, le=1)
    max_image_size_mb: int = Field(default=10, ge=1, le=20)
    max_image_pixels: int = Field(default=20000000, ge=10000, le=40000000)
    detection_size: int = Field(default=640, ge=320, le=1280)
    detection_threshold: float = Field(default=0.8, ge=0.5, le=1)
    min_face_size: int = Field(default=30, ge=10, le=200)
    max_faces: int = Field(default=20, ge=1, le=50)
    max_samples: int = Field(default=2000, ge=1, le=10000)
    cpu_threads: int = Field(default=2, ge=1, le=4)
    gesture_enabled: bool = False
    gesture_min_quality: float = Field(default=0.7, ge=0.5, le=0.99)
    gesture_max_people: int = Field(default=4, ge=1, le=8)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    data_dir: Path = Path("/data")
    model_dir: Path = Path("/opt/models")

    @property
    def upload_limit(self) -> int:
        return self.max_image_size_mb * 1024 * 1024


def load_settings() -> Settings:
    path = Path(os.environ.get("SESHAT_OPTIONS", "/data/options.json"))
    values = json.loads(path.read_text()) if path.exists() else {}
    for field in ("api_key", "data_dir", "model_dir"):
        if value := os.environ.get(f"SESHAT_{field.upper()}"):
            values[field] = value
    try:
        return Settings(**values)
    except ValidationError as error:
        fields = ", ".join(".".join(map(str, item["loc"])) for item in error.errors())
        raise RuntimeError(
            f"Invalid Seshat options: {fields}. API key must contain at least 32 characters."
        ) from None
