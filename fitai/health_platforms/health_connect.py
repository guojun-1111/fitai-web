# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Health Connect 平台实现（通过 HCGateway REST API）。
Android Health Connect → HCGateway 配套 App → HCGateway Server → 本平台。

HCGateway 开源项目: https://github.com/ShadM00/Health-Connect
"""
import time
from datetime import datetime, timezone
import requests
from fitai.health_platforms.base import HealthPlatform

HC_DATA_TYPE_MAP = {
    "steps": "steps",
    "heart_rate": "heart_rate",
    "sleep": "sleep",
    "calories": "calories",
    "spo2": "oxygen_saturation",
    "weight": "weight",
    "body_fat": "body_fat",
    "blood_pressure_sys": "blood_pressure",
    "blood_pressure_dia": "blood_pressure",
    "blood_glucose": "blood_glucose",
    "hydration": "hydration",
    "exercise": "exercise",
}

UNIT_MAP = {
    "steps": "步", "heart_rate": "bpm", "sleep": "分钟", "calories": "千卡",
    "spo2": "%", "weight": "kg", "body_fat": "%",
    "blood_pressure_sys": "mmHg", "blood_pressure_dia": "mmHg",
    "blood_glucose": "mmol/L", "hydration": "ml", "exercise": "分钟",
}

HC_GATEWAY_TYPES = sorted(set(HC_DATA_TYPE_MAP.values()))


class HealthConnectPlatform(HealthPlatform):

    def __init__(self, server_url: str = "", encryption_key: str = ""):
        self.server_url = server_url.rstrip("/") if server_url else ""
        self.encryption_key = encryption_key
        self._api_base = f"{self.server_url}/api/v2" if self.server_url else ""

    def get_platform_name(self) -> str:
        return "health_connect"

    def get_display_name(self) -> str:
        return "Health Connect (Android)"

    def get_device_list(self) -> str:
        return "Android · 小米手环 (Mi Fitness) · Samsung Health · Fitbit · Zepp"

    def is_oauth_platform(self) -> bool:
        return False

    def get_config_fields(self) -> list:
        return [
            {"name": "server_url", "label": "HCGateway 服务器地址",
             "placeholder": "http://192.168.1.100:6644", "type": "text", "required": True},
            {"name": "encryption_key", "label": "Fernet 加密密钥",
             "placeholder": "从 HCGateway 服务器获取", "type": "password", "required": True},
        ]

    def get_connection_status(self) -> dict:
        if not self.server_url or not self.encryption_key:
            return {"connected": False, "detail": "服务器地址或密钥未配置"}
        try:
            resp = requests.get(f"{self._api_base}/health", timeout=5)
            if resp.status_code == 200:
                return {"connected": True, "detail": "服务器正常"}
            return {"connected": False, "detail": f"服务器返回: {resp.status_code}"}
        except requests.ConnectionError:
            return {"connected": False, "detail": f"无法连接服务器: {self.server_url}"}
        except requests.RequestException as e:
            return {"connected": False, "detail": f"连接失败: {e}"}

    def get_auth_url(self, state: str = "") -> str:
        return ""

    def exchange_code(self, code: str) -> dict:
        raise NotImplementedError("Health Connect uses Fernet encryption, not OAuth")

    def refresh_access_token(self, refresh_token: str) -> dict:
        return {"access_token": self.encryption_key, "expires_at": 2147483647}

    def is_connected(self) -> bool:
        try:
            from database import get_oauth_token
        except ImportError:
            return False
        token = get_oauth_token(self.get_platform_name())
        if not token:
            return False
        if token.get("refresh_token"):
            return True
        return token.get("expires_at", 0) > time.time()

    def fetch_data(self, access_token: str, data_types: list,
                   start_time_ms: int, end_time_ms: int) -> list:
        if not self._api_base or not self.encryption_key:
            return []

        start_date = _ms_to_date_str(start_time_ms)
        end_date = _ms_to_date_str(end_time_ms)

        results = []
        for dt in data_types:
            hc_type = HC_DATA_TYPE_MAP.get(dt)
            if not hc_type:
                continue
            try:
                resp = requests.post(
                    f"{self._api_base}/data/{hc_type}",
                    json={
                        "password": self.encryption_key,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                    timeout=30,
                )
                if resp.status_code == 404:
                    continue
                if resp.status_code != 200:
                    print(f"[HealthConnect] fetch {hc_type} failed: HTTP {resp.status_code}")
                    continue
                body = resp.json()
            except requests.RequestException as e:
                print(f"[HealthConnect] fetch {hc_type} error: {e}")
                continue
            except ValueError as e:
                print(f"[HealthConnect] parse {hc_type} response failed: {e}")
                continue

            if body.get("status") != "ok":
                continue

            records = body.get("data", [])
            for record in records:
                date_str = _parse_hcg_date(record.get("date", ""))
                if not date_str:
                    continue
                value = _extract_value(record, dt)
                if value is None:
                    continue
                results.append({
                    "date": date_str,
                    "source_platform": "health_connect",
                    "data_type": dt,
                    "value": value,
                    "unit": UNIT_MAP.get(dt, ""),
                    "detail_json": None,
                })

        return results


def _ms_to_date_str(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _parse_hcg_date(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d", "%m/%d/%Y"]:
        try:
            return datetime.strptime(raw[:19] if len(raw) >= 19 else raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw[:10] if len(raw) >= 10 else None


def _extract_value(record: dict, data_type: str) -> float | None:
    val = record.get("value")
    if val is not None:
        try:
            return round(float(val), 1)
        except (ValueError, TypeError):
            pass
    avg = record.get("average") or record.get("avg")
    if avg is not None:
        try:
            return round(float(avg), 1)
        except (ValueError, TypeError):
            pass
    return None
