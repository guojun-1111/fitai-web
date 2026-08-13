# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 用户档案路由（从 server.py 提取）。"""
import json
from fastapi import APIRouter, Request, HTTPException
from core.dependencies import get_user_id
from core.db_utils import db_fetch, db_execute

router = APIRouter(tags=["profile"])

PROFILE_DEFAULTS = {"name": "", "gender": "", "birth_year": None,
                    "height_cm": None, "weight_kg": None,
                    "fitness_goal": "", "activity_level": "", "notes": "",
                    "coach_style": "friend",
                    "equipment": "", "experience_level": "", "time_per_session": ""}


@router.get("/api/profile")
async def get_profile(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return PROFILE_DEFAULTS
    rows = await db_fetch("SELECT * FROM user_profile WHERE user_id = ?", (user_id,))
    if not rows:
        return PROFILE_DEFAULTS
    row = rows[0]
    return {k: (row[k] if row[k] is not None else ("" if k != "birth_year" else None))
            for k in PROFILE_DEFAULTS}


@router.post("/api/profile")
async def save_profile(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    await db_execute("""
        INSERT OR REPLACE INTO user_profile
        (user_id, name, gender, birth_year, height_cm, weight_kg, fitness_goal, activity_level, notes, coach_style, equipment, experience_level, time_per_session)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, body.get("name", ""), body.get("gender", ""),
          body.get("birth_year"), body.get("height_cm"), body.get("weight_kg"),
          body.get("fitness_goal", ""), body.get("activity_level", ""), body.get("notes", ""),
          body.get("coach_style", "friend"),
          body.get("equipment", ""), body.get("experience_level", ""), body.get("time_per_session", "")))
    return {"ok": True}


@router.post("/api/profile/update")
async def update_profile(request: Request):
    """Mini-program alias for profile save."""
    return await save_profile(request)
