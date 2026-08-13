# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitAI 数据库层 — 从 FitAI/database.py 移植，所有表增加 user_id 实现多用户隔离"""
import sqlite3
import atexit
import threading
import os
import hashlib
import base64
from datetime import date, timedelta
from pathlib import Path

DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DB_DIR / "fitai.db")

_db_conn = None
_db_lock = threading.Lock()


def get_db():
    """返回模块级单例连接，避免每次查询创建新连接导致泄漏"""
    global _db_conn
    if _db_conn is None:
        with _db_lock:
            if _db_conn is None:
                _db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
                _db_conn.row_factory = sqlite3.Row
                _db_conn.execute("PRAGMA journal_mode=WAL")
                _db_conn.execute("PRAGMA foreign_keys=ON")
                # V17: composite indexes for frequent query patterns
                _db_conn.execute("CREATE INDEX IF NOT EXISTS idx_workout_user_date ON workout_logs(user_id, date)")
                _db_conn.execute("CREATE INDEX IF NOT EXISTS idx_body_user_date ON body_metrics(user_id, date)")
                _db_conn.execute("CREATE INDEX IF NOT EXISTS idx_nutrition_user_date ON nutrition_logs(user_id, date)")
                _db_conn.execute("CREATE INDEX IF NOT EXISTS idx_oauth_user_platform ON oauth_tokens(user_id, platform, updated_at)")
    return _db_conn


def close_db():
    global _db_conn
    if _db_conn:
        _db_conn.close()
        _db_conn = None


atexit.register(close_db)


def _ensure_column(conn, table, column, col_type="TEXT"):
    """Add a column if it doesn't exist (safe migration)."""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workout_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL DEFAULT (date('now')),
            exercise_name TEXT NOT NULL,
            sets INTEGER,
            reps INTEGER,
            weight_kg REAL,
            duration_minutes INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_workout_user ON workout_logs(user_id);

        CREATE TABLE IF NOT EXISTS body_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL DEFAULT (date('now')),
            weight_kg REAL,
            body_fat_pct REAL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_body_user ON body_metrics(user_id);

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
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_nutrition_user ON nutrition_logs(user_id);

        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expires_at REAL NOT NULL,
            scopes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, platform)
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
            synced_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, source_platform, data_type, date)
        );

        CREATE TABLE IF NOT EXISTS health_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            records_fetched INTEGER DEFAULT 0,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS platform_config (
            platform TEXT NOT NULL UNIQUE,
            client_id TEXT NOT NULL DEFAULT '',
            client_secret TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            birth_year INTEGER,
            gender TEXT NOT NULL DEFAULT '',
            height_cm REAL,
            weight_kg REAL,
            fitness_goal TEXT NOT NULL DEFAULT '',
            activity_level TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id, created_at);

        CREATE TABLE IF NOT EXISTS workout_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            workout_type TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_seconds INTEGER,
            avg_heart_rate REAL,
            max_heart_rate REAL,
            heart_rate_data_json TEXT,
            calories_burned REAL,
            device_name TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS heart_rate_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id INTEGER REFERENCES workout_sessions(id),
            timestamp REAL NOT NULL,
            heart_rate INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS health_daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            data_type TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            source_platform TEXT,
            UNIQUE(user_id, date, data_type)
        );

        CREATE TABLE IF NOT EXISTS import_jobs (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            filename TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER DEFAULT 0,
            result_json TEXT,
            error_msg TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_import_jobs_user_status ON import_jobs(user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_user_platform ON health_sync_log(user_id, platform)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wsessions_user_date ON workout_sessions(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hr_samples_user_session ON heart_rate_samples(user_id, session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_user_type_date ON health_data(user_id, data_type, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_user_date ON health_data(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_summary_user_date ON health_daily_summary(user_id, date)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS exercise_library (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            name_zh TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            body_part TEXT NOT NULL,
            equipment TEXT NOT NULL,
            instructions_zh TEXT,
            instructions_en TEXT,
            image_url TEXT DEFAULT '',
            difficulty_level INTEGER DEFAULT 3,
            compound_score REAL DEFAULT 0.5
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exlib_category ON exercise_library(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exlib_bodypart ON exercise_library(body_part)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exlib_equipment ON exercise_library(equipment)")

    # V24: Auto-seed exercise library if table is empty
    row = conn.execute("SELECT COUNT(*) FROM exercise_library").fetchone()
    if row[0] == 0:
        try:
            import_exercise_library()
        except Exception as e:
            pass  # Non-fatal; data can be imported later via API

    # V20: wechat_session_key migration (SQLAlchemy users table)
    _ensure_column(conn, "users", "wechat_session_key", "TEXT(256)")

    # V29: coach_style for cross-generational AI persona
    _ensure_column(conn, "user_profile", "coach_style", "TEXT DEFAULT 'friend'")
    # V34: equipment, experience, time_per_session for plan personalization
    _ensure_column(conn, "user_profile", "equipment", "TEXT DEFAULT ''")
    _ensure_column(conn, "user_profile", "experience_level", "TEXT DEFAULT ''")
    _ensure_column(conn, "user_profile", "time_per_session", "TEXT DEFAULT ''")

    # V15: 训练计划
    conn.execute("""
        CREATE TABLE IF NOT EXISTS training_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            goal TEXT NOT NULL DEFAULT '',
            weeks INTEGER NOT NULL DEFAULT 4,
            plan_data TEXT NOT NULL DEFAULT '{}',
            day_progress TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_training_plans_user ON training_plans(user_id)")

    # V20: 训练反馈
    conn.execute("""
        CREATE TABLE IF NOT EXISTS training_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            rpe INTEGER,
            difficulty TEXT,
            soreness TEXT,
            sore_areas TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user_plan ON training_feedback(user_id, plan_id)")

    # V16: 订阅与支付
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_type TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',
            start_date TEXT DEFAULT (datetime('now')),
            end_date TEXT,
            payment_provider TEXT DEFAULT '',
            provider_subscription_id TEXT DEFAULT '',
            auto_renew INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subscription_id INTEGER,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            provider TEXT NOT NULL DEFAULT '',
            provider_payment_id TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id)")

    # V7.0: 如果旧表缺少 rpe 列，自动添加（安全迁移）
    for col_migration in [
        "ALTER TABLE workout_logs ADD COLUMN rpe INTEGER DEFAULT NULL",
    ]:
        try:
            conn.execute(col_migration)
        except sqlite3.OperationalError:
            pass  # 列已存在，跳过

    conn.commit()
    return conn


# ── 写入函数（均增加 user_id 参数）─────────────────────────────

def insert_workout(user_id: int, exercise_name, sets=None, reps=None, weight_kg=None, duration_minutes=None, notes=None, date=None, rpe=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO workout_logs (user_id, date, exercise_name, sets, reps, weight_kg, duration_minutes, notes, rpe) VALUES (?, COALESCE(?, date('now')), ?, ?, ?, ?, ?, ?, ?)",
        (user_id, date, exercise_name, sets, reps, weight_kg, duration_minutes, notes, rpe),
    )
    conn.commit()
    # 计算 sRPE 用于展示
    srpe_str = ""
    if rpe and duration_minutes:
        srpe_str = f"，sRPE负荷={rpe * float(duration_minutes):.0f}"
    return f"已记录训练: {exercise_name}{srpe_str}"


def insert_body_metric(user_id: int, weight_kg=None, body_fat_pct=None, notes=None, date=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO body_metrics (user_id, date, weight_kg, body_fat_pct, notes) VALUES (?, COALESCE(?, date('now')), ?, ?, ?)",
        (user_id, date, weight_kg, body_fat_pct, notes),
    )
    conn.commit()
    return "已记录体测数据"


def insert_nutrition(user_id: int, meal_type=None, food_name=None, calories=None, protein_g=None, carbs_g=None, fat_g=None, notes=None, date=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO nutrition_logs (user_id, date, meal_type, food_name, calories, protein_g, carbs_g, fat_g, notes) VALUES (?, COALESCE(?, date('now')), ?, ?, ?, ?, ?, ?, ?)",
        (user_id, date, meal_type, food_name, calories, protein_g, carbs_g, fat_g, notes),
    )
    conn.commit()
    return f"已记录饮食: {food_name}"


# ── 查询函数（均增加 user_id 过滤）─────────────────────────────

def get_workout_history(user_id: int, days=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM workout_logs WHERE user_id = ? AND date >= date('now', ?) ORDER BY date DESC LIMIT 50",
        (user_id, f"-{days} days"),
    ).fetchall()
    if not rows:
        return f"最近{days}天暂无训练记录。"
    lines = [f"最近{days}天训练记录:"]
    for r in rows:
        parts = [f"- {r['date']}: {r['exercise_name']}"]
        if r['sets']: parts.append(f"{r['sets']}组")
        if r['reps']: parts.append(f"x{r['reps']}次")
        if r['weight_kg']: parts.append(f"{r['weight_kg']}kg")
        if r['duration_minutes']: parts.append(f"{r['duration_minutes']}分钟")
        if r['notes']: parts.append(f"({r['notes']})")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def get_body_metrics_history(user_id: int, days=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM body_metrics WHERE user_id = ? AND date >= date('now', ?) ORDER BY date DESC LIMIT 50",
        (user_id, f"-{days} days"),
    ).fetchall()
    if not rows:
        return f"最近{days}天暂无体测记录。"
    lines = [f"最近{days}天体测记录:"]
    for r in rows:
        parts = [f"- {r['date']}:"]
        if r['weight_kg']: parts.append(f"体重{r['weight_kg']}kg")
        if r['body_fat_pct']: parts.append(f"体脂率{r['body_fat_pct']}%")
        if r['notes']: parts.append(f"({r['notes']})")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def get_nutrition_history(user_id: int, days=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM nutrition_logs WHERE user_id = ? AND date >= date('now', ?) ORDER BY date DESC LIMIT 50",
        (user_id, f"-{days} days"),
    ).fetchall()
    if not rows:
        return f"最近{days}天暂无饮食记录。"
    lines = [f"最近{days}天饮食记录:"]
    for r in rows:
        parts = [f"- {r['date']}:"]
        if r['meal_type']: parts.append(f"[{r['meal_type']}]")
        parts.append(r['food_name'])
        if r['calories']: parts.append(f"{r['calories']}千卡")
        if r['protein_g']: parts.append(f"蛋白质{r['protein_g']}g")
        if r['notes']: parts.append(f"({r['notes']})")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def get_workout_history_json(user_id: int, days=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM workout_logs WHERE user_id = ? AND date >= date('now', ?) ORDER BY date ASC",
        (user_id, f"-{days} days"),
    ).fetchall()
    return [dict(r) for r in rows]


def get_body_metrics_history_json(user_id: int, days=90):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM body_metrics WHERE user_id = ? AND date >= date('now', ?) ORDER BY date ASC",
        (user_id, f"-{days} days"),
    ).fetchall()
    return [dict(r) for r in rows]


def get_nutrition_history_json(user_id: int, days=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM nutrition_logs WHERE user_id = ? AND date >= date('now', ?) ORDER BY date ASC",
        (user_id, f"-{days} days"),
    ).fetchall()
    return [dict(r) for r in rows]


def get_health_data_history(user_id: int, days=30):
    conn = get_db()
    rows = conn.execute("""
        SELECT date, source_platform, data_type, value, unit FROM health_data
        WHERE user_id = ? AND date >= date('now', ?)
        UNION
        SELECT date, source_platform, data_type, value, unit FROM health_daily_summary
        WHERE user_id = ? AND date >= date('now', ?)
        ORDER BY date DESC LIMIT 100
    """, (user_id, f"-{days} days", user_id, f"-{days} days")).fetchall()
    if not rows:
        return f"最近{days}天暂无健康数据。"
    lines = [f"最近{days}天健康数据:"]
    for r in rows:
        lines.append(f"- {r['date']} [{r['source_platform']}] {r['data_type']}: {r['value']} {r['unit'] or ''}")
    return "\n".join(lines)


def get_health_data_history_json(user_id: int, days=30):
    """查询健康数据——联合热数据表和归档汇总表。"""
    conn = get_db()
    rows = conn.execute("""
        SELECT date, source_platform, data_type, value, unit FROM health_data
        WHERE user_id = ? AND date >= date('now', ?)
        UNION
        SELECT date, source_platform, data_type, value, unit FROM health_daily_summary
        WHERE user_id = ? AND date >= date('now', ?)
        ORDER BY date ASC
    """, (user_id, f"-{days} days", user_id, f"-{days} days")).fetchall()
    return [dict(r) for r in rows]


def get_streak(user_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT date FROM workout_logs WHERE user_id = ? ORDER BY date DESC LIMIT 60",
        (user_id,),
    ).fetchall()
    if not rows:
        return 0
    today_str = rows[0]["date"]
    if today_str < date.today().isoformat():
        return 0
    streak = 1
    for i in range(1, len(rows)):
        prev = date.fromisoformat(rows[i-1]["date"])
        curr = date.fromisoformat(rows[i]["date"])
        if (prev - curr).days == 1:
            streak += 1
        else:
            break
    return streak


def get_user_profile(user_id: int) -> dict | None:
    """Return full user_profile row as dict, or None if not found."""
    conn = get_db()
    row = conn.execute("SELECT * FROM user_profile WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_profile_summary(user_id: int) -> str:
    conn = get_db()
    row = conn.execute("SELECT * FROM user_profile WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return ""
    parts = []
    if row["name"]: parts.append(f"姓名: {row['name']}")
    if row["birth_year"]: parts.append(f"出生年份: {row['birth_year']}")
    if row["gender"]: parts.append(f"性别: {row['gender']}")
    if row["height_cm"]: parts.append(f"身高: {row['height_cm']}cm")
    if row["weight_kg"]: parts.append(f"体重: {row['weight_kg']}kg")
    if row["fitness_goal"]: parts.append(f"健身目标: {row['fitness_goal']}")
    if row["activity_level"]: parts.append(f"活动水平: {row['activity_level']}")
    return " / ".join(parts) if parts else ""


def save_chat_message(user_id: int, session_id: str, role: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_history (user_id, session_id, role, content) VALUES (?, ?, ?, ?)",
        (user_id, session_id, role, content),
    )
    conn.commit()


def get_chat_history(user_id: int, session_id: str, limit: int = 50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chat_history WHERE user_id = ? AND session_id = ? ORDER BY created_at ASC LIMIT ?",
        (user_id, session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_chat_sessions(user_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT session_id, MIN(created_at) as created_at FROM chat_history WHERE user_id = ? GROUP BY session_id ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_chat_session(user_id: int, session_id: str):
    conn = get_db()
    conn.execute("DELETE FROM chat_history WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    conn.commit()


# OAuth token encryption helpers
_ENCRYPTION_KEY = os.getenv("ENCRYPTION_SECRET_KEY", "")

def _derive_key(user_id: int, platform: str) -> bytes:
    """Derive a per-token encryption key from the master secret."""
    raw = f"{_ENCRYPTION_KEY}:{user_id}:{platform}".encode("utf-8")
    return hashlib.sha256(raw).digest()

def _encrypt_token(plaintext: str, user_id: int, platform: str) -> str:
    """XOR encrypt + base64 encode a token for storage."""
    if not plaintext:
        return ""
    key = _derive_key(user_id, platform)
    data = plaintext.encode("utf-8")
    encrypted = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")

def _decrypt_token(ciphertext: str, user_id: int, platform: str) -> str:
    """Base64 decode + XOR decrypt a stored token."""
    if not ciphertext:
        return ""
    try:
        key = _derive_key(user_id, platform)
        encrypted = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        decrypted = bytes(encrypted[i] ^ key[i % len(key)] for i in range(len(encrypted)))
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def save_wechat_session_key(user_id: int, session_key: str):
    """Encrypt and persist WeChat session_key to users table."""
    conn = get_db()
    encrypted = _encrypt_token(session_key, user_id, "wechat")
    conn.execute(
        "UPDATE users SET wechat_session_key = ? WHERE id = ?",
        (encrypted, user_id),
    )
    conn.commit()


def get_wechat_session_key(user_id: int) -> str:
    """Retrieve and decrypt WeChat session_key from users table."""
    conn = get_db()
    row = conn.execute(
        "SELECT wechat_session_key FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row or not row["wechat_session_key"]:
        return ""
    return _decrypt_token(row["wechat_session_key"], user_id, "wechat")


def decrypt_wechat_werun(encrypted_data_b64: str, iv_b64: str, session_key_b64: str) -> dict:
    """Decrypt WeChat wx.getWeRunData() encrypted payload.

    WeChat uses AES-128-CBC with PKCS#7 padding.
    session_key_b64 is the base64-encoded key from wx.login() → code2session.
    Returns the parsed stepInfoList: { stepInfoList: [{timestamp, step}] }
    """
    from Crypto.Cipher import AES
    session_key = base64.b64decode(session_key_b64)
    iv = base64.b64decode(iv_b64)
    ciphertext = base64.b64decode(encrypted_data_b64)
    cipher = AES.new(session_key, AES.MODE_CBC, iv=iv)
    plaintext = cipher.decrypt(ciphertext)
    pad_len = plaintext[-1]
    plaintext = plaintext[:-pad_len]
    return __import__('json').loads(plaintext.decode('utf-8'))

def save_oauth_token(platform: str, access_token: str, refresh_token=None, expires_at=None, scopes=None, user_id: int = 1):
    conn = get_db()
    encrypted_access = _encrypt_token(access_token, user_id, platform)
    encrypted_refresh = _encrypt_token(refresh_token or "", user_id, platform)
    conn.execute(
        "INSERT OR REPLACE INTO oauth_tokens (user_id, platform, access_token, refresh_token, expires_at, scopes, updated_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (user_id, platform, encrypted_access, encrypted_refresh, expires_at or 0, scopes),
    )
    conn.commit()


def get_last_sync_info(platform: str, user_id: int = 1):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM health_sync_log WHERE user_id = ? AND platform = ? ORDER BY started_at DESC LIMIT 1",
        (user_id, platform),
    ).fetchone()
    return dict(row) if row else None


def get_oauth_token(platform: str, user_id: int = 1):
    """获取已保存的 OAuth token。返回 dict 或 None。自动解密。"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM oauth_tokens WHERE user_id = ? AND platform = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id, platform),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["access_token"] = _decrypt_token(result.get("access_token", ""), user_id, platform)
    result["refresh_token"] = _decrypt_token(result.get("refresh_token", ""), user_id, platform)
    return result


def insert_sync_log(platform: str, user_id: int = 1):
    """插入一条同步日志，返回 log_id。"""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO health_sync_log (user_id, platform, started_at, status) VALUES (?, ?, datetime('now'), 'running')",
        (user_id, platform),
    )
    conn.commit()
    return cur.lastrowid


def update_sync_log(log_id: int, status: str, records_fetched: int = 0, error_message: str = None):
    """更新同步日志状态。"""
    conn = get_db()
    conn.execute(
        "UPDATE health_sync_log SET status = ?, records_fetched = ?, error_message = ?, finished_at = datetime('now') WHERE id = ?",
        (status, records_fetched, error_message, log_id),
    )
    conn.commit()


def insert_health_data(user_id: int, date: str, source_platform: str, data_type: str, value: float, unit: str = "", detail_json: str = None):
    """插入单条健康数据。便捷封装，内部调用批量写入。"""
    return insert_health_data_batch(user_id, [{
        "date": date, "source_platform": source_platform,
        "data_type": data_type, "value": value,
        "unit": unit, "detail_json": detail_json,
    }])


def insert_health_data_batch(user_id: int, records: list):
    """records: list of dicts with keys: date, source_platform, data_type, value, unit, detail_json。
    使用 executemany + 显式事务大幅提升写入性能。"""
    if not records:
        return 0
    conn = get_db()
    # V14: Per-type sanity limits (last line of defense)
    _VAL_MAX = {"steps": 100000, "heart_rate": 220, "sleep": 1440, "calories": 10000,
                "spo2": 100, "weight": 500, "body_fat": 60, "blood_pressure_sys": 300,
                "blood_pressure_dia": 200, "blood_glucose": 35, "exercise": 1440}
    _VAL_MIN = {"heart_rate": 30, "spo2": 50, "sleep": 10, "calories": 10}

    valid = []
    for r in records:
        try:
            val = float(r["value"])
            dt = r["data_type"]
            if val <= 0:
                continue
            if dt in _VAL_MAX and val > _VAL_MAX[dt]:
                continue
            if dt in _VAL_MIN and val < _VAL_MIN[dt]:
                continue
            valid.append((
                user_id, r["date"], r["source_platform"], dt,
                val, r.get("unit") or "", r.get("detail_json"),
            ))
        except (KeyError, ValueError, TypeError):
            pass
    if not valid:
        return 0
    conn.execute("BEGIN IMMEDIATE")
    conn.executemany(
        "INSERT OR REPLACE INTO health_data (user_id, date, source_platform, data_type, value, unit, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        valid,
    )
    conn.commit()
    return len(valid)


# ── Exercise Library (V7) ───────────────────────────────────────

def import_exercise_library(json_path: str = None):
    """从 JSON 文件导入 1,324 个标准健身动作到 exercise_library 表。"""
    import json
    if json_path is None:
        json_path = str(DB_DIR / "exercises_library.json")
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    conn = get_db()
    # Difficulty heuristic: body_weight = easy(2), dumbbell = medium(3), barbell = hard(4)
    equip_rank = {"body weight": 2, "dumbbell": 3, "cable": 3, "kettlebell": 3,
                   "barbell": 4, "leverage machine": 3, "smith machine": 4,
                   "sled machine": 4, "olympic barbell": 5, "ez barbell": 3}
    compound_cats = {"chest": 0.6, "back": 0.7, "upper legs": 0.8, "waist": 0.3,
                      "upper arms": 0.3, "shoulders": 0.5, "cardio": 0.2, "lower legs": 0.4,
                      "lower arms": 0.2, "neck": 0.1}

    count = 0
    for e in data:
        eid = e.get("id", "")
        name = e.get("name", "")
        inst = e.get("instructions", {})
        zh = inst.get("zh", "")
        en = inst.get("en", "")
        cat = e.get("category", "")
        bp = e.get("body_part", "")
        eq = e.get("equipment", "")
        difficulty = equip_rank.get(eq, 3)
        compound = compound_cats.get(bp, 0.3)
        media_id = e.get("media_id", "")
        img_url = f"https://static.exercisedb.dev/media/{media_id}.gif" if media_id else ""

        conn.execute(
            "INSERT OR REPLACE INTO exercise_library (id, name, name_zh, category, body_part, equipment, instructions_zh, instructions_en, image_url, difficulty_level, compound_score) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (eid, name, name, cat, bp, eq, zh, en, img_url, difficulty, round(compound, 1))
        )
        count += 1
    conn.commit()
    return count


def search_exercises_db(category=None, body_part=None, equipment=None, keyword=None, limit=50):
    """搜索动作库。"""
    conn = get_db()
    conditions = []
    params = []
    if category:
        conditions.append("category = ?")
        params.append(category)
    if body_part:
        conditions.append("body_part = ?")
        params.append(body_part)
    if equipment:
        conditions.append("equipment = ?")
        params.append(equipment)
    if keyword:
        conditions.append("(name LIKE ? OR instructions_zh LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM exercise_library WHERE {where} ORDER BY difficulty_level LIMIT ?",
        params + [limit]
    ).fetchall()
    results = [dict(r) for r in rows]
    # V36: 修复中文名——DB 中 name_zh 在导入时被填了英文，这里做运行时翻译
    _fix_exercise_names(results)
    return results


def _fix_exercise_names(exercises: list) -> None:
    """V36: 确保 name_zh 有中文值。优先用 EXERCISE_ZH 字典，不行从 instructions_zh 提取。"""
    try:
        from fitai.knowledge.fitkg import EXERCISE_ZH
    except ImportError:
        EXERCISE_ZH = {}
    for ex in exercises:
        name = ex.get("name", "")
        # 如果 name_zh 已经是中文，跳过
        if ex.get("name_zh") and any('一' <= c <= '鿿' for c in ex["name_zh"]):
            continue
        # 策略1: 查字典
        zh = EXERCISE_ZH.get(name.lower(), "")
        if zh:
            ex["name_zh"] = zh
            continue
        # 策略2: 从 instructions_zh 提取中文（取第一句的前15字）
        inst = ex.get("instructions_zh", "")
        if inst:
            # 找第一个中文句号或逗号前的文字
            for sep in ("。", "，", "、", "\n"):
                idx = inst.find(sep)
                if idx > 3:
                    inst = inst[:idx]
                    break
            clean = inst.strip()[:15]
            if clean and any('一' <= c <= '鿿' for c in clean):
                ex["name_zh"] = clean
                continue
        # 策略3: 保留现有值（英文）


def get_exercise_by_id(exercise_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM exercise_library WHERE id = ?", (exercise_id,)).fetchone()
    return dict(row) if row else None


def get_exercise_categories():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM exercise_library ORDER BY category").fetchall()
    return [r["category"] for r in rows]


def get_exercise_equipment():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT equipment FROM exercise_library ORDER BY equipment").fetchall()
    return [r["equipment"] for r in rows]


def archive_old_health_data(user_id=None, older_than_days=7):
    """将旧数据归档到 health_daily_summary 表。
    - 只归入 daily_summary（不删原数据，需手动运行 cleanup_archived_data 清理）
    - V14: 心率/血氧/血糖用 AVG(value)，步数/卡路里/睡眠用 MAX(value)
    返回归档条数。"""
    conn = get_db()
    uid_filter = "AND user_id = ?" if user_id else ""
    params = (user_id,) if user_id else ()

    # V14: avg_types use AVG instead of MAX (heart rate, spO2, blood glucose)
    conn.execute("BEGIN IMMEDIATE")
    count = 0

    # MAX-based types: steps, calories, sleep, exercise, weight, body_fat, blood_pressure
    c1 = conn.execute(f"""
        INSERT OR REPLACE INTO health_daily_summary (user_id, date, data_type, value, unit, source_platform)
        SELECT user_id, date, data_type, MAX(value), MAX(unit), MAX(source_platform)
        FROM health_data
        WHERE date < date('now', '-{older_than_days} days') {uid_filter}
        AND data_type NOT IN ('heart_rate', 'spo2', 'blood_glucose')
        GROUP BY user_id, date, data_type
    """, params).rowcount
    count += (c1 if c1 and c1 > 0 else 0)

    # AVG-based types: heart_rate, spo2, blood_glucose
    c2 = conn.execute(f"""
        INSERT OR REPLACE INTO health_daily_summary (user_id, date, data_type, value, unit, source_platform)
        SELECT user_id, date, data_type, AVG(value), MAX(unit), MAX(source_platform)
        FROM health_data
        WHERE date < date('now', '-{older_than_days} days') {uid_filter}
        AND data_type IN ('heart_rate', 'spo2', 'blood_glucose')
        GROUP BY user_id, date, data_type
    """, params).rowcount
    count += (c2 if c2 and c2 > 0 else 0)

    conn.commit()
    return count


def cleanup_archived_data(older_than_days=7):
    """删除已经归档到 health_daily_summary 的旧数据。归档验证通过后再执行此函数。"""
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    count = conn.execute(
        "DELETE FROM health_data WHERE date < date('now', ?)",
        (f"-{older_than_days} days",)
    ).rowcount
    conn.commit()
    return count
