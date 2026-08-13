# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
提醒调度引擎 — 定时 + 事件驱动的健康提醒
"""
import time
import threading
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict

from config import config


class ReminderType(Enum):
    WATER = "喝水"
    EYE_REST = "护眼休息"
    SEDENTARY = "久坐提醒"
    POSTURE = "坐姿纠正"
    LUNCH = "午饭时间"
    AFTERNOON = "该活动一下了"
    CUSTOM = "自定义"


class Reminder:
    """单条提醒"""
    def __init__(self, rtype: ReminderType, message: str, priority: int = 1):
        self.type = rtype
        self.message = message
        self.priority = priority  # 1=低, 2=中, 3=高（坐姿纠正应该高优先级）
        self.created_at = time.time()
        self.delivered = False

    def __repr__(self):
        return f"<Reminder {self.type.value}: {self.message}>"


class ReminderScheduler:
    """提醒调度器：定时提醒 + 事件触发提醒 + 去重防骚扰"""

    def __init__(self):
        cfg = config.reminder
        self.water_interval = cfg.water_interval_min * 60
        self.eye_rest_interval = cfg.eye_rest_interval_min * 60
        self.cooldown = cfg.cooldown_min * 60
        self.lunch_time = cfg.lunch_reminder_time
        self.afternoon_time = cfg.afternoon_reminder_time

        self._last_reminder_time: dict[ReminderType, float] = defaultdict(float)
        self._last_lunch_date = None
        self._last_afternoon_date = None
        self._enabled = True
        self._lock = threading.Lock()

        # 回调
        self.on_reminder = None  # callable(Reminder)

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def tick(self, posture_status: str, person_present: bool, sit_duration_min: float) -> list[Reminder]:
        """
        每个检测周期调用一次。返回本轮应触发的提醒列表。
        posture_status: "good" | "bad" | "unknown"
        person_present: 是否检测到人
        sit_duration_min: 持续坐着的时间（分钟）
        """
        if not self._enabled:
            return []

        now = time.time()
        triggered = []
        cfg_m = config.reminder
        cfg_s = config.sedentary

        # 1. 喝水提醒（定时）
        if self._can_remind(ReminderType.WATER, now):
            triggered.append(Reminder(
                ReminderType.WATER,
                self._random_water_msg(),
                priority=1,
            ))
            self._last_reminder_time[ReminderType.WATER] = now

        # 2. 护眼提醒（定时）
        if self._can_remind(ReminderType.EYE_REST, now):
            triggered.append(Reminder(
                ReminderType.EYE_REST,
                f"连续盯屏幕 {cfg_m.eye_rest_interval_min} 分钟了，请远眺 20 秒 👀",
                priority=1,
            ))
            self._last_reminder_time[ReminderType.EYE_REST] = now

        # 3. 久坐提醒（事件驱动）
        if (person_present and sit_duration_min >= cfg_s.max_sit_minutes
                and self._can_remind(ReminderType.SEDENTARY, now, cooldown=600)):
            triggered.append(Reminder(
                ReminderType.SEDENTARY,
                f"你已经连续坐了 {int(sit_duration_min)} 分钟了，起来活动一下吧 🏃",
                priority=3,
            ))
            self._last_reminder_time[ReminderType.SEDENTARY] = now

        # 4. 坐姿提醒（事件驱动，高优先级）
        if posture_status == "bad" and self._can_remind(ReminderType.POSTURE, now, cooldown=120):
            triggered.append(Reminder(
                ReminderType.POSTURE,
                self._random_posture_msg(),
                priority=3,
            ))
            self._last_reminder_time[ReminderType.POSTURE] = now

        # 5. 午饭提醒
        today = datetime.now().strftime("%Y-%m-%d")
        if self._check_time_trigger(self.lunch_time) and self._last_lunch_date != today:
            triggered.append(Reminder(ReminderType.LUNCH, "午饭时间到！记得吃点好的 🍱", priority=2))
            self._last_lunch_date = today

        # 6. 下午茶提醒
        if self._check_time_trigger(self.afternoon_time) and self._last_afternoon_date != today:
            triggered.append(Reminder(
                ReminderType.AFTERNOON,
                "下午了，站起来活动一下，喝杯水 ☕",
                priority=2,
            ))
            self._last_afternoon_date = today

        # 通知回调
        for r in triggered:
            if self.on_reminder:
                self.on_reminder(r)

        return triggered

    def _can_remind(self, rtype: ReminderType, now: float, cooldown: float = None) -> bool:
        """检查是否过了冷却时间"""
        if cooldown is None:
            cooldown = self.cooldown
        elapsed = now - self._last_reminder_time.get(rtype, 0)

        if rtype == ReminderType.WATER:
            return elapsed >= self.water_interval
        if rtype == ReminderType.EYE_REST:
            return elapsed >= self.eye_rest_interval

        return elapsed >= cooldown

    def _check_time_trigger(self, target: str) -> bool:
        """检查是否到了指定时间 ± 2 分钟"""
        now = datetime.now()
        h, m = map(int, target.split(":"))
        return now.hour == h and abs(now.minute - m) <= 2

    @staticmethod
    def _random_water_msg():
        msgs = [
            "该喝水啦！每天 8 杯，这是第几杯？💧",
            "身体缺水了，喝一杯吧 🥤",
            "喝水打卡！保持水分才能有好状态 💪",
        ]
        import random
        return random.choice(msgs)

    @staticmethod
    def _random_posture_msg():
        msgs = [
            "坐直一点！你现在的姿势不太对 🪑",
            "别驼背，肩膀向后打开～",
            "你的脊椎正在呼救，请调正坐姿 ⚠️",
        ]
        import random
        return random.choice(msgs)
