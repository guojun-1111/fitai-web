# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Agent Loop — 处理消息 + 调用 LLM + 执行工具 + 流式响应"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from loguru import logger


@dataclass
class AgentEvent:
    """Structured event emitted during agent execution for real-time streaming."""
    type: str  # "step", "thought", "action", "observation", "plan_card"
    content: str = ""
    step: int = 0
    func_name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None  # for plan_card events


def _classify_llm_error(error_text: str) -> str:
    lower = (error_text or "").lower()
    if any(h in lower for h in ("401", "unauthorized", "invalid api key", "invalid_api_key", "authentication", "insufficient_quota")):
        return "LLM_AUTH_ERROR: " + (error_text or "API Key 无效")
    if any(h in lower for h in ("429", "rate limit", "rate_limit", "too many requests")):
        return "LLM_RATE_LIMITED: " + (error_text or "请求过于频繁")
    if any(h in lower for h in ("model not found", "model_not_found", "does not exist", "invalid model")):
        return "LLM_MODEL_NOT_FOUND: " + (error_text or "模型不可用")
    if any(h in lower for h in ("timeout", "connection", "network", "dns", "refused", "unreachable")):
        return "LLM_NETWORK_ERROR: " + (error_text or "网络连接失败")
    return "LLM_UNKNOWN: " + (error_text or "未知错误")


class AgentLoop:
    def __init__(
        self,
        provider,
        tools=None,
        model: Optional[str] = None,
        max_iterations: int = 25,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        thinking_enabled: bool = True,
    ):
        self.provider = provider
        self.tools = tools
        self.model = model
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking_enabled = thinking_enabled

    async def process_message(
        self,
        message: str,
        system_prompt: str = "",
        context: Optional[List[Dict[str, Any]]] = None,
        channel: str = "web",
        cancel_token=None,
        timeout: float = 120.0,
    ) -> AsyncIterator[str]:
        request_trace_id = uuid.uuid4().hex[:8]
        messages: List[Dict[str, Any]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context:
            messages.extend(context[-20:])  # Keep last 20 messages for context

        messages.append({"role": "user", "content": message})

        tool_definitions = []
        if self.tools:
            tool_definitions = self.tools.get_definitions()

        iteration = 0
        total_tool_calls = 0
        content_buffer = ""
        reasoning_buffer = ""

        while iteration < self.max_iterations:
            if cancel_token and cancel_token.is_cancelled:
                yield "LLM_UNKNOWN: 请求已取消"
                return

            iteration += 1
            yield AgentEvent(type="step", step=iteration, content=f"第 {iteration} 步")
            tool_calls_buffer: List[dict] = []

            try:
                async for chunk in self.provider.chat_stream(
                    messages=messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    tools=tool_definitions if tool_definitions else None,
                ):
                    if cancel_token and cancel_token.is_cancelled:
                        yield "LLM_UNKNOWN: 请求已取消"
                        return

                    if chunk.is_error:
                        yield _classify_llm_error(chunk.raw_error or chunk.error or "")
                        return

                    if chunk.reasoning_content:
                        reasoning_buffer += chunk.reasoning_content

                    if chunk.content:
                        content_buffer += chunk.content
                        yield chunk.content

                    if chunk.tool_calls:
                        tool_calls_buffer.extend(chunk.tool_calls)

                    if chunk.is_done:
                        if tool_calls_buffer:
                            break

                if tool_calls_buffer:
                    # Emit thought event if reasoning was captured
                    if reasoning_buffer:
                        yield AgentEvent(type="thought", content=reasoning_buffer, step=iteration)

                    # Merge streaming tool call fragments by index only
                    # id is null in subsequent chunks, so (index,id) as key breaks merging
                    merged = {}
                    for tc in tool_calls_buffer:
                        key = tc.get("index", 0)
                        if key not in merged:
                            merged[key] = {"id": "", "name": "", "arguments": "", "index": key}
                        merged[key]["arguments"] += tc.get("arguments", "")
                        if tc.get("name"):
                            merged[key]["name"] = tc.get("name")
                        if tc.get("id"):
                            merged[key]["id"] = tc.get("id")
                    tool_calls_buffer = list(merged.values())

                    tool_results = []
                    for tc in tool_calls_buffer:
                        tool_name = tc.get("name", "")
                        if not tc.get("id"):
                            continue

                        try:
                            args_str = tc.get("arguments", "{}")
                            if isinstance(args_str, str):
                                arguments = json.loads(args_str) if args_str else {}
                            else:
                                arguments = args_str
                        except json.JSONDecodeError:
                            logger.warning(f"Tool call JSON parse failed for {tool_name}: args={repr(tc.get('arguments', '')[:200])}")
                            arguments = {}

                        if self.tools:
                            yield AgentEvent(type="action", func_name=tool_name, args=arguments,
                                           content=f"{tool_name}({json.dumps(arguments, ensure_ascii=False)[:100]})",
                                           step=iteration)
                            try:
                                logger.info(f"Executing tool: {tool_name} args={json.dumps(arguments, ensure_ascii=False)[:80]}")
                                result = await self.tools.execute(tool_name, arguments)
                                result_str = str(result)

                                # Detect [PLAN_CARD] marker in tool result and emit plan_card event
                                if "[PLAN_CARD]" in result_str and "[/PLAN_CARD]" in result_str:
                                    import re as _re
                                    pm = _re.search(r'\[PLAN_CARD\](.*?)\[/PLAN_CARD\]', result_str, _re.DOTALL)
                                    if pm:
                                        try:
                                            plan_data = json.loads(pm.group(1))
                                            yield AgentEvent(type="plan_card", content="propose", plan=plan_data)
                                        except json.JSONDecodeError:
                                            pass
                                    # Strip marker from result so it doesn't appear in text
                                    result_str = _re.sub(r'\[PLAN_CARD\].*?\[/PLAN_CARD\]', '', result_str, flags=_re.DOTALL).strip()

                                tool_results.append({"tool_call_id": tc["id"], "role": "tool", "content": result_str})
                                total_tool_calls += 1
                                yield AgentEvent(type="observation", content=result_str[:500], step=iteration)
                            except Exception as e:
                                tool_results.append({"tool_call_id": tc["id"], "role": "tool", "content": f"Error: {e}"})
                                total_tool_calls += 1
                                yield AgentEvent(type="observation", content=f"Error: {e}", step=iteration)

                    messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc.get("arguments", "{}")}} for tc in tool_calls_buffer if tc.get("id")]})
                    for tr in tool_results:
                        messages.append(tr)
                    tool_calls_buffer = []
                    continue

                break

            except asyncio.CancelledError:
                if cancel_token:
                    cancel_token.cancel()
                yield "LLM_UNKNOWN: 请求已取消"
                return

            except Exception as e:
                error_msg = str(e)
                logger.exception(f"Agent loop error: {error_msg}")
                yield _classify_llm_error(error_msg)
                return

        if not content_buffer and reasoning_buffer:
            yield reasoning_buffer
        if not content_buffer and not reasoning_buffer:
            logger.warning(f"Agent loop produced zero content after {iteration} iterations")
            yield "LLM_UNKNOWN: AI 模型返回了空响应，可能是 API 配额不足或模型暂时不可用，请稍后重试"
