# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
MediaPipe 姿态检测 + 坐姿分析
依赖：pip install mediapipe opencv-python numpy
"""
import math
import time
import cv2
import numpy as np

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False

from config import config


class PoseDetector:
    """基于 MediaPipe Pose 的坐姿检测器"""

    # MediaPipe 关键点索引
    NOSE = 0
    LEFT_EYE = 1; RIGHT_EYE = 4
    LEFT_EAR = 7; RIGHT_EAR = 8
    LEFT_SHOULDER = 11; RIGHT_SHOULDER = 12
    LEFT_HIP = 23; RIGHT_HIP = 24
    LEFT_KNEE = 25; RIGHT_KNEE = 26

    def __init__(self):
        if not HAS_MEDIAPIPE:
            raise ImportError("请安装 mediapipe：pip install mediapipe")

        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,          # 0=轻量, 1=完整, 2=高精度
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.mp_draw = mp.solutions.drawing_utils

        # 状态追踪
        self.bad_posture_count = 0
        self.good_posture_count = 0
        self.last_check_time = time.time()
        self.sitting = True
        self.sit_start_time = time.time()
        self.person_present = False
        self.last_present_time = time.time()

    def process_frame(self, frame) -> dict:
        """处理一帧图像，返回分析结果"""
        if not HAS_MEDIAPIPE:
            return {"error": "MediaPipe 未安装"}

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)

        result = {
            "timestamp": time.time(),
            "person_detected": False,
            "is_sitting": False,
            "posture_status": "unknown",
            "slouch_angle": None,
            "head_tilt_angle": None,
            "forward_head_distance": None,
            "alerts": [],
            "landmarks": None,
        }

        if results.pose_landmarks:
            result["person_detected"] = True
            result["landmarks"] = results.pose_landmarks
            lm = results.pose_landmarks.landmark

            h, w = frame.shape[:2]

            # 计算各角度
            result["slouch_angle"] = self._calc_slouch_angle(lm, h, w)
            result["head_tilt_angle"] = self._calc_head_tilt(lm)
            result["forward_head_distance"] = self._calc_forward_head(lm, h, w)
            result["is_sitting"] = self._detect_sitting(lm)

            # 生成警报
            cfg = config.posture
            if result["slouch_angle"] and result["slouch_angle"] > cfg.shoulder_slouch_angle:
                result["alerts"].append("slouch")
            if result["head_tilt_angle"] and result["head_tilt_angle"] > cfg.head_tilt_angle:
                result["alerts"].append("head_tilt")

            if result["alerts"]:
                result["posture_status"] = "bad"
            else:
                result["posture_status"] = "good"

        return result

    def _calc_slouch_angle(self, lm, h, w) -> float:
        """计算驼背角度：双肩中点 → 双髋中点 连线与垂直线的夹角"""
        sx = (lm[self.LEFT_SHOULDER].x + lm[self.RIGHT_SHOULDER].x) / 2 * w
        sy = (lm[self.LEFT_SHOULDER].y + lm[self.RIGHT_SHOULDER].y) / 2 * h
        hx = (lm[self.LEFT_HIP].x + lm[self.RIGHT_HIP].x) / 2 * w
        hy = (lm[self.LEFT_HIP].y + lm[self.RIGHT_HIP].y) / 2 * h

        dx, dy = sx - hx, sy - hy
        angle = abs(math.degrees(math.atan2(dx, abs(dy))))
        return round(angle, 1)

    def _calc_head_tilt(self, lm) -> float:
        """计算头部倾斜角：左耳 → 右耳 连线与水平线的夹角"""
        lx, ly = lm[self.LEFT_EAR].x, lm[self.LEFT_EAR].y
        rx, ry = lm[self.RIGHT_EAR].x, lm[self.RIGHT_EAR].y

        angle = abs(math.degrees(math.atan2(ry - ly, rx - lx + 1e-6)))
        if angle > 90:
            angle = angle - 90
        return round(angle, 1)

    def _calc_forward_head(self, lm, h, w) -> float:
        """估算头前伸程度：鼻子 vs 肩中点在 x 方向偏移（归一化）"""
        nose_x = lm[self.NOSE].x * w
        shoulder_center_x = (lm[self.LEFT_SHOULDER].x + lm[self.RIGHT_SHOULDER].x) / 2 * w
        shoulder_width = abs(lm[self.LEFT_SHOULDER].x - lm[self.RIGHT_SHOULDER].x) * w
        if shoulder_width < 10:
            return None
        ratio = abs(nose_x - shoulder_center_x) / shoulder_width
        return round(ratio * 10, 1)  # 转换为近似 cm（假设肩宽 40cm，ratio * 肩宽 ≈ cm）

    def _detect_sitting(self, lm) -> bool:
        """判断是否在坐着：膝盖 y 坐标 > 髋 y 坐标（髋在上）且视线大致水平"""
        hip_y = (lm[self.LEFT_HIP].y + lm[self.RIGHT_HIP].y) / 2
        knee_y = (lm[self.LEFT_KNEE].y + lm[self.RIGHT_KNEE].y) / 2
        return knee_y > hip_y

    def get_draw_frame(self, frame):
        """返回标注了姿态关键点的帧（调试用）"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)
        if results.pose_landmarks:
            self.mp_draw.draw_landmarks(frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS)
        return frame

    def release(self):
        self.pose.close()
