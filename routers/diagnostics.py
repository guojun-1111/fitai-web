# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 诊断路由（从 server.py 提取）。需登录。"""
from fastapi import APIRouter, Request, HTTPException
from core.dependencies import get_user_id
from diagnostics import run_diagnostics, enable_registration

router = APIRouter(tags=["diagnostics"])


@router.get("/api/diagnostics")
async def diagnostics(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    diag = await run_diagnostics()
    # 脱敏：去掉敏感字段
    if "checks" in diag:
        for k in list(diag["checks"].keys()):
            v = diag["checks"][k]
            if v.get("status") == "ok":
                diag["checks"][k] = {"status": "ok"}
            else:
                diag["checks"][k] = {"status": v.get("status", "fail")}
    return diag


@router.get("/api/diagnostics/fix-registration")
async def fix_registration(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    # 只有管理员可以操作
    from database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("SELECT is_admin FROM users WHERE id=:uid"), {"uid": user_id})
        row = r.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=403, detail="需要管理员权限")
    return await enable_registration()
