# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Personalized workout and health recommendations based on user data."""
from datetime import datetime, timedelta


def workout_recommendations(profile: dict, exercise_history: list, health_data: dict):
    """Generate personalized workout recommendations.

    Args:
        profile: user profile dict with fitness_goal, activity_level, birth_year, gender
        exercise_history: list of workout entries with exercise_name, date
        health_data: dict with recent metrics (steps, sleep, heart_rate summaries)

    Returns list of recommendation strings.
    """
    recs = []
    today = datetime.now().date()
    goal = profile.get("fitness_goal", "")
    activity_level = profile.get("activity_level", "")
    birth_year = profile.get("birth_year")
    age = today.year - birth_year if birth_year else 30

    # ---- Training frequency analysis ----
    recent_workout_dates = set()
    exercise_types = set()
    for w in exercise_history:
        recent_workout_dates.add(w.get("date", ""))
        if w.get("exercise_name"):
            exercise_types.add(w["exercise_name"])

    # Days since last workout
    last_workout_date = None
    workout_days_7 = 0
    workout_days_14 = 0
    for w in exercise_history:
        d = w.get("date", "")
        try:
            wd = datetime.strptime(d, "%Y-%m-%d").date()
            if last_workout_date is None or wd > last_workout_date:
                last_workout_date = wd
            if (today - wd).days <= 7:
                workout_days_7 += 1
            if (today - wd).days <= 14:
                workout_days_14 += 1
        except Exception:
            pass

    days_since_last = (today - last_workout_date).days if last_workout_date else 99
    avg_weekly = workout_days_14 / 2

    # ---- Recovery indicators ----
    sleep_ok = True
    hr_ok = True
    steps_ok = True

    if health_data.get("sleep"):
        sleep_info = health_data["sleep"]
        if isinstance(sleep_info, dict) and sleep_info.get("avg_duration_minutes", 999) < 360:
            sleep_ok = False
        elif isinstance(sleep_info, (int, float)) and sleep_info < 360:
            sleep_ok = False

    if health_data.get("heart_rate"):
        hr_info = health_data["heart_rate"]
        if isinstance(hr_info, dict) and hr_info.get("avg", 0) > 90:
            hr_ok = False

    if health_data.get("steps"):
        step_info = health_data["steps"]
        if isinstance(step_info, dict) and step_info.get("avg", 0) < 3000:
            steps_ok = False

    # ---- Generate recommendations ----

    # 1. Based on days since last workout
    if days_since_last > 3:
        if goal in ("增肌", "力量提升"):
            recs.append(f"距离上次训练已{days_since_last}天，今天适合进行力量训练（深蹲、卧推、硬拉等复合动作）")
        elif goal == "减脂":
            recs.append(f"已休息{days_since_last}天，建议今天做30-45分钟有氧+核心训练，心率保持在燃脂区间")
        else:
            recs.append(f"距离上次训练已{days_since_last}天，建议今天进行全身性训练唤醒身体")
    elif days_since_last == 0:
        recs.append("今天已经训练过了，注意补充蛋白质和充分休息")

    # 2. Based on recovery status
    if not sleep_ok:
        recs.append("近期睡眠不足，建议今天以低强度训练为主（瑜伽、拉伸、散步），优先保证休息恢复")
    if not hr_ok:
        recs.append("静息心率偏高可能是恢复不足的信号，今天建议做轻度有氧或休息")
    if not steps_ok:
        recs.append("日常步数偏少，建议午餐后散步15分钟，增加非运动消耗")

    # 3. Based on goal
    if goal == "增肌":
        if workout_days_7 < 3:
            recs.append("增肌需要每周至少3次力量训练，本周训练次数偏少")
        recs.append("训练后30分钟内补充蛋白质（20-30g），有助于肌肉合成")
    elif goal == "减脂":
        if workout_days_7 < 4:
            recs.append("减脂建议每周4-5次训练，结合有氧和力量")
        recs.append("保持每日热量缺口300-500千卡，优先选择高蛋白低GI食物")
    elif goal == "改善体能":
        recs.append("可以尝试间歇训练（HIIT），每周2次，每次20分钟，提升心肺功能")
    elif goal == "保持健康":
        if workout_days_7 < 2:
            recs.append("建议每周至少运动2-3次，每次30分钟以上，维持基础体能")

    # 4. Diversify if same exercises
    if len(exercise_types) <= 2 and workout_days_14 > 3:
        recs.append("训练内容较单一，建议增加训练动作多样性，避免身体适应性平台期")

    # 5. Weekly plan suggestion
    if exercise_history:
        recs.append(f"本周已训练{workout_days_7}天，平均每周{avg_weekly:.0f}天，建议维持或逐步增加训练频率")

    if not recs:
        recs.append("根据你的数据，当前训练状态良好，保持一致性是最重要的")

    return recs[:6]  # Cap at 6 recommendations


def nutrition_recommendations(profile: dict, nutrition_history: list):
    """Generate nutrition recommendations based on diet logs."""
    if not nutrition_history:
        return ["暂无饮食记录，建议开始记录每日饮食以便获得个性化建议"]

    recs = []
    goal = profile.get("fitness_goal", "")

    recent_cals = []
    recent_protein = []
    for n in nutrition_history[-7:]:
        if n.get("calories"):
            recent_cals.append(float(n["calories"]))
        if n.get("protein_g"):
            recent_protein.append(float(n["protein_g"]))

    if recent_cals:
        avg_cal = sum(recent_cals) / len(recent_cals)
        if goal == "增肌" and avg_cal < 2200:
            recs.append(f"日均热量{avg_cal:.0f}千卡偏低，增肌需要热量盈余，建议增加到2500+千卡")
        elif goal == "减脂" and avg_cal > 2000:
            recs.append(f"日均热量{avg_cal:.0f}千卡，减脂建议控制在1800千卡左右")

    if recent_protein:
        avg_protein = sum(recent_protein) / len(recent_protein)
        if goal == "增肌" and avg_protein < 80:
            recs.append(f"日均蛋白质{avg_protein:.0f}g不足，增肌建议每日摄入体重(kg)×1.6-2.0g蛋白质")
        elif avg_protein < 50:
            recs.append(f"日均蛋白质{avg_protein:.0f}g偏低，建议增加鸡胸肉、鱼、蛋、豆制品摄入")

    if not recs:
        recs.append("近期饮食结构总体合理，继续保持")

    return recs
