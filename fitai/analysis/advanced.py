# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""V6.0 创新算法：自适应周期化、多维交叉异常检测、指数加权健康评分。

与现有 trends.py / recommendations.py / periodization.py 协同工作，
可被 fitai_tools.py 中的工具函数调用。
"""
import math
from collections import defaultdict
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════════
# 1. 自适应周期化训练计划
# ═══════════════════════════════════════════════════════════════════

def adaptive_periodization(goal: str, exercise_history: list, profile: dict = None, weeks: int = 4) -> dict:
    """基于用户历史训练数据自适应调整的周期化训练计划。

    与 periodization.py 的静态模板不同，此函数：
    - 分析过去 4 周的训练完成率，自动调整下周强度
    - 检测训练频率是递增还是递减，调整容量建议
    - 识别训练动作偏好，推荐互补动作避免偏科

    Returns: dict with plan, adjustment_factors, insights
    """
    from fitai.analysis.periodization import WEEKLY_TEMPLATES

    template = WEEKLY_TEMPLATES.get(goal, WEEKLY_TEMPLATES["综合"])

    # ── 分析历史完成率 ──
    today = datetime.now().date()
    weekly_counts = defaultdict(int)
    weekly_duration = defaultdict(float)

    for w in (exercise_history or []):
        try:
            d = datetime.strptime(w.get("date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        week_key = d.isocalendar()[1]  # ISO week number
        weekly_counts[week_key] += 1
        weekly_duration[week_key] += w.get("duration_minutes", 0) or 0

    recent_weeks = sorted(weekly_counts.keys())[-4:]
    if len(recent_weeks) >= 2:
        # 计算周训练次数的趋势
        first_half_avg = sum(weekly_counts[w] for w in recent_weeks[:2]) / 2
        second_half_avg = sum(weekly_counts[w] for w in recent_weeks[2:]) / 2
        if second_half_avg > 0:
            compliance = min(second_half_avg / max(first_half_avg, 0.5), 2.0)
        else:
            compliance = 1.0
    else:
        compliance = 1.0  # 没有足够数据，使用默认强度

    # ── 根据完成率调整强度 ──
    intensity_map = {"中低": 1, "中等": 2, "中高": 3, "高": 4, "极高": 5}
    rev_intensity = {1: "中低", 2: "中等", 3: "中高", 4: "高", 5: "极高"}

    plan = []
    for i, week_tpl in enumerate(template[:weeks]):
        base_level = intensity_map.get(week_tpl["intensity"], 2)
        # 完成率 >1.2（越练越多）→ 升半级; <0.7（越练越少）→ 降半级
        if compliance >= 1.2 and base_level < 5:
            adj = 0.5
        elif compliance <= 0.7 and base_level > 1:
            adj = -0.5
        else:
            adj = 0
        adj_level = max(1, min(5, base_level + adj))
        adjusted_intensity = rev_intensity.get(int(adj_level), rev_intensity[2])

        plan.append({
            "week": i + 1,
            "focus": week_tpl["focus"],
            "intensity": adjusted_intensity,
            "cardio": week_tpl["cardio"],
            "strength": week_tpl["strength"],
            "note": week_tpl["note"],
            "adjusted": adj != 0,
        })

    # ── 分析训练动作多样性 ──
    exercise_types = set()
    for w in (exercise_history or [])[-30:]:
        if w.get("exercise_name"):
            exercise_types.add(w["exercise_name"])

    diversity_insight = ""
    if len(exercise_types) <= 3 and len(exercise_history or []) >= 10:
        diversity_insight = "训练动作较单一（近30天仅{}种），建议加入推/拉/腿互补动作突破平台期".format(len(exercise_types))

    return {
        "goal": goal,
        "weeks": len(plan),
        "plan": plan,
        "adjustment_factors": {
            "compliance_rate": round(compliance, 2),
            "recent_weekly_avg": round(second_half_avg, 1) if len(recent_weeks) >= 2 else 0,
            "intensity_adjusted": compliance < 0.7 or compliance >= 1.2,
        },
        "insights": [diversity_insight] if diversity_insight else [],
        "summary": "{}周{}计划（自适应调整，完成率{:.0%}）".format(weeks, goal, min(compliance, 2.0) / 2),
    }


# ═══════════════════════════════════════════════════════════════════
# 2. 多维交叉异常检测
# ═══════════════════════════════════════════════════════════════════

def cross_metric_anomaly(metrics_by_date: dict) -> list:
    """跨指标组合异常检测。识别即使单指标正常但组合异常的「隐性风险」。

    典型场景：
    - 睡眠时长正常 + 静息心率升高 + 步数骤降 = 潜在过度训练
    - 步数正常 + 卡路里消耗低 + 体重上升 = 代谢下降信号
    - 心率正常 + 睡眠短 + 步数高 = 压力积累（交感神经过度活跃）

    输入格式: {"2026-01-01": {"steps": 8500, "sleep": 420, "heart_rate": 72, "calories": 380}, ...}
    返回: list of anomaly signals with combined_score and interpretation
    """
    if len(metrics_by_date) < 7:
        return []

    dates = sorted(metrics_by_date.keys())
    signals = []

    # 定义风险模式：(指标1, 条件, 指标2, 条件, 指标3, 条件, 解释, 权重)
    risk_patterns = [
        # 过度训练信号
        ("sleep", lambda v, a: v < a * 0.85,
         "heart_rate", lambda v, a: v > a * 1.1,
         "steps", lambda v, a: v < a * 0.7,
         "潜在过度训练：睡眠减少+静息心率升高+活动量骤降", 3),
        # 代谢下降
        ("steps", lambda v, a: v > a * 0.8,
         "calories", lambda v, a: v < a * 0.7,
         "weight", lambda v, a: v > a * 1.02,
         "代谢下降信号：活动量正常但消耗低+体重升", 2),
        # 压力积累
        ("sleep", lambda v, a: v < a * 0.8,
         "heart_rate", lambda v, a: a * 0.9 <= v <= a * 1.1,
         "steps", lambda v, a: v > a * 1.3,
         "压力积累：睡眠不足但高活动量，注意恢复", 2),
        # 恢复不足（仅两个指标，m3/cond3 置 None）
        ("sleep", lambda v, a: v < a * 0.75,
         "calories", lambda v, a: v < a * 0.6,
         None, None,
         "恢复不足：睡眠和消耗双低，建议安排休息日", 3),
    ]

    # 滑动窗口累积器 — O(n) 基线计算，使用索引指针避免 .index() 扫描
    w_sum = {}  # 指标 → 累计值
    w_cnt = {}  # 指标 → 累计天数
    loop_start = len(dates) - len(dates[-14:])  # 循环起始索引
    window_start_idx = loop_start  # 滑动窗口左边界，从循环起点开始

    # 对每天的数据进行交叉检测
    for i, date in enumerate(dates[-14:], start=len(dates) - len(dates[-14:])):
        today_data = metrics_by_date.get(date, {})
        if not today_data:
            continue

        # 滑动窗口：加入新一天，移除超出 7 天的旧数据
        for k, v in today_data.items():
            if v and v > 0:
                w_sum[k] = w_sum.get(k, 0) + v
                w_cnt[k] = w_cnt.get(k, 0) + 1

        while window_start_idx < i and i - window_start_idx > 7:
            old_date = dates[window_start_idx]
            window_start_idx += 1
            old_data = metrics_by_date.get(old_date, {})
            for k, v in old_data.items():
                if v and v > 0 and k in w_sum:
                    w_sum[k] -= v
                    w_cnt[k] = max(w_cnt.get(k, 0) - 1, 0)

        avg_baseline = {k: w_sum[k] / max(w_cnt[k], 1) for k in w_sum}

        # 检查每个风险模式
        for pattern in risk_patterns:
            m1, cond1, m2, cond2, m3, cond3, desc, weight = pattern
            m1_val = today_data.get(m1)
            m1_avg = avg_baseline.get(m1)
            m2_val = today_data.get(m2)
            m2_avg = avg_baseline.get(m2)

            if not (m1_val and m1_avg and m2_val and m2_avg):
                continue

            m1_flag = cond1(m1_val, m1_avg) if cond1 else True
            m2_flag = cond2(m2_val, m2_avg) if cond2 else True

            if not m1_flag or not m2_flag:
                continue

            # 检查第三个指标（如果有）
            if m3 and cond3:
                m3_val = today_data.get(m3)
                m3_avg = avg_baseline.get(m3)
                if not (m3_val and m3_avg and cond3(m3_val, m3_avg)):
                    continue

            # 计算综合偏差分数
            deviations = []
            for m, cond, avg in [(m1, cond1, m1_avg), (m2, cond2, m2_avg)]:
                val = today_data.get(m)
                if val and avg and avg > 0:
                    deviations.append(abs(val - avg) / avg)

            combined_score = round(sum(deviations) / len(deviations) * weight * 10, 1) if deviations else weight

            signals.append({
                "date": date,
                "pattern": desc,
                "combined_score": combined_score,
                "severity": "high" if combined_score >= 8 else "medium" if combined_score >= 5 else "low",
                "metrics_involved": [m for m in [m1, m2, m3] if m],
            })

    # 去重：同一天同一类型的信号只保留一个
    seen = set()
    deduped = []
    for s in signals:
        key = (s["date"], s["pattern"][:20])
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return sorted(deduped, key=lambda s: s["combined_score"], reverse=True)[:10]


# ═══════════════════════════════════════════════════════════════════
# 3. 指数加权健康评分 (EWMA Health Score)
# ═══════════════════════════════════════════════════════════════════

def ewma_health_score(daily_metrics: list, half_life_days: int = 7) -> dict:
    """基于指数加权移动平均的综合健康评分。与 compute_health_score() 不同：
    - 越近的数据权重越大（指数衰减）
    - 数据越旧衰减越多（stale penalty）
    - 返回趋势箭头和评分变化方向

    输入: [{"date":"2026-01-01","steps":8500,"sleep":480,"calories":350,"heart_rate":65}, ...]
    """
    if not daily_metrics:
        return {"score": 50, "level": "无数据", "trend": "—", "change": 0}

    # 衰减因子：每天权重 = 0.5^(1/half_life)
    decay = 0.5 ** (1.0 / half_life_days)
    now = datetime.now().date()

    weighted_scores = []
    weights = []
    from fitai.analysis.trends import _score_day

    for entry in daily_metrics[-30:]:  # 最近 30 天
        try:
            d = datetime.strptime(entry.get("date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        age_days = (now - d).days
        if age_days < 0:
            age_days = 0

        w = decay ** age_days
        score = _score_day(entry)
        weighted_scores.append(score * w)
        weights.append(w)

    if not weights:
        return {"score": 50, "level": "无数据", "trend": "—", "change": 0}

    total_weight = sum(weights)
    ewma = sum(weighted_scores) / total_weight if total_weight > 0 else 50

    # Stale penalty：如果最近 3 天没有数据，扣分
    recent_dates = set()
    for entry in daily_metrics[-7:]:
        recent_dates.add(entry.get("date", ""))
    last_3_days = [(now - timedelta(days=i)).isoformat() for i in range(3)]
    stale_days = sum(1 for d in last_3_days if d not in recent_dates)
    stale_penalty = stale_days * 3

    final_score = max(0, min(100, round(ewma - stale_penalty)))

    # 趋势：比较最新 3 天 vs 前 3 天
    recent_3 = sum(weighted_scores[-3:]) / sum(weights[-3:]) if len(weighted_scores) >= 6 and sum(weights[-3:]) > 0 else ewma
    prior_3 = sum(weighted_scores[:-3]) / sum(weights[:-3]) if len(weighted_scores) >= 6 and sum(weights[:-3]) > 0 else ewma

    change = round(recent_3 - prior_3, 1)
    if change > 3:
        trend = "↑ 上升"
    elif change < -3:
        trend = "↓ 下降"
    else:
        trend = "→ 稳定"

    level = "优秀" if final_score >= 80 else "良好" if final_score >= 65 else "一般" if final_score >= 45 else "需关注"

    return {
        "score": final_score,
        "level": level,
        "trend": trend,
        "change": change,
        "data_days": len(weighted_scores),
        "stale_penalty": stale_penalty,
        "weight_decay_factor": round(decay, 3),
    }
