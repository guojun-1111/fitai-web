# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FitAI Web 配置 — 从环境变量加载"""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.resolve()
load_dotenv(PROJECT_ROOT / ".env")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_FAST_MODEL = os.getenv("LLM_FAST_MODEL", LLM_MODEL)

# Vision model for image analysis (separate from main text LLM)
LLM_VISION_PROVIDER = os.getenv("LLM_VISION_PROVIDER", "")
LLM_VISION_API_KEY = os.getenv("LLM_VISION_API_KEY", "")
LLM_VISION_BASE_URL = os.getenv("LLM_VISION_BASE_URL", "")
LLM_VISION_MODEL = os.getenv("LLM_VISION_MODEL", "")

FITAI_HOST = os.getenv("FITAI_HOST", "127.0.0.1")
FITAI_PORT = int(os.getenv("FITAI_PORT", "8000"))

DATABASE_PATH = PROJECT_ROOT / "data" / "fitai.db"

REMOTE_SETUP_SECRET_TTL_MINUTES = int(os.getenv("REMOTE_SETUP_SECRET_TTL_MINUTES", "30"))

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")

# Health platform placeholders (needed to prevent ImportError)
# CalorieNinjas — free food recognition API (10000 req/month)
CALORIENINJAS_API_KEY = os.getenv("CALORIENINJAS_API_KEY", "")

GOOGLE_FIT_CLIENT_ID = os.getenv("GOOGLE_FIT_CLIENT_ID", "")
GOOGLE_FIT_CLIENT_SECRET = os.getenv("GOOGLE_FIT_CLIENT_SECRET", "")
HUAWEI_HEALTH_CLIENT_ID = os.getenv("HUAWEI_HEALTH_CLIENT_ID", "")
HUAWEI_HEALTH_CLIENT_SECRET = os.getenv("HUAWEI_HEALTH_CLIENT_SECRET", "")
HEALTH_CONNECT_SERVER_URL = os.getenv("HEALTH_CONNECT_SERVER_URL", "")
HEALTH_CONNECT_ENCRYPTION_KEY = os.getenv("HEALTH_CONNECT_ENCRYPTION_KEY", "")
HEALTH_SYNC_INTERVAL_SECONDS = int(os.getenv("HEALTH_SYNC_INTERVAL_SECONDS", "1800"))
HEALTH_DATA_TYPES = os.getenv("HEALTH_DATA_TYPES", "steps,heart_rate,sleep,calories")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")
HUAWEI_REDIRECT_URI = os.getenv("HUAWEI_REDIRECT_URI", "")
FITBIT_CLIENT_ID = os.getenv("FITBIT_CLIENT_ID", "")
FITBIT_CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET", "")
FITBIT_REDIRECT_URI = os.getenv("FITBIT_REDIRECT_URI", "")

# WeChat Mini-Program
WECHAT_APPID = os.getenv("WECHAT_APPID", "")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
