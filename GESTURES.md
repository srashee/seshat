# Local arm gestures (Seshat 1.1.0)

## Upgrade and enable

Refresh Home Assistant's App Store, update Seshat to **1.1.0**, then set these options and restart the app:

```yaml
gesture_enabled: true
gesture_min_quality: 0.7
gesture_max_people: 4
```

Open Web UI and confirm “Arm gestures are on.” Upload a still photo showing your face, both shoulders, and the relevant elbow and wrist. The summary shows the primary person's name and gesture; the JSON retains per-face/per-arm results and reasons for undetermined poses. No gesture enrollment is needed.

Install/update `custom_components/seshat` from the same version and restart Core to get `sensor.front_door_gesture`. If you have not installed the companion integration yet, use the latest files for the first installation. Face embeddings and the face model/preprocessing ID are unchanged, so you do **not** need to enroll your face again.

## Results

| Label | Meaning |
|---|---|
| `pointing_up` | A nearly straight arm extends upward in the image. |
| `pointing_down` | A nearly straight arm extends downward **away from the torso**. Resting arms are excluded. |
| `hand_raised` | A wrist is clearly above its shoulder and elbow without meeting the straight-up rule. |
| `no_gesture` | Both arms are sufficiently visible, but neither meets a supported rule. |
| `undetermined` | Hidden/unreliable joints, ambiguous face/body association, conflicting gestures, or pose failure. See `gesture_reason`. |
| `no_face` | No usable face was detected, so no named-person gesture is reported. |
| `disabled` | The feature is off or the older app does not report gestures. |

These describe **arm geometry**, not intent or index-finger direction. Reaching for something can resemble pointing. Finger-only up/down, waving, and general activity descriptions are not supported. A single snapshot cannot establish motion. Directions are relative to the EXIF-oriented image; a tilted camera or rotated body reduces reliability. `left`/`right` refer to model anatomical arm labels, not screen position; mirror settings can affect them.

The top-level gesture always belongs to the same face as `best_match`. Other faces retain their own `gesture` object. `gesture_status` is `ok`, `limited` (person cap reached), `disabled`, or `unavailable`. A pose-only failure leaves face recognition available and reports an undetermined gesture, not a failed identity.

API example (illustrative scores):

```json
{
  "gesture": "pointing_up",
  "gesture_quality": 0.91,
  "gesture_arm": "left",
  "gesture_reason": "extended_arm_up",
  "gesture_status": "ok",
  "faces": [{
    "person": "Saad",
    "gesture": {
      "label": "pointing_up",
      "quality": 0.91,
      "arm": "left",
      "reason": "extended_arm_up",
      "arms": []
    }
  }]
}
```

The actual response also includes the existing face scores/bounding boxes and per-arm results. `gesture_quality` is the minimum pose score and relevant joint visibility/presence across the selected arm(s), **not a calibrated probability that the gesture is correct**. Undetermined/disabled results have no manufactured quality value.

## Example: Saad pointing up

```yaml
alias: Seshat - Saad pointing up
triggers:
  - trigger: event
    event_type: seshat_face_recognized
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.source_entity == 'image.front_door_event_image'
         and trigger.event.data.person == 'Saad'
         and trigger.event.data.gesture == 'pointing_up' }}
actions:
  - action: persistent_notification.create
    data:
      message: Saad is pointing up in the front-door event image.
```

For multiple people, inspect each item in `trigger.event.data.faces` and its `gesture.label`; do not combine one face's name with another face's gesture. Use events for repeated instances of the same gesture. Start with notifications and test raised, resting, hidden and downward arms before using gestures for other actions.

If manual image tests work but a held gesture does not trigger an automation, check whether the doorbell supplied a new event image. Pose analysis does not add continuous capture; a changed pose needs a new event image or the `seshat.recognize` action with updated source bytes.

## Association and rules

The Apache-2.0 OpenCV Zoo MediaPipe person detector finds body candidates and its lightweight pose model estimates 33 joints. Both run through the existing CPU OpenCV runtime. Input is bounded to a 960-pixel longest side; pose input is 256×256. Candidates are processed by detector score up to `gesture_max_people`, and crop sizes are bounded before allocation. Pose work shares the one inference worker and never runs during enrollment or when there are no detected faces.

A body is assigned to a face only if its reliable nose and median facial landmarks overlap that face box (10% tolerance), with plausible shoulder-to-face scale. At least three head landmarks and both shoulders must pass the quality gate. Both face-to-body and body-to-face assignments must be unique. Ambiguous assignments report `ambiguous_face_body_association`. Faces without reliable associated bodies—including unprocessed candidates beyond the cap—remain undetermined.

The relevant joints must be in frame and pass both visibility and presence thresholds. Shoulder span must be at least 20 original-image pixels and sufficiently horizontal. Projected upper/lower arm lengths must each be 0.2–2.5 shoulder widths. Straight-arm rules require an elbow angle of at least 150°:

- **Up:** wrist at least 0.75 shoulder widths above its shoulder; vertical component at least 70% of reach.
- **Down:** wrist more than one shoulder width below its shoulder; vertical component at least 65%; elbow and wrist at least 0.25 and 0.5 shoulder widths outward from their shoulder.
- **Raised:** wrist at least 0.35 shoulder widths above its shoulder and 0.2 shoulder widths above its elbow, after the pointing rules.

A clear gesture on one arm can be reported even when the other is hidden. Different positive gestures on two arms yield `undetermined` / `conflicting_arm_gestures`; the `arms` array retains both findings. Two arms with the same label report `arm=both`. Both arms must be reliable before reporting `no_gesture`.

## Models, privacy and verification

The two additional weights total about 17.5 MB, pinned to OpenCV Zoo revision `47534e27c9851bb1128ccc0102f1145e27f23f98` with hashes/licenses in `seshat/models.lock.json`. No new Python inference dependency or runtime download is needed. Adapted upstream helpers and Apache licenses are under `seshat/app/vendor`; model sources are [person detection](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/person_detection_mediapipe) and [pose estimation](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/pose_estimation_mediapipe).

Raw landmarks/images are not persisted; gesture labels and quality may appear in Home Assistant recorder history just like recognized names. The feature is disabled by default to preserve existing resource usage. Missing/corrupt pose models are reported in logs and `/health` as `gesture_model_loaded=false`, while face recognition continues.

Positive gesture rules are tested with synthetic landmarks. Real-model smoke tests verify pose decoding and conservative rejection of the cropped/occluded public-domain fixture. The browser test exercises enrollment, recognition with gestures enabled, deletion and restart persistence. These checks do not establish accuracy on your doorbell. Test held-out images of yourself in each intended pose, alongside resting arms, occlusion and multiple people, before relying on automation results.
