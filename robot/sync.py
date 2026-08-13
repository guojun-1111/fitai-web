# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
数据同步模块 — 将机器人采集的健康数据同步到 FitAI-web 后端
"""
import time
import json
import threading
import urllib.request
import urllib.error

from config import config


class FitAISync:
    """将坐姿记录、喝水次数等同步到 FitAI-web"""

    def __init__(self):
        self.base_url = config.fitai_api_url.rstrip("/")
        self._buffer = []       # 待同步数据
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()
        print(f"[Sync] 开始同步到 {self.base_url}")

    def stop(self):
        self._running = False

    def log_posture(self, status: str, slouch_angle: float, head_tilt: float, duration_min: float):
        """记录坐姿状态"""
        self._enqueue({
            "metric_type": "posture",
            "status": status,
            "slouch_angle": slouch_angle,
            "head_tilt_angle": head_tilt,
            "sit_duration_min": round(duration_min, 1),
        })

    def log_water(self, ml: int = 250):
        """记录喝水"""
        self._enqueue({
            "metric_type": "water",
            "amount_ml": ml,
        })

    def log_eye_rest(self, duration_sec: int):
        """记录护眼休息"""
        self._enqueue({
            "metric_type": "eye_rest",
            "duration_sec": duration_sec,
        })

    def log_stand_up(self, duration_min: float):
        """记录起身活动"""
        self._enqueue({
            "metric_type": "stand_up",
            "duration_min": round(duration_min, 1),
        })

    def _enqueue(self, data: dict):
        data["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock:
            self._buffer.append(data)

    def _sync_loop(self):
        while self._running:
            time.sleep(30)  # 每 30 秒同步一次
            self._flush()

    def _flush(self):
        with self._lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()

        payload = json.dumps({"records": batch}).encode()
        url = f"{self.base_url}/health/record"

        try:
            req = urllib.request.Request(url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    print(f"[Sync] 已同步 {len(batch)} 条数据")
                else:
                    # 失败则放回
                    with self._lock:
                        self._buffer = batch + self._buffer
        except urllib.error.URLError as e:
            print(f"[Sync] 同步失败: {e}")
            with self._lock:
                self._buffer = batch + self._buffer
