# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""后台健康数据同步服务。"""
import time
import threading
from datetime import datetime, timezone, timedelta
from tools.fitai_database import (
    get_oauth_token, save_oauth_token, insert_health_data,
    insert_sync_log, update_sync_log, get_last_sync_info,
)
from fitai.health_platforms import get_registered_platforms
from config import HEALTH_SYNC_INTERVAL_SECONDS, HEALTH_DATA_TYPES


class HealthSyncService:
    """后台定时同步器，遍历所有已连接平台拉取健康数据。"""

    _PLATFORM_INTERVALS = {
        "health_connect": 300,  # 5 分钟（近实时）
        # 其他平台使用默认 _interval
    }

    def __init__(self):
        self._running = False
        self._thread = None
        self._interval = HEALTH_SYNC_INTERVAL_SECONDS
        self._lock = threading.Lock()
        self._last_sync_times = {}  # platform_name -> float (unix timestamp)

    def start(self, interval_seconds: int = None):
        if interval_seconds:
            self._interval = interval_seconds
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print(f"[HealthSync] 后台同步已启动，间隔 {self._interval}s")

    def stop(self):
        self._running = False

    def _run_loop(self):
        # 启动后先等 10 秒再首次同步，避免阻塞服务启动
        time.sleep(10)
        while self._running:
            try:
                self.sync_all_connected()
            except Exception as e:
                print(f"[HealthSync] 同步出错: {e}")
            time.sleep(self._interval)

    def sync_all_connected(self):
        platforms = get_registered_platforms()
        now = time.time()
        for pf in platforms:
            if not pf.is_connected():
                continue
            name = pf.get_platform_name()
            interval = self._PLATFORM_INTERVALS.get(name, self._interval)
            last = self._last_sync_times.get(name, 0)
            if now - last >= interval:
                self._sync_platform(pf)
                self._last_sync_times[name] = now

    def _sync_platform(self, platform):
        with self._lock:
            name = platform.get_platform_name()
            token = get_oauth_token(name)
            if not token:
                return
            access_token = token["access_token"]

            # Token 将在 5 分钟内过期 → 先刷新
            if token["expires_at"] <= time.time() + 300 and token.get("refresh_token"):
                try:
                    new = platform.refresh_access_token(token["refresh_token"])
                    save_oauth_token(name, new["access_token"],
                                     token.get("refresh_token"),
                                     new["expires_at"], token.get("scopes", ""))
                    access_token = new["access_token"]
                except Exception as e:
                    print(f"[HealthSync] {name} token刷新失败: {e}")
                    return

            # 计算增量时间范围
            now = datetime.now(timezone.utc)
            last_sync = get_last_sync_info(name)
            if last_sync and last_sync.get("finished_at"):
                start = datetime.fromisoformat(last_sync["finished_at"])
            else:
                start = now - timedelta(days=7)

            start_ms = int(start.timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)

            if start_ms >= end_ms - 60000:
                return  # 不到 1 分钟的增量，跳过

            print(f"[HealthSync] 正在同步 {name}: {start.isoformat()} -> {now.isoformat()}")

            log_id = insert_sync_log(name)
            try:
                data = platform.fetch_data(access_token, HEALTH_DATA_TYPES,
                                           start_ms, end_ms)
                count = 0
                for record in data:
                    try:
                        record["user_id"] = record.get("user_id", 1)
                        insert_health_data(**record)
                        count += 1
                    except Exception as e:
                        print(f"[HealthSync] 写入失败: {e}")
                update_sync_log(log_id, "success", count)
                print(f"[HealthSync] {name} 同步完成: {count} 条")
            except Exception as e:
                update_sync_log(log_id, "error", 0, str(e))
                print(f"[HealthSync] {name} 同步失败: {e}")

    def sync_now(self, platform_name: str = None) -> str:
        """手动触发同步，返回文本结果。"""
        messages = []
        platforms = get_registered_platforms()
        for pf in platforms:
            if platform_name and pf.get_platform_name() != platform_name:
                continue
            if not pf.is_connected():
                messages.append(f"{pf.get_display_name()}: 未连接，跳过")
                continue
            try:
                self._sync_platform(pf)
                self._last_sync_times[pf.get_platform_name()] = time.time()
                messages.append(f"{pf.get_display_name()}: 同步完成")
            except Exception as e:
                messages.append(f"{pf.get_display_name()}: 同步失败 - {e}")
        return "\n".join(messages) if messages else "没有可用的健康平台。请先在设置中连接设备。"


sync_service = HealthSyncService()
