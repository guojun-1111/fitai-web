# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 周报路由（从 server.py 提取）。"""
from fastapi import APIRouter, Request
from core.dependencies import get_user_id
from core.db_utils import db_fetch
from core.cache import default_cache

router = APIRouter(tags=["weekly"])


@router.get("/api/weekly-summary")
async def weekly_summary(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return {"summary": None}
    ck = f"ws:{user_id}"
    cv = default_cache.get(ck, 180)
    if cv is not None:
        return cv

    summary = {}
    rows = await db_fetch(
        "SELECT data_type, SUM(value) as total, ROUND(AVG(value),1) as avg_val, COUNT(*) as cnt "
        "FROM health_data WHERE user_id=? AND date >= date('now','-7 days') GROUP BY data_type",
        (user_id,),
    )
    for r in rows:
        summary[r["data_type"]] = {"total": round(r["total"], 1),
                                   "avg": float(r["avg_val"]), "count": r["cnt"]}

    wk_rows = await db_fetch(
        "SELECT COUNT(*) as c FROM workout_logs WHERE user_id=? AND date >= date('now','-7 days')",
        (user_id,))
    summary["workout_count"] = wk_rows[0]["c"] if wk_rows else 0

    wt_rows = await db_fetch(
        "SELECT value FROM health_data WHERE user_id=? AND data_type='weight' "
        "AND date >= date('now','-7 days') ORDER BY date",
        (user_id,),
    )
    if len(wt_rows) >= 2:
        summary["weight_change"] = round(float(wt_rows[-1]["value"]) - float(wt_rows[0]["value"]), 1)

    result = {"summary": summary}
    default_cache.set(ck, result)
    return result
