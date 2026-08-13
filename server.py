# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitAI Web — 轻量多用户智能健身助手"""
import asyncio
import json
import mimetypes
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from loguru import logger

from config import FITAI_HOST, FITAI_PORT, CORS_ORIGINS
from database import init_db
from tools.fitai_database import init_db as init_fitai_db, get_user_profile_summary, get_user_profile
from tools.registry import ToolRegistry
from tools.agent_prompts import build_system_prompt
from auth.middleware import (
    RemoteAuthMiddleware, _ensure_setup_secret, _clear_setup_secret,
    _is_local, _has_valid_setup_secret,
)
from auth.utils import count_users
from providers.factory import create_provider

PROJECT_ROOT = Path(__file__).parent.resolve()
STATIC_DIR = PROJECT_ROOT / "static"


from core.dependencies import validate_days as _validate_days, get_user_id as _get_user_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    init_fitai_db()
    print(f"Database initialized at {PROJECT_ROOT / 'data' / 'fitai.db'}")

    # 启动后台导入 worker
    import threading as _thr
    from routers.import_data import start_import_worker
    _thr.Thread(target=start_import_worker, daemon=True).start()
    print("Import worker started")

    user_count = await count_users()
    if user_count > 0:
        _clear_setup_secret(app)
    else:
        secret = _ensure_setup_secret(app)
        print(f"\n{'='*60}")
        print(f"  首次初始化入口：/setup/{secret}")
        print(f"  本地访问: http://localhost:{FITAI_PORT}")
        print(f"{'='*60}\n")
        try:
            (PROJECT_ROOT / "data" / ".setup_url").write_text(f"Setup URL: /setup/{secret}\n")
        except Exception as e:
            logger.warning(f"Failed to write setup URL: {e}")

    yield


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

# Request ID middleware（追踪请求链路）
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    import uuid as _uuid
    request_id = request.headers.get("X-Request-ID", str(_uuid.uuid4())[:8])
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# Security headers middleware
@app.middleware("http")
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

# Structured HTTP request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    rid = getattr(request.state, "request_id", "-")
    logger.info("{method} {path} {status} {duration:.0f}ms rid={rid}",
                method=request.method, path=request.url.path,
                status=response.status_code, duration=duration, rid=rid)
    return response

# Enhanced health check with DB + cache stats
@app.get("/api/health")
async def health_check():
    db_ok = False
    try:
        from tools.fitai_database import get_db
        conn = get_db()
        conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "7.0",
        "database": "connected" if db_ok else "error",
        "cache_size": len(_cache),
        "setup_completed": (await count_users()) > 0,
    }

# System self-check endpoint
@app.get("/api/self-check")
async def self_check(request: Request):
    import sys
    try:
        import openai
        sdk_version = openai.__version__
    except Exception:
        sdk_version = "unknown"

    from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

    # 1. DB check
    db_ok = False
    db_error = ""
    try:
        from tools.fitai_database import get_db
        conn = get_db()
        conn.execute("SELECT 1")
        db_ok = True
    except Exception as e:
        db_error = str(e)[:200]

    # 2. LLM API check
    llm_ok = False
    llm_error = ""
    llm_first_byte_s = None
    try:
        from providers.factory import create_provider
        p = create_provider(
            api_key=LLM_API_KEY or None,
            api_base=LLM_BASE_URL or None,
            default_model=LLM_MODEL,
            provider_id=LLM_PROVIDER,
            thinking_enabled=False,
        )
        t0 = time.time()
        async for chunk in p.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model=LLM_MODEL,
            max_tokens=32,
        ):
            if chunk.content and llm_first_byte_s is None:
                llm_first_byte_s = round(time.time() - t0, 2)
            if chunk.is_error:
                llm_error = (chunk.raw_error or chunk.error or "")[:200]
                break
            if chunk.content:
                llm_ok = True
                break
        if not llm_ok and not llm_error:
            llm_error = "LLM returned no content"
    except Exception as e:
        llm_error = str(e)[:200]

    return {
        "status": "ok" if (db_ok and llm_ok) else "degraded",
        "python": sys.version.split()[0],
        "openai_sdk": sdk_version,
        "database": "connected" if db_ok else f"error: {db_error}",
        "llm": {
            "provider": LLM_PROVIDER,
            "model": LLM_MODEL,
            "base_url": LLM_BASE_URL or "(default)",
            "api_key_configured": bool(LLM_API_KEY and LLM_API_KEY.startswith("sk-")),
            "connected": llm_ok,
            "first_byte_s": llm_first_byte_s,
            "error": llm_error if not llm_ok else "",
        },
    }

# Auth routes
from auth.router import router as auth_router
app.include_router(auth_router)

@app.post("/api/chat")
async def chat(request: Request):
    try:
        body = await request.json()
        message = body.get("message", "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="消息不能为空")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    user_id = getattr(request.state, "user_id", 1)
    username = getattr(request.state, "username", "user")

    # Get user profile for system prompt personalization
    profile_text = get_user_profile_summary(user_id)
    profile = get_user_profile(user_id)
    coach_style = (profile.get('coach_style') or 'friend') if profile else 'friend'
    system_prompt = build_system_prompt(profile_text, get_reply_style(), coach_style)

    # Create provider
    from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    provider = create_provider(
        api_key=LLM_API_KEY or None,
        api_base=LLM_BASE_URL or None,
        default_model=LLM_MODEL,
        provider_id=LLM_PROVIDER,
    )

    # Create tool registry for this user
    tools = ToolRegistry(user_id=user_id)

    from agent.loop import AgentLoop
    agent = AgentLoop(
        provider=provider,
        tools=tools,
        model=LLM_MODEL,
        max_iterations=8,
    )

    async def event_stream():
        assistant_content = ""
        try:
            yield f"event: start\ndata: {json.dumps({'message_id': uuid.uuid4().hex[:8]})}\n\n"

            async for chunk in agent.process_message(
                message=message,
                system_prompt=system_prompt,
                channel="web",
            ):
                from agent.loop import AgentEvent
                if isinstance(chunk, AgentEvent):
                    continue
                if chunk.startswith("LLM_"):
                    code, _, msg = chunk.partition(": ")
                    yield f"event: error\ndata: {json.dumps({'error': msg, 'code': code})}\n\n"
                    return
                assistant_content += chunk
                yield f"event: message\ndata: {json.dumps({'content': chunk})}\n\n"

            # Save to chat history
            from tools.fitai_database import save_chat_message
            session_id = body.get("session_id", uuid.uuid4().hex[:12])
            save_chat_message(user_id, session_id, "user", message)
            save_chat_message(user_id, session_id, "assistant", assistant_content)

            yield f"event: done\ndata: {json.dumps({'content': assistant_content})}\n\n"

        except Exception as e:
            logger.exception("Chat SSE error")
            yield f"event: error\ndata: {json.dumps({'error': '服务器内部错误，请稍后重试', 'code': 'SERVER_ERROR'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/chat/sessions")
async def list_sessions(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return {"sessions": []}
    from tools.fitai_database import list_chat_sessions
    return {"sessions": list_chat_sessions(user_id)}


@app.get("/api/chat/sessions/{session_id}")
async def get_session_messages(session_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401)
    from tools.fitai_database import get_chat_history
    return {"messages": get_chat_history(user_id, session_id)}


@app.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401)
    from tools.fitai_database import delete_chat_session
    delete_chat_session(user_id, session_id)
    return {"success": True}


# ── WebSocket Chat ──────────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    # Authenticate before accepting the WebSocket connection
    # Support both cookie (web) and query param (mini-program)
    token = websocket.cookies.get("fitai_token") or websocket.query_params.get("token") or ""
    user_id = None
    username = "anonymous"
    if token:
        from auth.utils import validate_session
        session_info = await validate_session(token)
        if session_info:
            username, user_id = session_info
    if user_id is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()

    profile_text = get_user_profile_summary(user_id)
    profile = get_user_profile(user_id)
    coach_style = (profile.get('coach_style') or 'friend') if profile else 'friend'
    system_prompt = build_system_prompt(profile_text, get_reply_style(), coach_style)
    current_model = None
    history = []  # conversation context (last 10 rounds)

    # Rate limiting: max 10 messages per minute per connection
    _ws_msg_times = []

    try:
        import asyncio as _asyncio
        while True:
            try:
                data = await _asyncio.wait_for(websocket.receive_json(), timeout=120)
            except _asyncio.TimeoutError:
                await websocket.send_json({"type": "error", "content": "连接超时"})
                break
            # V17: heartbeat — reply to client pings
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            # Handle pong response (clear client-side timeout)
            if data.get("type") == "pong":
                continue

            # V21: Real-time pose rep analysis
            if data.get("type") == "pose_rep":
                rep = data.get("data", {})
                if not hasattr(websocket, "_pose_reps"):
                    websocket._pose_reps = []
                websocket._pose_reps.append(rep)
                if len(websocket._pose_reps) > 15:
                    websocket._pose_reps.pop(0)

                # Quick trend check on recent reps
                recent = websocket._pose_reps[-6:]
                if len(recent) >= 3:
                    qualities = [r.get("quality", 50) for r in recent]
                    # 3+ consecutive quality drops → alert
                    drops = sum(1 for i in range(1, len(qualities)) if qualities[i] < qualities[i-1])
                    if drops >= len(qualities) - 1 and qualities[-1] < qualities[0] - 10:
                        await websocket.send_json({
                            "type": "pose_insight",
                            "data": {
                                "alert": "quality_decline",
                                "message": "动作质量持续下降，建议休息30秒",
                                "quality_trend": [qualities[0], qualities[-1]],
                            }
                        })

                    # Specific metric check: knee valgus increasing
                    valgus_vals = [r.get("kneeValgus_max", 0) for r in recent if r.get("kneeValgus_max")]
                    if len(valgus_vals) >= 3:
                        v_drops = sum(1 for i in range(1, len(valgus_vals)) if valgus_vals[i] > valgus_vals[i-1])
                        if v_drops >= len(valgus_vals) - 1 and valgus_vals[-1] > 6:
                            await websocket.send_json({
                                "type": "pose_insight",
                                "data": {
                                    "alert": "valgus_worsening",
                                    "message": "膝盖内扣趋势加重，注意主动用臀肌推动膝盖向外",
                                }
                            })
                continue

            message = (data.get("content") or data.get("message") or "").strip()
            image_base64 = data.get("image", "")
            # For image messages, allow empty text
            if not message and not image_base64:
                await websocket.send_json({"type": "error", "content": "消息不能为空"})
                continue
            if not message and image_base64:
                message = "这是什么食物？帮我分析营养成分"

            # Rate limit check
            now = time.time()
            _ws_msg_times[:] = [t for t in _ws_msg_times if now - t < 60]
            if len(_ws_msg_times) >= 10:
                await websocket.send_json({"type": "error", "content": "消息太频繁，请稍后再试"})
                continue
            _ws_msg_times.append(now)

            # Dual-mode: deepthink (pro+thinking) vs quick (flash, no thinking)
            mode = data.get("model", "")  # "deepseek-v4-pro" or "deepseek-v4-flash"
            use_pro = (mode == "deepseek-v4-pro" or mode == "pro")
            selected_model = "deepseek-v4-pro" if use_pro else "deepseek-v4-flash"
            thinking = use_pro

            from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL
            if selected_model != current_model:
                current_model = selected_model
                provider = create_provider(api_key=LLM_API_KEY or None, api_base=LLM_BASE_URL or None, default_model=selected_model, provider_id=LLM_PROVIDER, thinking_enabled=thinking)
                tools = ToolRegistry(user_id=user_id)
                from agent.loop import AgentLoop
                agent = AgentLoop(provider=provider, tools=tools, model=selected_model, max_iterations=8)

            session_id = data.get("session_id", uuid.uuid4().hex[:12])
            from tools.fitai_database import save_chat_message
            save_chat_message(user_id, session_id, "user", message)

            assistant_content = ""

            # Build user message — for food photos, pre-analyze with vision model
            user_msg = message
            if image_base64:
                from config import LLM_VISION_PROVIDER, LLM_VISION_API_KEY, LLM_VISION_BASE_URL, LLM_VISION_MODEL

                if LLM_VISION_PROVIDER and LLM_VISION_MODEL and LLM_VISION_API_KEY:
                    try:
                        vision_provider = create_provider(
                            api_key=LLM_VISION_API_KEY,
                            api_base=LLM_VISION_BASE_URL or None,
                            default_model=LLM_VISION_MODEL,
                            provider_id=LLM_VISION_PROVIDER,
                            thinking_enabled=False,
                        )
                        vision_result = ""
                        async for chunk in vision_provider.chat_stream(
                            messages=[{"role": "user", "content": [
                                {"type": "text", "text": "请详细描述这张食物照片中的食物种类、分量，并估算热量（千卡）、蛋白质（g）、碳水（g）、脂肪（g）。直接给出数据，不需要额外解释。"},
                                {"type": "image_url", "image_url": {"url": image_base64}},
                            ]}],
                            model=LLM_VISION_MODEL,
                            max_tokens=1024,
                        ):
                            if chunk.is_error:
                                logger.warning(f"Vision API error: {chunk.error}")
                                break
                            if chunk.content:
                                vision_result += chunk.content
                        if vision_result:
                            user_msg = f"[用户上传了食物照片，已由视觉模型分析：{vision_result}]\n\n用户说：{message}\n\n请直接根据分析结果展示食物营养成分并询问用户是否需要保存这餐记录，不要再调用 analyze_food_photo 工具。"
                        else:
                            logger.warning("Vision API returned empty result, falling back")
                            user_msg = message + "\n[用户上传了一张食物照片，可以使用 analyze_food_photo 工具识别]"
                    except Exception as e:
                        logger.exception(f"Vision model failed: {e}")
                        user_msg = message + "\n[用户上传了一张食物照片，可以使用 analyze_food_photo 工具识别]"
                else:
                    user_msg = message + "\n[用户上传了一张食物照片，可以使用 analyze_food_photo 工具识别]"

            logger.info(f"WS query from {username}: model={selected_model} thinking={thinking} msg_len={len(message)} — \"{message[:60]}\"")
            chunk_count = 0
            step_count = 0
            text_chunk_count = 0
            from agent.loop import AgentEvent
            try:
                async for chunk in agent.process_message(message=user_msg, system_prompt=system_prompt, context=history, channel="web"):
                    chunk_count += 1
                    if isinstance(chunk, AgentEvent):
                        step_count += 1
                        if chunk.type == "plan_card":
                            await websocket.send_json({
                                "type": "plan_card",
                                "action": chunk.content or "propose",
                                "plan": chunk.plan or {},
                            })
                        else:
                            await websocket.send_json({
                                "type": chunk.type,
                                "content": chunk.content,
                                "step": chunk.step,
                                "func_name": chunk.func_name if chunk.func_name else "",
                                "args": chunk.args if chunk.args else {},
                                "action_type": "call" if chunk.type == "action" else "",
                            })
                    elif chunk.startswith("LLM_"):
                        code, _, msg = chunk.partition(": ")
                        await websocket.send_json({"type": "error", "content": msg})
                        break
                    else:
                        text_chunk_count += 1
                        assistant_content += chunk
                        await websocket.send_json({"type": "chunk", "content": chunk})
            except Exception as e:
                logger.exception(f"WS agent.process_message crashed: {e}")
                await websocket.send_json({"type": "error", "content": f"AI引擎出错: {str(e)[:100]}"})
            logger.info(f"WS loop done: total_chunks={chunk_count}, steps={step_count}, text={text_chunk_count}")
            if text_chunk_count == 0 and not assistant_content:
                logger.warning(f"WS empty response: model={selected_model} thinking={thinking} msg=\"{message[:80]}\"")

            if assistant_content:
                save_chat_message(user_id, session_id, "assistant", assistant_content)
                # Maintain conversation context (last 10 rounds)
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": assistant_content})
                if len(history) > 20:
                    history = history[-20:]

            await websocket.send_json({"type": "finish", "answer": assistant_content, "content": assistant_content, "steps": []})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            logger.exception("WebSocket error")
            await websocket.send_json({"type": "error", "content": "服务器内部错误"})
        except Exception as e2:
            logger.error(f"Error sending WS error: {e2}")


# LLM Test
@app.get("/api/llm-test")
async def llm_test(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "请先登录", "code": "AUTH_REQUIRED"}, status_code=401)
    from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    result = {"provider": LLM_PROVIDER, "model": LLM_MODEL, "api_key_configured": bool(LLM_API_KEY and LLM_API_KEY != "your-api-key-here")}
    if not result["api_key_configured"]:
        result["status"] = "error"; result["message"] = "API Key not configured"; return result
    provider = create_provider(api_key=LLM_API_KEY or None, api_base=LLM_BASE_URL or None, default_model=LLM_MODEL, provider_id=LLM_PROVIDER)
    chunks_received = 0
    try:
        async for chunk in provider.chat_stream(messages=[{"role": "user", "content": "say hi in one word"}], model=LLM_MODEL, max_tokens=50):
            chunks_received += 1
            if chunk.is_error:
                result["status"] = "error"; result["message"] = f"chunk #{chunks_received}: {chunk.raw_error or chunk.error}"; return result
            if chunk.content:
                result["status"] = "ok"; result["response"] = chunk.content; result["chunks"] = chunks_received
                return result
            if chunk.is_done:
                result["status"] = "ok"; result["response"] = f"(done after {chunks_received} chunks)"
                return result
        result["status"] = "ok"; result["response"] = f"(stream ended after {chunks_received} chunks)"
    except Exception as e:
        result["status"] = "error"; result["message"] = f"{type(e).__name__}: {e} (chunks: {chunks_received})"
    return result


@app.get("/api/chat-debug")
async def chat_debug(request: Request, message: str = "你好"):
    """SSE 流式测试：完整 AgentLoop + 系统提示词 + 工具（需登录）"""
    user_id = await get_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "请先登录", "code": "AUTH_REQUIRED"}, status_code=401)
    async def event_stream():
        try:
            from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
            from tools.agent_prompts import build_system_prompt
            from tools.registry import ToolRegistry
            from agent.loop import AgentLoop

            yield f"event: info\ndata: {{\"provider\":\"{LLM_PROVIDER}\",\"model\":\"{LLM_MODEL}\"}}\n\n"

            provider = create_provider(api_key=LLM_API_KEY or None, api_base=LLM_BASE_URL or None, default_model=LLM_MODEL, provider_id=LLM_PROVIDER, thinking_enabled=True)
            tools = ToolRegistry(user_id=1)
            system_prompt = build_system_prompt("")
            yield f"event: info\ndata: {{\"tools\":{len(tools.get_definitions())},\"prompt_len\":{len(system_prompt)}}}\n\n"

            agent = AgentLoop(provider=provider, tools=tools, model=LLM_MODEL, max_iterations=5)
            yield "event: start\ndata: {}\n\n"

            response = []
            async for chunk in agent.process_message(message=message, system_prompt=system_prompt[:500] if len(system_prompt) > 500 else system_prompt):
                response.append(chunk)
                if chunk.startswith("LLM_"):
                    code, _, msg = chunk.partition(": ")
                    yield f"event: error\ndata: {{\"code\":\"{code}\",\"message\":\"{msg}\"}}\n\n"
                    return
                yield f"event: chunk\ndata: {{\"text\":{json.dumps(chunk[:200])}}}\n\n"
            yield f"event: done\ndata: {{\"total_chunks\":{len(response)},\"full\":{json.dumps(''.join(response)[:500])}}}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {{\"message\":\"{type(e).__name__}: {e}\"}}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})



# ── FitAI Dashboard / Health API ────────────────────────────────

from routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)


# ── 内存缓存 + 异步SQL（提取至 core/ 模块）──
from core.cache import default_cache as _cache
from core.db_utils import db_fetch as _db_fetch


from core.config_state import get_model, get_reply_style
from routers.settings import router as settings_router
app.include_router(settings_router)
from routers.health_data import router as health_data_router
app.include_router(health_data_router)


from routers.import_data import router as import_router
app.include_router(import_router)

from routers.weekly import router as weekly_router
app.include_router(weekly_router)





# ── Diagnostics ──────────────────────────────────────────────────

from routers.diagnostics import router as diagnostics_router
app.include_router(diagnostics_router)


# ── Exercise Library (V7) ───────────────────────────────────────

from routers.exercises import router as exercises_router
app.include_router(exercises_router)


from routers.videos import router as videos_router
app.include_router(videos_router)


from routers.profile import router as profile_router
app.include_router(profile_router)

from routers.insights import router as insights_router
app.include_router(insights_router)
from routers.training import router as training_router
app.include_router(training_router)
from routers.billing import router as billing_router
app.include_router(billing_router)
from routers.pose_analysis import router as pose_analysis_router
app.include_router(pose_analysis_router)


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