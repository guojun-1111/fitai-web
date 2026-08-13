# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""远程访问认证中间件"""
import os
import secrets
import string
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from auth.utils import AUTH_COOKIE_NAME, count_users, validate_session, get_user_by_id

SETUP_SECRET_HEADER = "x-setup-secret"
SETUP_SECRET_LENGTH = 8
SETUP_SECRET_ALPHABET = string.ascii_letters
SETUP_SECRET_TTL_DEFAULT = 30

_FORWARDED_HEADERS = {"x-forwarded-for", "x-real-ip", "forwarded"}
_PUBLIC_PATHS = ("/api/auth/", "/api/diagnostics", "/api/exercises/")
_LOCAL_ONLY_SETUP = "/api/auth/setup"


def _is_loopback(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"} if host else False


def _is_local(request: Request) -> bool:
    client_ip = request.client.host if request.client and request.client.host else None
    if not _is_loopback(client_ip):
        return False
    header_keys = {k.lower() for k in request.headers.keys()}
    return not any(h in header_keys for h in _FORWARDED_HEADERS)


def _get_setup_secret(app) -> str | None:
    return getattr(app.state, "remote_setup_secret", None)


def _ensure_setup_secret(app) -> str:
    secret = _get_setup_secret(app)
    expires = getattr(app.state, "remote_setup_secret_expires_at", 0.0)
    if not secret or (expires and time.time() >= expires):
        secret = "".join(secrets.choice(SETUP_SECRET_ALPHABET) for _ in range(SETUP_SECRET_LENGTH))
        ttl = int(os.getenv("REMOTE_SETUP_SECRET_TTL_MINUTES", str(SETUP_SECRET_TTL_DEFAULT)))
        app.state.remote_setup_secret = secret
        app.state.remote_setup_secret_expires_at = time.time() + ttl * 60
    return secret


def _clear_setup_secret(app) -> None:
    app.state.remote_setup_secret = None
    app.state.remote_setup_secret_expires_at = 0.0


def _has_valid_setup_secret(app, candidate: str | None) -> bool:
    secret = _get_setup_secret(app)
    if not secret:
        return False
    expires = getattr(app.state, "remote_setup_secret_expires_at", 0.0)
    if expires and time.time() >= expires:
        _ensure_setup_secret(app)
        return False
    return bool(secret and candidate and secrets.compare_digest(secret, candidate.strip()))


class RemoteAuthMiddleware(BaseHTTPMiddleware):
    """保护非本地 HTTP 请求，需要 cookie 或 Bearer token 认证"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if _is_local(request):
            # 本地请求免认证，但仍填充 user_id 供仪表盘等端点使用
            token = request.cookies.get(AUTH_COOKIE_NAME)
            if token:
                session_info = await validate_session(token)
                if session_info:
                    request.state.username, request.state.user_id = session_info
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        if any(path.startswith(p) for p in _PUBLIC_PATHS):
            if path == _LOCAL_ONLY_SETUP and not _has_valid_setup_secret(request.app, request.headers.get(SETUP_SECRET_HEADER)):
                return JSONResponse(status_code=403, content={"detail": "首次初始化只能在本机完成", "code": "SETUP_LOCAL_ONLY"})
            return await call_next(request)

        user_count = await count_users()
        if user_count == 0:
            return JSONResponse(status_code=401, content={"detail": "Authentication setup required", "code": "AUTH_SETUP_REQUIRED"})

        token = request.cookies.get(AUTH_COOKIE_NAME)
        if not token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        session_info = await validate_session(token) if token else None
        if not session_info:
            return JSONResponse(status_code=401, content={"detail": "请先登录", "code": "AUTH_REQUIRED"})

        username, user_id = session_info
        request.state.username = username
        request.state.user_id = user_id
        user = await get_user_by_id(user_id)
        request.state.is_admin = user.get("is_admin", False) if user else False

        return await call_next(request)
