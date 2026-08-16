# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""WebSocket 聊天：认证、心跳、姿势实时分析、双模型切换、视觉食物分析、Agent 流式。"""
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from core.config_state import get_reply_style
from tools.fitai_database import get_user_profile, get_user_profile_summary
from tools.agent_prompts import build_system_prompt
from tools.registry import ToolRegistry
from providers.factory import create_provider

router = APIRouter()


@router.websocket("/ws/chat")
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
