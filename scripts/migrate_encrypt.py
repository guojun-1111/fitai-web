# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Migrate existing plaintext / legacy-XOR sensitive fields to AES-256-GCM.

Run once, AFTER setting ENCRYPTION_SECRET_KEY in .env. Backs up the DB first.

Usage:
    python scripts/migrate_encrypt.py
"""
import base64
import hashlib
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from core.crypto import encrypt_field, is_encrypted  # noqa: E402
from tools.fitai_database import get_db, DB_PATH  # noqa: E402


def legacy_xor_decrypt(ciphertext, user_id, platform):
    """Decrypt tokens written by the pre-Phase-3 XOR scheme (empty master key)."""
    if not ciphertext:
        return ""
    try:
        key = hashlib.sha256(f":{user_id}:{platform}".encode("utf-8")).digest()
        raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        dec = bytes(raw[i] ^ key[i % len(key)] for i in range(len(raw)))
        return dec.decode("utf-8")
    except Exception:
        return ""


def backup():
    if not os.path.exists(DB_PATH):
        return None
    bak = f"{DB_PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(DB_PATH, bak)
    return bak


def migrate_plaintext(table, columns, pk="id"):
    """Encrypt plaintext string columns in place (idempotent)."""
    conn = get_db()
    for col in columns:
        rows = conn.execute(
            f"SELECT {pk}, {col} FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchall()
        for r in rows:
            if is_encrypted(r[col]):
                continue
            conn.execute(
                f"UPDATE {table} SET {col} = ? WHERE {pk} = ?",
                (encrypt_field(r[col]), r[pk]),
            )
    conn.commit()


def migrate_xor(table, columns, user_col="user_id", platform_col=None, platform_literal=None):
    """Migrate old XOR-encrypted columns to AES-GCM (idempotent)."""
    conn = get_db()
    for col in columns:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchall()
        for r in rows:
            if is_encrypted(r[col]):
                continue
            platform = platform_literal if platform_literal is not None else r[platform_col]
            plaintext = legacy_xor_decrypt(r[col], r[user_col], platform)
            if not plaintext:
                continue
            conn.execute(
                f"UPDATE {table} SET {col} = ? WHERE id = ?",
                (encrypt_field(plaintext), r["id"]),
            )
    conn.commit()


def main():
    if not os.getenv("ENCRYPTION_SECRET_KEY"):
        print("错误：ENCRYPTION_SECRET_KEY 未设置。请先在 .env 中配置 32 字节 base64 密钥。")
        sys.exit(1)

    bak = backup()
    print(f"已备份: {bak}" if bak else "无 DB 文件，跳过备份")

    # 1. plaintext string fields → AES-GCM
    migrate_plaintext("chat_history", ["content"])
    migrate_plaintext("body_metrics", ["notes"])
    migrate_plaintext("nutrition_logs", ["food_name", "notes"])
    migrate_plaintext("user_profile", ["name", "gender", "notes"])
    migrate_plaintext("platform_config", ["client_secret"], pk="platform")
    migrate_plaintext("health_data", ["detail_json"])

    # 2. legacy XOR fields → AES-GCM
    migrate_xor("oauth_tokens", ["access_token", "refresh_token"], platform_col="platform")
    migrate_xor("users", ["wechat_session_key"], user_col="id", platform_literal="wechat")

    print("迁移完成。可以用 pytest 或手动验证读写正常。")


if __name__ == "__main__":
    main()
