# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""生理指标洞察：变点、心率分区、睡眠规律、训练负荷、渐进超负荷。"""
from fastapi import APIRouter, Request, HTTPException

from core.dependencies import get_user_id, validate_days
from core.db_utils import db_fetch
from routers.insights_common import _load_daily_metrics, _ewma_smooth, _format_changepoint_message

router = APIRouter()


@router.get("/changepoints")
async def insights_changepoints(request: Request, days: int = 60):
    """检测用户的生理状态变点。"""
    days = validate_days(days, max_days=180)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"changepoints": [], "message": "请先登录"}

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"changepoints": [], "message": "数据不足"}

    # EWMA-smoothed scores with adaptive residual std
    dates = sorted(daily_metrics.keys())
    from fitai.analysis.trends import compute_health_score

    scores = []
    for d in dates:
        score = compute_health_score(daily_metrics[d])
        scores.append(score["score"])

    from fitai.analysis.changepoint import detect_physiological_shifts
    predicted = _ewma_smooth(scores, span=7)
    # Adaptive std: wider when residuals are large
    residuals = [abs(scores[i] - predicted[i]) for i in range(len(scores))]
    avg_residual = sum(residuals) / len(residuals) if residuals else 5.0
    stds = [max(avg_residual * 1.2, 3.0)] * len(scores)

    shifts = detect_physiological_shifts(dates, scores, predicted, stds)

    return {
        "n_days": len(dates),
        "changepoints": shifts,
        "current_score": scores[-1] if scores else None,
        "message": _format_changepoint_message(shifts),
    }


@router.get("/hr-zones")
async def insights_hr_zones(request: Request, days: int = 7):
    """心率分区分析。"""
    days = validate_days(days, max_days=30)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    rows = await db_fetch(
        "SELECT value FROM health_data WHERE user_id=? AND data_type='heart_rate' "
        "AND date >= date('now', ?) ORDER BY date",
        (user_id, f"-{days} days"),
    )
    if not rows:
        return {"zones": {}, "message": "该时段无心率数据"}

    hr_samples = [{"heart_rate": r["value"], "timestamp": 0} for r in rows]

    # Get user age from profile
    age_row = await db_fetch("SELECT age FROM user_profile WHERE user_id=?", (user_id,))
    age = age_row[0]["age"] if age_row else 30

    from fitai.analysis.heart_rate import hr_zone_analysis
    zones = hr_zone_analysis(hr_samples, age=age, resting_hr=60)

    return {
        "n_samples": len(hr_samples),
        "days": days,
        "zones": zones,
    }


@router.get("/sleep-regularity")
async def insights_sleep_regularity(request: Request, days: int = 30):
    """睡眠规律指数（SRI）。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    rows = await db_fetch(
        "SELECT date, value FROM health_data WHERE user_id=? AND data_type='sleep' "
        "AND date >= date('now', ?) ORDER BY date",
        (user_id, f"-{days} days"),
    )
    if len(rows) < 5:
        return {"sri": None, "message": f"数据不足（需至少 5 天，当前 {len(rows)} 天）"}

    sleep_data = [{"date": r["date"], "value": r["value"]} for r in rows]
    from fitai.analysis.sleep import compute_sleep_regularity_index
    result = compute_sleep_regularity_index(sleep_data)

    return {
        "n_days": len(rows),
        **result,
    }


@router.get("/training-load")
async def insights_training_load(request: Request, days: int = 28):
    """急慢性负荷比（ACWR）受伤风险评估。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    rows = await db_fetch(
        "SELECT date, rpe, duration_minutes FROM workout_logs "
        "WHERE user_id=? AND date >= date('now', ?) "
        "AND rpe IS NOT NULL AND duration_minutes IS NOT NULL ORDER BY date",
        (user_id, f"-{days} days"),
    )
    if len(rows) < 7:
        return {"acwr": None, "risk": "unknown", "message": f"数据不足（需至少 7 天，当前 {len(rows)} 天）"}

    from fitai.analysis.trends import compute_acwr, compute_srpe
    loads = []
    for r in rows:
        sRPE = compute_srpe(r["rpe"], r["duration_minutes"])
        if sRPE > 0:
            loads.append({"date": r["date"], "load": sRPE})

    if len(loads) < 7:
        return {"acwr": None, "risk": "unknown", "message": "有效训练负荷数据不足"}

    result = compute_acwr(loads)

    return {
        "acwr": round(result.get("acwr", 0), 2),
        "acute_load": round(result.get("acute_load", 0), 1),
        "chronic_load": round(result.get("chronic_load", 0), 1),
        "risk": result.get("risk", "unknown"),
        "n_days": len(loads),
    }


@router.get("/progressive-overload")
async def insights_progressive_overload(request: Request, days: int = 56):
    """渐进超负荷检测（所有训练动作）。"""
    days = validate_days(days, max_days=180)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    from tools.fitai_database import get_workout_history_json
    from fitai.analysis.trends import detect_progressive_overload

    workouts = get_workout_history_json(user_id, days)
    if not workouts:
        return {"results": [], "message": "该时段无训练记录"}

    # Group by exercise name
    by_name = {}
    for w in workouts:
        name = w.get("exercise_name", "未知")
        if name not in by_name:
            by_name[name] = []
        by_name[name].append(w)

    results = []
    for name, history in by_name.items():
        if len(history) < 4:
            continue
        # Detect overload on weight (primary metric)
        result = detect_progressive_overload(history, name, "weight_kg")
        if result.get("detected"):
            results.append({
                "exercise": name,
                "pr": result.get("pr"),
                "trend": result.get("trend"),
                "message": result.get("message", ""),
            })

    results.sort(key=lambda r: abs(r.get("trend", 0) or 0), reverse=True)

    return {
        "n_exercises": len(by_name),
        "n_days": days,
        "progressing": results[:10],
        "n_progressing": len(results),
    }
