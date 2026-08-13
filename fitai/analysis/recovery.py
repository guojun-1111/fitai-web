# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""恢复评分：根据训练强度、睡眠、心率计算今日恢复状态(0-100)。"""

def compute_recovery_score(workout_intensity: float = 0, sleep_hours: float = 8,
                           resting_hr: float = 65, resting_hr_baseline: float = 60,
                           steps: float = 10000, training_days_streak: int = 0) -> dict:
    """输入昨日各指标，输出恢复评分和建议。

    workout_intensity: 0-10（主观/估算强度）
    sleep_hours: 昨日睡眠小时数
    resting_hr: 今日静息心率
    resting_hr_baseline: 个人基线静息心率（最近 30 天平均）
    steps: 昨日步数
    training_days_streak: 连续训练天数
    """
    score = 60  # 基准分
    details = []

    # 1. 训练强度惩罚（权重 30）：昨天练得越猛，今天需要越多恢复
    if workout_intensity >= 7:
        score -= 20
        details.append("昨日高强度训练 -20")
    elif workout_intensity >= 5:
        score -= 10
        details.append("昨日中等强度训练 -10")
    elif workout_intensity >= 3:
        score -= 5
        details.append("昨日轻度训练 -5")
    else:
        score += 5
        details.append("昨日休息或有氧 +5")

    # 2. 睡眠恢复（权重 25）：睡得好恢复就好
    if sleep_hours >= 8:
        score += 10
        details.append(f"睡眠充足({sleep_hours}h) +10")
    elif sleep_hours >= 7:
        score += 5
        details.append(f"睡眠及格({sleep_hours}h) +5")
    elif sleep_hours >= 5:
        score -= 5
        details.append(f"睡眠偏少({sleep_hours}h) -5")
    else:
        score -= 15
        details.append(f"睡眠严重不足({sleep_hours}h) -15")

    # 3. 心率恢复（权重 25）：静息心率高于基线 = 身体在恢复中
    hr_diff = resting_hr - resting_hr_baseline
    if hr_diff <= 0:
        score += 10
        details.append("心率正常或偏低 +10")
    elif hr_diff <= 5:
        score += 3
        details.append(f"心率略高(+{hr_diff:.0f}bpm) +3")
    elif hr_diff <= 10:
        score -= 8
        details.append(f"心率偏高(+{hr_diff:.0f}bpm)，注意休息 -8")
    else:
        score -= 15
        details.append(f"心率过高(+{hr_diff:.0f}bpm)，建议今天休息 -15")

    # 4. 连续训练惩罚（权重 20）：连练太多天需要恢复
    if training_days_streak >= 7:
        score -= 12
        details.append(f"连续训练{training_days_streak}天 -12")
    elif training_days_streak >= 5:
        score -= 6
        details.append(f"连续训练{training_days_streak}天 -6")
    elif training_days_streak >= 3:
        score -= 3
        details.append(f"连续训练{training_days_streak}天 -3")

    score = max(0, min(100, round(score)))

    # 建议
    if score >= 75:
        advice = "身体恢复良好，可以进行高强度训练"
        action = "train_hard"
    elif score >= 55:
        advice = "恢复中等，建议中等强度或技术训练"
        action = "train_moderate"
    elif score >= 35:
        advice = "恢复欠佳，建议轻量有氧或拉伸"
        action = "train_light"
    else:
        advice = "需要休息！今天做拉伸或彻底休息"
        action = "rest"

    return {
        "score": score, "action": action, "advice": advice,
        "details": "; ".join(details)
    }
