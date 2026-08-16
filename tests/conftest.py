# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Shared fixtures for FitAI-web tests."""
import os
import sys
import pytest
import sqlite3

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 隔离 SQLAlchemy async 层（auth）：指向临时文件，避免污染真实 data/fitai.db
# 必须在 import database / server 之前设置（本模块在测试收集期最先加载）
import tempfile
_TEST_DB_DIR = tempfile.mkdtemp(prefix="fitai_test_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_DIR}/auth.db"


@pytest.fixture
def test_db():
    """In-memory SQLite database with full schema for testing."""
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    # Create all application tables
    db.executescript("""
        CREATE TABLE IF NOT EXISTS workout_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_name TEXT NOT NULL,
            sets INTEGER,
            reps INTEGER,
            weight_kg REAL,
            duration_minutes REAL,
            rpe INTEGER DEFAULT NULL,
            date TEXT DEFAULT (date('now')),
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS body_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weight_kg REAL,
            body_fat_pct REAL,
            date TEXT DEFAULT (date('now')),
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS nutrition_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL DEFAULT (date('now')),
            meal_type TEXT,
            food_name TEXT NOT NULL,
            calories REAL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS health_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            source_platform TEXT NOT NULL,
            data_type TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            detail_json TEXT,
            synced_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS health_daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            data_type TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            source_platform TEXT
        );
        CREATE TABLE IF NOT EXISTS workout_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_name TEXT NOT NULL,
            sets INTEGER,
            reps INTEGER,
            weight_kg REAL,
            duration_minutes REAL,
            date TEXT,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            token_type TEXT DEFAULT 'Bearer',
            expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS health_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            status TEXT DEFAULT 'running',
            started_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT,
            records_synced INTEGER DEFAULT 0,
            error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS user_profile (
            user_id INTEGER PRIMARY KEY,
            name TEXT DEFAULT '',
            gender TEXT DEFAULT '',
            birth_year INTEGER,
            height_cm REAL,
            weight_kg REAL,
            fitness_goal TEXT DEFAULT '',
            activity_level TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            coach_style TEXT DEFAULT 'friend',
            equipment TEXT DEFAULT '',
            experience_level TEXT DEFAULT '',
            time_per_session TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS import_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT DEFAULT 'queued',
            filename TEXT,
            platform TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT,
            records_count INTEGER DEFAULT 0,
            error_message TEXT
        );
    """)

    yield db
    db.close()


@pytest.fixture
def user_id():
    return 1


@pytest.fixture
def monkeypatch_fitai_db(monkeypatch, test_db):
    """Monkey-patch tools.fitai_database.get_db to return test DB."""
    import tools.fitai_database as fidb

    def mock_get_db():
        return test_db

    monkeypatch.setattr(fidb, "get_db", mock_get_db)

    # Also patch init_db to create tables
    def mock_init_db():
        pass  # Tables already created in test_db fixture

    monkeypatch.setattr(fidb, "init_db", mock_init_db)
    return test_db


@pytest.fixture
def client(monkeypatch_fitai_db, monkeypatch):
    """TestClient + 已认证测试用户（Bearer token），双 DB 层隔离。"""
    import uuid as _uuid
    import asyncio as _asyncio

    # lifespan 里 init_fitai_db 绑定的是原 init_db（绕过 monkeypatch_fitai_db 的 init_db patch），需额外 patch
    import core.lifespan as lifespan_mod
    monkeypatch.setattr(lifespan_mod, "init_fitai_db", lambda: None)

    # 避免后台 import worker 线程干扰测试
    import routers.import_data as import_data
    monkeypatch.setattr(import_data, "start_import_worker", lambda: None)

    from fastapi.testclient import TestClient
    from server import app

    # 直接创建用户 + session token（绕开 secure cookie 与 registration 关闭）
    from auth.utils import create_user, create_session
    username = f"test_{_uuid.uuid4().hex[:8]}"
    password = "TestPass123"

    async def _setup():
        from database import init_db
        await init_db()  # 建 users/settings 表
        ok, msg, info = await create_user(username, password)
        assert ok, f"create_user failed: {msg}"
        return await create_session(username, info["id"])

    token = _asyncio.run(_setup())

    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
