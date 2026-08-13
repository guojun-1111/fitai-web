# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""OpenAI SDK 流式提供商（DeepSeek 兼容）"""
import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from openai import AsyncOpenAI

from providers.base import LLMProvider, StreamChunk


def _get_reasoning(delta) -> str:
    """Extract reasoning_content from delta, with fallback for older SDKs."""
    val = getattr(delta, 'reasoning_content', None)
    if val:
        return val
    # Fallback: Pydantic v2 model_extra for fields not in the schema (SDK < 1.55.0)
    if hasattr(delta, 'model_extra') and delta.model_extra:
        return delta.model_extra.get('reasoning_content', '') or ''
    return ''


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, api_base: str, model: str, timeout: float = 120.0, max_retries: int = 3, provider_id: str = "openai", thinking_enabled: bool = True):
        self._provider_id = provider_id
        self._model = model
        self._thinking_enabled = thinking_enabled
        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base, timeout=timeout, max_retries=max_retries)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[StreamChunk]:
        if not messages:
            yield StreamChunk(is_error=True, error="No messages provided")
            return

        actual_model = model or self._model
        extra_body = {}
        if self._provider_id == "deepseek" and self._thinking_enabled:
            extra_body["thinking"] = {"type": "enabled"}

        params: Dict[str, Any] = {
            "model": actual_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "extra_body": extra_body if extra_body else None,
        }
        if tools:
            params["tools"] = tools

        t0 = time.time()
        first_byte_ts = None
        reasoning_buf = ""
        has_content = False
        has_tool_calls = False
        delta_fields_seen = set()
        total_chunks = 0

        try:
            stream = await self._client.chat.completions.create(**{k: v for k, v in params.items() if v is not None})
            async for chunk in stream:
                total_chunks += 1
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta

                    # Log delta field names on first content-bearing chunk
                    if not delta_fields_seen:
                        if hasattr(delta, 'model_extra') and delta.model_extra:
                            delta_fields_seen.update(delta.model_extra.keys())
                        delta_fields_seen.update(k for k in delta.__dict__ if not k.startswith('_') and getattr(delta, k))
                        logger.info(f"LLM delta fields: {sorted(delta_fields_seen)}")

                    # Accumulate reasoning silently
                    reasoning = _get_reasoning(delta)
                    if reasoning:
                        if first_byte_ts is None:
                            first_byte_ts = time.time()
                        reasoning_buf += reasoning

                    # Real content — yield immediately
                    if delta.content:
                        if first_byte_ts is None:
                            first_byte_ts = time.time()
                        has_content = True
                        yield StreamChunk(content=delta.content)

                    if delta.tool_calls:
                        if first_byte_ts is None:
                            first_byte_ts = time.time()
                        has_tool_calls = True
                        tc_list = []
                        for tc in delta.tool_calls:
                            tc_list.append({
                                "index": tc.index,
                                "id": tc.id,
                                "name": tc.function.name if tc.function else "",
                                "arguments": tc.function.arguments if tc.function else "",
                            })
                        yield StreamChunk(tool_calls=tc_list)

                if chunk.choices and chunk.choices[0].finish_reason:
                    # Only flush reasoning as content when model is truly done
                    if reasoning_buf and not has_content and not has_tool_calls:
                        logger.info(f"Flushing {len(reasoning_buf)} chars of reasoning as content")
                        yield StreamChunk(content=reasoning_buf)
                        has_content = True

                    # Empty response fallback: API returned stop but no content at all
                    if not has_content and not has_tool_calls:
                        logger.warning(f"LLM returned empty response! model={actual_model}, finish_reason={chunk.choices[0].finish_reason}, delta_fields={sorted(delta_fields_seen)}, reasoning_buf_len={len(reasoning_buf)}")
                        yield StreamChunk(is_error=True, error="AI 模型返回了空响应，可能是 API 配额不足或模型暂时不可用，请稍后重试")

                    yield StreamChunk(is_done=True, finish_reason=chunk.choices[0].finish_reason)

        except Exception as e:
            error_msg = str(e)
            yield StreamChunk(is_error=True, error=error_msg, raw_error=error_msg)

        elapsed = time.time() - t0
        fb = f"{first_byte_ts - t0:.2f}s" if first_byte_ts else "N/A"
        logger.info(f"LLM call done: model={actual_model}, msgs={len(messages)}, tools={len(tools) if tools else 0}, "
                     f"chunks={total_chunks}, first_byte={fb}, total={elapsed:.2f}s, "
                     f"has_content={has_content}, has_tool_calls={has_tool_calls}, reasoning_len={len(reasoning_buf)}")
