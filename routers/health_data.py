# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 健康数据路由 — 记录、分析、喝水、周报、平台同步（从 server.py 提取）。"""
import json
import asyncio as _asyncio
from datetime import date as dt_date
from fastapi import APIRouter, Request, HTTPException
from core.dependencies import get_user_id, validate_days
from core.cache import default_cache
from core.db_utils import db_fetch, db_execute
from tools.fitai_database import (get_health_data_history_json,
                                   insert_health_data_batch, get_oauth_token)
from tools.fitai_tools import invalidate_user_analysis_cache

router = APIRouter(tags=["health"])


# ══ 静态路径 ══

@router.get("/api/health/analysis-summary")
async def health_analysis_summary(request: Request, days: int = 7):
    days = validate_days(days)
    user_id = await get_user_id(request)
    if user_id is None:
        return {"summary": {}, "weekly_trends": {}}

    cache_key = f"as:{user_id}:{days}"
    cached = default_cache.get(cache_key)
    if cached is not None:
        return cached

    from statistics import mean
    raw_data = await _asyncio.get_event_loop().run_in_executor(
        None, get_health_data_history_json, user_id, days)
    if not raw_data:
        result = {"summary": {}, "weekly_trends": {}}
        default_cache.set(cache_key, result)
        return result

    by_type = {}
    for r in raw_data:
        dt = r.get("data_type", "")
        if dt not in by_type:
            by_type[dt] = []
        by_type[dt].append(float(r["value"]))

    summary = {}
    for dt, values in by_type.items():
        if not values:
            continue
        summary[dt] = {
            "has_data": True, "latest": values[-1],
            "stats_7d": {"avg": round(mean(values), 1), "min": round(min(values), 1),
                         "max": round(max(values), 1), "count": len(values)},
        }

    weekly_trends = {}
    for dt, values in by_type.items():
        if len(values) < 2:
            continue
        mid = len(values) // 2
        prev_avg = mean(values[:mid]) if values[:mid] else 0
        curr_avg = mean(values[mid:]) if values[mid:] else 0
        if prev_avg > 0:
            pct = round((curr_avg - prev_avg) / prev_avg * 100, 1)
            weekly_trends[dt] = {"direction": "up" if pct > 0 else "down" if pct < 0 else "stable", "pct": abs(pct)}

    result = {"summary": summary, "weekly_trends": weekly_trends}
    default_cache.set(cache_key, result)
    return result


@router.get("/api/health/water-today")
async def health_water_today(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return {"total": 0, "target": 8}
    ck = f"wt:{user_id}"
    cv = default_cache.get(ck, 120)
    if cv is not None:
        return cv
    today = dt_date.today().isoformat()
    rows = await db_fetch(
        "SELECT COALESCE(SUM(value), 0) as total FROM health_data WHERE user_id = ? AND date = ? AND data_type = 'water'",
        (user_id, today),
    )
    total = int(rows[0]["total"]) if rows else 0
    result = {"total": total, "target": 8}
    default_cache.set(ck, result)
    return result


@router.post("/api/health/record")
async def health_record(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    data_type = body.get("data_type") or body.get("type", "")
    record_date = body.get("date") or dt_date.today().isoformat()
    source = body.get("source", "manual")
    value = float(body.get("value", 0))
    unit = body.get("unit", "")

    if data_type == "water":
        rows = await db_fetch(
            "SELECT value FROM health_data WHERE user_id = ? AND date = ? AND source_platform = ? AND data_type = ?",
            (user_id, record_date, source, data_type),
        )
        if rows:
            value = float(rows[0]["value"]) + value

    records = [{"date": record_date, "source_platform": source,
                "data_type": data_type, "value": value, "unit": unit}]
    inserted = insert_health_data_batch(user_id, records)
    default_cache.invalidate(str(user_id))
    invalidate_user_analysis_cache(user_id)
    if inserted == 0:
        return {"success": False, "count": 0, "detail": "数据校验未通过（值超出合理范围）"}
    return {"success": True, "count": inserted}


@router.get("/api/health/weekly")
async def health_weekly(request: Request, data_type: str = "steps", weeks: int = 12):
    user_id = await get_user_id(request)
    if user_id is None:
        return {"weeks": [], "data_type": data_type}
    rows = await db_fetch(
        "SELECT strftime('%Y-W%W', date) AS week, AVG(value) AS avg, SUM(value) AS total "
        "FROM health_data WHERE user_id = ? AND data_type = ? AND date >= date('now', ?) "
        "GROUP BY week ORDER BY week ASC",
        (user_id, data_type, f"-{weeks * 7} days"),
    )
    return {"weeks": [dict(r) for r in rows], "data_type": data_type}


@router.get("/api/health/last-sync")
async def health_last_sync(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return {"last_sync": {}}
    rows = await db_fetch(
        "SELECT platform, MAX(finished_at) AS finished_at FROM health_sync_log "
        "WHERE user_id = ? AND status = 'done' GROUP BY platform", (user_id,))
    return {"last_sync": {r["platform"]: {"finished_at": r["finished_at"]} for r in rows}}


@router.get("/api/health/platforms")
async def health_platforms(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        return {"platforms": []}
    rows = await db_fetch(
        "SELECT DISTINCT platform, access_token IS NOT NULL AS connected "
        "FROM oauth_tokens WHERE user_id = ?", (user_id,))
    platforms = []
    for r in rows:
        token = get_oauth_token(user_id, r["platform"])
        platforms.append({"name": r["platform"],
                          "display_name": r["platform"].replace("_", " ").title(),
                          "connected": bool(token), "device_list": ""})
    return {"platforms": platforms}


# ══ V20: WeChat WeRun step sync ══

@router.post("/api/health/wechat/werun")
async def wechat_werun_sync(request: Request):
    """Decrypt and store WeChat WeRun step data.

    Receives wx.getWeRunData() encrypted payload, decrypts with stored
    session_key, writes step records to health_data.
    """
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    from tools.fitai_database import get_wechat_session_key, decrypt_wechat_werun, insert_health_data_batch

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    encrypted_data = body.get("encryptedData", "")
    iv = body.get("iv", "")
    if not encrypted_data or not iv:
        raise HTTPException(status_code=400, detail="缺少 encryptedData 或 iv")

    session_key = get_wechat_session_key(user_id)
    if not session_key:
        raise HTTPException(status_code=400, detail="微信 session_key 未找到，请重新登录")

    try:
        decrypted = decrypt_wechat_werun(encrypted_data, iv, session_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解密失败: {str(e)}")

    step_list = decrypted.get("stepInfoList", [])
    if not step_list:
        return {"success": True, "count": 0, "message": "没有新的步数数据"}

    # Convert WeChat timestamps to date strings and insert
    from datetime import datetime as _dt
    records = []
    for entry in step_list:
        ts = entry.get("timestamp", 0)
        steps = entry.get("step", 0)
        if ts and steps:
            date_str = _dt.fromtimestamp(ts).strftime("%Y-%m-%d")
            records.append({
                "date": date_str,
                "source_platform": "wechat_werun",
                "data_type": "steps",
                "value": float(steps),
                "unit": "步",
            })

    if records:
        insert_health_data_batch(user_id, records)
        from core.cache import default_cache
        default_cache.invalidate(str(user_id))

    return {"success": True, "count": len(records)}


# ══ 动态路径（platform 参数）— 必须在静态路径之后 ══

_ALLOWED_PLATFORMS = {"google_fit", "apple_health", "huawei_health", "health_connect", "fitbit", "local_import"}

def _validate_platform(platform: str):
    if platform not in _ALLOWED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

@router.get("/api/health/{platform}/auth-url")
async def health_auth_url(platform: str):
    _validate_platform(platform)
    try:
        mod = __import__(f"fitai.health_platforms.{platform}", fromlist=["get_auth_url"])
        return {"url": mod.get_auth_url()}
    except Exception:
        return {"error": f"Platform {platform} not available"}


@router.get("/api/health/{platform}/config-status")
async def health_config_status(platform: str):
    _validate_platform(platform)
    try:
        mod = __import__(f"fitai.health_platforms.{platform}", fromlist=["is_configured"])
        return {"configured": mod.is_configured()}
    except Exception:
        return {"configured": False}


@router.post("/api/health/{platform}/config")
async def health_config_save(platform: str, request: Request):
    _validate_platform(platform)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    await db_execute("INSERT OR REPLACE INTO platform_config (platform, client_id, client_secret) VALUES (?, ?, ?)",
               (platform, body.get("client_id", ""), body.get("client_secret", "")))
    return {"message": f"{platform} credentials saved"}


# ══ V15: Data Export ══

@router.get("/api/health/export")
async def health_export(request: Request, format: str = "json"):
    """导出用户全部健康数据，支持 JSON 和 CSV 格式。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    from fastapi.responses import StreamingResponse
    import csv
    import io

    rows = await db_fetch(
        "SELECT date, data_type, value, unit, source_platform FROM health_data "
        "WHERE user_id = ? ORDER BY date, data_type",
        (user_id,),
    )

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "data_type", "value", "unit", "source_platform"])
        for r in rows:
            writer.writerow([r["date"], r["data_type"], r["value"],
                           r["unit"] if "unit" in r.keys() else "",
                           r["source_platform"] if "source_platform" in r.keys() else ""])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=fitai_health_export.csv"},
        )

    # JSON format
    return {
        "user_id": user_id,
        "count": len(rows),
        "data": [{"date": r["date"], "data_type": r["data_type"], "value": r["value"],
                  "unit": r["unit"] if "unit" in r.keys() else "",
                  "source_platform": r["source_platform"] if "source_platform" in r.keys() else ""} for r in rows],
    }
