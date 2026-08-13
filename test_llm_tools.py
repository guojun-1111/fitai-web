# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
from providers.factory import create_provider
from tools.registry import ToolRegistry
from config import LLM_API_KEY, LLM_BASE_URL, LLM_PROVIDER

async def test():
    tools = ToolRegistry(user_id=1)
    tool_defs = tools.get_definitions()
    print(f"Tool definitions: {len(tool_defs)} tools")
    for t in tool_defs[:3]:
        name = t.get("function", {}).get("name", "?")
        print(f"  - {name}")

    p = create_provider(api_key=LLM_API_KEY, api_base=LLM_BASE_URL or None, default_model="deepseek-v4-flash", provider_id=LLM_PROVIDER, thinking_enabled=False)
    msgs = [{"role": "user", "content": "你好"}]
    content = ""
    error = ""
    tc_count = 0
    async for chunk in p.chat_stream(messages=msgs, model="deepseek-v4-flash", max_tokens=256, tools=tool_defs):
        if chunk.is_error:
            error = chunk.error or ""
            print(f"ERROR: {error}")
        if chunk.content:
            content += chunk.content
        if chunk.tool_calls:
            tc_count += len(chunk.tool_calls)
        if chunk.is_done:
            print(f"DONE. content_len={len(content)}, tool_calls={tc_count}, content={repr(content[:200])}")
            return
    print(f"STREAM ENDED. content_len={len(content)}")

asyncio.run(test())
