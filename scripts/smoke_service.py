"""Exercise real Uvicorn listeners and restart persistence using temporary records.

Requires locally acquired models and free TCP ports 8000/8099. No downloads.
Optionally pass --browser-script to exercise the UI with a Node Playwright script.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(browser_script: str | None = None, node: str = "node") -> None:
    key = secrets.token_urlsafe(32)
    headers = {"Authorization": f"Bearer {key}"}

    def request(path: str, data: bytes | None = None, method: str = "GET"):
        req = urllib.request.Request(
            f"http://127.0.0.1:8000/{path}",
            data=data,
            headers={**headers, "Content-Type": "image/png"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)

    with tempfile.TemporaryDirectory(prefix="seshat-smoke-") as storage:
        env = {
            **os.environ,
            "SESHAT_API_KEY": key,
            "SESHAT_DATA_DIR": storage,
            "SESHAT_MODEL_DIR": str(ROOT / "models"),
            "SESHAT_OPTIONS": str(Path(storage) / "options.json"),
        }
        log_path = Path(storage) / "server.log"
        for iteration in range(2):
            with log_path.open("w") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "app"],
                    cwd=ROOT / "seshat",
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                try:
                    ready = False
                    for _ in range(100):
                        if process.poll() is not None:
                            raise RuntimeError(f"Server exited: {log_path.read_text()}")
                        try:
                            request("settings")
                            ready = True
                            break
                        except (urllib.error.URLError, TimeoutError):
                            time.sleep(0.1)
                    assert ready, "Server did not become ready"
                    assert request("health")["model_loaded"]
                    if iteration == 0:
                        for url in ("http://127.0.0.1:8000/people", "http://127.0.0.1:8099/people"):
                            try:
                                urllib.request.urlopen(url, timeout=5)
                            except urllib.error.HTTPError as error:
                                assert error.code == 401
                            else:
                                raise AssertionError("Unauthenticated request unexpectedly succeeded")
                        if browser_script:
                            browser = subprocess.run(
                                [node, browser_script],
                                env=env,
                                cwd=ROOT,
                                capture_output=True,
                                text=True,
                                timeout=90,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            )
                            print(browser.stdout)
                            if browser.returncode:
                                raise RuntimeError(browser.stderr)
                        photo = (ROOT / "seshat/tests/fixtures/astronaut.png").read_bytes()
                        request("enroll/Fixture", photo, "POST")
                        result = request("recognize", photo, "POST")
                        assert result["best_match"]["person"] == "Fixture"
                        print(f"Live CPU recognition passed; processing_ms={result['processing_ms']}")
                    else:
                        assert request("people")["people"][0]["name"] == "Fixture"
                        request("people/Fixture", method="DELETE")
                        assert request("people")["people"] == []
                        print("Restart persistence and deletion passed; both listener auth checks passed")
                finally:
                    if sys.platform == "win32" and process.poll() is None:
                        # The Windows venv launcher can have a child interpreter.
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            capture_output=True,
                            check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-script")
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    run(args.browser_script, args.node)
