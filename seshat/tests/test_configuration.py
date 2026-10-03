import json

import pytest
from app.config import Settings, load_settings
from pydantic import ValidationError


@pytest.mark.parametrize(
    "options",
    [
        {"cpu_threads": 0},
        {"recognition_threshold": 2},
        {"api_key": "short"},
        {"max_image_size_mb": 21},
        {"unexpected": True},
        {"gesture_min_quality": 0.1},
        {"gesture_max_people": 0},
    ],
)
def test_invalid_options(options):
    with pytest.raises(ValidationError):
        Settings(**({"api_key": "x" * 32} | options))


def test_invalid_secret_not_in_startup_error(tmp_path, monkeypatch):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"api_key": "secret-value"}))
    monkeypatch.setenv("SESHAT_OPTIONS", str(options))
    monkeypatch.delenv("SESHAT_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as error:
        load_settings()
    assert "secret-value" not in str(error.value)
