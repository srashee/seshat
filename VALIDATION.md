# Validation record

Verified locally on Windows on 2026-10-03. Updated for 1.1.0 arm gestures.

## Passed

- `pytest -q --tb=short`: **69 passed**, including real YuNet/SFace enrollment/recognition, real person/pose decoding, and conservative rejection of the partially visible fixture's arm pose.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
- JavaScript syntax check: passed.
- Live Uvicorn API test: authenticated recognition, unauthenticated rejection on both listeners, enrollment persistence across a process restart, and deletion passed.
- Headless Microsoft Edge test with gestures enabled: connected with a temporary API key, enrolled a reference photo, recognized the face with an undetermined gesture, and deleted the person. No JavaScript page errors. The UI displayed the feature status and person/gesture summary.
- Desktop (1280 px) and mobile (390 px) screenshots inspected; controls and results remain readable with no horizontal overflow visible.
- The live recognition sample with pose inference took approximately 85 ms on the development computer. This is not an Intel N95 benchmark.
- Synthetic-landmark tests exercise pointing up/down, hand raised, resting-arm rejection, hidden joints, conflicting arms, one-to-one multi-person association, resource caps and pose-failure isolation. Controller tests verify combined identity/gesture events and compatibility with older app responses. Positive gesture detection has not yet been validated on real doorbell photos.

The browser test used temporary storage and a generated key. Its records and service processes were cleaned up.

## Reproduce

```bash
pip install -r requirements-dev.txt
python seshat/scripts/download_models.py --output models
pytest -q
ruff check .
ruff format --check .
python scripts/smoke_service.py --gestures
```

For the browser test, install Playwright with `npm install --no-save playwright`, then run `npx playwright install chromium` and:

```bash
python scripts/smoke_service.py --gestures --browser-script scripts/browser_smoke.cjs
```

Alternatively, set `SESHAT_BROWSER_CHANNEL=msedge` to use installed Edge. Set `SESHAT_SCREENSHOT_DIR` to save desktop/mobile screenshots. The smoke test requires free ports 8000 and 8099 and locally acquired models.

## Remaining deployment verification

- GitHub Actions successfully built and health-checked 1.0.0, but the first HAOS installation exposed a Supervisor `BUILD_FROM` override absent from that original CI build. Version 1.0.1 pins both Docker stages directly to Debian/Python and adds the same Alpine override to CI as a regression check. See the GitHub Verify run for the patch commit for its result.
- Installation under Home Assistant Supervisor, real Ingress proxy access, and the physical doorbell acceptance procedure require the target HAOS installation. Local controller tests use Home Assistant doubles; they do not establish live HAOS compatibility.
- Recognition accuracy, false-positive rate, and N95 resource usage require representative doorbell images and on-device testing.

One non-failing dependency warning remains: Starlette's test client deprecates its HTTPX adapter in favor of HTTPX2. All current tests pass with the pinned HTTPX adapter.
