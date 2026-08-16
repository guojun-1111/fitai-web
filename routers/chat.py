# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""聊天路由：SSE 流式对话 + 会话管理。"""
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from core.config_state import get_reply_style
from tools.fitai_database import (
    get_user_profile, get_user_profile_summary,
    save_chat_message, list_chat_sessions, get_chat_history, delete_chat_session,
)
from tools.agent_prompts import build_system_prompt
from tools.registry import ToolRegistry
from providers.factory import create_provider

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
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


@router.get("/sessions")
async def list_sessions(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return {"sessions": []}
    from tools.fitai_database import list_chat_sessions
    return {"sessions": list_chat_sessions(user_id)}


@router.get("/sessions/{session_id}")
async def get_session_messages(session_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401)
    from tools.fitai_database import get_chat_history
    return {"messages": get_chat_history(user_id, session_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401)
    from tools.fitai_database import delete_chat_session
    delete_chat_session(user_id, session_id)
    return {"success": True}
