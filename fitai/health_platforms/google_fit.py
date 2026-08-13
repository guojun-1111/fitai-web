# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Google Fit REST API 平台实现。"""
import time
import requests
from fitai.health_platforms.base import HealthPlatform
from config import GOOGLE_REDIRECT_URI

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_FITNESS_API = "https://www.googleapis.com/fitness/v1/users/me"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
]

DATA_TYPE_MAP = {
    "steps": "com.google.step_count.delta",
    "heart_rate": "com.google.heart_rate.bpm",
    "sleep": "com.google.sleep.segment",
    "calories": "com.google.calories.expended",
    "spo2": "com.google.oxygen_saturation",
}

UNIT_MAP = {
    "steps": "步",
    "heart_rate": "bpm",
    "sleep": "分钟",
    "calories": "千卡",
    "spo2": "%",
}


class GoogleFitPlatform(HealthPlatform):

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._scope_str = " ".join(GOOGLE_SCOPES)

    def get_platform_name(self) -> str:
        return "google_fit"

    def get_display_name(self) -> str:
        return "Google Fit"

    def get_device_list(self) -> str:
        return "Android · 小米手环 · Wear OS"

    def get_auth_url(self, state: str = "") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": self._scope_str,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        qs = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
        return f"{GOOGLE_AUTH_URL}?{qs}"

    def exchange_code(self, code: str) -> dict:
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        resp = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=15)
        resp.raise_for_status()
        token = resp.json()
        expires_at = time.time() + token.get("expires_in", 3600) - 60
        return {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token", ""),
            "expires_at": expires_at,
            "scopes": token.get("scope", self._scope_str),
        }

    def refresh_access_token(self, refresh_token: str) -> dict:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        resp = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=15)
        resp.raise_for_status()
        token = resp.json()
        expires_at = time.time() + token.get("expires_in", 3600) - 60
        return {"access_token": token["access_token"], "expires_at": expires_at}

    def fetch_data(self, access_token: str, data_types: list,
                   start_time_ms: int, end_time_ms: int) -> list:
        headers = {"Authorization": f"Bearer {access_token}"}
        results = []

        for dt in data_types:
            gf_type = DATA_TYPE_MAP.get(dt)
            if not gf_type:
                continue

            # V15: 心率/血氧用15分钟桶保留日内变化，步数/卡路里/睡眠保持日桶
            bucket_ms = 86400000 if data_type in ("steps", "calories", "sleep") else 900000
            body = {
                "aggregateBy": [{"dataTypeName": gf_type}],
                "bucketByTime": {"durationMillis": bucket_ms},
                "startTimeMillis": start_time_ms,
                "endTimeMillis": end_time_ms,
            }

            try:
                resp = requests.post(
                    f"{GOOGLE_FITNESS_API}/dataset:aggregate",
                    headers=headers,
                    json=body,
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[GoogleFit] fetch {dt} failed: {e}")
                continue

            for bucket in data.get("bucket", []):
                start_ms = int(bucket.get("startTimeMillis", 0))
                date_str = _ms_to_date(start_ms)
                value = _extract_value(bucket, dt)
                if value is not None:
                    detail = _extract_detail(bucket, dt)
                    results.append({
                        "date": date_str,
                        "source_platform": "google_fit",
                        "data_type": dt,
                        "value": value,
                        "unit": UNIT_MAP.get(dt, ""),
                        "detail_json": detail,
                    })

        return results


def _ms_to_date(ms: int) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d")


def _extract_value(bucket: dict, data_type: str) -> float | None:
    """从 bucket 中提取主值。"""
    datasets = bucket.get("dataset", [])
    for ds in datasets:
        points = ds.get("point", [])
        for p in points:
            vals = p.get("value", [])
            if not vals:
                continue
            if data_type == "steps":
                return sum(v.get("intVal", 0) for v in vals)
            elif data_type == "calories":
                return sum(v.get("fpVal", 0) for v in vals)
            elif data_type == "heart_rate":
                return _avg([v.get("fpVal", 0) for v in vals if v.get("fpVal")])
            elif data_type == "sleep":
                return _calc_sleep_duration(points)
            elif data_type == "spo2":
                vals_fp = [v.get("fpVal", 0) for v in vals if v.get("fpVal")]
                return _avg(vals_fp) if vals_fp else None
    return None


def _extract_detail(bucket: dict, data_type: str) -> str | None:
    """提取额外详情（如睡眠阶段）。"""
    import json
    datasets = bucket.get("dataset", [])
    if data_type == "sleep":
        stages = []
        for ds in datasets:
            for p in ds.get("point", []):
                for v in p.get("value", []):
                    if v.get("intVal"):
                        stages.append({"type": v.get("intVal"), "name": _sleep_type_name(v.get("intVal"))})
        if stages:
            return json.dumps(stages, ensure_ascii=False)
    return None


def _avg(lst: list) -> float | None:
    return round(sum(lst) / len(lst), 1) if lst else None


def _calc_sleep_duration(points: list) -> float | None:
    """计算实际睡眠时长（分钟）—— 排除清醒阶段后的有效睡眠时间。"""
    if not points:
        return None
    total_ns = 0
    for p in points:
        start = p.get("startTimeNanos", 0)
        end = p.get("endTimeNanos", 0)
        if not start or not end:
            continue
        # Skip awake stages (code 4 = 清醒)
        vals = p.get("value", [])
        is_awake = any(v.get("intVal") == 4 for v in vals)
        if not is_awake:
            total_ns += (end - start)
    if total_ns <= 0:
        return None
    return round(total_ns / 1e9 / 60, 1)


def _sleep_type_name(code: int) -> str:
    mapping = {1: "浅睡", 2: "深睡", 3: "REM", 4: "清醒"}
    return mapping.get(code, f"未知({code})")
