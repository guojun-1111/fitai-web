# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""因果洞察共享工具：数据加载、因果缓存、格式化。"""
import hashlib
import time as _time
from collections import OrderedDict as _OrderedDict

from core.db_utils import db_fetch

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
