# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
FitAI 桌面健康机器人 — 主程序
运行在树莓派 / 核心板 Linux 上

功能：
  - 摄像头 + MediaPipe 实时姿态检测（驼背、歪头、久坐）
  - 定时提醒（喝水、护眼、午饭）
  - 屏幕表情交互动画
  - 语音播报提醒
  - 与 ESP32 串口通信（传感器读取、舵机、LED）
  - 数据同步到 FitAI-web 后端

用法：
  python main.py                      # 正常模式（需要摄像头 + PyGame）
  python main.py --headless           # 无头模式（纯命令行，调试用）
  python main.py --no-camera          # 不启动摄像头（只用定时提醒）
"""

import argparse
import time
import signal
import sys
import threading

from config import config, RobotConfig
from pose_detector import PoseDetector
from reminder import ReminderScheduler, ReminderType
from esp32_comm import ESP32Comm
from display import DisplayEngine
from tts_engine import TTSEngine
from sync import FitAISync


class FitAIRobot:
    """桌面健康机器人主控制器"""

    def __init__(self, headless: bool = False, no_camera: bool = False):
        self.headless = headless
        self.no_camera = no_camera
        self.running = False

        # 各子系统
        self.pose_detector = None
        self.reminder = ReminderScheduler()
        self.esp32 = ESP32Comm()
        self.display = DisplayEngine(headless=headless)
        self.tts = TTSEngine()
        self.sync = FitAISync()

        # 状态追踪
        self.person_present = False
        self.person_absent_since = None
        self.current_posture = "unknown"
        self.sit_start_time = time.time()
        self.sit_duration_min = 0.0
        self.is_sitting = True
        self.water_count_today = 0
        self.last_emotion = "smile"

        # 摄像头
        self.cap = None
        if not no_camera:
            import cv2
            self._init_camera()

    def _init_camera(self):
        import cv2
        cfg = config
        self.cap = cv2.VideoCapture(cfg.camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.camera_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.camera_height)
        self.cap.set(cv2.CAP_PROP_FPS, cfg.camera_fps)

    def start(self):
        """启动所有子系统"""
        self.running = True
        print("=" * 50)
        print("  FitAI 桌面健康机器人 启动中...")
        print("=" * 50)

        # 初始化姿态检测
        if not self.no_camera:
            try:
                self.pose_detector = PoseDetector()
                print("[OK] MediaPipe 姿态检测已加载")
            except Exception as e:
                print(f"[WARN] 姿态检测加载失败: {e}，将仅使用定时提醒")

        # 连接 ESP32
        self.esp32.connect()

        # 初始化屏幕
        self.display.init()
        self.display.set_emotion("smile")

        # 启动数据同步
        self.sync.start()

        # 欢迎语音
        greeting = "你好！我是 FitAI 桌面健康助手，我会帮你监测坐姿、提醒喝水和休息。"
        self.tts.speak(greeting)

        print("[OK] 所有子系统就绪")
        self._main_loop()

    def stop(self):
        """安全关闭所有子系统"""
        print("\n正在关闭...")
        self.running = False
        if self.pose_detector:
            self.pose_detector.release()
        if self.cap:
            self.cap.release()
        self.esp32.disconnect()
        self.display.quit()
        self.sync.stop()
        print("已关闭，再见！")

    def _main_loop(self):
        tick = 0
        last_pose_check = 0
        cfg_posture = config.posture

        while self.running:
            loop_start = time.time()

            # 1. 姿态检测（摄像头）
            if self.pose_detector and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    now = time.time()
                    if now - last_pose_check >= cfg_posture.check_interval_sec:
                        result = self.pose_detector.process_frame(frame)
                        self._handle_pose_result(result)
                        last_pose_check = now

            # 2. 更新人存在状态（摄像头 + ESP32 传感器）
            self._update_presence()

            # 3. 提醒调度
            reminders = self.reminder.tick(
                posture_status=self.current_posture,
                person_present=self.person_present,
                sit_duration_min=self.sit_duration_min,
            )
            for r in reminders:
                self._handle_reminder(r)

            # 4. 屏幕动画
            if tick % 2 == 0:
                self.display.update()

            # 5. ESP32 状态更新
            if self.esp32.is_person_present != self.person_present:
                pass  # 已在 _update_presence 中处理

            # 6. 同步日志
            if tick % 120 == 0:  # 每 2 分钟记录一次坐姿
                if self.current_posture in ("good", "bad"):
                    self.sync.log_posture(
                        self.current_posture,
                        getattr(self, "last_slouch", 0),
                        getattr(self, "last_head_tilt", 0),
                        self.sit_duration_min,
                    )

            tick += 1
            elapsed = time.time() - loop_start
            sleep_time = max(0, 0.2 - elapsed)
            time.sleep(sleep_time)

    def _handle_pose_result(self, result: dict):
        """处理姿态检测结果"""
        person = result.get("person_detected", False)
        alerts = result.get("alerts", [])
        self.current_posture = result.get("posture_status", "unknown")
        self.last_slouch = result.get("slouch_angle", 0) or 0
        self.last_head_tilt = result.get("head_tilt_angle", 0) or 0

        # 更新坐着时长
        if result.get("is_sitting"):
            if not self.is_sitting:
                self.sit_start_time = time.time()
                self.is_sitting = True
            self.sit_duration_min = (time.time() - self.sit_start_time) / 60
        else:
            if self.is_sitting:
                # 用户起身了
                stand_duration = time.time() - self.sit_start_time
                if stand_duration > config.sedentary.stand_remind_minutes * 60:
                    self.sync.log_stand_up(self.sit_duration_min)
                    self.sit_duration_min = 0
                    self.sit_start_time = time.time()
                self.is_sitting = False

        # 根据姿态更新表情
        if alerts:
            self.display.set_emotion("worried")
            self.last_emotion = "worried"
        else:
            if self.last_emotion != "smile":
                self.display.set_emotion("smile")
                self.last_emotion = "smile"

    def _update_presence(self):
        """综合判断是否有人在桌前"""
        # 摄像头判断（主要依据）
        cam_present = self.pose_detector is not None and self.current_posture != "unknown"

        # ESP32 传感器判断（辅助）
        esp_present = self.esp32.is_person_present if self.esp32._ser else cam_present

        was_present = self.person_present
        self.person_present = cam_present or esp_present

        # 人离开 → 重置久坐计时
        if was_present and not self.person_present:
            self.person_absent_since = time.time()
        elif not was_present and self.person_present:
            # 人回来了
            if self.person_absent_since:
                absent_min = (time.time() - self.person_absent_since) / 60
                if absent_min > config.sedentary.away_timeout_minutes:
                    self.sit_start_time = time.time()
                    self.sit_duration_min = 0
            self.person_absent_since = None

    def _handle_reminder(self, reminder):
        """处理提醒：语音 + 屏幕表情 + 发送到 ESP32"""
        print(f"[提醒] {reminder.type.value}: {reminder.message}")

        # 语音播报
        if reminder.priority >= 2:
            self.tts.speak(reminder.message)

        # 屏幕表情
        if reminder.type == ReminderType.POSTURE:
            self.display.set_emotion("worried")
        elif reminder.type == ReminderType.SEDENTARY:
            self.esp32.set_emotion("surprised")
            self.display.set_emotion("surprised")

        # ESP32 动作
        if reminder.type == ReminderType.SEDENTARY:
            self.esp32.beep(2000, 300)
        elif reminder.type == ReminderType.POSTURE:
            self.esp32.beep(1500, 150)

        # 记录喝水
        if reminder.type == ReminderType.WATER:
            self.water_count_today += 1
            # 如果称重传感器检测到水杯重量下降，说明真的喝水了
            w = self.esp32.latest_sensor.get("weight_g", 0)
            if w > 50:  # 杯子里有水
                self.sync.log_water(250)


def main():
    parser = argparse.ArgumentParser(description="FitAI 桌面健康机器人")
    parser.add_argument("--headless", action="store_true", help="无头模式（不启动屏幕渲染）")
    parser.add_argument("--no-camera", action="store_true", help="不启动摄像头（仅定时提醒）")
    parser.add_argument("--mock-esp32", action="store_true", help="模拟 ESP32（串口不可用时）")
    args = parser.parse_args()

    robot = FitAIRobot(headless=args.headless, no_camera=args.no_camera)

    # 优雅退出
    def shutdown(sig, frame):
        robot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        robot.start()
    except KeyboardInterrupt:
        robot.stop()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        robot.stop()


if __name__ == "__main__":
    main()
