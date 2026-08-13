# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V15: 训练计划路由 — AI 生成周计划 + 进度追踪。"""
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from core.dependencies import get_user_id, validate_days
from core.db_utils import db_fetch, db_execute

router = APIRouter(prefix="/api/training", tags=["training"])


@router.post("/plan")
async def create_training_plan(request: Request):
    """AI 生成训练计划并保存。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    name = body.get("name", "我的训练计划")
    goal = body.get("goal", "综合提升")
    weeks = min(int(body.get("weeks", 4)), 12)

    # V18: Use daily planner for single-week plans, periodization for multi-week
    if weeks <= 1:
        from fitai.analysis.daily_planner import generate_daily_plan
        plan_data = generate_daily_plan(goal=goal, frequency=3)
    else:
        from fitai.analysis.periodization import generate_plan as gen_weekly
        plan_data = gen_weekly(goal, weeks=weeks)

    await db_execute(
        "INSERT INTO training_plans (user_id, name, goal, weeks, plan_data) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, goal, weeks, json.dumps(plan_data, ensure_ascii=False)),
    )
    # Deactivate old plans
    await db_execute(
        "UPDATE training_plans SET status='archived' WHERE user_id=? AND status='active' AND id != (SELECT MAX(id) FROM training_plans WHERE user_id=?)",
        (user_id, user_id),
    )

    return {"success": True, "plan_data": plan_data, "message": f"已生成 {weeks} 周训练计划"}


@router.post("/plan/complete-day")
async def complete_training_day(request: Request):
    """标记某天训练完成。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    plan_id = body.get("plan_id")
    day_key = body.get("day", "")
    if not plan_id or not day_key:
        raise HTTPException(status_code=400, detail="缺少 plan_id 或 day")

    rows = await db_fetch(
        "SELECT day_progress FROM training_plans WHERE id=? AND user_id=?",
        (plan_id, user_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="计划不存在")

    progress = json.loads(rows[0]["day_progress"] or "{}")
    progress[day_key] = True

    await db_execute(
        "UPDATE training_plans SET day_progress=? WHERE id=?",
        (json.dumps(progress), plan_id),
    )
    return {"success": True, "day": day_key, "progress": progress}


@router.post("/plan/feedback")
async def save_training_feedback(request: Request):
    """V20: 保存训练后反馈（RPE + 难度 + 酸痛）。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    plan_id = body.get("plan_id")
    day_key = body.get("day", "")
    if not plan_id or not day_key:
        raise HTTPException(status_code=400, detail="缺少 plan_id 或 day")

    await db_execute(
        "INSERT OR REPLACE INTO training_feedback "
        "(user_id, plan_id, day_key, rpe, difficulty, soreness, sore_areas, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, plan_id, day_key,
         body.get("rpe"), body.get("difficulty", ""),
         body.get("soreness", ""), json.dumps(body.get("sore_areas", [])),
         body.get("notes", "")),
    )
    return {"success": True, "message": "反馈已保存"}


@router.post("/plan/next-week")
async def generate_next_week_plan(request: Request):
    """V21: 根据上周反馈生成调整后的下周计划。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    # 获取当前活跃计划
    rows = await db_fetch(
        "SELECT * FROM training_plans WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="没有活跃的训练计划")

    plan = rows[0]
    plan_data = json.loads(plan["plan_data"])

    # 获取该计划的所有反馈
    feedback_rows = await db_fetch(
        "SELECT * FROM training_feedback WHERE user_id=? AND plan_id=?",
        (user_id, plan["id"]),
    )

    feedbacks = []
    for fr in feedback_rows:
        feedbacks.append({
            "day_key": fr["day_key"],
            "rpe": fr["rpe"],
            "difficulty": fr["difficulty"],
            "soreness": fr["soreness"],
            "sore_areas": fr["sore_areas"],
            "notes": fr["notes"],
        })

    # 调整计划
    from fitai.analysis.daily_planner import adjust_plan
    adjusted = adjust_plan(plan_data, feedbacks, user_id)

    # 保存新计划
    new_name = f"{plan['name']}（调整版）" if plan["name"] else "调整计划"
    await db_execute(
        "INSERT INTO training_plans (user_id, name, goal, weeks, plan_data) VALUES (?, ?, ?, ?, ?)",
        (user_id, new_name, plan["goal"], plan["weeks"], json.dumps(adjusted, ensure_ascii=False)),
    )
    await db_execute(
        "UPDATE training_plans SET status='archived' WHERE user_id=? AND status='active' AND id != (SELECT MAX(id) FROM training_plans WHERE user_id=?)",
        (user_id, user_id),
    )

    return {
        "success": True,
        "plan_data": adjusted,
        "feedback_count": len(feedbacks),
        "message": "已根据你的训练反馈生成调整后的新计划",
    }


@router.get("/plan")
async def get_training_plan(request: Request):
    """获取当前活跃的训练计划（V20：含 streak + missed_days）。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    rows = await db_fetch(
        "SELECT * FROM training_plans WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    if not rows:
        return {"plan": None, "message": "还没有训练计划"}
    r = rows[0]
    progress = json.loads(r["day_progress"])

    # V20: 计算 streak 和 missed_days
    from datetime import date as dt_date, timedelta
    today = dt_date.today()
    today_idx = (today.weekday()) % 7  # Monday=0
    plan_created = r["created_at"][:10] if r["created_at"] else str(today)

    # Count consecutive completed days backward from today
    streak = 0
    for offset in range(7):
        check_date = today - timedelta(days=offset)
        if str(check_date) < plan_created:
            break
        check_idx = check_date.weekday()
        day_key = f"day-{check_idx + 1}"
        if progress.get(day_key):
            streak += 1
        else:
            break

    # Count missed days (training days that weren't completed)
    missed_days = 0
    plan_data = json.loads(r["plan_data"])
    for day in plan_data.get("days", []):
        day_num = day.get("day", 0)
        if not day.get("is_rest") and not progress.get(f"day-{day_num}"):
            # Check if this day has already passed
            plan_start = plan_created
            day_date = (dt_date.today() - timedelta(days=today_idx - (day_num - 1)))
            if str(day_date) <= str(today) and str(day_date) >= plan_start:
                missed_days += 1

    return {
        "plan": {
            "id": r["id"], "name": r["name"], "goal": r["goal"],
            "weeks": r["weeks"], "status": r["status"],
            "plan_data": plan_data,
            "day_progress": progress,
            "created_at": r["created_at"],
        },
        "streak": streak,
        "missed_days": missed_days,
    }


@router.post("/onboarding/quick-start")
async def quick_start(request: Request):
    """V18: 3 问冷启动 → 即时生成 7 天训练计划。"""
    import traceback
    try:
        user_id = await get_user_id(request)
        if user_id is None:
            raise HTTPException(status_code=401, detail="请先登录")
        try:
            body = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        goal = body.get("goal", "更健康")
        frequency = min(max(int(body.get("frequency", 3)), 2), 5)
        pain_point = body.get("pain_point", "不知道练什么")
        age_group = body.get("age_group", "unknown")
        # V34: 装备、经验、时长
        equipment = body.get("equipment", "")
        experience_level = body.get("experience_level", "")
        time_per_session = body.get("time_per_session", "")

        # Map age_group → coach_style + estimated birth_year
        AGE_STYLE_MAP = {
            "under20": ("friend", 2010),
            "20-30": ("friend", 2000),
            "30-45": ("coach", 1988),
            "45plus": ("family", 1965),
            "unknown": ("coach", None),
        }
        coach_style, est_birth_year = AGE_STYLE_MAP.get(age_group, ("coach", None))

        from fitai.analysis.daily_planner import generate_daily_plan
        plan_data = generate_daily_plan(
            goal=goal, frequency=frequency, pain_point=pain_point,
            equipment=equipment, experience_level=experience_level,
            time_per_session=time_per_session,
            ttm_stage=body.get("ttm_stage", ""),
            motivation_types=body.get("motivation_types", ""),
            self_efficacy=int(body.get("self_efficacy", 0) or 0),
            implementation_intent=body.get("implementation_intent", ""),
            has_autonomous_motivation=body.get("has_autonomous_motivation", True),
        )

        # Save to training_plans table with day-level plan
        await db_execute(
            "INSERT INTO training_plans (user_id, name, goal, weeks, plan_data) VALUES (?, ?, ?, ?, ?)",
            (user_id, f"{goal}·7天计划", goal, 1, json.dumps(plan_data, ensure_ascii=False)),
        )
        # Archive old plans
        await db_execute(
            "UPDATE training_plans SET status='archived' WHERE user_id=? AND status='active' AND id != (SELECT MAX(id) FROM training_plans WHERE user_id=?)",
            (user_id, user_id),
        )

        # Update user_profile with goal, coach_style, and birth_year from onboarding
        profile_rows = await db_fetch(
            "SELECT fitness_goal, coach_style FROM user_profile WHERE user_id=?", (user_id,)
        )
        existing_goal = profile_rows[0]["fitness_goal"] if profile_rows else ""
        existing_coach = profile_rows[0]["coach_style"] if profile_rows else ""
        new_goal = existing_goal or goal
        new_coach = existing_coach or coach_style
        await db_execute(
            "INSERT OR REPLACE INTO user_profile (user_id, fitness_goal, coach_style, birth_year, equipment, experience_level, time_per_session) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, new_goal, new_coach, est_birth_year, equipment, experience_level, time_per_session),
        )

        return {"success": True, "plan": plan_data}
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"{type(e).__name__}: {str(e)}", "traceback": traceback.format_exc()[-500:]},
        )


@router.post("/status-check")
async def save_status_check(request: Request):
    """V29: 保存用户当日训练状态反馈（有精神/一般/有点累）。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    status = body.get("status", "normal")
    if status not in ("energetic", "normal", "tired"):
        raise HTTPException(status_code=400, detail="status must be energetic/normal/tired")

    from datetime import date as dt_date
    today = str(dt_date.today())
    await db_execute(
        "INSERT OR REPLACE INTO training_feedback "
        "(user_id, plan_id, day_key, notes) VALUES (?, 0, ?, ?)",
        (user_id, today, json.dumps({"status_check": status})),
    )
    return {"success": True, "status": status}
