"""Conservative image-only arm gestures with explicit face/body association.

Labels describe visible arm geometry, not finger direction or a person's intent.
Coordinates use the EXIF-oriented image: up/down mean image up/down.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from .config import Settings
from .vendor.person_detection_mediapipe.mp_persondet import MPPersonDet
from .vendor.pose_estimation_mediapipe.mp_pose import MPPose

LOGGER = logging.getLogger(__name__)
POSE_MODEL_ID = "mediapipe-pose-2023mar-9d89c599-person-47fd5599-rules-v1"
MAX_POSE_SIDE = 960


@dataclass
class Pose:
    # MediaPipe landmark order; each row is x, y, z, visibility, presence.
    landmarks: np.ndarray
    score: float


@dataclass
class PoseBatch:
    poses: list[Pose]
    limited: bool = False


class PoseBackend(Protocol):
    def infer(self, image: np.ndarray) -> PoseBatch: ...


def unknown_gesture(reason: str, label: str = "undetermined") -> dict:
    return {"label": label, "quality": None, "arm": None, "reason": reason, "arms": []}


def usable(landmarks: np.ndarray, indices: list[int], width: int, height: int, cutoff: float) -> bool:
    selected = landmarks[indices]
    return bool(
        np.isfinite(selected).all()
        and np.all(selected[:, 3:] >= cutoff)
        and np.all(selected[:, 3:] <= 1)
        and np.all(selected[:, 0] >= 0)
        and np.all(selected[:, 0] < width)
        and np.all(selected[:, 1] >= 0)
        and np.all(selected[:, 1] < height)
    )


def classify_pose(pose: Pose, width: int, height: int, cutoff: float) -> dict:
    points = pose.landmarks
    if points.shape != (33, 5) or not np.isfinite(pose.score) or pose.score < cutoff:
        return unknown_gesture("low_pose_quality")
    if not usable(points, [11, 12], width, height, cutoff):
        return unknown_gesture("shoulders_not_visible")
    shoulders = points[[11, 12], :2]
    span = float(np.linalg.norm(shoulders[0] - shoulders[1]))
    # Strong profiles, tiny bodies, or near-vertical shoulder lines are unreliable.
    if span < 20 or abs(shoulders[0, 0] - shoulders[1, 0]) < span * 0.7:
        return unknown_gesture("body_too_small_or_sideways")
    arms = []
    for side, shoulder_index, elbow_index, wrist_index, other_shoulder in (
        ("left", 11, 13, 15, 12),
        ("right", 12, 14, 16, 11),
    ):
        indices = [11, 12, elbow_index, wrist_index]
        if not usable(points, indices, width, height, cutoff):
            arms.append({"arm": side, "label": "undetermined", "quality": None, "reason": "arm_not_visible"})
            continue
        shoulder, elbow, wrist = points[[shoulder_index, elbow_index, wrist_index], :2]
        upper, lower = shoulder - elbow, wrist - elbow
        upper_length, lower_length = float(np.linalg.norm(upper)), float(np.linalg.norm(lower))
        quality = float(min(pose.score, np.min(points[indices, 3:])))
        if not (0.2 * span <= upper_length <= 2.5 * span and 0.2 * span <= lower_length <= 2.5 * span):
            arms.append(
                {"arm": side, "label": "undetermined", "quality": None, "reason": "implausible_arm_geometry"}
            )
            continue
        angle = float(
            np.degrees(np.arccos(np.clip(np.dot(upper, lower) / (upper_length * lower_length), -1, 1)))
        )
        delta = wrist - shoulder
        reach = float(np.linalg.norm(delta))
        vertical = abs(float(delta[1])) / max(reach, 1)
        outward_sign = float(np.sign(shoulder[0] - points[other_shoulder, 0]))
        elbow_out = float((elbow[0] - shoulder[0]) * outward_sign) / span
        wrist_out = float((wrist[0] - shoulder[0]) * outward_sign) / span
        label, reason = "no_gesture", "no_supported_arm_pose"
        if angle >= 150 and delta[1] < -0.75 * span and vertical >= 0.7:
            label, reason = "pointing_up", "extended_arm_up"
        elif angle >= 150 and delta[1] > span and vertical >= 0.65 and elbow_out >= 0.25 and wrist_out >= 0.5:
            # Require an arm held away from the torso; hanging arms are not pointing.
            label, reason = "pointing_down", "extended_arm_down_away_from_torso"
        elif wrist[1] < shoulder[1] - 0.35 * span and wrist[1] < elbow[1] - 0.2 * span:
            label, reason = "hand_raised", "bent_or_nonvertical_raised_arm"
        arms.append({"arm": side, "label": label, "quality": quality, "reason": reason})

    positive = [arm for arm in arms if arm["label"] not in ("undetermined", "no_gesture")]
    labels = {arm["label"] for arm in positive}
    if len(labels) > 1:
        result = unknown_gesture("conflicting_arm_gestures")
    elif positive:
        result = {
            "label": positive[0]["label"],
            "quality": min(arm["quality"] for arm in positive),
            "arm": "both" if len(positive) == 2 else positive[0]["arm"],
            "reason": positive[0]["reason"],
        }
    elif any(arm["label"] == "undetermined" for arm in arms):
        result = unknown_gesture("arm_not_visible_or_reliable")
    else:
        result = {
            "label": "no_gesture",
            "quality": min(arm["quality"] for arm in arms),
            "arm": None,
            "reason": "no_supported_arm_pose",
        }
    result["arms"] = arms
    return result


def attach_gestures(faces: list[dict], poses: list[Pose], width: int, height: int, cutoff: float) -> None:
    """Associate only unambiguous one-to-one head/face overlaps, never by identity score."""
    face_candidates: list[list[int]] = [[] for _ in faces]
    pose_candidates: list[list[int]] = [[] for _ in poses]
    for index, pose in enumerate(poses):
        points = pose.landmarks
        if (
            points.shape != (33, 5)
            or not np.isfinite(pose.score)
            or pose.score < cutoff
            or not usable(points, [0, 11, 12], width, height, cutoff)
        ):
            continue
        head = [j for j in range(11) if usable(points, [j], width, height, cutoff)]
        if len(head) < 3:
            continue
        head_center = np.median(points[head, :2], axis=0)
        shoulder_span = np.linalg.norm(points[11, :2] - points[12, :2])
        for face_index, face in enumerate(faces):
            box = face["bbox"]
            x, y, fw, fh = (box[key] for key in ("x", "y", "width", "height"))
            if fw <= 0 or fh <= 0 or not 0.6 * fw <= shoulder_span <= 6 * fw:
                continue
            # Both the nose and the median facial landmarks must be in the face box.
            if all(
                x - 0.1 * fw <= point[0] <= x + 1.1 * fw and y - 0.1 * fh <= point[1] <= y + 1.1 * fh
                for point in (points[0], head_center)
            ):
                face_candidates[face_index].append(index)
                pose_candidates[index].append(face_index)
    for index, face in enumerate(faces):
        candidates = face_candidates[index]
        if not candidates:
            face["gesture"] = unknown_gesture("no_reliable_body_for_face")
        elif len(candidates) != 1 or len(pose_candidates[candidates[0]]) != 1:
            face["gesture"] = unknown_gesture("ambiguous_face_body_association")
        else:
            face["gesture"] = classify_pose(poses[candidates[0]], width, height, cutoff)


class GestureEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.detector = MPPersonDet(
            str(settings.model_dir / "person.onnx"),
            scoreThreshold=0.6,
            topK=1000,
            backendId=cv2.dnn.DNN_BACKEND_OPENCV,
            targetId=cv2.dnn.DNN_TARGET_CPU,
        )
        self.pose = MPPose(
            str(settings.model_dir / "pose.onnx"),
            confThreshold=settings.gesture_min_quality,
            backendId=cv2.dnn.DNN_BACKEND_OPENCV,
            targetId=cv2.dnn.DNN_TARGET_CPU,
        )
        LOGGER.info("gesture_model_initialized model=%s", POSE_MODEL_ID)

    def infer(self, image: np.ndarray) -> PoseBatch:
        height, width = image.shape[:2]
        scale = min(1.0, MAX_POSE_SIDE / max(width, height))
        small = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))))
        detections = sorted(self.detector.infer(small), key=lambda row: -float(row[-1]))
        batch = PoseBatch([], limited=len(detections) > self.settings.gesture_max_people)
        for detection in detections[: self.settings.gesture_max_people]:
            if not np.isfinite(detection).all():
                continue
            center, edge = detection[4:8].reshape(2, 2)
            radius = float(np.linalg.norm(center - edge))
            # Bound the helper's crop/pad allocation, including malformed model output.
            if not 10 <= radius <= MAX_POSE_SIDE * 1.25:
                continue
            if (
                center[0] + radius <= 0
                or center[1] + radius <= 0
                or center[0] - radius >= small.shape[1]
                or center[1] - radius >= small.shape[0]
            ):
                continue
            output = self.pose.infer(small, detection.copy())
            if output is None:
                continue
            landmarks = output[1][:33].copy()
            landmarks[:, :3] /= scale
            batch.poses.append(Pose(landmarks, float(output[-1])))
        return batch
