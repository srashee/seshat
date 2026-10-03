from unittest.mock import Mock

import numpy as np
import pytest
from app.gestures import GestureEngine, Pose, PoseBatch, attach_gestures, classify_pose
from app.main import Runtime


def landmarks() -> np.ndarray:
    points = np.zeros((33, 5), dtype=np.float32)
    points[:, 3:] = 0.95
    points[:11, :2] = [330, 245]
    points[11, :2], points[12, :2] = [280, 300], [380, 300]
    points[13, :2], points[15, :2] = [275, 390], [270, 490]
    points[14, :2], points[16, :2] = [385, 390], [390, 490]
    return points


def pose_for(label: str) -> Pose:
    points = landmarks()
    if label == "pointing_up":
        points[13, :2], points[15, :2] = [280, 200], [280, 100]
    elif label == "pointing_down":
        points[13, :2], points[15, :2] = [235, 390], [190, 480]
    elif label == "hand_raised":
        points[13, :2], points[15, :2] = [210, 330], [210, 230]
    return Pose(points, 0.96)


@pytest.mark.parametrize("label", ["pointing_up", "pointing_down", "hand_raised", "no_gesture"])
def test_supported_arm_geometry(label):
    result = classify_pose(pose_for(label), 640, 640, 0.7)
    assert result["label"] == label
    assert result["quality"] == pytest.approx(0.95)
    assert result["arm"] == (None if label == "no_gesture" else "left")


def test_hanging_arms_are_not_pointing_down():
    result = classify_pose(pose_for("no_gesture"), 640, 640, 0.7)
    assert result["label"] == "no_gesture"
    assert all(arm["label"] == "no_gesture" for arm in result["arms"])


@pytest.mark.parametrize("change", ["occluded", "out_of_frame", "nan", "short", "profile", "score"])
def test_unreliable_pose_is_undetermined(change):
    pose = pose_for("pointing_up")
    if change == "occluded":
        pose.landmarks[15, 3] = 0.2
    elif change == "out_of_frame":
        pose.landmarks[15, 1] = -1
    elif change == "nan":
        pose.landmarks[11, 0] = np.nan
    elif change == "short":
        pose.landmarks[15, :2] = pose.landmarks[13, :2]
    elif change == "profile":
        pose.landmarks[12, :2] = [285, 400]
    else:
        pose.score = 0.4
    assert classify_pose(pose, 640, 640, 0.7)["label"] == "undetermined"


def test_one_clear_gesture_works_with_other_arm_occluded():
    pose = pose_for("pointing_up")
    pose.landmarks[16, 3] = 0.1
    assert classify_pose(pose, 640, 640, 0.7)["label"] == "pointing_up"


def test_conflicting_arms_do_not_guess():
    pose = pose_for("pointing_up")
    pose.landmarks[14, :2], pose.landmarks[16, :2] = [425, 390], [470, 480]
    result = classify_pose(pose, 640, 640, 0.7)
    assert result["label"] == "undetermined"
    assert result["reason"] == "conflicting_arm_gestures"
    assert {arm["label"] for arm in result["arms"]} == {"pointing_up", "pointing_down"}


def test_both_arms_same_gesture():
    pose = pose_for("pointing_up")
    pose.landmarks[14, :2], pose.landmarks[16, :2] = [380, 200], [380, 100]
    result = classify_pose(pose, 640, 640, 0.7)
    assert result["label"] == "pointing_up" and result["arm"] == "both"


def face_at(x=300, name="Saad"):
    return {"person": name, "bbox": {"x": x, "y": 220, "width": 60, "height": 60}}


def test_multi_person_association_uses_own_face():
    first, second = pose_for("pointing_up"), pose_for("pointing_down")
    second.landmarks[:, 0] += 300
    faces = [face_at(), face_at(600, "Other")]
    attach_gestures(faces, [second, first], 1000, 640, 0.7)
    assert faces[0]["gesture"]["label"] == "pointing_up"
    assert faces[1]["gesture"]["label"] == "pointing_down"


def test_unassociated_and_ambiguous_faces():
    faces = [face_at(50)]
    attach_gestures(faces, [pose_for("pointing_up")], 640, 640, 0.7)
    assert faces[0]["gesture"]["reason"] == "no_reliable_body_for_face"
    faces = [face_at(), face_at(310, "Other")]
    attach_gestures(faces, [pose_for("pointing_up")], 640, 640, 0.7)
    assert all(face["gesture"]["reason"] == "ambiguous_face_body_association" for face in faces)
    faces = [face_at()]
    attach_gestures(faces, [pose_for("pointing_up"), pose_for("pointing_down")], 640, 640, 0.7)
    assert faces[0]["gesture"]["label"] == "undetermined"


def test_hidden_nose_cannot_assign_body_to_identity():
    pose = pose_for("pointing_up")
    pose.landmarks[0, 3] = 0.1
    faces = [face_at()]
    attach_gestures(faces, [pose], 640, 640, 0.7)
    assert faces[0]["gesture"]["label"] == "undetermined"


def test_pose_detection_and_crop_bounds(runtime):
    engine = GestureEngine.__new__(GestureEngine)
    engine.settings = runtime.settings
    engine.settings.gesture_max_people = 1
    enormous_crop = np.array([0, 0, 30, 30, 320, 320, 1e8, 1e8, 0, 0, 0, 0, 0.95])
    engine.detector = Mock(infer=Mock(return_value=[enormous_crop, enormous_crop]))
    engine.pose = Mock()
    batch = engine.infer(np.zeros((2000, 1000, 3), dtype=np.uint8))
    assert batch.limited and batch.poses == []
    engine.pose.infer.assert_not_called()
    assert max(engine.detector.infer.call_args.args[0].shape[:2]) == 960


def test_pose_failure_preserves_face_result(runtime, png, face):
    runtime.engine.output = [face]
    runtime.settings.gesture_enabled = True
    runtime.recognizer.gestures = Mock(infer=Mock(side_effect=RuntimeError("pose failure")))
    result = runtime.recognizer.recognize(png(), "image/png")
    assert result["best_match"]["person"] == "Unknown"
    assert result["gesture"] == "undetermined"
    assert result["gesture_reason"] == "pose_inference_failed"
    assert result["gesture_status"] == "unavailable"


def test_disabled_and_no_face_skip_pose_inference(runtime, png, face):
    backend = Mock()
    runtime.recognizer.gestures = backend
    runtime.engine.output = [face]
    result = runtime.recognizer.recognize(png(), "image/png")
    assert result["gesture"] == "disabled"
    runtime.settings.gesture_enabled = True
    runtime.engine.output = []
    result = runtime.recognizer.recognize(png(), "image/png")
    assert result["gesture"] == "no_face"
    backend.infer.assert_not_called()


def test_missing_pose_model_does_not_break_startup(runtime, monkeypatch):
    runtime.settings.gesture_enabled = True
    monkeypatch.setattr("app.main.GestureEngine", Mock(side_effect=OSError("missing model")))
    fallback = Runtime(runtime.settings, engine=runtime.engine)
    try:
        assert fallback.engine is runtime.engine and fallback.gestures is None
    finally:
        fallback.close()


def test_recognizer_reports_gesture_for_the_best_face(runtime, monkeypatch, face):
    image = np.zeros((640, 640, 3), dtype=np.uint8)
    monkeypatch.setattr("app.recognition.decode", lambda *_: image)
    runtime.settings.gesture_enabled = True
    face.bbox = face_at()["bbox"]
    runtime.engine.output = [face]
    runtime.recognizer.gestures = Mock(
        infer=Mock(return_value=PoseBatch([pose_for("pointing_up")], limited=True))
    )
    result = runtime.recognizer.recognize(b"test", "image/png")
    assert result["gesture"] == result["best_match"]["gesture"]["label"] == "pointing_up"
    assert result["gesture_status"] == "limited"
