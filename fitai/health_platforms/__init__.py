# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""健康平台注册中心。"""
_registry: list = []


def register_platform(platform_cls, *args, **kwargs):
    instance = platform_cls(*args, **kwargs)
    _registry.append(instance)
    print(f"[HealthPlatforms] 已注册: {instance.get_display_name()} ({instance.get_platform_name()})")
    return instance


def get_registered_platforms() -> list:
    return list(_registry)


def get_platform_by_name(name: str):
    for p in _registry:
        if p.get_platform_name() == name:
            return p
    return None


def init_platforms(google_client_id="", google_client_secret="",
                   huawei_client_id="", huawei_client_secret="",
                   hc_server_url="", hc_encryption_key="",
                   fitbit_client_id="", fitbit_client_secret="", fitbit_redirect_uri=""):
    """按配置初始化平台（跳过凭据为空的平台）。"""
    if google_client_id and google_client_secret:
        from health_platforms.google_fit import GoogleFitPlatform
        register_platform(GoogleFitPlatform, google_client_id, google_client_secret)

    if huawei_client_id and huawei_client_secret:
        from health_platforms.huawei_health import HuaweiHealthPlatform
        register_platform(HuaweiHealthPlatform, huawei_client_id, huawei_client_secret)

    if hc_server_url and hc_encryption_key:
        from health_platforms.health_connect import HealthConnectPlatform
        register_platform(HealthConnectPlatform, hc_server_url, hc_encryption_key)

    if fitbit_client_id and fitbit_client_secret:
        from health_platforms.fitbit import FitbitPlatform
        register_platform(FitbitPlatform, fitbit_client_id, fitbit_client_secret, fitbit_redirect_uri)

    return _registry
