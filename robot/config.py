# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
桌面健康机器人 — 配置（所有可调参数集中管理）
"""
import os
from dataclasses import dataclass, field

@dataclass
class PostureConfig:
    """坐姿检测阈值"""
    shoulder_slouch_angle: float = 30.0      # 驼背判定：肩-髋连线与垂直线的夹角（度）
    head_tilt_angle: float = 20.0            # 歪头判定：头部倾斜角（度）
    forward_head_cm: float = 8.0             # 头前伸判定（cm），需已知摄像头距离
    check_interval_sec: float = 5.0          # 检测间隔（秒）
    consecutive_bad_frames: int = 3          # 连续 N 帧不良才触发提醒

@dataclass
class SedentaryConfig:
    """久坐检测"""
    max_sit_minutes: int = 45                # 最长连续坐着的时间（分钟）
    stand_remind_minutes: int = 3            # 站起来活动的最短时长（分钟）
    away_timeout_minutes: int = 5            # 人离开座位超过 N 分钟，重置久坐计时

@dataclass
class ReminderConfig:
    """提醒调度"""
    water_interval_min: int = 45             # 喝水提醒间隔（分钟）
    eye_rest_interval_min: int = 20          # 护眼提醒间隔（20-20-20 法则）
    eye_rest_duration_sec: int = 20          # 远眺时长（秒）
    lunch_reminder_time: str = "12:00"       # 午饭提醒
    afternoon_reminder_time: str = "15:00"   # 下午茶/活动提醒
    cooldown_min: int = 5                    # 同类型提醒最短间隔，避免骚扰

@dataclass
class DisplayConfig:
    """屏幕 & 动画"""
    screen_width: int = 320
    screen_height: int = 240
    blink_interval_sec: float = 3.0          # 眨眼动画间隔
    idle_animation: str = "smile_blink"      # 默认表情
    warning_animation: str = "worried"        # 警告表情
    celebrate_animation: str = "confetti"     # 庆祝表情

@dataclass
class ESP32Config:
    """与 ESP32 的通信"""
    uart_port: str = "/dev/ttyS0"            # 树莓派上的串口
    baud_rate: int = 115200
    heartbeat_interval_sec: float = 2.0      # 心跳间隔

@dataclass
class RobotConfig:
    """总配置"""
    posture: PostureConfig = field(default_factory=PostureConfig)
    sedentary: SedentaryConfig = field(default_factory=SedentaryConfig)
    reminder: ReminderConfig = field(default_factory=ReminderConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    esp32: ESP32Config = field(default_factory=ESP32Config)

    # 摄像头
    camera_id: int = 0
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 15

    # FitAI-web 后端
    fitai_api_url: str = field(default_factory=lambda: os.getenv("FITAI_API_URL", "http://localhost:8000/api"))

    # TTS
    tts_engine: str = "edge"                 # "edge" | "pyttsx3" | "none"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"  # Edge-TTS 中文女声
    tts_rate: str = "+10%"


config = RobotConfig()
