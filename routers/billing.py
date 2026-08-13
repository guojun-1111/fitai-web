# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V16: 订阅与支付路由。"""
import json
from fastapi import APIRouter, Request, HTTPException
from core.dependencies import get_user_id
from core.db_utils import db_fetch, db_execute

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Plan definitions
PLANS = {
    "free": {"name": "免费版", "price": 0, "features": ["基础健康仪表盘", "手动数据导入", "7天历史"]},
    "pro": {"name": "专业版", "price": 29, "features": ["AI 因果洞察", "无限历史", "设备接入", "训练计划", "数据导出"]},
    "ultimate": {"name": "旗舰版", "price": 59, "features": ["全部专业版功能", "实时心率区间", "自定义训练计划", "优先AI响应", "家庭成员共享"]},
}


@router.get("/status")
async def billing_status(request: Request):
    """获取当前用户的订阅状态。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    rows = await db_fetch(
        "SELECT * FROM subscriptions WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    if not rows:
        # 自动创建免费订阅
        await db_execute(
            "INSERT INTO subscriptions (user_id, plan_type, status) VALUES (?, 'free', 'active')",
            (user_id,),
        )
        sub = {"plan_type": "free", "status": "active"}
    else:
        sub = dict(rows[0])

    return {
        "subscription": sub,
        "plans": PLANS,
    }


@router.post("/subscribe")
async def billing_subscribe(request: Request):
    """创建/升级订阅（支付接口桩）。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    plan_type = body.get("plan_type", "free")
    if plan_type not in PLANS:
        raise HTTPException(status_code=400, detail=f"未知套餐: {plan_type}")

    plan = PLANS[plan_type]
    if plan["price"] > 0:
        # Payment not yet integrated — return payment URL placeholder
        return {
            "success": False,
            "message": "支付功能即将上线，当前可免费使用全部功能",
            "plan": plan,
        }

    # Free plan: activate immediately
    await db_execute(
        "UPDATE subscriptions SET status='cancelled' WHERE user_id=? AND status='active'",
        (user_id,),
    )
    await db_execute(
        "INSERT INTO subscriptions (user_id, plan_type, status) VALUES (?, ?, 'active')",
        (user_id, plan_type),
    )
    return {
        "success": True,
        "plan": plan,
        "message": f"已切换到{plan['name']}",
    }
