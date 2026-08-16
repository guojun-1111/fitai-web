# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""应用生命周期：初始化数据库、启动后台 import worker、处理 setup secret。"""
from contextlib import asynccontextmanager
from pathlib import Path

from loguru import logger

from config import FITAI_PORT
from database import init_db
from tools.fitai_database import init_db as init_fitai_db
from auth.middleware import _ensure_setup_secret, _clear_setup_secret
from auth.utils import count_users

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


@asynccontextmanager
async def lifespan(app):
    await init_db()
    init_fitai_db()
    print(f"Database initialized at {PROJECT_ROOT / 'data' / 'fitai.db'}")

    # 启动后台导入 worker
    import threading as _thr
    from routers.import_data import start_import_worker
    _thr.Thread(target=start_import_worker, daemon=True).start()
    print("Import worker started")

    user_count = await count_users()
    if user_count > 0:
        _clear_setup_secret(app)
    else:
        secret = _ensure_setup_secret(app)
        print(f"\n{'='*60}")
        print(f"  首次初始化入口：/setup/{secret}")
        print(f"  本地访问: http://localhost:{FITAI_PORT}")
        print(f"{'='*60}\n")
        try:
            (PROJECT_ROOT / "data" / ".setup_url").write_text(f"Setup URL: /setup/{secret}\n")
        except Exception as e:
            logger.warning(f"Failed to write setup URL: {e}")

    yield
