# Changelog

## 1.1.0

- Optional local arm-gesture recognition: pointing up, pointing down and hand raised, plus explicit no-gesture/undetermined results.
- Conservative one-to-one face/body association, visibility checks, resting-arm rejection and bounded CPU pose inference.
- Add gesture results to API faces, the existing Home Assistant event and the new Front Door Gesture sensor.
- Keep face recognition/enrollment working when pose inference is disabled or unavailable; existing embeddings remain compatible.
- Include checksum-pinned Apache-2.0 person/pose models, a readable UI summary, and gesture/association/real-model/browser tests.

## 1.0.1

- Pin both Docker stages directly to the Debian/Python base so Supervisor's Alpine `BUILD_FROM` override cannot break installation.
- Exercise that override in CI and verify the resulting container has Debian and Python/pip before its health check.

## 1.0.0

- Initial local YuNet/SFace recognition app with authenticated API and Supervisor-only Ingress.
- Durable multi-sample enrollment, ambiguity-aware matching and per-sample deletion.
- Home Assistant image integration, native sensors, result events and latest-image processing.
- Unit/contract/CPU model smoke tests and GitHub build/release workflows.
