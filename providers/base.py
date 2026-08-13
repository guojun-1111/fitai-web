# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM Provider 抽象基类 + 数据类型"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class StreamChunk:
    content: str = ""
    reasoning_content: str = ""
    is_error: bool = False
    error: str = ""
    raw_error: str = ""
    is_done: bool = False
    finish_reason: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    provider_payload: Optional[Dict[str, Any]] = None
    is_reasoning: bool = False
    has_provider_payload: bool = False

    @property
    def is_content(self) -> bool:
        return bool(self.content and not self.is_error and not self.is_done and not self.is_reasoning)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式对话，返回 StreamChunk 异步迭代器"""
        ...

    @property
    @abstractmethod
    def provider_id(self) -> str:
        ...
