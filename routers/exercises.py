# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 训练动作库路由（从 server.py 提取）。"""
import re
from collections import Counter, defaultdict

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from core.dependencies import get_user_id
from core.cache import default_cache
from tools.fitai_database import (search_exercises_db, get_exercise_by_id,
                                   get_exercise_categories, get_exercise_equipment,
                                   import_exercise_library, get_workout_history_json)

router = APIRouter(tags=["exercises"])

EMPTY_ANALYSIS = {"total_workouts": 0, "total_exercise_minutes": 0,
                  "frequency": [], "monthly_trend": [], "calories_by_month": []}
EMPTY_TYPE = {"total_count": 0, "days": 0, "total_minutes": 0,
              "monthly_trend": [], "history": []}

# ══ 静态路径必须在动态路径之前定义 ══

@router.get("/api/exercises/library")
async def exercises_library(category: str = "", body_part: str = "",
                            equipment: str = "", keyword: str = "", limit: int = 50):
    result = search_exercises_db(category=category or None, body_part=body_part or None,
                                  equipment=equipment or None, keyword=keyword or None,
                                  limit=limit)
    return {"exercises": result, "total": len(result)}


@router.get("/api/exercises/categories")
async def exercises_categories():
    return {"categories": get_exercise_categories()}


@router.get("/api/exercises/equipment")
async def exercises_equipment():
    return {"equipment": get_exercise_equipment()}


@router.get("/api/exercises/image/{media_id}")
async def exercise_image(media_id: str):
    """代理 ExerciseDB 的 GIF 图片，绕开国内浏览器无法直连的 CDN。"""
    media_id = re.sub(r"[^a-zA-Z0-9]", "", (media_id or "").split(".")[0])
    if not media_id:
        return Response(status_code=400)
    cache_key = f"exgif:{media_id}"
    cached = default_cache.get(cache_key, 180)
    if cached is not None:
        return Response(content=cached, media_type="image/gif",
                        headers={"Cache-Control": "public, max-age=86400"})
    url = f"https://static.exercisedb.dev/media/{media_id}.gif"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return Response(status_code=502)
        data = r.content
        default_cache.set(cache_key, data)
        return Response(content=data, media_type="image/gif",
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        return Response(status_code=502)


@router.post("/api/exercises/import")
async def exercises_import():
    count = import_exercise_library()
    return {"imported": count}


@router.get("/api/exercises/analysis")
async def exercises_analysis(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return EMPTY_ANALYSIS
    workouts = get_workout_history_json(user_id, 365)
    if not workouts:
        return EMPTY_ANALYSIS

    freq = Counter(w["exercise_name"] for w in workouts)
    frequency = [{"name": k, "count": v,
                  "total_minutes": sum(w.get("duration_minutes", 0) or 0 for w in workouts if w["exercise_name"] == k),
                  "days": len(set(w["date"] for w in workouts if w["exercise_name"] == k))}
                 for k, v in freq.most_common()]

    monthly = defaultdict(lambda: {"count": 0, "total_minutes": 0})
    for w in workouts:
        m = w["date"][:7]
        monthly[m]["count"] += 1
        monthly[m]["total_minutes"] += w.get("duration_minutes", 0) or 0

    monthly_trend = [{"month": k, "count": v["count"], "total_minutes": v["total_minutes"]}
                     for k, v in sorted(monthly.items())]
    calories_by_month = [{"month": k, "calories": v["total_minutes"] * 5}
                         for k, v in sorted(monthly.items())]
    total_minutes = sum(w.get("duration_minutes", 0) or 0 for w in workouts)

    return {"total_workouts": len(workouts), "total_exercise_minutes": total_minutes,
            "frequency": frequency, "monthly_trend": monthly_trend,
            "calories_by_month": calories_by_month}


@router.get("/api/exercises/type/{name}")
async def exercises_type(name: str, request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return EMPTY_TYPE
    workouts = [w for w in get_workout_history_json(user_id, 365)
                if w["exercise_name"] == name]
    if not workouts:
        return EMPTY_TYPE

    total_count = len(workouts)
    days = len(set(w["date"] for w in workouts))
    total_minutes = sum(w.get("duration_minutes", 0) or 0 for w in workouts)
    max_weight = max((w.get("weight_kg", 0) or 0 for w in workouts), default=0)
    total_volume = sum((w.get("sets", 0) or 0) * (w.get("reps", 0) or 0)
                       for w in workouts)

    monthly = defaultdict(lambda: {"cnt": 0, "total_min": 0})
    for w in workouts:
        m = w["date"][:7]
        monthly[m]["cnt"] += 1
        monthly[m]["total_min"] += w.get("duration_minutes", 0) or 0
    monthly_trend = [{"month": k, "cnt": v["cnt"], "total_min": v["total_min"]}
                     for k, v in sorted(monthly.items())]
    history = sorted(workouts, key=lambda w: w["date"], reverse=True)[:50]

    return {"total_count": total_count, "days": days, "total_minutes": total_minutes,
            "max_weight": max_weight if max_weight > 0 else None,
            "total_volume": total_volume if total_volume > 0 else None,
            "monthly_trend": monthly_trend, "history": history}


# ══ 动态路径放在最后 ══

@router.get("/api/exercises/{exercise_id}")
async def exercise_detail(exercise_id: str):
    ex = get_exercise_by_id(exercise_id)
    return ex or {"error": "Not found"}
