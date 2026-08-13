# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider 工厂函数"""
from typing import Optional

from providers.base import LLMProvider
from providers.registry import get_provider_meta, PROVIDERS
from providers.openai_provider import OpenAIProvider


def create_provider(
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    default_model: Optional[str] = None,
    provider_id: str = "deepseek",
    timeout: float = 120.0,
    max_retries: int = 3,
    thinking_enabled: bool = True,
) -> LLMProvider:
    meta = get_provider_meta(provider_id)
    if meta is None:
        meta = get_provider_meta("deepseek")

    key = api_key or ""
    base = api_base or meta.default_api_base
    model = default_model or meta.default_model

    return OpenAIProvider(
        api_key=key,
        api_base=base,
        model=model,
        timeout=timeout,
        max_retries=max_retries,
        provider_id=meta.provider_id,
        thinking_enabled=thinking_enabled,
    )
