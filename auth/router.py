# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""认证 API 端点：状态、设置、注册、登录、注销、改密、用户管理、微信登录"""
import asyncio
import secrets
import threading
import time
from typing import Dict

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth.middleware import _is_local, _ensure_setup_secret, _clear_setup_secret, _has_valid_setup_secret, AUTH_COOKIE_NAME
from auth.utils import (
    TOKEN_EXPIRY, count_users, create_session, create_user, delete_user_by_id,
    get_all_users, get_user_by_username, hash_password, is_registration_allowed,
    revoke_all_sessions, revoke_session, set_user_admin, set_registration_allowed,
    validate_password, validate_session, validate_username, verify_password,
)
from config import FITAI_HOST, WECHAT_APPID, WECHAT_SECRET

router = APIRouter(prefix="/api/auth", tags=["auth"])

_RATE_WINDOW = 15 * 60
_RATE_MAX = 5
_RATE_LOCKOUT = 15 * 60
_auth_lock = threading.Lock()
_auth_attempts: Dict[str, list[float]] = {}
_auth_lockouts: Dict[str, float] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class SetPasswordRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ToggleAdminRequest(BaseModel):
    is_admin: bool


class SetRegistrationRequest(BaseModel):
    allowed: bool


class WeChatLoginRequest(BaseModel):
    code: str


class WeChatBindRequest(BaseModel):
    code: str


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def _rate_key(action: str, request: Request, username: str = "") -> str:
    return f"{action}:{_client_ip(request)}:{username.strip().lower()}"


def _check_rate(action: str, request: Request, username: str = "") -> tuple[bool, int]:
    key = _rate_key(action, request, username)
    now = time.time()
    with _auth_lock:
        for k in list(_auth_attempts):
            _auth_attempts[k] = [ts for ts in _auth_attempts[k] if ts >= now - _RATE_WINDOW]
            if not _auth_attempts[k]:
                del _auth_attempts[k]
        for k, v in list(_auth_lockouts.items()):
            if v <= now:
                del _auth_lockouts[k]
        if key in _auth_lockouts and _auth_lockouts[key] > now:
            return False, max(1, int(_auth_lockouts[key] - now))
    return True, 0


def _record_failure(action: str, request: Request, username: str = "") -> None:
    key = _rate_key(action, request, username)
    now = time.time()
    with _auth_lock:
        _auth_attempts.setdefault(key, []).append(now)
        if len([ts for ts in _auth_attempts[key] if ts >= now - _RATE_WINDOW]) >= _RATE_MAX:
            _auth_lockouts[key] = now + _RATE_LOCKOUT


def _clear_failure(action: str, request: Request, username: str = "") -> None:
    key = _rate_key(action, request, username)
    with _auth_lock:
        _auth_attempts.pop(key, None)
        _auth_lockouts.pop(key, None)


def _set_cookie(response: JSONResponse, token: str, request: Request) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME, value=token, httponly=True, samesite="lax",
        secure=True, max_age=TOKEN_EXPIRY, path="/",
    )


def _get_token(request: Request) -> str | None:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token or None


def _require_admin(request: Request):
    if not getattr(request.state, 'is_admin', False):
        raise HTTPException(status_code=403, detail="需要管理员权限")


# ── WeChat Login ──────────────────────────────────────────────────

async def _wechat_code2session(code: str) -> dict | None:
    """Exchange wx.login() code for openid and session_key via WeChat API.

    开发工具中 wx.login 返回 mock code，直接用它当 openid 创建测试账号。
    """
    if not WECHAT_APPID or not WECHAT_SECRET:
        return None

    # 微信开发者工具返回的 code 以 "the code is a mock one" 开头
    # 直接用 code 的 hash 当 openid，跳过真实 API 调用
    if code.startswith("the code"):
        import hashlib
        mock_openid = "dev_" + hashlib.md5(code.encode()).hexdigest()[:16]
        return {"openid": mock_openid, "session_key": "dev_session_key"}

    url = (
        f"https://api.weixin.qq.com/sns/jscode2session"
        f"?appid={WECHAT_APPID}&secret={WECHAT_SECRET}&js_code={code}&grant_type=authorization_code"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
            if "errcode" in data and data["errcode"] != 0:
                return None
            return data
    except Exception:
        return None


async def _get_or_create_wechat_user(openid: str) -> tuple[int, str]:
    """Find existing user by WeChat openid, or create a new one."""
    from database import AsyncSessionLocal
    from models.user import User as UserModel

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(UserModel).where(UserModel.wechat_openid == openid)
        )
        user = result.scalar_one_or_none()
        if user:
            return user.id, user.username

    username = f"wx_{openid[-12:]}"
    user_count = await count_users()
    is_first = user_count == 0
    success, msg, user_info = await create_user(username, secrets.token_urlsafe(32), is_admin=is_first)
    if not success:
        username = f"wx_{secrets.token_hex(6)}"
        success, msg, user_info = await create_user(username, secrets.token_urlsafe(32), is_admin=is_first)

    async with AsyncSessionLocal() as session:
        from sqlalchemy import update
        await session.execute(
            update(UserModel).where(UserModel.id == user_info["id"]).values(wechat_openid=openid)
        )
        await session.commit()

    return user_info["id"], username


@router.post("/wechat-login")
async def wechat_login(data: WeChatLoginRequest, request: Request):
    """微信小程序一键登录：用 wx.login() code 换取 session token。"""
    try:
        session_data = await _wechat_code2session(data.code)
        if not session_data:
            return JSONResponse(status_code=401, content={"detail": "微信登录失败，请重试"})

        openid = session_data.get("openid")
        if not openid:
            return JSONResponse(status_code=401, content={"detail": "无法获取微信用户标识"})

        user_id, username = await _get_or_create_wechat_user(openid)

        # V20: store session_key for WeRunData decryption
        session_key = session_data.get("session_key", "")
        if session_key:
            from tools.fitai_database import save_wechat_session_key
            await asyncio.to_thread(save_wechat_session_key, user_id, session_key)

        token = await create_session(username, user_id)
        response = JSONResponse(content={
            "success": True, "message": "微信登录成功",
            "token": token,
            "user": {"id": user_id, "username": username}
        })
        _set_cookie(response, token, request)
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": f"服务器内部错误: {str(e)}"})


@router.post("/wechat-bind")
async def wechat_bind(data: WeChatBindRequest, request: Request):
    """将微信账号绑定到当前已登录用户。"""
    token = _get_token(request)
    session_info = await validate_session(token) if token else None
    if not session_info:
        return JSONResponse(status_code=401, content={"detail": "请先登录"})

    session_data = await _wechat_code2session(data.code)
    if not session_data:
        return JSONResponse(status_code=400, content={"detail": "微信验证失败"})

    openid = session_data.get("openid")
    if not openid:
        return JSONResponse(status_code=400, content={"detail": "无法获取微信用户标识"})

    from database import AsyncSessionLocal
    from models.user import User as UserModel
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(UserModel).where(UserModel.id == session_info[1]).values(wechat_openid=openid)
        )
        await session.commit()

    return {"success": True, "message": "微信账号绑定成功"}


# ── Status ──────────────────────────────────────────────────────

@router.get("/status")
async def auth_status(request: Request):
    is_local = _is_local(request)
    user_count = await count_users()
    auth_enabled = user_count > 0
    token = _get_token(request)
    session_info = await validate_session(token) if token else None
    is_admin = False
    if session_info:
        from auth.utils import get_user_by_id
        user = await get_user_by_id(session_info[1])
        is_admin = user.get("is_admin", False) if user else False
    return {
        "is_local": is_local,
        "auth_enabled": auth_enabled,
        "authenticated": session_info is not None,
        "is_admin": is_admin,
        "remote_access_enabled": FITAI_HOST not in ("127.0.0.1", "localhost"),
        "setup_allowed": not auth_enabled and (is_local or _has_valid_setup_secret(request.app, request.headers.get("x-setup-secret"))),
        "registration_allowed": await is_registration_allowed(),
        "user_count": user_count,
    }


# ── Setup (first admin) ─────────────────────────────────────────

@router.post("/setup")
async def setup_password(data: SetPasswordRequest, request: Request):
    if not _is_local(request) and not _has_valid_setup_secret(request.app, request.headers.get("x-setup-secret")):
        return JSONResponse(status_code=403, content={"detail": "首次初始化只能在本机完成", "code": "SETUP_LOCAL_ONLY"})

    allowed, retry = _check_rate("setup", request, data.username)
    if not allowed:
        return JSONResponse(status_code=429, content={"detail": f"尝试过于频繁，请 {retry} 秒后再试"})

    user_count = await count_users()
    if user_count > 0:
        return JSONResponse(status_code=400, content={"detail": "已存在用户账号，请使用注册或登录接口"})

    success, message, user_info = await create_user(data.username.strip(), data.password, is_admin=True)
    if not success:
        _record_failure("setup", request, data.username)
        return JSONResponse(status_code=400, content={"detail": message})

    _clear_setup_secret(request.app)
    _clear_failure("setup", request, data.username)
    token = await create_session(data.username.strip(), user_info["id"])
    response = JSONResponse(content={"success": True, "message": "管理员账号创建成功"})
    _set_cookie(response, token, request)
    return response


# ── Register ────────────────────────────────────────────────────

@router.post("/register")
async def register(data: RegisterRequest, request: Request):
    user_count = await count_users()
    if user_count > 0 and not await is_registration_allowed():
        return JSONResponse(status_code=403, content={"detail": "管理员已关闭公开注册", "code": "REGISTRATION_CLOSED"})

    allowed, retry = _check_rate("register", request, data.username)
    if not allowed:
        return JSONResponse(status_code=429, content={"detail": f"尝试过于频繁，请 {retry} 秒后再试"})

    is_first = user_count == 0
    success, message, user_info = await create_user(data.username.strip(), data.password, data.email, is_admin=is_first)
    if not success:
        _record_failure("register", request, data.username)
        return JSONResponse(status_code=409 if "已存在" in message else 400, content={"detail": message})

    _clear_failure("register", request, data.username)
    token = await create_session(data.username.strip(), user_info["id"])
    response = JSONResponse(content={"success": True, "message": message, "user": user_info})
    _set_cookie(response, token, request)
    return response


# ── Login ───────────────────────────────────────────────────────

@router.post("/login")
async def login(data: LoginRequest, request: Request):
    allowed, retry = _check_rate("login", request, data.username)
    if not allowed:
        return JSONResponse(status_code=429, content={"detail": f"尝试过于频繁，请 {retry} 秒后再试"})

    user_count = await count_users()
    if user_count == 0:
        return JSONResponse(status_code=403, content={"detail": "管理员尚未完成初始化，请先设置账号和密码"})

    normalized = data.username.strip()
    user = await get_user_by_username(normalized)
    if user is None or not verify_password(data.password, user["hashed_password"]):
        _record_failure("login", request, normalized)
        return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})

    _clear_failure("login", request, normalized)
    token = await create_session(user["username"], user["id"])
    response = JSONResponse(content={"success": True, "message": "登录成功",
        "token": token,
        "user": {"id": user["id"], "username": user["username"], "is_admin": user["is_admin"]}})
    _set_cookie(response, token, request)
    return response


# ── Logout ──────────────────────────────────────────────────────

@router.post("/logout")
async def logout(request: Request):
    token = _get_token(request)
    if token:
        await revoke_session(token)
    response = JSONResponse(content={"success": True})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response


# ── Change password ─────────────────────────────────────────────

@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, request: Request):
    token = _get_token(request)
    session_info = await validate_session(token) if token else None
    if not session_info:
        return JSONResponse(status_code=401, content={"detail": "请先登录"})

    username, user_id = session_info
    user = await get_user_by_username(username)
    if user is None or not verify_password(data.old_password, user["hashed_password"]):
        return JSONResponse(status_code=401, content={"detail": "旧密码错误"})

    valid, msg = validate_password(data.new_password)
    if not valid:
        return JSONResponse(status_code=400, content={"detail": msg})

    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        db_user = await session.get(__import__('models.user', fromlist=['User']).User, user_id)
        if db_user:
            db_user.hashed_password = hash_password(data.new_password)
            await session.commit()

    await revoke_all_sessions(user_id=user_id)
    return {"success": True, "message": "密码修改成功，请重新登录"}


# ── User management (admin only) ────────────────────────────────

@router.get("/users")
async def list_users(request: Request):
    _require_admin(request)
    users = await get_all_users()
    return {"users": users, "total": len(users)}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, request: Request):
    _require_admin(request)
    if getattr(request.state, 'user_id', None) == user_id:
        return JSONResponse(status_code=400, content={"detail": "不能删除自己的账号"})
    success = await delete_user_by_id(user_id)
    if not success:
        return JSONResponse(status_code=404, content={"detail": "用户不存在"})
    return {"success": True, "message": "用户已删除"}


@router.put("/users/{user_id}/admin")
async def toggle_admin(user_id: int, data: ToggleAdminRequest, request: Request):
    _require_admin(request)
    if getattr(request.state, 'user_id', None) == user_id and not data.is_admin:
        return JSONResponse(status_code=400, content={"detail": "不能取消自己的管理员权限"})
    success = await set_user_admin(user_id, data.is_admin)
    if not success:
        return JSONResponse(status_code=404, content={"detail": "用户不存在"})
    return {"success": True, "message": "管理员状态已更新"}


@router.put("/registration")
async def set_registration(data: SetRegistrationRequest, request: Request):
    _require_admin(request)
    await set_registration_allowed(data.allowed)
    return {"success": True, "registration_open": data.allowed}
