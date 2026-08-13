# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 仪表盘路由 — workout、metrics、stats、health、nutrition（从 server.py 提取）。"""
from fastapi import APIRouter, Request
from core.dependencies import get_user_id, validate_days
from core.cache import default_cache
from core.db_utils import db_fetch
from tools.fitai_database import (get_workout_history_json, get_body_metrics_history_json,
                                   get_nutrition_history_json, get_streak)
from auth.utils import is_registration_allowed

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/workout")
async def dashboard_workout(request: Request, days: int = 1):
    days = validate_days(days)
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return {"sessions": [], "total_duration": 0, "total_exercises": 0}
    ck = f"dw:{user_id}:{days}"
    cv = default_cache.get(ck, 300)
    if cv is not None:
        return cv
    workouts = get_workout_history_json(user_id, days)
    total_dur = sum(w.get("duration_minutes", 0) or 0 for w in workouts)
    result = {"data": workouts, "sessions": workouts, "total_duration": total_dur,
              "total_exercises": len(workouts), "streak": get_streak(user_id)}
    default_cache.set(ck, result)
    return result


@router.get("/api/dashboard/metrics")
async def dashboard_metrics(request: Request, days: int = 90):
    days = validate_days(days)
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return {"body_metrics": [], "workouts": []}
    ck = f"dm:{user_id}:{days}"
    cv = default_cache.get(ck, 300)
    if cv is not None:
        return cv
    body = get_body_metrics_history_json(user_id, days)
    result = {"data": body, "body_metrics": body,
              "workouts": get_workout_history_json(user_id, days)}
    default_cache.set(ck, result)
    return result


@router.get("/api/stats")
async def stats(request: Request, days: int = 7):
    days = validate_days(days)
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return {"workouts": [], "body_metrics": [], "nutrition": []}
    ck = f"st:{user_id}:{days}"
    cv = default_cache.get(ck, 300)
    if cv is not None:
        return cv
    result = {"workouts": get_workout_history_json(user_id, days),
              "body_metrics": get_body_metrics_history_json(user_id, days),
              "nutrition": get_nutrition_history_json(user_id, days)}
    default_cache.set(ck, result)
    return result


@router.get("/api/dashboard/health")
async def dashboard_health(request: Request, data_type: str = "steps", days: int = 7):
    days = validate_days(days)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"data": []}
    ck = f"dh:{user_id}:{data_type}:{days}"
    cv = default_cache.get(ck, 180)
    if cv is not None:
        return cv
    rows = await db_fetch(
        "SELECT date, value, unit FROM health_data WHERE user_id = ? AND data_type = ? "
        "AND date >= date('now', ?) ORDER BY date ASC",
        (user_id, data_type, f"-{days} days"),
    )
    result = {"data": [dict(r) for r in rows]}
    default_cache.set(ck, result)
    return result


@router.get("/api/dashboard/health-batch")
async def dashboard_health_batch(request: Request, types: str = "steps,sleep,calories", days: int = 7):
    days = validate_days(days)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"data": {}}

    ck = f"dhb:{user_id}:{types}:{days}"
    cv = default_cache.get(ck, 300)
    if cv is not None:
        return cv

    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if not type_list:
        return {"data": {}}

    placeholders = ",".join(["?" for _ in type_list])
    params = [user_id, f"-{days} days"] + type_list
    rows = await db_fetch(
        f"SELECT data_type, date, value, unit FROM health_data WHERE user_id=? "
        f"AND date>=date('now',?) AND data_type IN ({placeholders}) ORDER BY date",
        tuple(params),
    )

    result_data = {}
    for r in rows:
        dt = r["data_type"]
        if dt not in result_data:
            result_data[dt] = []
        result_data[dt].append({"date": r["date"], "value": r["value"], "unit": r["unit"]})

    result = {"data": result_data}
    default_cache.set(ck, result)
    return result


@router.get("/api/dashboard/nutrition")
async def dashboard_nutrition(request: Request, days: int = 7):
    days = validate_days(days)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"data": []}
    ck = f"dn:{user_id}:{days}"
    cv = default_cache.get(ck, 300)
    if cv is not None:
        return cv
    result = {"data": get_nutrition_history_json(user_id, days)}
    default_cache.set(ck, result)
    return result


@router.get("/api/auth/registration-status")
async def registration_status():
    return {"registration_allowed": await is_registration_allowed()}
