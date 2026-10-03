# OpenCV Zoo pose adapters

Adapted from https://github.com/opencv/opencv_zoo at revision
`47534e27c9851bb1128ccc0102f1145e27f23f98`:

- `models/person_detection_mediapipe/mp_persondet.py`
- `models/pose_estimation_mediapipe/mp_pose.py`

Both upstream directories license all their files under Apache-2.0. Copies of
the full license are retained in the corresponding directories. Model licenses
are also acquired separately alongside the downloaded weights.

Seshat modifications:

- Generate the 2,254 detector anchor centers rather than embedding the literal
  table; exact equality with the pinned upstream array was verified.
- Convert detector boxes from corners to width/height before OpenCV NMS.
- Copy person keypoints before coordinate transforms, preserving caller data.
- Clip sigmoid logits to prevent numeric overflow and fix backend setter fields.
- Omit full-frame segmentation-mask postprocessing, which gestures do not use.
- Keep upstream landmark decoding without optional heatmap refinement.
- Apply repository formatting/lint rules.

The Seshat wrapper bounds image/crop sizes and person counts before using these
adapters. These are image-mode inference helpers; no tracking or video loop runs.
