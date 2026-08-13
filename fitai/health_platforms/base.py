# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""健康平台抽象基类，所有健康数据平台必须实现此接口。"""
from abc import ABC, abstractmethod
import time
from tools.fitai_database import get_oauth_token


class HealthPlatform(ABC):

    @abstractmethod
    def get_platform_name(self) -> str:
        """机器名，如 'google_fit'、'huawei_health'"""
        ...

    @abstractmethod
    def get_display_name(self) -> str:
        """展示名，如 'Google Fit'、'华为健康'"""
        ...

    @abstractmethod
    def get_device_list(self) -> str:
        """该平台覆盖的设备描述"""
        ...

    @abstractmethod
    def get_auth_url(self, state: str = "") -> str:
        """生成 OAuth 授权 URL"""
        ...

    @abstractmethod
    def exchange_code(self, code: str) -> dict:
        """用 authorization code 交换 token，返回 dict: access_token, refresh_token, expires_at, scopes"""
        ...

    @abstractmethod
    def refresh_access_token(self, refresh_token: str) -> dict:
        """刷新 access_token，返回 dict: access_token, expires_at"""
        ...

    @abstractmethod
    def fetch_data(self, access_token: str, data_types: list,
                   start_time_ms: int, end_time_ms: int) -> list:
        """拉取健康数据，返回统一格式 list[dict]: {date, data_type, value, unit, detail_json}"""
        ...

    def is_oauth_platform(self) -> bool:
        """是否 OAuth 平台。非 OAuth 平台（如 Health Connect）覆盖为 False。"""
        return True

    def get_config_fields(self) -> list:
        """返回额外配置字段。非 OAuth 平台覆盖。
        每个字段: {name, label, placeholder, type, required}"""
        return []

    def get_connection_status(self) -> dict:
        """检查连接状态，返回 {connected: bool, detail: str}。非 OAuth 平台覆盖。"""
        if self.is_connected():
            return {"connected": True, "detail": "已授权"}
        return {"connected": False, "detail": "未连接"}

    def is_connected(self) -> bool:
        token = get_oauth_token(self.get_platform_name())
        if not token:
            return False
        if token.get("refresh_token"):
            return True
        return token.get("expires_at", 0) > time.time()
