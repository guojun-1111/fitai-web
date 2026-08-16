# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""调试端点：LLM 连通性测试 + Agent 流式调试（均需登录）。"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core.dependencies import get_user_id
from providers.factory import create_provider

router = APIRouter(prefix="/api", tags=["debug"])


@router.get("/llm-test")
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


@router.get("/chat-debug")
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
