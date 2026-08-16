# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""隐私与数据管理路由 — 全量数据导出（GDPR 携带权）与账户注销（被遗忘权）。"""
import io
import json
import zipfile

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response

from core.dependencies import get_user_id
from core.db_utils import db_fetch
from core.crypto import decrypt_field
from tools.fitai_database import delete_user_data_cascade

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

# 表名 -> 需要解密的列（导出时还原明文）
_EXPORT_TABLES = {
    "user_profile": ["name", "gender", "notes"],
    "health_data": ["detail_json"],
    "health_daily_summary": [],
    "heart_rate_samples": [],
    "workout_logs": [],
    "workout_sessions": ["heart_rate_data_json", "notes"],
    "body_metrics": ["notes"],
    "nutrition_logs": ["food_name", "notes"],
    "chat_history": ["content"],
    "training_plans": [],
    "training_feedback": ["notes", "sore_areas"],
    "subscriptions": [],
    "payments": [],
}


@router.get("/export")
async def export_data(request: Request):
    """导出当前用户全部个人数据，打包为 ZIP（每表一个 JSON 文件）。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for table, encrypted_cols in _EXPORT_TABLES.items():
            try:
                rows = await db_fetch(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,))
            except Exception:
                continue  # 表尚不存在则跳过
            data = [dict(r) for r in rows]
            for row in data:
                for col in encrypted_cols:
                    row[col] = decrypt_field(row.get(col, ""))
            zf.writestr(
                f"{table}.json",
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
            )

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=fitai_export.zip"},
    )


@router.delete("/account")
async def delete_account(request: Request):
    """自助注销账户，级联删除全部个人数据（不可撤销）。"""
    user_id = await get_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")

    deleted = delete_user_data_cascade(user_id)

    from auth.utils import delete_user_by_id
    account_removed = await delete_user_by_id(user_id)

    return {"ok": account_removed, "deleted_records": deleted}
