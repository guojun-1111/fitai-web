# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Sleep quality analysis and recommendations."""
import math
from collections import defaultdict


def sleep_quality_analysis(sleep_data: list):
    """Analyze sleep quality from daily sleep duration data.

    Args:
        sleep_data: list of {"date": str, "value": float} (minutes of sleep)

    Returns dict with quality score, consistency, debt, patterns, and recommendations.
    """
    if not sleep_data:
        return {"error": "no sleep data", "score": 0}

    durations = [d["value"] for d in sleep_data]
    dates = [d.get("date", "") for d in sleep_data]
    n = len(durations)

    avg_duration = sum(durations) / n
    target = 480  # 8 hours baseline

    # ---- Quality score (0-100) ----
    score = _compute_sleep_score(durations, target)

    # ---- Consistency (std dev) ----
    variance = sum((v - avg_duration) ** 2 for v in durations) / max(n, 1)
    consistency_std = math.sqrt(variance)
    consistency_label = "优秀" if consistency_std < 30 else "良好" if consistency_std < 60 else "一般" if consistency_std < 90 else "不稳定"

    # ---- Sleep debt ----
    shortfall = [max(0, target - v) for v in durations]
    total_debt = sum(shortfall)
    avg_debt = total_debt / max(n, 1)

    # ---- Weekend vs weekday ----
    weekday_durs = []
    weekend_durs = []
    for i, d in enumerate(sleep_data):
        date_str = d.get("date", "")
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt.weekday() < 5:
                weekday_durs.append(durations[i])
            else:
                weekend_durs.append(durations[i])
        except Exception:
            pass

    weekday_avg = sum(weekday_durs) / len(weekday_durs) if weekday_durs else avg_duration
    weekend_avg = sum(weekend_durs) / len(weekend_durs) if weekend_durs else avg_duration
    weekend_catchup = weekend_avg - weekday_avg

    # ---- Recommendations ----
    recommendations = _sleep_recommendations(avg_duration, consistency_std, weekend_catchup, avg_debt)

    return {
        "score": round(score, 1),
        "score_label": "优秀" if score >= 85 else "良好" if score >= 70 else "一般" if score >= 50 else "需改善",
        "avg_duration_minutes": round(avg_duration, 0),
        "avg_duration_hours": round(avg_duration / 60, 1),
        "consistency_std_minutes": round(consistency_std, 0),
        "consistency_label": consistency_label,
        "total_sleep_debt_minutes": round(total_debt, 0),
        "avg_daily_debt_minutes": round(avg_debt, 0),
        "weekday_avg": round(weekday_avg, 0),
        "weekend_avg": round(weekend_avg, 0),
        "weekend_catchup": round(weekend_catchup, 0),
        "recommendations": recommendations,
        "data_points": n,
    }


def _compute_sleep_score(durations: list, target: float) -> float:
    """Compute 0-100 sleep quality score."""
    n = len(durations)
    avg = sum(durations) / n

    # Duration score (0-50 points)
    ratio = min(avg / target, 1.5)  # Cap at 150%
    if ratio >= 1.0:
        duration_score = 50
    elif ratio >= 0.875:  # 7+ hours
        duration_score = 45
    elif ratio >= 0.75:   # 6+ hours
        duration_score = 35
    elif ratio >= 0.625:  # 5+ hours
        duration_score = 20
    else:
        duration_score = 10

    # Consistency score (0-30 points)
    variance = sum((v - avg) ** 2 for v in durations) / max(n, 1)
    std_dev = math.sqrt(variance)
    if std_dev < 30:
        consistency_score = 30
    elif std_dev < 60:
        consistency_score = 20
    elif std_dev < 90:
        consistency_score = 10
    else:
        consistency_score = 5

    # Sufficiency rate (0-20 points) — what fraction of days meet target
    sufficient_days = sum(1 for v in durations if v >= target * 0.875)  # 7h+
    sufficiency_rate = sufficient_days / max(n, 1)
    sufficiency_score = round(sufficiency_rate * 20)

    return duration_score + consistency_score + sufficiency_score


def _sleep_recommendations(avg_duration, consistency_std, weekend_catchup, avg_debt):
    """Generate sleep recommendations based on patterns."""
    recs = []

    if avg_duration < 360:  # < 6 hours
        recs.append("每天睡眠严重不足（<6小时），建议将就寝时间提前30-60分钟，目标达到7小时以上")
    elif avg_duration < 420:  # < 7 hours
        recs.append("睡眠时间偏少（<7小时），尝试每天早睡15分钟，逐步延长睡眠时间")
    elif avg_duration < 480:
        recs.append("睡眠时间接近标准，可再增加30分钟达到8小时的理想时长")

    if consistency_std > 90:
        recs.append("睡眠时间波动较大，建议固定就寝和起床时间，周末不要过度补觉")
    elif consistency_std > 60:
        recs.append("睡眠时间有一定波动，尽量保持规律作息")

    if weekend_catchup > 120:  # > 2 hours catchup
        recs.append(f"周末额外睡眠{weekend_catchup:.0f}分钟，说明平时睡眠不足，建议工作日增加每日睡眠时长")
    elif weekend_catchup > 60:
        recs.append("周末睡得比平时多，适度补觉有益但不要超过2小时，以免打乱生物钟")

    if avg_debt > 60:
        recs.append(f"日均睡眠债务{avg_debt:.0f}分钟，长期睡眠债务会影响运动表现和恢复，优先改善睡眠")

    if not recs:
        recs.append("睡眠状况良好，继续保持规律作息")

    return recs


# ═══════════════════════════════════════════════════════════════════
# V7.0 睡眠规律指数 (Sleep Regularity Index)
# ═══════════════════════════════════════════════════════════════════

def compute_sleep_regularity_index(sleep_data: list) -> dict:
    """计算睡眠规律指数（SRI），衡量睡眠作息的一致性。

    基于 Phillips et al., 2017, Scientific Reports 的方法：
    SRI = 连续两天在同一时间段的睡眠/清醒状态一致的概率（0-100）。

    简化实现：使用入睡时间和起床时间，将每天划分为 30 分钟粒度的时间箱，
    计算相邻两天箱位状态一致的比例。

    如果只有时长数据（无具体入睡/起床时间），则退化为时长一致性评分。

    Args:
        sleep_data: list of dicts，每条记录需包含：
            - date: str 日期 "YYYY-MM-DD"
            - value: float 睡眠时长（分钟）[必须]
            - bed_time: str 入睡时间 "HH:MM" [可选，用于精确 SRI]
            - wake_time: str 起床时间 "HH:MM" [可选，用于精确 SRI]

    Returns:
        dict with sri_score, regularity_label, bin_count, data_days
    """
    from datetime import datetime, timedelta

    if len(sleep_data) < 3:
        return {"sri_score": None, "regularity_label": "数据不足", "data_days": len(sleep_data)}

    n = len(sleep_data)
    has_timing = any("bed_time" in d and "wake_time" in d and d.get("bed_time") and d.get("wake_time")
                     for d in sleep_data)

    if has_timing:
        sri = _compute_sri_with_timing(sleep_data)
    else:
        sri = _compute_sri_from_duration(sleep_data)

    if sri >= 85:
        label = "非常规律"
    elif sri >= 70:
        label = "比较规律"
    elif sri >= 50:
        label = "略有波动"
    else:
        label = "不规律"

    return {
        "sri_score": round(sri, 1),
        "regularity_label": label,
        "has_timing_data": has_timing,
        "data_days": n,
    }


def _compute_sri_with_timing(sleep_data: list) -> float:
    """基于入睡/起床时间的精确 SRI 计算。

    将每天分为 48 个 30 分钟时间箱（00:00-00:30, 00:30-01:00, ...），
    标记每个箱为睡眠(1)或清醒(0)，比较相邻两天的状态一致性。
    """
    from datetime import datetime

    BINS_PER_DAY = 48  # 30 分钟粒度
    MISSING_PENALTY = 0.5  # 缺失时间箱的默认分

    # 构建每天的时间箱向量
    daily_bins = {}
    for entry in sleep_data:
        bed_str = entry.get("bed_time", "")
        wake_str = entry.get("wake_time", "")
        if not bed_str or not wake_str:
            continue

        try:
            bed_h, bed_m = map(int, bed_str.split(":"))
            wake_h, wake_m = map(int, wake_str.split(":"))
        except (ValueError, AttributeError):
            continue

        bed_bin = bed_h * 2 + (1 if bed_m >= 30 else 0)
        wake_bin = wake_h * 2 + (1 if wake_m >= 30 else 0)

        bins = [0] * BINS_PER_DAY
        if wake_bin > bed_bin:
            # 同一天内
            for b in range(bed_bin, wake_bin):
                bins[b] = 1
        else:
            # 跨天（熬夜到第二天）
            for b in range(bed_bin, BINS_PER_DAY):
                bins[b] = 1
            for b in range(0, wake_bin):
                bins[b] = 1

        daily_bins[entry.get("date", "")] = bins

    # 比较相邻天
    sorted_dates = sorted(daily_bins.keys())
    if len(sorted_dates) < 2:
        return 50.0

    total_bins = 0
    matching_bins = 0
    for i in range(len(sorted_dates) - 1):
        bins1 = daily_bins[sorted_dates[i]]
        bins2 = daily_bins[sorted_dates[i + 1]]
        for b in range(BINS_PER_DAY):
            total_bins += 1
            if bins1[b] == bins2[b]:
                matching_bins += 1

    return (matching_bins / max(total_bins, 1)) * 100


def _compute_sri_from_duration(sleep_data: list) -> float:
    """从睡眠时长估算规律性（无入睡/起床时间时的退化方案）。

    使用相邻天时长变化率 + 总体标准差来估算一致性分数。
    连续两天睡眠时长差 < 30 分钟 = 高度一致。
    """
    n = len(sleep_data)
    durations = [d["value"] for d in sleep_data]

    # 相邻天差异分（0-60 分）
    adjacent_score = 0
    pairs = 0
    for i in range(n - 1):
        diff = abs(durations[i] - durations[i + 1])
        pairs += 1
        if diff <= 15:
            adjacent_score += 1.0
        elif diff <= 30:
            adjacent_score += 0.8
        elif diff <= 45:
            adjacent_score += 0.5
        elif diff <= 60:
            adjacent_score += 0.3
        else:
            adjacent_score += 0.1

    adj_component = (adjacent_score / max(pairs, 1)) * 60

    # 总体稳定性分（0-40 分）
    mean_dur = sum(durations) / n
    variance = sum((v - mean_dur) ** 2 for v in durations) / n
    std_dev = math.sqrt(variance)
    cv = std_dev / mean_dur if mean_dur > 0 else 1

    if cv < 0.05:
        stability_component = 40
    elif cv < 0.1:
        stability_component = 35
    elif cv < 0.15:
        stability_component = 25
    elif cv < 0.25:
        stability_component = 15
    else:
        stability_component = 5

    return adj_component + stability_component
