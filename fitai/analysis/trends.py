# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Trend detection, anomaly detection, correlation analysis for health metrics."""
import math
from collections import defaultdict


def moving_average(values: list, window=7):
    """Compute simple moving average. Returns same-length list with None for edges."""
    if len(values) < window:
        return [None] * len(values)
    result = []
    half = window // 2
    for i in range(len(values)):
        if i < half or i >= len(values) - (window - half - 1):
            result.append(None)
        else:
            start = i - half
            end = i + (window - half)
            result.append(sum(values[start:end]) / (end - start))
    return result


def detect_trend(values: list, dates: list = None):
    """Detect trend direction using simple linear regression on index positions.

    Returns dict with: direction ('improving'/'declining'/'stable'), slope_per_day,
    percent_change_per_week, confidence (R-squared 0-1).
    """
    n = len(values)
    if n < 3:
        return {"direction": "stable", "slope_per_day": 0, "percent_change_per_week": 0, "confidence": 0}

    x_vals = list(range(n))
    mean_x = sum(x_vals) / n
    mean_y = sum(values) / n

    num = sum((x_vals[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    den = sum((x_vals[i] - mean_x) ** 2 for i in range(n))

    if den == 0:
        slope = 0
    else:
        slope = num / den

    # R-squared
    y_pred = [mean_y + slope * (x_vals[i] - mean_x) for i in range(n)]
    ss_res = sum((values[i] - y_pred[i]) ** 2 for i in range(n))
    ss_tot = sum((values[i] - mean_y) ** 2 for i in range(n))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    mean_val = mean_y if mean_y != 0 else 1
    pct_per_week = (slope * 7 / mean_val) * 100

    # Direction (for health metrics, higher is generally better for steps/sleep, not for weight)
    if abs(pct_per_week) < 0.5:
        direction = "stable"
    else:
        direction = "improving" if pct_per_week > 0 else "declining"

    return {
        "direction": direction,
        "slope_per_day": round(slope, 4),
        "percent_change_per_week": round(pct_per_week, 2),
        "confidence": round(r_squared, 3),
    }


def detect_anomalies(values: list, dates: list = None, method="zscore", threshold=2.5):
    """Detect anomalies using Z-score method. Returns list of anomaly dicts."""
    n = len(values)
    if n < 4:
        return []

    mean_val = sum(values) / n
    variance = sum((v - mean_val) ** 2 for v in values) / n
    std_dev = math.sqrt(variance) if variance > 0 else 1

    anomalies = []
    for i, v in enumerate(values):
        z = (v - mean_val) / std_dev if std_dev > 0 else 0
        if abs(z) > threshold:
            anomalies.append({
                "index": i,
                "date": dates[i] if dates else str(i),
                "value": v,
                "z_score": round(z, 2),
                "deviation": round(v - mean_val, 1),
                "severity": "high" if abs(z) > 3 else "medium",
            })
    return anomalies


def compute_correlation(x_values: list, y_values: list):
    """Compute Pearson correlation coefficient between two arrays."""
    n = len(x_values)
    if n < 3 or len(y_values) != n:
        return {"coefficient": 0, "interpretation": "insufficient data"}

    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    num = sum((x_values[i] - mean_x) * (y_values[i] - mean_y) for i in range(n))
    den_x = math.sqrt(sum((x_values[i] - mean_x) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((y_values[i] - mean_y) ** 2 for i in range(n)))

    if den_x == 0 or den_y == 0:
        r = 0
    else:
        r = num / (den_x * den_y)
    r = max(-1, min(1, r))

    abs_r = abs(r)
    if abs_r < 0.2:
        interp = "极弱相关"
    elif abs_r < 0.4:
        interp = "弱相关"
    elif abs_r < 0.6:
        interp = "中等相关"
    elif abs_r < 0.8:
        interp = "强相关"
    else:
        interp = "极强相关"

    direction = "正相关" if r > 0 else "负相关"

    return {
        "coefficient": round(r, 3),
        "interpretation": f"{interp}（{direction}）",
        "direction": "positive" if r > 0 else "negative",
    }


def analyze_metric_trend(data: list, metric_name: str, higher_is_better: bool = True):
    """Full trend analysis for a single metric. Returns comprehensive dict."""
    if not data:
        return {"metric": metric_name, "error": "no data"}

    values = [d["value"] for d in data]
    dates = [d.get("date", "") for d in data]

    trend = detect_trend(values, dates)
    anomalies = detect_anomalies(values, dates)
    ma = moving_average(values, window=min(7, len(values)))

    # Adjust direction for metrics where lower is better
    if not higher_is_better:
        if trend["direction"] == "improving":
            trend["direction"] = "declining"
        elif trend["direction"] == "declining":
            trend["direction"] = "improving"

    return {
        "metric": metric_name,
        "trend": trend,
        "anomalies": anomalies[-5:],  # last 5 anomalies
        "latest": values[-1] if values else 0,
        "average": round(sum(values) / len(values), 1),
        "max": max(values),
        "min": min(values),
        "data_points": len(values),
        "smoothed_values": [round(v, 1) if v is not None else None for v in ma],
        "dates": dates,
        "raw_values": values,
    }


# ========== V5.2 创新算法 ==========

def adaptive_anomaly_detection(values: list, dates: list = None):
    """自适应异常检测。根据用户自身的历史波动幅度动态调整 z-score 阈值。
    稳定用户阈值收紧(1.5)，波动用户阈值放宽(3.0)，大幅降低误报。"""
    n = len(values)
    if n < 7:
        return []

    mean_val = sum(values) / n
    variance = sum((v - mean_val) ** 2 for v in values) / n
    std_dev = math.sqrt(variance) if variance > 0 else 1
    cv = std_dev / mean_val if mean_val > 0 else 1  # 变异系数

    # 自适应阈值：CV 小 → 阈值紧；CV 大 → 阈值松
    if cv < 0.1:
        threshold = 1.5  # 很稳定
    elif cv < 0.2:
        threshold = 2.0
    elif cv < 0.4:
        threshold = 2.5
    else:
        threshold = 3.0  # 波动很大

    anomalies = []
    for i, v in enumerate(values):
        z = (v - mean_val) / std_dev if std_dev > 0 else 0
        if abs(z) > threshold:
            anomalies.append({
                "index": i, "date": dates[i] if dates else str(i),
                "value": round(v, 1), "z_score": round(z, 2),
                "direction": "high" if z > 0 else "low",
                "threshold": threshold,
            })
    return anomalies


def _score_day(metrics: dict) -> float:
    """单日健康评分（0-100），被 compute_health_score 和 ewma_health_score 共用。"""
    score = 50.0
    if "steps" in metrics:
        score += min(metrics["steps"] / 10000 * 20, 25) - 10
    if "sleep" in metrics:
        score += min(metrics["sleep"] / 480 * 25, 30) - 12.5
    if "calories" in metrics:
        score += min(metrics["calories"] / 500 * 15, 20) - 7.5
    if "heart_rate" in metrics:
        hr = metrics["heart_rate"]
        score += 5 if 55 <= hr <= 75 else (-8 if hr < 55 or hr > 85 else 0)
    if "weight" in metrics and "weight_prev" in metrics:
        score += 5 if metrics["weight"] <= metrics["weight_prev"] else -3
    return max(0, min(100, score))


def compute_health_score(metrics: dict) -> dict:
    """多指标融合综合健康分(0-100)。
    输入: {steps: 8500, sleep: 480, calories: 350, heart_rate: 65, weight: 72.5}"""
    score = round(_score_day(metrics))
    level = "优秀" if score >= 80 else "良好" if score >= 65 else "一般" if score >= 45 else "需关注"
    details = []
    if "steps" in metrics:
        details.append(f"步数 {metrics['steps']}步")
    if "sleep" in metrics:
        details.append(f"睡眠 {metrics['sleep']}分钟")
    if "heart_rate" in metrics:
        details.append(f"心率 {metrics['heart_rate']}bpm")
    return {"score": score, "level": level, "details": "; ".join(details)}


# ═══════════════════════════════════════════════════════════════════
# V7.0 训练负荷分析
# ═══════════════════════════════════════════════════════════════════

def compute_acwr(workout_loads: list, acute_window: int = 7, chronic_window: int = 28) -> dict:
    """计算急慢性负荷比（Acute-to-Chronic Workload Ratio）。

    ACWR = 急性负荷(7天平均) / 慢性负荷(28天平均)

    这是运动科学中预测受伤风险的金标准指标（Gabbett, 2016, BJSM）：
    - ACWR < 0.8: 负荷不足，训练效果低
    - 0.8 ≤ ACWR ≤ 1.3: 安全区间，适应良好
    - 1.3 < ACWR ≤ 1.5: 风险升高，需注意恢复
    - ACWR > 1.5: 危险区间，受伤风险显著增加

    Args:
        workout_loads: list of {"date": str, "load": float}，按日期升序
                       load 为 sRPE（session RPE = RPE × 时长分钟数）或其他负荷指标
        acute_window: 急性窗口天数（默认 7）
        chronic_window: 慢性窗口天数（默认 28）

    Returns:
        dict with acwr, acute_load, chronic_load, risk_level, recommendation
    """
    if len(workout_loads) < chronic_window:
        return {
            "acwr": None,
            "acute_load": None,
            "chronic_load": None,
            "risk_level": "数据不足",
            "recommendation": f"需要至少 {chronic_window} 天数据才能计算 ACWR",
            "data_days": len(workout_loads),
        }

    loads = [w["load"] for w in workout_loads]
    dates = [w.get("date", "") for w in workout_loads]

    # 急性负荷：最近 acute_window 天的日均负荷
    acute_loads = loads[-acute_window:]
    acute_avg = sum(acute_loads) / len(acute_loads)

    # 慢性负荷：最近 chronic_window 天的日均负荷
    chronic_loads = loads[-chronic_window:]
    chronic_avg = sum(chronic_loads) / len(chronic_loads)

    if chronic_avg == 0:
        acwr = 1.0
    else:
        acwr = round(acute_avg / chronic_avg, 2)

    # 耦合负荷比（Coupled ACWR）：用滚动 4 周平均替代简单平均，更准确
    if len(weekly_avgs := _weekly_averages(loads)) >= 4:
        coupled_chronic = sum(weekly_avgs[-4:]) / 4
        coupled_acwr = round(acute_avg / coupled_chronic, 2) if coupled_chronic > 0 else acwr
    else:
        coupled_acwr = acwr

    # 风险等级
    if acwr > 1.5:
        risk_level = "危险"
        recommendation = f"ACWR={acwr}，受伤风险显著增加。建议本周降低训练量 30-50%，优先恢复"
    elif acwr > 1.3:
        risk_level = "偏高"
        recommendation = f"ACWR={acwr}，处于风险上升区。关注身体感受，确保充足睡眠和营养"
    elif acwr >= 0.8:
        risk_level = "安全"
        recommendation = f"ACWR={acwr}，训练负荷处于安全区间，身体适应良好"
    else:
        risk_level = "偏低"
        recommendation = f"ACWR={acwr}，训练负荷偏低，可适当增加训练量以提升适应"

    return {
        "acwr": acwr,
        "coupled_acwr": coupled_acwr,
        "acute_load": round(acute_avg, 1),
        "chronic_load": round(chronic_avg, 1),
        "risk_level": risk_level,
        "recommendation": recommendation,
        "data_days": len(workout_loads),
        "acute_days": len(acute_loads),
        "chronic_days": len(chronic_loads),
        "recent_dates": dates[-14:] if len(dates) >= 14 else dates,
    }


def _weekly_averages(loads: list) -> list:
    """计算每周平均负荷（用于耦合 ACWR）。"""
    if len(loads) < 7:
        return []
    weekly = []
    for i in range(0, len(loads), 7):
        week_loads = loads[i:i + 7]
        weekly.append(sum(week_loads) / len(week_loads))
    return weekly


# ═══════════════════════════════════════════════════════════════════
# V7.0 渐进超负荷检测 + sRPE 训练负荷
# ═══════════════════════════════════════════════════════════════════

def compute_srpe(rpe: int, duration_minutes: float) -> float:
    """计算 session RPE（训练负荷）。sRPE = RPE × 训练时长（分钟）。
    运动科学中量化训练负荷的标准方法（Foster, 2001）。RPE 使用 1-10 量表。
    """
    return rpe * duration_minutes


def detect_progressive_overload(workout_history: list, exercise_name: str = None,
                                metric: str = "weight_kg") -> dict:
    """检测渐进超负荷。比较最近 2 周 vs 之前 2 周，检测负重/次数/训练量增长。

    Args:
        workout_history: list of dicts with exercise_name, date, weight_kg, reps, sets
        exercise_name: 指定动作名（None = 所有动作）
        metric: "weight_kg", "reps", "volume"

    Returns:
        dict with overload_detected, prs, celebration
    """
    from collections import defaultdict

    if not workout_history or len(workout_history) < 6:
        return {"overload_detected": False, "reason": "数据不足（需要至少 6 次训练记录）"}

    by_exercise = defaultdict(list)
    for w in workout_history:
        name = w.get("exercise_name", "")
        if not name:
            continue
        by_exercise[name].append(w)

    prs = []
    for ex_name, records in by_exercise.items():
        if exercise_name and ex_name != exercise_name:
            continue
        if len(records) < 6:
            continue

        records.sort(key=lambda r: r.get("date", ""))

        def _metric_val(r):
            if metric == "weight_kg":
                return r.get("weight_kg", 0) or 0
            elif metric == "reps":
                return r.get("reps", 0) or 0
            elif metric == "volume":
                w = r.get("weight_kg", 0) or 0
                reps = r.get("reps", 0) or 0
                sets = r.get("sets", 1) or 1
                return w * reps * sets
            return r.get("weight_kg", 0) or 0

        def _group_by_week(recs):
            weekly = defaultdict(list)
            for rec in recs:
                try:
                    from datetime import datetime
                    d = datetime.strptime(rec.get("date", ""), "%Y-%m-%d")
                    weekly[d.isocalendar()[1]].append(_metric_val(rec))
                except (ValueError, TypeError):
                    pass
            return [max(vals) for _, vals in sorted(weekly.items()) if vals]

        weekly_tops = _group_by_week(records)
        if len(weekly_tops) < 4:
            continue

        recent_2 = weekly_tops[-2:]
        prior_2 = weekly_tops[:-2]
        recent_avg = sum(recent_2) / len(recent_2)
        prior_avg = sum(prior_2) / len(prior_2)
        change_pct = (recent_avg - prior_avg) / prior_avg * 100 if prior_avg > 0 else 0

        all_time_best = max(_metric_val(r) for r in records)
        is_new_pr = recent_2[-1] >= all_time_best and change_pct > 0

        if change_pct >= 2.5:
            prs.append({
                "exercise_name": ex_name, "metric": metric,
                "change_pct": round(change_pct, 1),
                "recent_avg": round(recent_avg, 1),
                "prior_avg": round(prior_avg, 1),
                "is_new_pr": is_new_pr,
                "all_time_best": round(all_time_best, 1),
            })

    if prs:
        new_prs = [p for p in prs if p["is_new_pr"]]
        if new_prs:
            names = ", ".join(p["exercise_name"] for p in new_prs[:3])
            celebration = f"新 PR! {names} 突破历史最佳，渐进超负荷成功"
        else:
            names = ", ".join(p["exercise_name"] for p in prs[:3])
            celebration = f"进步中: {names} 持续增长，超负荷适应良好"
        return {
            "overload_detected": True, "pr_count": len(prs),
            "new_pr_count": len(new_prs), "prs": prs, "celebration": celebration,
        }

    return {"overload_detected": False, "reason": "近 2 周未检测到显著超负荷，建议增加训练刺激"}


def impute_missing(values: list, dates: list = None, window: int = 7) -> list:
    """稀疏数据补全。用移动平均估算缺失值，标记为估算数据。
    返回与输入等长的补全后列表。"""
    n = len(values)
    if n < 3:
        return [(v, False) for v in values]  # 全部标记为真实

    result = []
    for i in range(n):
        if values[i] is not None and values[i] > 0:
            result.append((values[i], False))  # 真实数据
        else:
            # 取前后 window//2 个非空值的平均
            half = window // 2
            neighbors = []
            for j in range(max(0, i - half), min(n, i + half + 1)):
                if j != i and values[j] is not None and values[j] > 0:
                    neighbors.append(values[j])
            if len(neighbors) >= 2:
                estimated = round(sum(neighbors) / len(neighbors), 1)
                result.append((estimated, True))  # 估算数据
            else:
                result.append((0, True))

    return result
