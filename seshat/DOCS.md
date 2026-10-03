# Seshat setup

1. Generate a random API key of at least 32 characters. Set `api_key` in Configuration; leave the port mapping disabled.
2. Start Seshat and enable Start on boot and Watchdog.
3. Open Web UI. Enter a name, select several photos with one face each, and select Enroll photos. Test a separate event image.
4. Copy the repository's `custom_components/seshat` folder to `/config/custom_components/seshat` in Home Assistant Core, then restart Core.
5. Add Seshat under Settings → Devices & services. Use `http://<Seshat Info-page hostname>:8000`, the same key, `image.front_door_event_image`, and a 1000 ms debounce.
6. Run `seshat.recognize` in Developer tools → Actions. Inspect `sensor.front_door_recognized_person` and listen for `seshat_face_recognized`.

`recognition_threshold` is cosine similarity (higher is stricter), initially 0.363. `ambiguity_margin` initially requires a 0.05 gap between different people. Confidence is a derived score, not a probability. Unknown means an unmatched face; No Face means no usable detection. Failures make sensors unavailable.

Use 1–2 `cpu_threads` on an Intel N95. `detection_size` defaults to 640. Upload limits, pixel limits, face/sample caps and detector settings are available in Configuration. Keep biometric data and backups private. The database lives at `/data/faces.db` and original images are not retained for enrollment.

The repository-root README documents every option, API commands, automations, model licenses, backup/migration behavior, troubleshooting and the complete doorbell acceptance test.

## Optional arm gestures (1.1.0)

Set `gesture_enabled: true` and restart the app. The Web UI will report that arm gestures are on. Keep the face, both shoulders, and the gesturing arm's elbow/wrist clearly visible in a still event image. Supported labels are `pointing_up`, `pointing_down` and `hand_raised`; unclear poses return `undetermined`. An arm resting at your side does not count as pointing down. These are arm-position labels, not finger gestures or motion recognition.

`gesture_min_quality` defaults to 0.7 (visibility/presence gate, not identity probability); `gesture_max_people` defaults to 4 to bound CPU work. Pose inference is optional and shares the single inference worker. Existing face enrollments do not need to be replaced.

Install or update the companion integration from the same 1.1.0 source and restart Home Assistant Core to get `sensor.front_door_gesture`. The `seshat_face_recognized` event contains `person`, `gesture`, `gesture_quality`, `gesture_arm`, and per-face gesture details. Use both the person and gesture in an automation condition. See the root README for the full example and limitations.
