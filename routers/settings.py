# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 模型/回复风格设置路由（从 server.py 提取）。"""
import json
from fastapi import APIRouter, Request, HTTPException
from core.config_state import get_model, set_model, get_reply_style, set_reply_style

router = APIRouter(tags=["settings"])


@router.get("/api/settings/model")
async def api_get_model():
    return {"model": get_model(), "ok": True}


@router.post("/api/settings/model")
async def api_set_model(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    model = body.get("model", "deepseek-v4-flash")
    ok = set_model(model)
    return {"ok": ok, "model": get_model()} if ok else {"ok": False, "error": "invalid model"}


@router.get("/api/settings/reply-style")
async def api_get_reply_style():
    return {"style": get_reply_style()}


@router.post("/api/settings/reply-style")
async def api_set_reply_style(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    style = body.get("style", "casual")
    ok = set_reply_style(style)
    return {"ok": ok, "style": get_reply_style()} if ok else {"ok": False, "error": "invalid style"}
