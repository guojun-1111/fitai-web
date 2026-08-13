# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM 提供商注册表（精简版：3 个提供商）"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProviderMeta:
    provider_id: str
    name: str
    default_api_base: str
    default_model: str
    env_key: str
    provider_group: str = "openai"


PROVIDERS: Dict[str, ProviderMeta] = {
    "deepseek": ProviderMeta(
        provider_id="deepseek",
        name="DeepSeek",
        default_api_base="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        env_key="LLM_API_KEY",
    ),
    "openai": ProviderMeta(
        provider_id="openai",
        name="OpenAI",
        default_api_base="https://api.openai.com/v1",
        default_model="gpt-4o",
        env_key="LLM_API_KEY",
    ),
    "ollama": ProviderMeta(
        provider_id="ollama",
        name="Ollama (本地)",
        default_api_base="http://localhost:11434/v1",
        default_model="llama3",
        env_key="LLM_API_KEY",
    ),
}


def get_provider_meta(provider_id: str) -> Optional[ProviderMeta]:
    return PROVIDERS.get(provider_id)


def get_all_providers() -> List[Dict]:
    return [
        {
            "id": p.provider_id,
            "name": p.name,
            "default_model": p.default_model,
            "group": p.provider_group,
        }
        for p in PROVIDERS.values()
    ]
