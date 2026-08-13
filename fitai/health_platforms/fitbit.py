# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fitbit Web API 平台实现 — OAuth 2.0 + PKCE。"""
import hashlib
import base64
import secrets
import time
import requests
from fitai.health_platforms.base import HealthPlatform

FITBIT_AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
FITBIT_API_BASE = "https://api.fitbit.com/1/user/-"

FITBIT_SCOPES = ["activity", "heartrate", "sleep", "profile", "nutrition", "weight"]

# Fitbit API endpoints per data type (date-based, not range-based)
DATA_ENDPOINTS = {
    "steps": "/activities/steps/date/{date}/1d.json",
    "heart_rate": "/activities/heart/date/{date}/1d.json",
    "sleep": "/sleep/date/{date}.json",
    "calories": "/activities/calories/date/{date}/1d.json",
    "weight": "/body/log/weight/date/{date}.json",
    "body_fat": "/body/log/fat/date/{date}.json",
    "spo2": "/spo2/date/{date}.json",
}

UNIT_MAP = {
    "steps": "步", "heart_rate": "bpm", "sleep": "分钟",
    "calories": "千卡", "spo2": "%", "weight": "kg", "body_fat": "%",
}


def _generate_pkce() -> tuple[str, str]:
    """生成 PKCE code_verifier 和 code_challenge。"""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class FitbitPlatform(HealthPlatform):

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._scope_str = " ".join(FITBIT_SCOPES)

    def get_platform_name(self) -> str:
        return "fitbit"

    def get_display_name(self) -> str:
        return "Fitbit"

    def get_device_list(self) -> str:
        return "Fitbit · Google Pixel Watch · Versa · Sense"

    def get_auth_url(self, state: str = "") -> str:
        verifier, challenge = _generate_pkce()
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self._scope_str,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
        # Store verifier in state for later use
        return FITBIT_AUTH_URL + "?" + query, verifier

    def exchange_code(self, code: str, code_verifier: str = "") -> dict:
        data = {
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(FITBIT_TOKEN_URL, data=data, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise Exception(f"Fitbit token exchange failed: {resp.status_code} {resp.text[:200]}")
        js = resp.json()
        return {
            "access_token": js["access_token"],
            "refresh_token": js["refresh_token"],
            "expires_at": int(time.time()) + js.get("expires_in", 28800),
            "scopes": js.get("scope", ""),
        }

    def refresh_access_token(self, refresh_token: str) -> dict:
        data = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(FITBIT_TOKEN_URL, data=data, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise Exception(f"Fitbit refresh failed: {resp.status_code}")
        js = resp.json()
        return {
            "access_token": js["access_token"],
            "refresh_token": js.get("refresh_token", refresh_token),
            "expires_at": int(time.time()) + js.get("expires_in", 28800),
        }

    def fetch_data(self, access_token: str, data_types: list,
                   start_time_ms: int, end_time_ms: int) -> list:
        """拉取指定日期范围的健康数据。Fitbit API 按天查询。"""
        from datetime import datetime, timezone, timedelta

        start_date = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc)
        end_date = datetime.fromtimestamp(end_time_ms / 1000, tz=timezone.utc)
        headers = {"Authorization": f"Bearer {access_token}"}
        results = []

        # Iterate day by day
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            for dt in data_types:
                if dt not in DATA_ENDPOINTS:
                    continue
                try:
                    url = FITBIT_API_BASE + DATA_ENDPOINTS[dt].format(date=date_str)
                    resp = requests.get(url, headers=headers, timeout=15)
                    if resp.status_code == 429:
                        time.sleep(1)
                        resp = requests.get(url, headers=headers, timeout=15)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    value = self._extract_value(data, dt)
                    if value is not None and value > 0:
                        results.append({
                            "date": date_str,
                            "data_type": dt,
                            "value": value,
                            "unit": UNIT_MAP.get(dt, ""),
                            "detail_json": None,
                        })
                except Exception:
                    continue
            current += timedelta(days=1)
            time.sleep(0.3)  # Rate limit: 150 req/hour

        return results

    def _extract_value(self, data: dict, data_type: str) -> float | None:
        """从 Fitbit API 响应中提取主值。"""
        if data_type == "steps":
            summary = data.get("activities-steps", [])
            return float(summary[0].get("value", 0)) if summary else 0
        if data_type == "heart_rate":
            activities = data.get("activities-heart", [])
            if activities:
                resting = activities[0].get("value", {}).get("restingHeartRate", 0)
                return float(resting) if resting else None
            return None
        if data_type == "sleep":
            summary = data.get("summary", {})
            total = summary.get("totalMinutesAsleep", 0)
            return float(total) if total > 0 else None
        if data_type == "calories":
            summary = data.get("activities-calories", [])
            return float(summary[0].get("value", 0)) if summary else 0
        if data_type == "weight":
            entries = data.get("weight", [])
            return float(entries[0].get("weight", 0)) if entries else None
        if data_type == "body_fat":
            entries = data.get("fat", [])
            return float(entries[0].get("fat", 0)) if entries else None
        if data_type == "spo2":
            entries = data.get("minutes", [])
            if entries:
                return float(entries[0].get("value", 0))
            return None
        return None
