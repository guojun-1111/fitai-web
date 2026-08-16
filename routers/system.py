# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""系统端点：健康检查 + 自检。"""
import time

from fastapi import APIRouter, Request

from core.cache import default_cache as _cache
from auth.utils import count_users
from providers.factory import create_provider

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health_check():
    db_ok = False
    try:
        from tools.fitai_database import get_db
        conn = get_db()
        conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "7.0",
        "database": "connected" if db_ok else "error",
        "cache_size": len(_cache),
        "setup_completed": (await count_users()) > 0,
    }


@router.get("/self-check")
async def self_check(request: Request):
    import sys
    try:
        import openai
        sdk_version = openai.__version__
    except Exception:
        sdk_version = "unknown"

    from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

    # 1. DB check
    db_ok = False
    db_error = ""
    try:
        from tools.fitai_database import get_db
        conn = get_db()
        conn.execute("SELECT 1")
        db_ok = True
    except Exception as e:
        db_error = str(e)[:200]

    # 2. LLM API check
    llm_ok = False
    llm_error = ""
    llm_first_byte_s = None
    try:
        p = create_provider(
            api_key=LLM_API_KEY or None,
            api_base=LLM_BASE_URL or None,
            default_model=LLM_MODEL,
            provider_id=LLM_PROVIDER,
            thinking_enabled=False,
        )
        t0 = time.time()
        async for chunk in p.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            model=LLM_MODEL,
            max_tokens=32,
        ):
            if chunk.content and llm_first_byte_s is None:
                llm_first_byte_s = round(time.time() - t0, 2)
            if chunk.is_error:
                llm_error = (chunk.raw_error or chunk.error or "")[:200]
                break
            if chunk.content:
                llm_ok = True
                break
        if not llm_ok and not llm_error:
            llm_error = "LLM returned no content"
    except Exception as e:
        llm_error = str(e)[:200]

    return {
        "status": "ok" if (db_ok and llm_ok) else "degraded",
        "python": sys.version.split()[0],
        "openai_sdk": sdk_version,
        "database": "connected" if db_ok else f"error: {db_error}",
        "llm": {
            "provider": LLM_PROVIDER,
            "model": LLM_MODEL,
            "base_url": LLM_BASE_URL or "(default)",
            "api_key_configured": bool(LLM_API_KEY and LLM_API_KEY.startswith("sk-")),
            "connected": llm_ok,
            "first_byte_s": llm_first_byte_s,
            "error": llm_error if not llm_ok else "",
        },
    }
