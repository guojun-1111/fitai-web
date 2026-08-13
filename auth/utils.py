# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""认证工具：密码哈希、用户管理、会话管理"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Optional, Tuple

from sqlalchemy import func, select, text

from database import AsyncSessionLocal, engine, Base
from models.user import User

AUTH_COOKIE_NAME = "fitai_token"
_AUTH_SESSION_PREFIX = "auth.session."
TOKEN_EXPIRY = 86400

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LEN = 32
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{3,32}$")


def validate_password(password: str) -> Tuple[bool, str]:
    if len(password) < 8:
        return False, "密码至少8位"
    if not (any(c.isupper() for c in password) and any(c.islower() for c in password) and any(c.isdigit() for c in password)):
        return False, "密码必须同时包含大写字母、小写字母和数字"
    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    if not _USERNAME_PATTERN.fullmatch(username.strip()):
        return False, "账号只能包含字母、数字、点、下划线、@ 和中划线，长度 3-32 位"
    return True, ""


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_KEY_LEN)
    return "$".join(["scrypt", str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P), _b64encode(salt), _b64encode(derived)])


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if not stored_hash.startswith("scrypt$"):
        return False
    parts = stored_hash.split("$")
    if len(parts) != 6:
        return False
    try:
        derived = hashlib.scrypt(password.encode("utf-8"), salt=_b64decode(parts[4]), n=int(parts[1]), r=int(parts[2]), p=int(parts[3]), dklen=_SCRYPT_KEY_LEN)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64encode(derived), parts[5])


# ── User CRUD ───────────────────────────────────────────────────

async def create_user(username: str, password: str, email: str | None = None, is_admin: bool = False) -> Tuple[bool, str, dict | None]:
    valid, msg = validate_username(username)
    if not valid:
        return False, msg, None
    valid, msg = validate_password(password)
    if not valid:
        return False, msg, None
    normalized = username.strip()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == normalized))
        if result.scalar_one_or_none() is not None:
            return False, "用户名已存在", None
        user = User(username=normalized, hashed_password=hash_password(password), email=email.strip() if email else None, is_admin=is_admin)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return True, "注册成功" if not is_admin else "管理员账号创建成功", {"id": user.id, "username": user.username, "is_admin": user.is_admin}


async def get_user_by_username(username: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username.strip()))
        user = result.scalar_one_or_none()
        return {"id": user.id, "username": user.username, "hashed_password": user.hashed_password, "is_admin": user.is_admin} if user else None


async def get_user_by_id(user_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        return {"id": user.id, "username": user.username, "hashed_password": user.hashed_password, "is_admin": user.is_admin} if user else None


async def count_users() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar() or 0


async def get_all_users() -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.created_at.desc()))
        return [{"id": u.id, "username": u.username, "is_admin": u.is_admin, "email": u.email, "created_at": u.created_at.isoformat() if u.created_at else None} for u in result.scalars().all()]


async def delete_user_by_id(user_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return False
        await session.delete(user)
        await session.commit()
        return True


async def set_user_admin(user_id: int, is_admin: bool) -> bool:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return False
        user.is_admin = is_admin
        await session.commit()
        return True


# ── Registration toggle ─────────────────────────────────────────

async def is_registration_allowed() -> bool:
    user_count = await count_users()
    if user_count == 0:
        return True
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT value FROM settings WHERE key = 'auth.registration_open'"))
        row = result.fetchone()
        return json.loads(row[0]) is True if row else False


async def set_registration_allowed(allowed: bool) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("INSERT OR REPLACE INTO settings (key, value) VALUES ('auth.registration_open', :v)"), {"v": json.dumps(allowed)})
        await session.commit()


# ── Session management ──────────────────────────────────────────

def _session_key(token: str) -> str:
    return f"{_AUTH_SESSION_PREFIX}{hashlib.sha256(token.encode('utf-8')).hexdigest()}"


async def create_session(username: str, user_id: int) -> str:
    await _ensure_settings_table()
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"username": username, "user_id": user_id, "created_at": time.time()})
    async with AsyncSessionLocal() as session:
        await session.execute(text("INSERT OR REPLACE INTO settings (key, value) VALUES (:k, :v)"), {"k": _session_key(token), "v": payload})
        await session.commit()
    return token


async def validate_session(token: str) -> Optional[Tuple[str, int]]:
    if not token:
        return None
    key = _session_key(token)
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key})
        row = result.fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        if not isinstance(data, dict):
            return None
        username = data.get("username")
        user_id = data.get("user_id")
        created_at = data.get("created_at")
        if not isinstance(username, str) or not username:
            return None
        try:
            user_id = int(user_id)
            created_at = float(created_at)
        except (TypeError, ValueError):
            return None
        if time.time() - created_at > TOKEN_EXPIRY:
            await session.execute(text("DELETE FROM settings WHERE key = :k"), {"k": key})
            await session.commit()
            return None
        return (username, user_id)


async def revoke_session(token: str) -> bool:
    if not token:
        return False
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("DELETE FROM settings WHERE key = :k"), {"k": _session_key(token)})
        await session.commit()
        return result.rowcount > 0


async def revoke_all_sessions(user_id: Optional[int] = None) -> int:
    removed = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT key, value FROM settings WHERE key LIKE :p"), {"p": f"{_AUTH_SESSION_PREFIX}%"})
        for row in result:
            data = json.loads(row[1])
            if not isinstance(data, dict):
                continue
            if user_id is not None and data.get("user_id") == user_id:
                await session.execute(text("DELETE FROM settings WHERE key = :k"), {"k": row[0]})
                removed += 1
            elif time.time() - float(data.get("created_at", 0)) > TOKEN_EXPIRY:
                await session.execute(text("DELETE FROM settings WHERE key = :k"), {"k": row[0]})
                removed += 1
        if removed:
            await session.commit()
    return removed


async def _ensure_settings_table():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
