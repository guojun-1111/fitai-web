# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Heart rate zone analysis and resting HR trend detection."""


def hr_zone_analysis(hr_samples: list, age=30, resting_hr=70):
    """Categorize heart rate readings into training zones.

    Args:
        hr_samples: list of {"timestamp": float, "heart_rate": int}
        age: user age for max HR estimation
        resting_hr: estimated resting heart rate

    Returns dict with zone distribution, time in zones, and training effect.
    """
    if not hr_samples:
        return {"error": "no heart rate data"}

    max_hr = 208 - 0.7 * age  # Tanaka 公式（2001, JACC），比 220-age 更准确
    reserve = max_hr - resting_hr

    zones = {"rest": 0, "fat_burn": 0, "cardio": 0, "peak": 0}
    zone_ranges = {}

    for s in hr_samples:
        hr = s["heart_rate"]
        pct = hr / max_hr if max_hr > 0 else 0
        if pct < 0.6:
            zones["rest"] += 1
        elif pct < 0.7:
            zones["fat_burn"] += 1
        elif pct < 0.85:
            zones["cardio"] += 1
        else:
            zones["peak"] += 1

    total = max(sum(zones.values()), 1)

    # Zone boundaries
    zone_ranges = {
        "rest": f"<{int(max_hr * 0.6)} bpm ({int(resting_hr)}-{int(max_hr * 0.6)})",
        "fat_burn": f"{int(max_hr * 0.6)}-{int(max_hr * 0.7)} bpm",
        "cardio": f"{int(max_hr * 0.7)}-{int(max_hr * 0.85)} bpm",
        "peak": f">{int(max_hr * 0.85)} bpm",
    }

    avg_hr = sum(s["heart_rate"] for s in hr_samples) / len(hr_samples)
    max_hr_recorded = max(s["heart_rate"] for s in hr_samples)

    # Training effect assessment
    fat_burn_pct = zones["fat_burn"] / total * 100
    cardio_pct = zones["cardio"] / total * 100
    peak_pct = zones["peak"] / total * 100

    if cardio_pct + peak_pct > 60:
        training_effect = "高强度训练，有利于提升最大摄氧量，注意充分恢复"
    elif fat_burn_pct > 50:
        training_effect = "主要处于燃脂区间，适合减脂和控制体重"
    elif zones["rest"] / total > 0.7:
        training_effect = "运动强度偏低，建议适当提高心率至燃脂区间（60-70%最大心率）"
    else:
        training_effect = "均衡的训练强度分布"

    return {
        "avg_hr": round(avg_hr, 1),
        "max_hr_recorded": max_hr_recorded,
        "max_hr_estimated": max_hr,
        "resting_hr": resting_hr,
        "zone_distribution": {
            "rest": {"count": zones["rest"], "percent": round(zones["rest"] / total * 100, 1)},
            "fat_burn": {"count": zones["fat_burn"], "percent": round(zones["fat_burn"] / total * 100, 1)},
            "cardio": {"count": zones["cardio"], "percent": round(zones["cardio"] / total * 100, 1)},
            "peak": {"count": zones["peak"], "percent": round(zones["peak"] / total * 100, 1)},
        },
        "zone_ranges": zone_ranges,
        "training_effect": training_effect,
        "total_readings": total,
    }


def resting_hr_trend(daily_hr_data: list):
    """Track resting heart rate over time.

    Args:
        daily_hr_data: list of {"date": str, "avg_hr": float, "min_hr": float}

    Returns resting HR trend analysis. Lower resting HR = better cardiovascular fitness.
    """
    if len(daily_hr_data) < 3:
        return {"error": "insufficient data for trend", "data_points": len(daily_hr_data)}

    from .trends import detect_trend

    resting_values = [d.get("min_hr", d.get("avg_hr", 0)) for d in daily_hr_data]
    dates = [d.get("date", "") for d in daily_hr_data]

    trend = detect_trend(resting_values, dates)

    # For resting HR, declining is IMPROVING
    if trend["direction"] == "improving":
        trend["direction"] = "declining"
    elif trend["direction"] == "declining":
        trend["direction"] = "improving"

    return {
        "current_resting_hr": round(resting_values[-1], 1) if resting_values else 0,
        "avg_resting_hr": round(sum(resting_values) / len(resting_values), 1),
        "trend": trend,
        "data_points": len(daily_hr_data),
        "interpretation": _interpret_hr_trend(trend, resting_values[-1] if resting_values else 0),
    }


def _interpret_hr_trend(trend, current_hr):
    """Interpret resting HR trend."""
    parts = []
    if current_hr < 50:
        parts.append(f"静息心率{current_hr:.0f} bpm，处于运动员水平")
    elif current_hr < 60:
        parts.append(f"静息心率{current_hr:.0f} bpm，心血管状况优秀")
    elif current_hr < 70:
        parts.append(f"静息心率{current_hr:.0f} bpm，处于正常偏低水平")
    elif current_hr < 80:
        parts.append(f"静息心率{current_hr:.0f} bpm，处于正常范围")
    elif current_hr < 100:
        parts.append(f"静息心率{current_hr:.0f} bpm，处于正常偏高水平")
    else:
        parts.append(f"静息心率{current_hr:.0f} bpm，偏高，建议关注")

    if trend["direction"] == "improving":
        parts.append("静息心率呈下降趋势，心血管功能在改善")
    elif trend["direction"] == "declining":
        parts.append("静息心率有上升趋势，可能训练过度或恢复不足，建议增加休息日")
    else:
        parts.append("静息心率保持稳定")

    return "。".join(parts)
