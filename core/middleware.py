# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""HTTP 中间件：请求 ID、安全响应头、结构化请求日志。"""
import time

from fastapi import Request
from loguru import logger


async def add_request_id(request: Request, call_next):
    import uuid as _uuid
    request_id = request.headers.get("X-Request-ID", str(_uuid.uuid4())[:8])
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' ws: wss: blob:; "
        "worker-src 'self' blob:"
    )
    return response


async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    rid = getattr(request.state, "request_id", "-")
    logger.info("{method} {path} {status} {duration:.0f}ms rid={rid}",
                method=request.method, path=request.url.path,
                status=response.status_code, duration=duration, rid=rid)
    return response
