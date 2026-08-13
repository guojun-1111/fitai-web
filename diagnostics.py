# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""自诊断模块：一键检测系统各部分是否正常"""
import json
from typing import Any

async def run_diagnostics() -> dict[str, Any]:
    results = {
        "server": "ok",
        "checks": {},
        "summary": {"pass": 0, "fail": 0, "warn": 0},
    }

    async def check(name: str, fn):
        try:
            r = await fn()
            results["checks"][name] = {"status": "ok", **r}
            results["summary"]["pass"] += 1
        except Exception as e:
            results["checks"][name] = {"status": "fail", "error": str(e)}
            results["summary"]["fail"] += 1

    # 1. Database check
    async def check_db():
        from database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as s:
            r = await s.execute(text("SELECT COUNT(*) FROM users"))
            user_count = r.scalar()
            r = await s.execute(text("SELECT COUNT(*) FROM workout_logs"))
            workout_count = r.scalar()
        return {"users": user_count, "workout_logs": workout_count}

    # 2. LLM check
    async def check_llm():
        from config import LLM_PROVIDER, LLM_API_KEY, LLM_MODEL
        from providers.factory import create_provider
        provider = create_provider(api_key=LLM_API_KEY or None, provider_id=LLM_PROVIDER, default_model=LLM_MODEL, thinking_enabled=False)
        content = ""
        async for chunk in provider.chat_stream(messages=[{"role": "user", "content": "hi"}], model=LLM_MODEL, max_tokens=20):
            if chunk.is_error:
                raise Exception(chunk.raw_error or chunk.error or "LLM error")
            if chunk.content:
                content += chunk.content
            if len(content) > 5:
                break
        return {"provider": LLM_PROVIDER, "model": LLM_MODEL, "response_sample": content[:50]}

    # 3. Registration chain
    async def check_registration():
        from auth.utils import count_users, is_registration_allowed, get_user_by_id
        user_count = await count_users()
        reg_open = await is_registration_allowed()
        user1 = await get_user_by_id(1) if user_count > 0 else None
        is_admin = user1.get("is_admin", False) if user1 else False
        issues = []
        if user_count == 0:
            issues.append("无用户，需先完成初始化")
        if user_count > 0 and not is_admin:
            issues.append("用户ID=1不是管理员，数据库异常")
        if user_count > 0 and not reg_open:
            issues.append("注册已关闭")
        return {
            "user_count": user_count,
            "registration_open": reg_open,
            "user1_is_admin": is_admin,
            "issues": issues,
            "action": "访问 /api/auth/registration-status 查看状态"
        }

    # 4. Tools check
    async def check_tools():
        from tools.registry import ToolRegistry
        tools = ToolRegistry(user_id=1)
        defs = tools.get_definitions()
        tool_names = [t["function"]["name"] for t in defs]
        return {"count": len(tool_names), "tools": tool_names}

    # 5. Context test
    async def check_context():
        from config import LLM_PROVIDER, LLM_API_KEY, LLM_MODEL
        from providers.factory import create_provider
        from tools.registry import ToolRegistry
        from tools.agent_prompts import build_system_prompt
        from agent.loop import AgentLoop

        provider = create_provider(api_key=LLM_API_KEY or None, provider_id=LLM_PROVIDER, default_model=LLM_MODEL, thinking_enabled=False)
        tools = ToolRegistry(user_id=1)
        agent = AgentLoop(provider=provider, tools=tools, model=LLM_MODEL, max_iterations=3)

        # Test with context
        context = [
            {"role": "assistant", "content": "要不要我帮你查一下深蹲的教学视频？"},
        ]
        response = ""
        async for chunk in agent.process_message(message="要", system_prompt=build_system_prompt(""), context=context):
            if chunk.startswith("LLM_"): break
            response += chunk

        has_context = "深蹲" in response or "视频" in response or "squat" in response.lower()
        return {
            "context_understood": has_context,
            "response_sample": response[:100],
            "note": "Agent应理解'要'指'要查深蹲视频'" if not has_context else "上下文正常"
        }

    await check("database", check_db)
    await check("llm", check_llm)
    await check("registration", check_registration)
    await check("tools", check_tools)
    await check("context", check_context)

    # If registration is closed and admin exists, offer fix
    reg_check = results["checks"].get("registration", {})
    if not reg_check.get("registration_open") and reg_check.get("user1_is_admin"):
        results["fix_available"] = {
            "problem": "注册已关闭",
            "fix_url": "/api/diagnostics/fix-registration",
            "description": "访问此 URL 即可开启注册（无需登录）"
        }

    return results


async def enable_registration():
    """直接开启注册（调试用）"""
    from auth.utils import set_registration_allowed, count_users, get_user_by_id
    user_count = await count_users()
    if user_count == 0:
        return {"status": "error", "message": "无用户，请先完成初始化"}
    user1 = await get_user_by_id(1)
    if not user1 or not user1.get("is_admin"):
        return {"status": "error", "message": "用户1不是管理员"}
    await set_registration_allowed(True)
    return {"status": "ok", "message": "注册已开启！现在可以注册新账号了", "registration_open": True}
