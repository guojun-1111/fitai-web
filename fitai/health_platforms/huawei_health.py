# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""华为健康 Kit 云 API 平台实现。"""
import time
import requests
from fitai.health_platforms.base import HealthPlatform
from config import HUAWEI_REDIRECT_URI

HUAWEI_AUTH_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/authorize"
HUAWEI_TOKEN_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
HUAWEI_HEALTH_API = "https://health-api.cloud.huawei.com/healthkit/v2"

HUAWEI_SCOPES = [
    "https://www.huawei.com/healthkit/step.readboth",
    "https://www.huawei.com/healthkit/heartrate.readboth",
    "https://www.huawei.com/healthkit/sleeptime.readboth",
    "https://www.huawei.com/healthkit/calorie.readboth",
    "https://www.huawei.com/healthkit/oxygenSaturation.readboth",
    "https://www.huawei.com/healthkit/activityrecord.readboth",
]

DATA_TYPE_ENDPOINTS = {
    "steps": "/dataCollectors/steps/daily",
    "heart_rate": "/dataCollectors/heartRate/daily",
    "sleep": "/dataCollectors/sleep/daily",
    "calories": "/dataCollectors/calories/daily",
    "spo2": "/dataCollectors/oxygenSaturation/daily",
    "exercise": "/activityRecords",
}

# 华为活动类型 → 中文名称
HUAWEI_ACTIVITY_MAP = {
    1: "步行", 2: "跑步", 3: "骑行", 4: "游泳", 5: "徒步",
    6: "力量训练", 7: "椭圆机", 8: "划船", 9: "跳绳",
    10: "瑜伽", 11: "普拉提", 12: "篮球", 13: "足球",
    14: "羽毛球", 15: "乒乓球", 16: "网球", 17: "排球",
    18: "舞蹈", 19: "拳击", 20: "滑雪", 21: "滑冰",
    22: "攀岩", 23: "HIIT", 24: "交叉训练", 25: "核心训练",
    26: "柔韧性训练", 27: "登山", 28: "太极拳",
}

UNIT_MAP = {
    "steps": "步",
    "heart_rate": "bpm",
    "sleep": "分钟",
    "calories": "千卡",
    "spo2": "%",
}


class HuaweiHealthPlatform(HealthPlatform):

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._scope_str = " ".join(HUAWEI_SCOPES)

    def get_platform_name(self) -> str:
        return "huawei_health"

    def get_display_name(self) -> str:
        return "华为健康"

    def get_device_list(self) -> str:
        return "鸿蒙 · 华为手环 · 荣耀"

    def get_auth_url(self, state: str = "") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": HUAWEI_REDIRECT_URI,
            "response_type": "code",
            "scope": self._scope_str,
            "access_type": "offline",
            "state": state,
        }
        qs = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
        return f"{HUAWEI_AUTH_URL}?{qs}"

    def exchange_code(self, code: str) -> dict:
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": HUAWEI_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(HUAWEI_TOKEN_URL, data=data, headers=headers, timeout=15)
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
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(HUAWEI_TOKEN_URL, data=data, headers=headers, timeout=15)
        resp.raise_for_status()
        token = resp.json()
        expires_at = time.time() + token.get("expires_in", 3600) - 60
        return {"access_token": token["access_token"], "expires_at": expires_at}

    def fetch_data(self, access_token: str, data_types: list,
                   start_time_ms: int, end_time_ms: int) -> list:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        results = []

        for dt in data_types:
            endpoint = DATA_TYPE_ENDPOINTS.get(dt)
            if not endpoint:
                continue

            try:
                if dt == "exercise":
                    # 活动记录走单独路径，直接写入 workout_logs
                    self._fetch_activities(access_token, start_time_ms, end_time_ms)
                    continue

                # 华为 Health Kit 使用 dataCollector 查询
                url = f"{HUAWEI_HEALTH_API}{endpoint}"
                params = {
                    "startTime": str(start_time_ms),
                    "endTime": str(end_time_ms),
                }
                resp = requests.get(url, headers=headers, params=params, timeout=20)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[HuaweiHealth] fetch {dt} failed: {e}")
                continue

            parsed = _parse_huawei_response(data, dt)
            results.extend(parsed)

        return results

    def _fetch_activities(self, access_token: str, start_time_ms: int, end_time_ms: int):
        """拉取华为活动记录（跑步、骑行、游泳等），写入 workout_logs。"""
        from database import insert_workout
        import datetime as dt_module

        url = f"{HUAWEI_HEALTH_API}/activityRecords"
        params = {
            "startTime": str(start_time_ms),
            "endTime": str(end_time_ms),
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)
            if resp.status_code == 404:
                return
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[HuaweiHealth] fetch activities failed: {e}")
            return

        count = 0
        for group in data.get("group", []):
            activity_type = group.get("activityType", 0)
            exercise_name = HUAWEI_ACTIVITY_MAP.get(activity_type)
            if not exercise_name:
                continue

            start_ts = group.get("startTime", 0)
            end_ts = group.get("endTime", 0)
            date_str = _ms_to_date(int(start_ts)) if start_ts else None
            if not date_str:
                continue

            duration_min = None
            if start_ts and end_ts:
                duration_min = round((int(end_ts) - int(start_ts)) / 60000, 1)

            kcal = group.get("calorie", 0) or 0
            distance = group.get("distance", 0) or 0
            altitude = group.get("altitudeOffset", 0) or 0

            notes_parts = []
            if kcal > 0:
                notes_parts.append(f"{round(kcal)}千卡")
            if distance > 0:
                notes_parts.append(f"{round(distance / 1000, 2)}km")
            if altitude > 0:
                notes_parts.append(f"爬升{round(altitude)}m")
            notes = " · ".join(notes_parts) if notes_parts else None

            try:
                insert_workout(
                    exercise_name=exercise_name,
                    duration_minutes=duration_min,
                    notes=notes,
                    date=date_str,
                )
                count += 1
            except Exception as e:
                print(f"[HuaweiHealth] workout insert failed: {e}")

        if count > 0:
            print(f"[HuaweiHealth] 活动记录: {count} 条")


def _parse_huawei_response(data: dict, data_type: str) -> list:
    """解析华为 Health Kit 响应为统一格式。"""
    import datetime

    results = []
    groups = data.get("group", []) or data.get("data", [])

    # 如果有 group 结构
    for group in groups:
        samples = group.get("sample", []) or group.get("samples", []) or []
        for sample in samples:
            ts = sample.get("startTime", 0) or sample.get("time", 0)
            if not ts:
                continue
            date_str = _ms_to_date(int(ts))
            value = _extract_huawei_value(sample, data_type)
            if value is not None:
                detail = None
                # V15: 提取睡眠阶段详情
                if data_type == "sleep":
                    fields = sample.get("fields", {}) or sample.get("fieldValues", {})
                    stages = {}
                    for k, v in fields.items():
                        if k in ("deepSleep", "lightSleep", "remSleep", "wakeSleep"):
                            try:
                                stages[k] = float(v)
                            except (ValueError, TypeError):
                                pass
                    if stages:
                        import json
                        detail = json.dumps(stages, ensure_ascii=False)
                results.append({
                    "date": date_str,
                    "source_platform": "huawei_health",
                    "data_type": data_type,
                    "value": value,
                    "unit": UNIT_MAP.get(data_type, ""),
                    "detail_json": detail,
                })

    # 扁平结构备选：直接在 data 中
    if not results and isinstance(data, dict):
        samples = data.get("samplePoints", []) or data.get("samples", []) or []
        for s in samples:
            ts = s.get("startTime", 0) or s.get("time", 0)
            if not ts:
                ts = s.get("startTimeMillis", 0)
            if not ts:
                continue
            date_str = _ms_to_date(int(ts))
            value = _extract_huawei_value(s, data_type)
            if value is not None:
                detail_f = None
                if data_type == "sleep":
                    fields_f = s.get("fields", {}) or s.get("fieldValues", {})
                    stages_f = {}
                    for k_f, v_f in fields_f.items():
                        if k_f in ("deepSleep", "lightSleep", "remSleep", "wakeSleep"):
                            try:
                                stages_f[k_f] = float(v_f)
                            except (ValueError, TypeError):
                                pass
                    if stages_f:
                        import json
                        detail_f = json.dumps(stages_f, ensure_ascii=False)
                results.append({
                    "date": date_str, "source_platform": "huawei_health",
                    "data_type": data_type, "value": value,
                    "unit": UNIT_MAP.get(data_type, ""),
                    "detail_json": detail_f,
                })

    return results


def _extract_huawei_value(sample: dict, data_type: str) -> float | None:
    """从华为数据点中提取值。"""
    # 尝试多种可能的字段名
    val = sample.get("value") or sample.get("dataValue")
    if val is not None:
        try:
            return round(float(val), 1)
        except (ValueError, TypeError):
            pass

    # 复合字段
    fields = sample.get("fields", {}) or sample.get("fieldValues", {})
    if fields:
        if data_type == "sleep":
            # 睡眠时长（分钟）
            duration = fields.get("duration", 0) or fields.get("sleepDuration", 0)
            if duration:
                return round(float(duration), 1)
        if data_type == "steps":
            count = fields.get("stepCount", 0) or fields.get("count", 0)
            return float(count)
        if data_type == "heart_rate":
            bpm = fields.get("heartRate", 0) or fields.get("bpm", 0)
            return float(bpm)
        if data_type == "calories":
            cal = fields.get("calories", 0) or fields.get("energy", 0)
            return float(cal)
        if data_type == "spo2":
            spo2 = fields.get("oxygenSaturation", 0) or fields.get("spo2", 0)
            return float(spo2)
        # 尝试第一个数值字段
        for v in fields.values():
            try:
                return round(float(v), 1)
            except (ValueError, TypeError):
                continue

    return None


def _ms_to_date(ms: int) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d")
