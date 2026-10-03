"""Acquire immutable model artifacts at build time and verify LFS SHA-256."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


def download(destination: Path):
    lock = json.loads((Path(__file__).parents[1] / "models.lock.json").read_text())
    destination.mkdir(parents=True, exist_ok=True)
    repo, rev = lock["repository"], lock["revision"]
    for model in lock["models"]:
        target = destination / model["name"]
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != model["sha256"]:
            url = f"https://media.githubusercontent.com/media/{repo}/{rev}/{model['path']}"
            partial = target.with_suffix(".part")
            try:
                with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
                    digest = hashlib.sha256()
                    count = 0
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > model["bytes"]:
                            raise RuntimeError("Model exceeds expected size")
                        digest.update(block)
                        output.write(block)
                if count != model["bytes"] or digest.hexdigest() != model["sha256"]:
                    raise RuntimeError(f"Checksum mismatch: {model['name']}")
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
        license_url = f"https://raw.githubusercontent.com/{repo}/{rev}/{model['license_path']}"
        with urllib.request.urlopen(license_url, timeout=30) as response:
            (destination / f"{model['name']}.LICENSE").write_bytes(response.read())
        print(f"Verified {model['name']} sha256={model['sha256']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("models"))
    download(parser.parse_args().output)
