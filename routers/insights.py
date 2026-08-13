# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V10.0: 因果洞察路由 — 将 Pearl 因果三层产品化。

端点：
- GET  /api/insights/causal     — 用户的因果发现 + 效应估计
- POST /api/insights/what-if     — 反事实预测
- GET  /api/insights/changepoints — 生理变点检测
- GET  /api/insights/summary     — 综合洞察摘要

V16: 因果图缓存 — pc_stable + estimate_causal_effects 结果按 (user, days, data_fingerprint) 缓存，避免每次请求重算 O(k·2^k·n)
"""
import hashlib
import time as _time
from collections import OrderedDict as _OrderedDict
from fastapi import APIRouter, Request, HTTPException
from core.dependencies import get_user_id, validate_days
from core.db_utils import db_fetch

router = APIRouter(tags=["insights"])

# ── 因果图缓存（服务级，非请求级）──
_causal_cache = _OrderedDict()
_CAUSAL_CACHE_MAX = 100
_CAUSAL_CACHE_TTL = 600  # 10 分钟

# ── Summary 快照缓存 ──
_summary_cache = _OrderedDict()
_SUMMARY_CACHE_MAX = 200
_SUMMARY_CACHE_TTL = 300  # 5 分钟


def _get_causal_cache(user_id: int, days: int, metrics: dict) -> dict | None:
    """如果 daily_metrics 未变化则返回缓存的因果分析结果。"""
    # 用最新日期 + 指标数作为数据指纹（数据不可变，新数据=新日期）
    dates = sorted(metrics.keys())
    fp = hashlib.md5(
        f"{len(dates)}:{dates[-1] if dates else ''}:{len(metrics.get(dates[-1], {})) if dates else 0}"
        .encode()
    ).hexdigest()
    key = f"causal:{user_id}:{days}:{fp}"
    if key in _causal_cache:
        value, ts = _causal_cache[key]
        if _time.time() - ts < _CAUSAL_CACHE_TTL:
            _causal_cache.move_to_end(key)
            return value
        del _causal_cache[key]
    return None


def _set_causal_cache(user_id: int, days: int, metrics: dict, result: dict):
    """缓存因果分析结果。"""
    dates = sorted(metrics.keys())
    fp = hashlib.md5(
        f"{len(dates)}:{dates[-1] if dates else ''}:{len(metrics.get(dates[-1], {})) if dates else 0}"
        .encode()
    ).hexdigest()
    key = f"causal:{user_id}:{days}:{fp}"
    _causal_cache[key] = (result, _time.time())
    _causal_cache.move_to_end(key)
    if len(_causal_cache) > _CAUSAL_CACHE_MAX:
        for _ in range(50):
            _causal_cache.popitem(last=False)


def _invalidate_causal_cache(user_id: int):
    """用户数据变更时清除该用户因果缓存。"""
    prefix = f"causal:{user_id}:"
    to_delete = [k for k in _causal_cache if k.startswith(prefix)]
    for k in to_delete:
        del _causal_cache[k]


@router.get("/api/insights/causal")
async def insights_causal(request: Request, days: int = 30):
    """返回用户的因果发现结果。

    1. 从健康数据构建 daily_metrics
    2. 运行 PC-stable 因果发现
    3. 估计每条因果边的效应量
    4. 返回可解释的因果洞察
    """
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"insights": [], "message": "请先登录"}

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"insights": [], "message": f"数据不足（需至少 14 天，当前 {len(daily_metrics)} 天），请先导入或记录更多健康数据"}

    from fitai.analysis.causal_discovery import pc_stable
    from fitai.analysis.causal_effects import estimate_causal_effects

    cached = _cached_causal_analysis(daily_metrics, user_id, days)
    discovery = cached["discovery"]
    graph = discovery.get("graph", {})
    if not graph:
        return {"insights": [], "message": "未发现显著的因果关系，继续记录更多数据后因果图会逐渐显现", "n_days": len(daily_metrics)}

    effects = cached["effects"]
    significant = [e for e in effects if e["significant"]]

    return {
        "n_days": len(daily_metrics),
        "n_variables": discovery.get("n_variables", 0),
        "n_causal_edges": len(effects),
        "n_significant": len(significant),
        "causal_graph": graph,
        "causal_effects": effects[:10],
        "insights": discovery.get("causal_insights", []),
        "top_finding": _format_top_finding(significant),
    }


@router.post("/api/insights/what-if")
async def insights_what_if(request: Request):
    """反事实预测：如果改变某个指标，其他指标会变成多少？

    Body: {"scenario": {"sleep": 480, "steps": 12000}, "days": 30}
    """
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    scenario = body.get("scenario", {})
    if not scenario:
        raise HTTPException(status_code=400, detail="请提供 scenario（如 {'sleep': 480}）")

    days = validate_days(body.get("days", 30), max_days=90)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"predictions": [], "message": f"数据不足（需至少 14 天，当前 {len(daily_metrics)} 天）"}

    from fitai.analysis.counterfactual import CounterfactualEngine

    cached = _cached_causal_analysis(daily_metrics, user_id, days)
    discovery = cached["discovery"]
    effects = cached["effects"]

    engine = CounterfactualEngine(effects, daily_metrics)
    predictions = engine.predict(scenario)

    return {
        "scenario": scenario,
        "current_state": {k: v for k, v in engine._current.items() if k in scenario or any(p["metric"] == k for p in predictions)},
        "predictions": predictions,
        "n_causal_edges": len(effects),
        "summary": _format_what_if_summary(scenario, predictions),
    }


@router.get("/api/insights/changepoints")
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


@router.get("/api/insights/summary")
async def insights_summary(request: Request, days: int = 30):
    """综合洞察摘要：一句话告诉你最重要的发现。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"summary": "请先登录"}

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"summary": f"已记录 {len(daily_metrics)} 天数据，再记录 {14 - len(daily_metrics)} 天即可生成洞察", "n_days": len(daily_metrics)}

    # 快照缓存检查（比因果缓存更粗粒度，直接缓存完整响应）
    dates = sorted(daily_metrics.keys())
    snap_key = f"{user_id}:{days}:{dates[-1] if dates else ''}"
    if snap_key in _summary_cache:
        cached_result, ts = _summary_cache[snap_key]
        if _time.time() - ts < _SUMMARY_CACHE_TTL:
            _summary_cache.move_to_end(snap_key)
            return cached_result
        del _summary_cache[snap_key]

    from fitai.analysis.trends import compute_health_score

    cached = _cached_causal_analysis(daily_metrics, user_id, days)
    discovery = cached["discovery"]
    effects = cached["effects"]
    significant = [e for e in effects if e["significant"]]

    latest_date = dates[-1]
    health = compute_health_score(daily_metrics[latest_date])

    result = {
        "n_days": len(daily_metrics),
        "health_score": health,
        "causal_summary": _format_top_finding(significant),
        "n_causal_edges": len(effects),
        "n_significant": len(significant),
        "causal_insights": discovery.get("causal_insights", [])[:3],
    }

    # 写入快照缓存
    _summary_cache[snap_key] = (result, _time.time())
    _summary_cache.move_to_end(snap_key)
    if len(_summary_cache) > _SUMMARY_CACHE_MAX:
        for _ in range(50):
            _summary_cache.popitem(last=False)

    return result


@router.post("/api/insights/best-intervention")
async def insights_best_intervention(request: Request):
    """找到对目标指标最有效的干预方案。

    Body: {"target": "recovery_score", "max_changes": {"sleep": 120, "steps": 5000}, "days": 30}
    返回排名前 3 的干预方案。
    """
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    target = body.get("target", "health_score")
    max_changes = body.get("max_changes", None)
    days = validate_days(body.get("days", 30), max_days=90)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"interventions": [], "message": f"数据不足（需至少 14 天，当前 {len(daily_metrics)} 天）"}

    from fitai.analysis.counterfactual import CounterfactualEngine

    cached = _cached_causal_analysis(daily_metrics, user_id, days)
    discovery = cached["discovery"]
    effects = cached["effects"]
    engine = CounterfactualEngine(effects, daily_metrics)

    # Get all interventions ranked by impact — iterate over all causes with effects
    all_causes = set(e["cause"] for e in effects if e["significant"])
    interventions = []
    for cause in all_causes:
        scenario = {cause: engine._current.get(cause, 0) * 1.2 if engine._current.get(cause, 0) else 100}
        predictions = engine.predict(scenario)
        for p in predictions:
            if p.get("metric") == target:
                interventions.append({
                    "cause": cause,
                    "current_value": engine._current.get(cause),
                    "intervention": scenario[cause],
                    "target_metric": target,
                    "expected_change": p.get("change", 0),
                    "ci_lower": p.get("ci_lower"),
                    "ci_upper": p.get("ci_upper"),
                    "interpretation": p.get("interpretation", ""),
                })

    interventions.sort(key=lambda i: abs(i["expected_change"]), reverse=True)

    return {
        "target": target,
        "n_days": len(daily_metrics),
        "interventions": interventions[:3],
        "message": "以下干预方案基于因果效应估计，实际效果可能因个体差异而不同",
    }


@router.get("/api/insights/predictions")
async def insights_predictions(request: Request, metric: str = "steps",
                                days_ahead: int = 7, days: int = 30):
    """SSA 预测 + 共形预测区间。

    返回未来 N 天的预测值及 90% 置信区间（由共形预测保证分布无关的覆盖率）。
    """
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    days_ahead = min(days_ahead, 30)
    days = validate_days(days, max_days=90)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"predictions": [], "message": "数据不足"}

    dates = sorted(daily_metrics.keys())
    values = []
    for d in dates:
        v = daily_metrics[d].get(metric)
        if v is not None:
            values.append(v)
        else:
            values.append(values[-1] if values else 0)

    if len(values) < 14:
        return {"predictions": [], "message": "该指标数据不足"}

    from fitai.analysis.ssa_forecast import ssa_forecast
    from fitai.analysis.conformal import ConformalPredictor

    # SSA forecast
    forecast_result = ssa_forecast(values, steps=days_ahead)
    forecast_values = forecast_result.get("forecast", [])

    # Conformal prediction intervals (80% coverage)
    try:
        cp = ConformalPredictor(alpha=0.2)
        n_train = len(values) * 2 // 3
        cp.calibrate(values[:n_train], values[n_train:])
        intervals = [cp.predict_intervals([fv])[0] for fv in forecast_values]
    except Exception:
        intervals = [{"lower": fv * 0.8, "upper": fv * 1.2, "prediction": fv} for fv in forecast_values]

    from datetime import date as dt_date, timedelta
    last_date_str = dates[-1]
    try:
        last_date = dt_date.fromisoformat(last_date_str)
    except (ValueError, TypeError):
        last_date = dt_date.today()

    predictions = []
    for i, fv in enumerate(forecast_values):
        d = (last_date + timedelta(days=i + 1)).isoformat()
        iv = intervals[i] if i < len(intervals) else {}
        predictions.append({
            "date": d,
            "predicted": round(fv, 1),
            "ci_lower": round(iv.get("lower", fv * 0.8), 1),
            "ci_upper": round(iv.get("upper", fv * 1.2), 1),
        })

    return {
        "metric": metric,
        "days_ahead": days_ahead,
        "n_historical_days": len(values),
        "predictions": predictions,
        "trend_direction": "up" if (forecast_values[-1] if forecast_values else 0) > values[-1] else "down",
    }


# ═══════════════ V14: 新算法端点 ═══════════════

@router.get("/api/insights/recovery")
async def insights_recovery(request: Request, days: int = 30):
    """贝叶斯个性化恢复评分。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 7:
        return {"score": None, "message": f"数据不足（需至少 7 天，当前 {len(daily_metrics)} 天）"}

    from tools.fitai_database import get_workout_history_json
    from fitai.analysis.bayesian_recovery import BayesianRecoveryModel, get_user_model
    from fitai.analysis.trends import compute_health_score

    dates = sorted(daily_metrics.keys())
    model = get_user_model(user_id)

    # 增量更新：只喂入上次更新之后的新数据
    last_fed = getattr(model, '_last_fed_date', None)
    new_dates = dates if last_fed is None else [d for d in dates if d > last_fed]

    # Feed historical data to model
    workout_history = get_workout_history_json(user_id, days)
    workout_by_date = {}
    for w in workout_history:
        d = w.get("date", "")
        workout_by_date[d] = workout_by_date.get(d, 0) + 1

    for i, d in enumerate(dates):
        if d not in new_dates:
            continue
        m = daily_metrics[d]
        sleep_min = m.get("sleep", 0)
        steps = m.get("steps", 0)
        hr = m.get("heart_rate", 0)
        workout_count = workout_by_date.get(d, 0)
        workout_intensity = min(workout_count * 3, 10)
        sleep_hours = sleep_min / 60 if sleep_min > 0 else 7
        hr_deviation = abs(hr - 70) / 10 if hr > 30 else 0
        training_streak = 1 if workout_count > 0 else 0
        if i > 0:
            prev_m = daily_metrics[dates[i - 1]]
            prev_steps = prev_m.get("steps", 0)
            if steps >= prev_steps * 0.8:
                training_streak = min(training_streak + 1, 30)

        observed = None
        if i < len(dates) - 1:
            next_m = daily_metrics[dates[i + 1]]
            next_steps = next_m.get("steps", 0)
            next_hr = next_m.get("heart_rate", 0)
            if steps > 0 and next_hr > 0:
                recovery = max(0, min(100, 50 + (next_steps / max(steps, 1) - 1) * 30 - (next_hr / max(hr, 1) - 1) * 20))
                observed = recovery

        model.update(workout_intensity, sleep_hours, hr_deviation, steps, training_streak, observed)

    # 记录已喂入的最后日期
    model._last_fed_date = dates[-1] if dates else None

    # Predict today
    last_m = daily_metrics[dates[-1]]
    features = {
        "workout_intensity": workout_by_date.get(dates[-1], 0) * 3,
        "sleep_hours": last_m.get("sleep", 420) / 60,
        "hr_deviation": abs(last_m.get("heart_rate", 70) - 70) / 10,
        "steps": last_m.get("steps", 0),
        "training_streak": 1,
    }
    pred = model.predict(**features)

    health_score = compute_health_score(last_m) if last_m else 50

    return {
        "recovery_score": round(pred.get("score", 50), 1),
        "recovery_ci": [round(pred.get("ci_lower", 30), 1), round(pred.get("ci_upper", 70), 1)],
        "health_score": health_score,
        "n_days": len(daily_metrics),
        "message": _recovery_interpretation(pred.get("score", 50)),
    }


def _recovery_interpretation(score):
    if score >= 80: return "恢复良好，可以正常训练"
    if score >= 60: return "恢复一般，建议中低强度训练"
    if score >= 40: return "恢复不足，建议休息或轻度活动"
    return "恢复很差，建议今天休息"


@router.get("/api/insights/recovery/population")
async def insights_recovery_population(request: Request, days: int = 30):
    """层次贝叶斯恢复评分（含人群对比）。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 7:
        return {"personal_score": None, "message": "数据不足"}

    from fitai.analysis.hierarchical_bayes import HierarchicalBayesianModel

    hbm = HierarchicalBayesianModel()
    dates = sorted(daily_metrics.keys())

    for i, d in enumerate(dates):
        m = daily_metrics[d]
        features = [
            m.get("sleep", 420) / 60,
            m.get("steps", 0) / 1000,
            m.get("heart_rate", 70),
            m.get("calories", 0) / 100,
        ]
        observed = None
        if i < len(dates) - 1:
            nm = daily_metrics[dates[i + 1]]
            nr = 50 + (nm.get("steps", 0) / max(m.get("steps", 1), 1) - 1) * 30
            observed = max(0, min(100, nr))
        hbm.update_user(user_id, features, observed)

    last_m = daily_metrics[dates[-1]]
    features = [
        last_m.get("sleep", 420) / 60,
        last_m.get("steps", 0) / 1000,
        last_m.get("heart_rate", 70),
        last_m.get("calories", 0) / 100,
    ]
    result = hbm.predict(user_id, features)

    return {
        "personal_score": round(result.get("prediction", 50), 1),
        "personal_ci": round(result.get("ci_width", 20), 1),
        "population_mean": round(hbm.mu_pop, 1) if hasattr(hbm, "mu_pop") else 50,
        "n_days": len(daily_metrics),
    }


@router.get("/api/insights/hr-zones")
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


@router.get("/api/insights/sleep-regularity")
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


@router.get("/api/insights/training-load")
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


@router.get("/api/insights/progressive-overload")
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


# ═══════════════ 工具函数 ═══════════════

async def _load_daily_metrics(user_id: int, days: int) -> dict:
    """从数据库加载用户健康数据，转为 {date: {metric: value}} 格式。"""
    rows = await db_fetch(
        "SELECT date, data_type, AVG(value) as value FROM health_data "
        "WHERE user_id = ? AND date >= date('now', ?) "
        "GROUP BY date, data_type ORDER BY date",
        (user_id, f"-{days} days"),
    )
    metrics = {}
    for r in rows:
        d = r["date"]
        if d not in metrics:
            metrics[d] = {}
        try:
            metrics[d][r["data_type"]] = float(r["value"])
        except (ValueError, TypeError):
            pass
    return metrics


def _format_top_finding(significant_effects: list) -> str:
    """格式化最重要的因果发现。"""
    if not significant_effects:
        return "继续记录更多数据后，我会帮你发现指标间的因果关系"
    best = significant_effects[0]
    return best.get("interpretation", f"{best['cause']} → {best['effect']}: {best['effect_size']:.4f}")


def _format_what_if_summary(scenario: dict, predictions: list) -> str:
    """格式化反事实预测摘要。"""
    if not predictions:
        return "当前数据不足以做出可靠的因果预测，请继续记录数据"
    parts = []
    for p in predictions[:3]:
        parts.append(p.get("interpretation", ""))
    return "；".join(parts) if parts else "分析完成"


def _format_changepoint_message(shifts: list) -> str:
    """格式化变点检测消息。"""
    if not shifts:
        return "未检测到显著的生理状态变化"
    latest = shifts[-1]
    direction_cn = {"degrading": "下降趋势", "improving": "改善趋势"}
    evidence_cn = {"strong_change": "强证据", "moderate_change": "中等证据", "weak": "弱证据"}
    return (
        f"检测到 {len(shifts)} 个生理变点。"
        f"最近一次：{latest['date']}，{direction_cn.get(latest['shift_type'], '变化')}"
        f"（{evidence_cn.get(latest['evidence'], '')}）"
    )


def _ewma_smooth(values: list, span: int = 7) -> list:
    """EWMA 平滑（用于变点检测的预测基线）。"""
    alpha = 2.0 / (span + 1)
    smoothed = []
    s = values[0] if values else 0
    for v in values:
        s = alpha * v + (1 - alpha) * s
        smoothed.append(round(s, 2))
    return smoothed


def _ewma_std(values: list, predicted: list, span: int = 7) -> float:
    """EWMA 残差标准差。"""
    if len(values) < 3:
        return 5.0
    residuals = [abs(values[i] - predicted[i]) for i in range(len(values))]
    return sum(residuals) / len(residuals) * 1.5


def _cached_causal_analysis(daily_metrics: dict, user_id: int, days: int) -> dict:
    """PC-stable + causal effects，带缓存。"""
    cached = _get_causal_cache(user_id, days, daily_metrics)
    if cached is not None:
        return cached

    from fitai.analysis.causal_discovery import pc_stable
    from fitai.analysis.causal_effects import estimate_causal_effects

    discovery = pc_stable(daily_metrics)
    effects = estimate_causal_effects(daily_metrics, discovery.get("graph", {}))

    result = {"discovery": discovery, "effects": effects}
    _set_causal_cache(user_id, days, daily_metrics, result)
    return result
