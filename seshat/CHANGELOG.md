# Changelog

## 1.0.1

- Pin both Docker stages directly to the Debian/Python base so Supervisor's Alpine `BUILD_FROM` override cannot break installation.
- Exercise that override in CI and verify the resulting container has Debian and Python/pip before its health check.

## 1.0.0

- Initial local YuNet/SFace recognition app with authenticated API and Supervisor-only Ingress.
- Durable multi-sample enrollment, ambiguity-aware matching and per-sample deletion.
- Home Assistant image integration, native sensors, result events and latest-image processing.
- Unit/contract/CPU model smoke tests and GitHub build/release workflows.
