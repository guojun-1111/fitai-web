# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: FastAPI 共享依赖（从 server.py 提取，供各 router 使用）。"""
from fastapi import Request, HTTPException


def validate_days(days: int, max_days: int = 365) -> int:
    """校验并钳制 days 参数。"""
    if days < 1:
        raise HTTPException(status_code=422, detail="days must be positive")
    if days > max_days:
        return max_days
    return days


async def get_user_id(request: Request):
    """从 request.state 取 user_id，若未设置则从 cookie 回退解析。

    处理 /api/health 等路径中间件跳过认证的情况。
    """
    uid = getattr(request.state, "user_id", None)
    if uid is not None:
        return uid
    from auth.utils import AUTH_COOKIE_NAME, validate_session
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        info = await validate_session(token)
        if info:
            return info[1]
    return None
