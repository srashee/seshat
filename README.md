# Seshat

Local face recognition and identity records for Home Assistant OS. Named for the ancient Egyptian goddess of writing and record-keeping.

Seshat processes **event images**, not video streams. It runs on an amd64 CPU, keeps enrolled embeddings in `/data/faces.db`, and exposes native Home Assistant sensors and a recognition event. No cloud recognition, telemetry, MQTT broker, GPU, or Home Assistant access token is required.

The repository includes a Supervisor-managed app (formerly called an add-on), a small custom integration, a plain HTML/JS enrollment interface, automated tests, and build/release workflows. See [VALIDATION.md](VALIDATION.md) for what has actually been executed and remaining deployment checks.

To publish your own repository and versioned releases, follow [PUBLISHING.md](PUBLISHING.md).

## Architecture

```text
image.front_door_event_image state/attribute update
    ↓  async_track_state_change_event; debounce and coalesce
Home Assistant custom integration
    ↓  homeassistant.components.image.async_get_image(hass, entity_id)
Actual JPEG/PNG bytes → SHA-256 duplicate check
    ↓  POST http://<app-hostname>:8000/recognize, Bearer Seshat API key
Seshat app: decode → YuNet detect → SFace embed → SQLite reference matching
    ↓  structured JSON response
Custom integration: native SensorEntity updates + seshat_face_recognized event
    ↓
sensor.front_door_recognized_person = Saad / Unknown / No Face
```

The integration retrieves the image inside Home Assistant, so it does not need an HTTP image-proxy token. The image entity's state is a timestamp, not image bytes. The current image helper returns an `Image` with `.content` and `.content_type`; this is the mechanism used here. The source integration remains responsible for fetching its camera's image and invalidating its own cache.

Why this architecture:

| Alternative | Decision |
|---|---|
| MQTT discovery | Valid native solution, but adds a broker and credentials the installation does not already have. |
| REST sensors | Polling and split trigger/result logic are unnecessary here. |
| REST state writes | Do not provide the entity lifecycle and registry behavior of a real integration. |
| Events plus template sensors | Viable, but needs more manual YAML and lifecycle/error handling. |
| Small custom integration | Chosen: native sensors, image access, event handling, availability and unload behavior, with no ML dependencies in Core. |
| App uses Supervisor API | Supported via `homeassistant_api: true`, `SUPERVISOR_TOKEN`, and `http://supervisor/core/api/`; unnecessary privileges for this design. Both API permissions are disabled. |

Home Assistant has no universal notification for image content that changes without any entity state or attribute update. Seshat listens for both state and meaningful attribute changes, ignores token-only rotations, and hashes fetched bytes. If a camera integration silently changes its image, use its documented event to call `seshat.recognize`; see below. Seshat does not invent a camera event or continuously poll healthy sources.

## Install on HAOS

### 1. Add the app repository

The project repository is [srashee/seshat](https://github.com/srashee/seshat). Its prepared local source must be pushed before Home Assistant can install it.

In current Home Assistant, open **Settings → Apps → Install app → ⋮ → Repositories**, add `https://github.com/srashee/seshat`, and install **Seshat**. Older versions label these screens **Settings → Add-ons → Add-on Store → ⋮ → Repositories**. Refresh the store if the repository does not appear immediately.

Alternatively, for local HAOS development, copy the `seshat/` directory to `/addons/seshat` using the Samba or SSH app, reload the store, and install Seshat under Local apps. Supervisor builds and manages the container; do not run Docker manually on HAOS.

The default packaging builds from source, including the models, at installation. Initial installation therefore needs access to the package registries and official model source. Runtime image processing works offline. Only `amd64` is advertised; arm64 requires a separate wheel/build/inference validation before adding it.

### 2. Configure and start Seshat

Generate a random API key on your development computer:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the generated value into **Seshat → Configuration → api_key**, save, and start the app. The blank shipped default deliberately fails startup. A key must be at least 32 characters. Keep the network port mapping disabled, enable Start on boot and Watchdog, and open the Web UI through Home Assistant Ingress.

This is a Seshat-specific shared secret, **not** a Home Assistant long-lived access token. It authorizes enrollment/deletion as well as recognition. Treat it as an administrator credential. It is stored in Supervisor options and the integration's protected Core configuration storage, never in automation YAML. Rotating it requires updating both ends; for v1, remove and re-add the integration to change its connection settings.

### 3. Install the custom integration

Copy the repository's **`custom_components/seshat` directory** into **`/config/custom_components/seshat`** on Home Assistant. `/config` here means Home Assistant Core's configuration directory as exposed by Samba/File Editor, not the app's `/data` directory. Restart Home Assistant.

Open **Settings → Devices & services → Add integration → Seshat**. Enter:

| Field | Value |
|---|---|
| Seshat base URL | `http://<hostname shown on Seshat's Info page>:8000` |
| API key | Same generated key as the app option |
| Event image | `image.front_door_event_image` |
| Debounce window | `1000` milliseconds initially |

For a local app the hostname is typically `local-seshat`. A GitHub repository installation has a repository prefix, so use the actual Info-page hostname, not the local default. Internal app DNS names use hyphens. No host port mapping is needed for Core-to-app communication.

The integration validates the connection using an authenticated request, then creates one device with three sensors. If it is not listed after copying, verify the folder nesting, restart Core, refresh your browser, and inspect Core logs. v1 supports one configured image source.

## First enrollment

Open **Seshat → Open Web UI**. Home Assistant authenticates the Ingress session; you should not need to type a key there.

1. Enter **Saad** in “Person's name”.
2. Choose several JPEG/PNG reference photos, with one usable face per photo.
3. Select **Enroll photos**. Each file gets its own success/error result; successful files remain enrolled if another fails.
4. Check the sample count in Enrolled people.
5. Under Test an event image, upload a separate image to inspect the name, cosine similarity, distance, and bounding box.

Names accept Unicode letters/numbers, spaces, hyphens, underscores and apostrophes, up to 64 characters. `Unknown`, `No Face`, and `Unavailable` are reserved. Uploaded filenames are never used as storage paths. Duplicate copies of the same image for the same person/model return the existing sample ID. Multiple different photos add separate samples. The UI can delete individual samples or a person's entire enrollment.

Use a handful of clear, representative references rather than hundreds of near-identical photos. Include daytime and night/IR doorbell images, normal glasses, beard changes, and modest head-angle differences. Faces that are distant, blurred, strongly profiled, obscured by hats, or pointed downward may remain unrecognizable. Add representative references or improve camera framing before loosening thresholds.

## Configuration

Options are validated both by Supervisor and Pydantic. Restart the app after changes.

| App option | Default | Meaning |
|---|---:|---|
| `api_key` | empty, must set | Shared API credential, minimum 32 characters. |
| `recognition_threshold` | `0.363` | Minimum cosine similarity, range −1 to 1; higher is stricter. |
| `ambiguity_margin` | `0.05` | Required gap between the two best **different people**, range 0–1. |
| `max_image_size_mb` | `10` | Maximum image bytes in MiB, range 1–20. Entire HTTP body also capped with 64 KiB multipart allowance. |
| `max_image_pixels` | `20000000` | Decode pixel cap, range 10,000–40,000,000. |
| `detection_size` | `640` | Longest side for detection only, range 320–1280; no upscaling. Alignment uses the original oriented image. |
| `detection_threshold` | `0.8` | YuNet detector score cutoff, range 0.5–1; separate from identity similarity. |
| `min_face_size` | `30` | Minimum usable face side in original-image pixels, range 10–200. |
| `max_faces` | `20` | Reject images with more detector candidates than this, range 1–50. |
| `max_samples` | `2000` | Total stored enrollment limit across people and model versions, range 1–10000. |
| `cpu_threads` | `2` | OpenCV CPU threads, range 1–4. Start with 1–2 on an N95. |
| `log_level` | `info` | `debug`, `info`, `warning`, or `error`. Debug includes stage timings. |

`debounce_ms` belongs to the integration, where changes are observed; default 1000, range 0–10000. Local development also supports `SESHAT_DATA_DIR`, `SESHAT_MODEL_DIR`, `SESHAT_OPTIONS` (JSON options path), and `SESHAT_API_KEY`. On HAOS persistent data always uses `/data`.

## Recognition semantics

YuNet finds landmarks and bounding boxes, SFace aligns each usable face and emits a normalized 128-dimensional embedding. For each face:

1. Compare its embedding with **every** enrolled sample from the same model/preprocessing version, using cosine dot products.
2. Score each person by their **highest** sample similarity. This preserves separate lighting/pose references rather than averaging incompatible poses. Large galleries can increase false-match risk; keep references curated.
3. Sort people by descending score, breaking equal scores by name. Accept only if the best score reaches `recognition_threshold` and the gap to the next different person reaches `ambiguity_margin`. A single enrolled person has no runner-up gap requirement.
4. Otherwise label the face `Unknown`. With no references, similarity/distance are `null`.

`similarity` is cosine similarity in [−1, 1]. `distance = 1 − similarity` in [0, 2], **not** Euclidean distance. `confidence = max(0, similarity)` for an accepted match and `0` for Unknown. This compatibility/display field is **not a probability**; a score of 0.94 does not mean “94% certain.” The confidence sensor deliberately has no percent unit.

Faces are ordered left-to-right, then top-to-bottom. `best_match` selects the accepted identity with highest similarity; if none is accepted, it selects the Unknown face with highest available similarity. Equal scores keep the earlier face. With zero usable detections, `faces=[]` and `best_match=null`. Bounding boxes use the decoded, EXIF-oriented image coordinates.

### Engine and model choice

OpenCV's maintained headless Python wheel avoids dlib compilation and brings a CPU DNN runtime, landmark alignment, detector and embedder in one dependency. YuNet is about 233 KB; SFace is about 38.7 MB. ONNX Runtime is another good CPU option, but requires additional model preprocessing/alignment code here. InsightFace is capable, but its pretrained model licensing must be considered separately from its library license. Seshat uses the OpenCV Zoo models with explicit per-model license files instead.

The downloader uses OpenCV Zoo revision `47534e27c9851bb1128ccc0102f1145e27f23f98`, immutable model paths and SHA-256 hashes from Git LFS pointers. [models.lock.json](seshat/models.lock.json) records source, sizes, hashes and licenses. Model licenses are copied into `/opt/models` in the image: YuNet **MIT**, SFace **Apache-2.0**. No models download at container startup. Python dependencies are pinned; the base image tag is pinned to Python 3.12.14, but OS package repositories/transitive dependencies mean builds are not claimed to be byte-for-byte reproducible.

The initial cosine cutoff 0.363 comes from OpenCV's SFace tutorial and its benchmark setting. Doorbell images differ materially from that benchmark. Tune against held-out known and unknown visitors, including night conditions. Raise the threshold and/or margin when false matches occur. Do not treat recognition as a liveness test or use it alone to unlock a door; photos can match.

## Entities and events

| Entity (default ID) | Value |
|---|---|
| `sensor.front_door_recognized_person` | Accepted name, `Unknown`, or `No Face`. |
| `sensor.front_door_face_confidence` | Derived similarity score 0–1, not probability. |
| `sensor.front_door_face_processing_time` | Decode/detect/embed/match duration in milliseconds, excluding transport/debounce. |

Entity IDs can get suffixes if those names already exist; confirm them on the integration page. Sensors start unavailable until the first success. A failed request makes them natively **`unavailable`**; it does not report Unknown. Last successful results remain in memory for recovery but are not exposed as current attributes while unavailable. The result remains the latest successful image result until a new source event or a failure; it is not a live presence indicator.

The person sensor's attributes contain `person`, `confidence`, `distance`, `faces_detected`, `faces`, `best_match`, `processing_ms`, `timestamp` (UTC result time), `source_entity`, `image_hash`, `threshold`, and `model`. Faces contain bounding boxes and all scoring fields. The same result is emitted in **`seshat_face_recognized`** for every completed, nonduplicate, current image, including Unknown and No Face results. Failures do not emit recognition events.

Use the event for repeated visits by the same person: a state trigger from Saad to Saad will not fire. Use `source_entity` to scope automations. The full face list lets you detect unknown companions even when the primary state is a known person.

```yaml
# Every successful recognition of Saad, including consecutive visits.
alias: Seshat - Saad at the door
triggers:
  - trigger: event
    event_type: seshat_face_recognized
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.source_entity == 'image.front_door_event_image'
         and trigger.event.data.person == 'Saad' }}
actions:
  - action: persistent_notification.create
    data:
      title: Front door
      message: Saad was recognized in the latest event image.
mode: queued
```

```yaml
# Simple change-of-person trigger.
triggers:
  - trigger: state
    entity_id: sensor.front_door_recognized_person
    to: "Saad"
actions:
  - action: persistent_notification.create
    data:
      message: Saad is at the front door.
```

```yaml
# An unknown face anywhere in the image, including beside a known person.
alias: Seshat - Unknown visitor
triggers:
  - trigger: event
    event_type: seshat_face_recognized
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.source_entity == 'image.front_door_event_image'
         and (trigger.event.data.faces | selectattr('person', 'eq', 'Unknown') | list | count) > 0 }}
actions:
  - action: persistent_notification.create
    data:
      message: An unrecognized face was detected at the door.
```

```yaml
# Multiple people; the faces array preserves each match and bounding box.
alias: Seshat - Multiple faces
triggers:
  - trigger: event
    event_type: seshat_face_recognized
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.faces_detected > 1 }}"
actions:
  - action: persistent_notification.create
    data:
      message: >-
        {{ trigger.event.data.faces | map(attribute='person') | join(', ') }}
```

To recognize on a camera integration's own supported event, create an automation with that integration's documented trigger and this action **after its event image becomes available**:

```yaml
actions:
  - action: seshat.recognize
```

The action forces processing even if the bytes match the previous image. It does not call a cloud API or fetch a continuous stream. It is also available in **Developer tools → Actions** for manual testing. If the camera supplies the notification before updating its image, use its image-ready event or a short automation delay; Seshat cannot infer an undocumented camera-specific ordering guarantee.

## Queue, duplicate and failure behavior

The integration keeps one worker and one pending notification. A fixed debounce window coalesces bursts without indefinite starvation. During a running request, subsequent events replace the pending update. After the request finishes, the newest image is fetched. An old result superseded while fetching/inferencing is discarded instead of being published. SHA-256 suppresses identical bytes after a successful result; forced actions bypass that check. Hashes are held only in memory, so a restart can process the current image once again.

All API detection/enrollment/matching work shares one executor thread. Busy requests receive `429` rather than building an unbounded inference queue. Client cancellation does not free the worker until the actual CPU operation completes. The integration retries a busy API up to three attempts, times out individual recognition calls after 45 seconds and image retrieval after 15 seconds, then marks sensors unavailable. After errors it schedules a 30-second recovery attempt; successful healthy operation is event-driven. New source updates supersede recovery timers.

Each listener admits at most four requests; body ingestion has a 30-second timeout. Upload bytes, decoded pixels, face candidates and stored samples are bounded. JPEG/PNG is checked against actual file format, malformed/animated images are rejected, and EXIF orientation is applied. OpenCV threads are limited, GPU/OpenCL is disabled, and there is only one ML runtime. Docker Compose adds two-CPU/1-GiB limits for development; these are not claimed to apply to Supervisor. On HAOS use the thread and detection-size settings to control load. N95 latency and peak memory must be measured on the actual installation.

Model load failure prevents startup; Supervisor's watchdog can detect a dead service. Database failures return `503`. Shutdown stops listeners and drains the single executor. Native inference cannot be force-cancelled safely in a Python thread; if a native call hangs, restart the app. No service errors can crash Core's main process.

## API and local development

Install Docker Engine/Desktop with Linux containers on your **development computer**, then:

```bash
cp .env.example .env
# Put a generated SESHAT_API_KEY value in .env.
docker compose up --build
```

Open [the local enrollment UI](http://localhost:8000) and enter the same key. The UI keeps it only in page memory. Compose publishes only `127.0.0.1:8000`. Its named `seshat_data` volume persists enrollments across rebuilds; `docker compose down -v` deletes that volume and its identities.

With `SESHAT_API_KEY` exported in your shell (PowerShell users should use `curl.exe` and `$env:SESHAT_API_KEY`):

```bash
curl http://localhost:8000/health
curl -H "Authorization: Bearer $SESHAT_API_KEY" \
  -F "file=@saad-day.jpg" http://localhost:8000/enroll/Saad
curl -H "Authorization: Bearer $SESHAT_API_KEY" \
  -F "file=@saad-night.jpg" http://localhost:8000/enroll/Saad
curl -H "Authorization: Bearer $SESHAT_API_KEY" \
  -F "file=@test.jpg" http://localhost:8000/recognize
curl -H "Authorization: Bearer $SESHAT_API_KEY" http://localhost:8000/people
curl -X DELETE -H "Authorization: Bearer $SESHAT_API_KEY" \
  http://localhost:8000/people/Saad
```

`DELETE /people/{name}/{sample_id}` removes one sample. URL-encode names when necessary. `/people` returns names, counts and sample IDs/model/timestamps. `POST` endpoints also accept raw JPEG/PNG bodies with the appropriate `Content-Type`. `/settings` returns non-secret model/threshold/upload settings. Only `/health` and the static UI shell are public on the API listener. Ingress has a separate listener.

Error responses use `{"detail": "..."}` with `401` unauthorized, `413` too large, `415` wrong MIME, `422` malformed image/name or invalid enrollment, `404` missing enrollment, `429` busy, and `503` database/recognition failure. An empty detection result is HTTP 200.

For native Python development (Python 3.12):

```bash
python -m venv .venv
# Activate .venv using your shell's activation command.
pip install -r requirements-dev.txt
python seshat/scripts/download_models.py --output models
export SESHAT_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export SESHAT_MODEL_DIR="$PWD/models"
export SESHAT_DATA_DIR="$PWD/data"
cd seshat
python -m app
```

Native mode binds the authenticated API on all interfaces; prefer Compose's loopback-only mapping or a local firewall during development. Port 8099 always rejects clients other than Supervisor's Ingress address.

## Privacy, storage and upgrades

Runtime has no telemetry or external model/image uploads. The image's own Home Assistant integration may have separate network behavior. Image bytes are temporary, not written to the enrollment database; multipart parsing may spool larger uploads to temporary storage, which is closed after each request. No image contents or embeddings appear in application logs. HTTP access logs are disabled so enrollment paths/names are not recorded by Uvicorn. Logs contain stage counts/timings and exception classes. Home Assistant's own logs/backups may contain result names.

Ingress port 8099 accepts **only the actual TCP peer `172.30.32.2`**, as required by Supervisor, and does not trust forwarded-IP headers. The separate port-8000 API uses constant-time bearer-key comparison. No ports are published on HAOS by default. Anyone granted Seshat Ingress access is trusted to manage enrollments; use Home Assistant's app access controls accordingly. Do not publish either port to the Internet. This is local HTTP within the trusted Supervisor network; configure TLS if deliberately moving the service across an untrusted network.

SQLite uses transactions, WAL, a schema version, normalized float32 embeddings, model ID, source-image hash, sample UUID and UTC creation time. Runtime files use a restrictive umask on Linux. Data survives Supervisor restarts, HAOS reboot and app upgrades because `/data` is persistent. Removing the app/data or deleting its backup can remove these records. Back up the app with Home Assistant's backup UI before upgrades. For manual SQLite copying, stop the app first or use SQLite's backup API; copying only a live `.db` without its WAL is unsafe.

Embeddings are biometric data, **not encrypted at rest by this application**. Protect HAOS storage and backups. Deleting samples removes active database rows; it does not erase historical Home Assistant backups, recorder data, or SSD remnants. Configure recorder exclusions for the three sensors if you do not want identity history recorded.

Changing the model or preprocessing requires a new `MODEL_ID`. Queries never mix model versions, and old samples remain visible with their model IDs. Original photos are intentionally not retained, so regeneration requires re-enrolling from photos you keep privately. Keep the previous image/database backup for rollback. Future schema versions fail closed rather than silently overwriting data.

## End-to-end acceptance test

1. In Developer tools → States, confirm `image.front_door_event_image` exists and contains a recent timestamp. Open its image to verify bytes can be retrieved by Home Assistant.
2. Start Seshat, open its Web UI, and enroll Saad. Upload a held-out test image there and inspect scores.
3. Install/configure the Seshat integration. Confirm the three sensors appear.
4. In Developer tools → Events, listen for `seshat_face_recognized`.
5. Run the `seshat.recognize` action. Verify the event's `source_entity`, faces and `timestamp`, and inspect the person sensor.
6. Generate a real doorbell event with Saad facing the camera. Expect a new event and `Saad` if the threshold/margin accept the match.
7. Try an unenrolled visitor; expect a detected `Unknown`. Try an image with no usable face; expect `No Face`.
8. Generate rapid image updates and inspect app CPU/logs: one inference at a time; no stale result published after a newer notification.
9. Stop the app and invoke recognition: sensors should become unavailable. Restart it and allow recovery; expect a current result without restarting Core.
10. Restart the app/HAOS and confirm enrollment counts survive. Use normal event automations for repeated recognition of the same name.

## Troubleshooting

| Symptom | Checks |
|---|---|
| App will not start | Set a random API key of at least 32 characters; inspect validated option names in logs; confirm amd64. |
| Model will not load/build | Check registry/GitHub access at **build time**, model checksum error, available disk and memory. Rebuild the app; do not disable checksum verification. |
| Integration cannot connect | Use the actual app Info-page hostname and port 8000; verify the shared key and running app. No HA token is needed. |
| Image retrieval/authentication fails | The helper runs inside Core, so check the source camera/image integration's credentials, state, logs and image availability. A 401 from Seshat instead indicates its API key. |
| Image does not trigger | Check state/meaningful attribute updates. Token-only rotations are ignored. Call `seshat.recognize` after the camera's documented image-ready event if it does not publish a state change. |
| Duplicate triggers | Inspect actual bytes/hash: a camera can encode identical pixels with different JPEG metadata. Only byte-identical images are deduplicated. Forced actions intentionally bypass hashing. |
| Faces not detected | Check resolution, head angle, blur, `min_face_size`, and detection settings. Small/obscured faces can result in No Face. Test through Ingress. |
| Known person is Unknown | Compare similarity, threshold and runner-up margin. Add representative references and inspect enrollment model IDs. |
| False positive | Raise threshold/margin, remove bad reference photos, and test against held-out unknown visitors. Never loosen blindly for night vision. |
| CPU high | Use 1 thread, reduce detection size, increase debounce window, and ensure automations are not forcing recognition continuously. |
| API 429 | Inference/enrollment is busy. Retry after a short delay. HA automatically retries and then performs recovery. |
| Database error/capacity | Check `/data` free space and permissions, sample count, and backups. Remove unneeded samples through the UI. |
| Sensors appear stale | They represent the last result, not live presence. Check source image timestamp and whether any events were emitted. |
| Ingress unauthorized | Use Open Web UI in Home Assistant, not a direct connection to 8099; only Supervisor is trusted there. |

## Tests and releases

```bash
ruff check .
ruff format --check .
pytest -m "not ml"
python seshat/scripts/download_models.py --output models
pytest -m ml
docker build -t seshat:test ./seshat
```

Unit tests use synthetic embeddings and generated PNGs; they never fetch remote fixtures. ML smoke tests only run with locally acquired models. Controller tests use explicit Home Assistant doubles and do not substitute for the HAOS acceptance procedure above.

`test.yml` runs lint, tests, model acquisition, ML smoke tests, Docker build and container-health verification. `build.yml` validates a `v1.0.0`-style tag against `seshat/config.yaml` and publishes `ghcr.io/<your-account>/seshat-amd64:1.0.0` using GitHub's built-in token. No external credentials are embedded. Configure repository Actions/package permissions and package visibility in GitHub.

Source builds are the default. After the first successful release and making the GHCR package public, you may add `image: ghcr.io/srashee/seshat-{arch}` to the app config to use prebuilt images. The release workflow also creates a draft GitHub release with a companion integration ZIP. Keep app, integration and image versions synchronized; install updated custom integration files and restart Core when changing integration code. No workflow automatically deploys to your home.

## Verified upstream references

Reviewed 2026-10-02; live documentation can evolve. The custom integration's image-helper contract should be checked when upgrading Home Assistant.

- [Home Assistant app configuration and current build arguments](https://developers.home-assistant.io/docs/apps/configuration/)
- [App repositories](https://developers.home-assistant.io/docs/apps/repository/)
- [Supervisor networking and API authentication](https://developers.home-assistant.io/docs/apps/communication/)
- [Ingress authentication and required source-IP restriction](https://developers.home-assistant.io/docs/apps/presentation/)
- [HAOS common tasks and installation terminology](https://www.home-assistant.io/common-tasks/os/)
- [Image entity contract](https://developers.home-assistant.io/docs/core/entity/image/)
- [Current image implementation and `async_get_image`](https://github.com/home-assistant/core/blob/dev/homeassistant/components/image/__init__.py)
- [OpenCV YuNet/SFace tutorial, metric and initial threshold](https://docs.opencv.org/4.13.0/d0/dd4/tutorial_dnn_face.html)
- [Pinned YuNet source/license](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet)
- [Pinned SFace source/license](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_recognition_sface)
