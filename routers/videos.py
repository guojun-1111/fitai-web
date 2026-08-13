# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 视频搜索路由（从 server.py 提取）。"""
from fastapi import APIRouter, Request
from loguru import logger
from tools.fitai_tools import search_bilibili_videos

router = APIRouter(tags=["videos"])


@router.get("/api/videos")
async def videos(limit: int = 6, exercise: str = ""):
    try:
        data = search_bilibili_videos(exercise, limit) if exercise else search_bilibili_videos("健身", limit)
        return {"data": data}
    except Exception as e:
        logger.warning(f"Video search failed: {e}")
        return {"data": []}
