# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""因果洞察：因果发现、反事实预测、最佳干预、综合摘要。"""
import time as _time

from fastapi import APIRouter, Request, HTTPException

from core.dependencies import get_user_id, validate_days
from routers.insights_common import (
    _load_daily_metrics, _cached_causal_analysis,
    _format_top_finding, _format_what_if_summary,
    _summary_cache, _SUMMARY_CACHE_MAX, _SUMMARY_CACHE_TTL,
)

router = APIRouter()


@router.get("/causal")
async def insights_causal(request: Request, days: int = 30):
    """返回用户的因果发现结果。"""
    days = validate_days(days, max_days=90)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"insights": [], "message": "请先登录"}

    daily_metrics = await _load_daily_metrics(user_id, days)
    if len(daily_metrics) < 14:
        return {"insights": [], "message": f"数据不足（需至少 14 天，当前 {len(daily_metrics)} 天），请先导入或记录更多健康数据"}

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


@router.post("/what-if")
async def insights_what_if(request: Request):
    """反事实预测：如果改变某个指标，其他指标会变成多少？"""
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


@router.get("/summary")
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


@router.post("/best-intervention")
async def insights_best_intervention(request: Request):
    """找到对目标指标最有效的干预方案。"""
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
