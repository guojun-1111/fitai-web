# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""V7.0: 健康数据导入路由 + 后台 worker（从 server.py 提取）。"""
import json
import os as _os
import uuid
import threading
import shutil
from concurrent.futures import ProcessPoolExecutor
from fastapi import APIRouter, Request, HTTPException
from loguru import logger
from core.dependencies import get_user_id
from core.cache import default_cache
from core.db_utils import db_fetch, db_execute
from tools.fitai_database import get_db, insert_health_data_batch, insert_workout
from tools.fitai_tools import invalidate_user_analysis_cache

router = APIRouter(tags=["import"])

_ALLOWED_EXTENSIONS = {".xml", ".csv", ".json", ".zip", ".tcx", ".gpx"}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB

_IMPORT_DIR = "/tmp/fitai_imports"
_os.makedirs(_IMPORT_DIR, exist_ok=True)
_import_lock = threading.Lock()
_import_running = False


def _import_worker_fn(file_path, filename, platform, user_id):
    """在独立子进程中执行导入。必须是模块级函数（ProcessPoolExecutor pickle 要求）。"""
    from fitai.health_platforms.importer import import_file
    return import_file(file_path, platform, user_id)


def _run_import_job(job_id: str):
    global _import_running
    conn = get_db()
    file_path = _os.path.join(_IMPORT_DIR, job_id)
    try:
        conn.execute("UPDATE import_jobs SET status='running' WHERE id=?", (job_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return
        user_id = row["user_id"]
        filename = row["filename"] or "import.dat"

        with ProcessPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_import_worker_fn, file_path, filename, "local_import", user_id)
            result = future.result(timeout=1800)

        conn.execute(
            "UPDATE import_jobs SET status='done', progress=100, result_json=?, finished_at=datetime('now') WHERE id=?",
            (json.dumps(result), job_id),
        )
        conn.commit()
    except Exception as e:
        conn.execute(
            "UPDATE import_jobs SET status='error', error_msg=?, finished_at=datetime('now') WHERE id=?",
            (f"{type(e).__name__}: {e}", job_id),
        )
        conn.commit()
    finally:
        try:
            _os.unlink(file_path)
        except OSError:
            pass
        with _import_lock:
            _import_running = False


def start_import_worker():
    """后台线程：循环取 queued 任务 → 子进程执行。在 lifespan 中调用。"""
    global _import_running
    import time as _time
    while True:
        _time.sleep(2)
        with _import_lock:
            if _import_running:
                continue
            _import_running = True
        try:
            conn = get_db()
            row = conn.execute(
                "SELECT id FROM import_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if row:
                _run_import_job(row["id"])
            else:
                with _import_lock:
                    _import_running = False
        except Exception as e:
            logger.exception(f"Import worker error: {e}")
            with _import_lock:
                _import_running = False


# ══ 路由 ══

@router.post("/api/health/import-file")
async def health_import_file(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(status_code=400, detail="请使用文件上传方式")

    form = await request.form()
    file = form.get("file")
    if file is None:
        raise HTTPException(status_code=400, detail="未找到上传文件")

    filename = file.filename or "import.dat"

    # Validate filename: no path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="文件名包含非法字符")

    # Validate extension
    ext = _os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}，支持: {', '.join(sorted(_ALLOWED_EXTENSIONS))}")

    job_id = uuid.uuid4().hex[:12]
    file_path = _os.path.join(_IMPORT_DIR, job_id)

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.warning(f"File read failed (fd closed): {e}, retrying with seek")
        try:
            await file.seek(0)
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as e2:
            logger.exception(f"File save failed")
            if _os.path.exists(file_path):
                _os.unlink(file_path)
            raise HTTPException(status_code=500, detail="文件保存失败，请重试")

    # Validate actual file size after saving
    actual_size = _os.path.getsize(file_path)
    if actual_size > _MAX_UPLOAD_BYTES:
        _os.unlink(file_path)
        raise HTTPException(status_code=400, detail=f"文件过大（{actual_size / 1024 / 1024:.1f}MB），最大支持 50MB")

    ahead_rows = await db_fetch(
        "SELECT COUNT(*) as c FROM import_jobs WHERE status IN ('queued','running') AND id != ?",
        (job_id,)
    )
    ahead = ahead_rows[0]["c"] if ahead_rows else 0

    await db_execute(
        "INSERT INTO import_jobs (id, user_id, filename, status) VALUES (?, ?, ?, 'queued')",
        (job_id, user_id, filename),
    )
    return {"job_id": job_id, "status": "queued", "queue_ahead": ahead,
            "message": f"已加入导入队列（前方 {ahead} 人），请等待处理"}


@router.get("/api/health/import-status")
async def health_import_status(request: Request, job_id: str = ""):
    user_id = await get_user_id(request)
    if not job_id:
        return {"error": "缺少 job_id 参数"}

    rows = await db_fetch(
        "SELECT status, progress, result_json, error_msg FROM import_jobs WHERE id=? AND user_id=?",
        (job_id, user_id or 0),
    )

    if not rows:
        return {"status": "not_found", "message": "任务不存在"}

    row = rows[0]
    result = {"status": row["status"], "progress": row["progress"]}
    if row["status"] == "done" and row["result_json"]:
        result["result"] = json.loads(row["result_json"])
    if row["status"] == "error":
        result["error"] = row["error_msg"]
    return result


@router.post("/api/health/import-batch")
async def health_import_batch(request: Request):
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    records = body.get("records", [])
    workouts = body.get("workouts", [])

    if not records and not workouts:
        return {"success": False, "error": "没有可导入的数据"}

    total = 0
    if records:
        total += insert_health_data_batch(user_id, records)
    for w in workouts:
        try:
            insert_workout(user_id, w.get("exercise_name", ""), None, None, None,
                          w.get("duration_minutes"), None, w.get("date"))
            total += 1
        except Exception as e:
            logger.warning(f"Failed to insert workout: {e}")

    default_cache.invalidate(str(user_id))
    invalidate_user_analysis_cache(user_id)
    return {"success": True, "count": total, "message": f"成功导入 {total} 条数据"}
