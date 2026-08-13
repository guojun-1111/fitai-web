# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V21+V39: Pose analysis API — causal root cause diagnosis for exercise form."""
import json
import os
import tempfile
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from core.dependencies import get_user_id

router = APIRouter(prefix="/api/pose", tags=["pose"])

# ── Biomechanical guidance per exercise (always available) ──

_EXERCISE_GUIDANCE = {
    "squat": {
        "key_checkpoints": [
            "双脚与肩同宽，脚尖微微朝外 15-30°",
            "下蹲时膝盖方向与脚尖一致，不要内扣",
            "保持背部挺直，核心收紧，视线向前",
            "下蹲至大腿与地面平行或更低",
            "重心放在脚后跟，不要前倾",
        ],
        "common_issues": [
            {"issue": "膝盖内扣", "cause": "臀中肌力量不足，髋外展无力", "fix": "弹力带侧步走激活臀中肌，深蹲时主动将膝盖向外推"},
            {"issue": "背部弯曲", "cause": "核心力量不足，或负重过大", "fix": "从无负重开始，注意保持挺胸；加练平板支撑和鸟狗式"},
            {"issue": "重心前移", "cause": "踝关节灵活性差，或习惯了错误模式", "fix": "做脚踝活动度训练；深蹲时可扶墙或杆子保持平衡"},
            {"issue": "深度不够", "cause": "髋关节灵活度不足或心理恐惧", "fix": "做高脚杯深蹲降低重心；逐步增加深度，不求一步到位"},
        ],
    },
    "pushup": {
        "key_checkpoints": [
            "手放在肩膀正下方或略宽",
            "身体从头到脚跟成一条直线",
            "下降时肘部与身体呈 45° 角",
            "下降到胸部接近地面但不触地",
            "全程核心和臀部收紧",
        ],
        "common_issues": [
            {"issue": "塌腰", "cause": "核心肌群无力，腹肌未能持续收紧", "fix": "从跪姿俯卧撑开始，确保身体直线；加练平板支撑加强核心"},
            {"issue": "肘部外展过大", "cause": "肩胛骨稳定性差，习惯性外展", "fix": "想象肘部夹住身体；做窄距俯卧撑练习"},
            {"issue": "头部下垂或抬起", "cause": "颈部肌肉紧张，专注力不足", "fix": "保持颈部自然延伸，视线看向地面略前方"},
            {"issue": "半程俯卧撑", "cause": "力量不足或对幅度的认知偏差", "fix": "降低难度（跪姿或上斜），确保每次胸触标志物"},
        ],
    },
    "plank": {
        "key_checkpoints": [
            "肘部在肩膀正下方",
            "身体从脚跟到后脑一条直线",
            "收紧臀部和腹部，骨盆保持中立",
            "双脚踏实地蹬向后方",
            "呼吸自然，不要憋气",
        ],
        "common_issues": [
            {"issue": "臀部过高", "cause": "核心未能正确激活，用髋屈肌代偿", "fix": "降低到膝盖平板；想象用肚脐贴向脊柱"},
            {"issue": "塌腰", "cause": "腹横肌力量不足，骨盆前倾", "fix": "收紧臀部，骨盆后倾；从 15 秒开始逐步增加时间"},
            {"issue": "耸肩", "cause": "上背部力量不足，颈部紧张", "fix": "主动将肩胛骨向下向后沉；放松颈部"},
        ],
    },
    "lunge": {
        "key_checkpoints": [
            "双脚分开与髋同宽，前后脚在两条平行线上",
            "躯干保持直立，核心收紧",
            "前膝不要超过脚尖",
            "后膝轻轻触地但不支撑重量",
            "用前腿发力推回起始位置",
        ],
        "common_issues": [
            {"issue": "前膝超过脚尖", "cause": "步幅太小或股四头肌控制不足", "fix": "加大前后脚距离；想象重心放在前脚跟"},
            {"issue": "躯干前倾", "cause": "核心未激活，用腰代偿", "fix": "保持挺胸；双手叉腰感受躯干直立"},
            {"issue": "膝盖不稳/晃动", "cause": "单腿稳定性差，臀中肌弱", "fix": "扶着墙做，确保膝盖稳定；加练单腿平衡练习"},
        ],
    },
    "ytw": {
        "key_checkpoints": [
            "俯卧在垫子上，额头贴地",
            "双臂分别举成 Y（45°）、T（90°）、W（肘部内收）形",
            "拇指朝上，掌心相对",
            "用背部肌肉发力带动手臂上抬",
            "不要耸肩，保持肩胛骨下沉",
        ],
        "common_issues": [
            {"issue": "耸肩代偿", "cause": "上斜方肌过度活跃，中下斜方肌弱", "fix": "先做肩胛骨后缩练习；抬臂前先沉肩"},
            {"issue": "抬臂幅度不足", "cause": "肩袖肌群弱，肩关节活动度不足", "fix": "从无负重开始，关注肌肉感受而非幅度"},
            {"issue": "使用惯性", "cause": "动作过快，忽略了肌肉控制", "fix": "慢速做（抬起2秒→保持2秒→放下2秒）"},
        ],
    },
}


@router.post("/analyze-set")
async def analyze_pose_set(request: Request):
    """Analyze a completed set of squat reps and return root cause diagnosis.

    Body: {
        exercise: "squat",
        reps: [{rep, kneeAngle_min, hipAngle_min, backAngle_max, kneeValgus_max, quality, duration_ms}, ...],
        changepoint_state: {state, cusumPos, ewma, alarmCount, n} | null
    }
    """
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    reps = body.get("reps", [])
    exercise = body.get("exercise", "squat")
    changepoint_state = body.get("changepoint_state")

    if not reps or len(reps) < 3:
        return {
            "success": True,
            "diagnosis": None,
            "message": "至少需要3个完整的深蹲 reps 才能进行分析",
        }

    # Dispatch to the right diagnosis function
    from fitai.analysis.pose_diagnostics import (
        analyze_squat_set, analyze_pushup_set, analyze_lunge_set,
        analyze_plank_session, analyze_ytw_session,
    )

    result = None
    if exercise == "pushup":
        result = analyze_pushup_set(reps, changepoint_state)
    elif exercise == "plank":
        result = analyze_plank_session({
            "duration_sec": len(reps) * 10 if reps else 0,
            "avg_quality": sum(r.get("quality", 50) for r in reps) / max(len(reps), 1),
            "hip_sag_events": sum(1 for r in reps if r.get("quality", 100) < 70),
        })
    elif exercise == "lunge":
        result = analyze_lunge_set(reps, changepoint_state)
    elif exercise == "ytw":
        result = analyze_ytw_session(reps)
    else:
        result = analyze_squat_set(reps, changepoint_state)

    return {
        "success": True,
        **result,
    }


@router.post("/analyze-video")
async def analyze_pose_video(
    request: Request,
    video: UploadFile = File(...),
    exercise: str = Form("squat"),
):
    """V39: Analyze an uploaded exercise video.

    Receives video from mini-program camera, attempts frame extraction and
    MediaPipe Pose analysis, returns biomechanical diagnosis.

    If MediaPipe is not installed, falls back to exercise-specific biomechanical
    guidance from the knowledge base — which provides actionable correction advice
    for the most common form issues of the selected exercise.
    """
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    # Validate exercise
    exercise = exercise.lower().strip()
    guidance = _EXERCISE_GUIDANCE.get(exercise)
    if not guidance:
        guidance = _EXERCISE_GUIDANCE["squat"]
        exercise = "squat"

    # Try MediaPipe-based analysis
    mp_result = None
    video_duration = 0
    frame_count = 0

    try:
        import cv2
        import numpy as np

        # Save uploaded video to temp file
        suffix = os.path.splitext(video.filename or "video.mp4")[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await video.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            cap = cv2.VideoCapture(tmp_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                video_duration = frame_count / fps if fps > 0 else 0

                # Try MediaPipe
                try:
                    import mediapipe as mp
                    mp_pose = mp.solutions.pose
                    pose = mp_pose.Pose(
                        static_image_mode=False,
                        model_complexity=1,
                        min_detection_confidence=0.5,
                        min_tracking_confidence=0.5,
                    )

                    all_landmarks = []
                    frame_idx = 0
                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        frame_idx += 1
                        if frame_idx % 3 != 0:  # Sample every 3rd frame
                            continue
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        results = pose.process(rgb)
                        if results.pose_landmarks:
                            all_landmarks.append({
                                "frame": frame_idx,
                                "landmarks": [
                                    {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
                                    for lm in results.pose_landmarks.landmark
                                ],
                            })

                    pose.close()

                    if all_landmarks and len(all_landmarks) >= 6:
                        # Compute rep metrics from landmarks
                        reps = _extract_reps_from_landmarks(all_landmarks, exercise)
                        if reps and len(reps) >= 2:
                            from fitai.analysis.pose_diagnostics import (
                                analyze_squat_set, analyze_pushup_set, analyze_lunge_set,
                                analyze_plank_session, analyze_ytw_session,
                            )
                            if exercise == "pushup":
                                mp_result = analyze_pushup_set(reps, None)
                            elif exercise == "plank":
                                mp_result = analyze_plank_session({
                                    "duration_sec": video_duration,
                                    "avg_quality": sum(r.get("quality", 50) for r in reps) / len(reps),
                                    "hip_sag_events": sum(1 for r in reps if r.get("quality", 100) < 70),
                                })
                            elif exercise == "lunge":
                                mp_result = analyze_lunge_set(reps, None)
                            elif exercise == "ytw":
                                mp_result = analyze_ytw_session(reps)
                            else:
                                mp_result = analyze_squat_set(reps, None)

                except ImportError:
                    pass  # MediaPipe not installed — fall through to guidance mode

        finally:
            cap.release()
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except ImportError:
        pass  # cv2 not installed — fall through to guidance mode
    except Exception:
        pass  # Analysis error — fall through to guidance mode

    if mp_result:
        return {
            "success": True,
            "mode": "mediapipe",
            "exercise": exercise,
            "video_duration_sec": round(video_duration, 1),
            "frames_analyzed": frame_count,
            "overall_score": mp_result.get("overall_score"),
            "diagnosis": mp_result.get("diagnosis", ""),
            "causal_path": mp_result.get("causal_path", ""),
            "correction": mp_result.get("correction", ""),
            "correction_exercise": mp_result.get("correction_exercise", ""),
            "quality_detail": mp_result.get("quality_detail", []),
            "key_checkpoints": guidance["key_checkpoints"],
        }

    # Fallback: return biomechanical KB guidance
    issues = guidance["common_issues"]
    primary = issues[0] if issues else {"issue": "", "cause": "", "fix": ""}

    return {
        "success": True,
        "mode": "guidance",
        "exercise": exercise,
        "video_duration_sec": round(video_duration, 1) if video_duration else None,
        "overall_score": None,
        "diagnosis": f"「{primary['issue']}」是{exercise}最常见的动作问题。{primary['cause']}。",
        "causal_path": f"动作模式错误 → {primary['issue']} → {primary['cause']}",
        "correction": primary["fix"],
        "correction_exercise": "",
        "key_checkpoints": guidance["key_checkpoints"],
        "common_issues": [
            {"issue": ci["issue"], "cause": ci["cause"], "fix": ci["fix"]}
            for ci in issues
        ],
        "message": "服务器未安装 MediaPipe，当前返回基于生物力学知识库的动作指导。安装 mediapipe + opencv 后可获得完整的 AI 姿态分析。",
    }


def _extract_reps_from_landmarks(all_landmarks: list, exercise: str) -> list:
    """Extract per-rep quality metrics from pose landmark sequences."""
    import math

    def _angle(a, b, c):
        """Angle at point b formed by points a-b-c (in 2D)."""
        ba = (a["x"] - b["x"], a["y"] - b["y"])
        bc = (c["x"] - b["x"], c["y"] - b["y"])
        dot = ba[0] * bc[0] + ba[1] * bc[1]
        mag_ba = math.sqrt(ba[0]**2 + ba[1]**2)
        mag_bc = math.sqrt(bc[0]**2 + bc[1]**2)
        if mag_ba < 1e-6 or mag_bc < 1e-6:
            return 90
        cos_a = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
        return math.degrees(math.acos(cos_a))

    # MediaPipe landmark indices:
    # 11=left_shoulder, 12=right_shoulder, 23=left_hip, 24=right_hip
    # 25=left_knee, 26=right_knee, 27=left_ankle, 28=right_ankle

    knee_angles = []
    hip_angles = []

    for frame_data in all_landmarks:
        lm = frame_data["landmarks"]
        if len(lm) < 29:
            continue

        # Right knee angle (hip-knee-ankle) for squat
        if all(lm[i]["visibility"] > 0.5 for i in [24, 26, 28]):
            knee_angles.append(_angle(lm[24], lm[26], lm[28]))

        # Right hip angle (shoulder-hip-knee)
        if all(lm[i]["visibility"] > 0.5 for i in [12, 24, 26]):
            hip_angles.append(_angle(lm[12], lm[24], lm[26]))

    if not knee_angles or len(knee_angles) < 3:
        return []

    # Simple rep detection: find knee angle minima (bottom of squat)
    reps = []
    rep_idx = 0
    min_knee = None
    min_hip = None

    for i in range(1, len(knee_angles) - 1):
        if knee_angles[i] < knee_angles[i - 1] and knee_angles[i] < knee_angles[i + 1]:
            # Local minimum = bottom of rep
            if min_knee is None or knee_angles[i] < min_knee:
                min_knee = knee_angles[i]
                min_hip = hip_angles[i] if i < len(hip_angles) else None

            # If angle rises significantly, rep is complete
            if min_knee is not None and knee_angles[i + 1] - min_knee > 15:
                rep_idx += 1
                quality = max(0, min(100, int(100 - abs(min_knee - 90) - abs((min_hip or 90) - 80))))
                reps.append({
                    "rep": rep_idx,
                    "kneeAngle_min": round(min_knee, 1),
                    "hipAngle_min": round(min_hip, 1) if min_hip else None,
                    "quality": quality,
                })
                min_knee = None
                min_hip = None

    return reps
