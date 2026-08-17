# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitAI Web — 轻量多用户智能健身助手"""
import sys
import mimetypes
from pathlib import Path

# 无论从哪个目录启动，都能 import 顶层模块（database/config/auth/...）
sys.path.insert(0, str(Path(__file__).resolve().parent))

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from config import FITAI_HOST, FITAI_PORT, CORS_ORIGINS
from auth.middleware import RemoteAuthMiddleware
from core.lifespan import lifespan
from core.middleware import add_request_id, security_headers, log_requests

PROJECT_ROOT = Path(__file__).parent.resolve()
STATIC_DIR = PROJECT_ROOT / "static"


app = FastAPI(
    title="FitAI-Web — AI Fitness Coach API",
    description="""Open-source AI fitness coaching platform with causal health intelligence.

## Core Capabilities
- **Causal Discovery**: PC-stable algorithm for health indicator causal graphs
- **Bayesian Recovery**: NIG conjugate prior online recovery scoring
- **Anomaly Detection**: Fisher's combined test + BH-FDR probabilistic framework
- **AI Coach Agent**: 22 function-calling tools with streaming ReAct loop
- **Pose Correction**: Real-time MediaPipe pose diagnostics (5 exercises)

## Authentication
Most endpoints require a Bearer token. Obtain one via `POST /api/login`.
On first run, visit the setup URL printed in server logs to create an admin account.
""",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理：返回结构化错误而非 traceback。"""
    from loguru import logger
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"error": "服务器内部错误，请稍后重试", "code": "INTERNAL_ERROR"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()] if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True if CORS_ORIGINS != "*" else False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RemoteAuthMiddleware)

app.middleware("http")(add_request_id)
app.middleware("http")(security_headers)
app.middleware("http")(log_requests)


# ── 集中注册所有 router ──────────────────────────────────────────

from auth.router import router as auth_router
from routers.chat import router as chat_router
from routers.system import router as system_router
from routers.debug import router as debug_router
from routers.ws_chat import router as ws_chat_router
from routers.dashboard import router as dashboard_router
from routers.settings import router as settings_router
from routers.health_data import router as health_data_router
from routers.import_data import router as import_router
from routers.weekly import router as weekly_router
from routers.diagnostics import router as diagnostics_router
from routers.exercises import router as exercises_router
from routers.videos import router as videos_router
from routers.profile import router as profile_router
from routers.insights import router as insights_router
from routers.training import router as training_router
from routers.billing import router as billing_router
from routers.pose_analysis import router as pose_analysis_router
from routers.privacy import router as privacy_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(system_router)
app.include_router(debug_router)
app.include_router(ws_chat_router)
app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(health_data_router)
app.include_router(import_router)
app.include_router(weekly_router)
app.include_router(diagnostics_router)
app.include_router(exercises_router)
app.include_router(videos_router)
app.include_router(profile_router)
app.include_router(insights_router)
app.include_router(training_router)
app.include_router(billing_router)
app.include_router(pose_analysis_router)
app.include_router(privacy_router)


# Static files
if STATIC_DIR.exists():
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @app.get("/")
    async def serve_landing():
        return FileResponse(str(STATIC_DIR / "landing.html"), headers=_NO_CACHE)

    @app.get("/app")
    async def serve_app():
        return FileResponse(str(STATIC_DIR / "index.html"), headers=_NO_CACHE)

    @app.get("/login")
    async def serve_login():
        return FileResponse(str(STATIC_DIR / "login.html"), headers=_NO_CACHE)

    @app.get("/sw.js")
    async def serve_sw():
        return FileResponse(
            str(STATIC_DIR / "sw.js"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    # Catch-all for static files — must be last so /, /app, /login etc. match first
    _MIME_MAP = {".mjs": "application/javascript", ".wasm": "application/wasm"}

    @app.get("/{path:path}")
    async def serve_any(path: str):
        target = STATIC_DIR / path
        if target.is_file():
            try:
                target.relative_to(STATIC_DIR)
            except ValueError:
                return FileResponse(str(STATIC_DIR / "landing.html"))
            media_type = _MIME_MAP.get(target.suffix)
            headers = {}
            if media_type:
                headers["Content-Type"] = media_type
            if target.suffix in (".task", ".wasm", ".mjs"):
                headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return FileResponse(str(target), media_type=media_type, headers=headers)
        return FileResponse(str(STATIC_DIR / "landing.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host=FITAI_HOST, port=FITAI_PORT, reload=True)
