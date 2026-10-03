# Validation record

Verified locally on Windows on 2026-10-03.

## Passed

- `pytest -q --tb=short`: **41 passed**, including real YuNet/SFace inference and enrollment against the bundled public-domain fixture, plus recognition of a modified JPEG variant.
- `ruff check .`: passed.
- `ruff format --check .`: passed (26 Python files).
- JavaScript syntax check: passed.
- Live Uvicorn API test: authenticated recognition, unauthenticated rejection on both listeners, enrollment persistence across a process restart, and deletion passed.
- Headless Microsoft Edge test: connected with a temporary API key, enrolled a reference photo through the UI, recognized it, and deleted the person through the UI. No JavaScript page errors.
- Desktop (1280 px) and mobile (390 px) screenshots inspected; controls and results remain readable with no horizontal overflow visible.
- The live recognition sample took approximately 34 ms on the development computer. This is not an Intel N95 benchmark.

The browser test used temporary storage and a generated key. Its records and service processes were cleaned up.

## Reproduce

```bash
pip install -r requirements-dev.txt
python seshat/scripts/download_models.py --output models
pytest -q
ruff check .
ruff format --check .
python scripts/smoke_service.py
```

For the browser test, install Playwright with `npm install --no-save playwright`, then run `npx playwright install chromium` and:

```bash
python scripts/smoke_service.py --browser-script scripts/browser_smoke.cjs
```

Alternatively, set `SESHAT_BROWSER_CHANNEL=msedge` to use installed Edge. Set `SESHAT_SCREENSHOT_DIR` to save desktop/mobile screenshots. The smoke test requires free ports 8000 and 8099 and locally acquired models.

## Remaining deployment verification

- Docker image build and container health check require a running Docker Linux engine. Docker Desktop is installed in the user's local application directory; the initial build attempt could not connect to its engine.
- Installation under Home Assistant Supervisor, real Ingress proxy access, and the physical doorbell acceptance procedure require the target HAOS installation. Local controller tests use Home Assistant doubles; they do not establish live HAOS compatibility.
- Recognition accuracy, false-positive rate, and N95 resource usage require representative doorbell images and on-device testing.

One non-failing dependency warning remains: Starlette's test client deprecates its HTTPX adapter in favor of HTTPX2. All current tests pass with the pinned HTTPX adapter.
