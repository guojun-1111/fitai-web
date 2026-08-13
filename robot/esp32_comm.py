# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
与 ESP32 的 UART 通信协议

协议格式（JSON 行，换行符分隔）：
  主控 → ESP32:
    {"cmd":"servo","angle":[90,0]}           // 头部舵机两个角度
    {"cmd":"led","r":255,"g":0,"b":0}        // LED 表情颜色
    {"cmd":"led_matrix","emotion":"smile"}    // LED 矩阵表情
    {"cmd":"beep","freq":2000,"dur":200}     // 蜂鸣提示

  ESP32 → 主控:
    {"event":"sensor","ir":1,"distance_cm":85,"weight_g":0}
    {"event":"heartbeat","battery_mv":3850}
    {"event":"button","code":1}
"""
import json
import time
import threading
from collections import deque

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

from config import config


class ESP32Comm:
    """与 ESP32 模组的串口通信"""

    def __init__(self):
        cfg = config.esp32
        self.port = cfg.uart_port
        self.baud = cfg.baud_rate
        self.heartbeat_interval = cfg.heartbeat_interval_sec

        self._ser = None
        self._lock = threading.Lock()
        self._rx_buffer = b""
        self._running = False
        self._rx_thread = None
        self._hb_thread = None

        # 最新传感器数据
        self.latest_sensor = {
            "ir_presence": 0,       # 红外人体感应
            "distance_cm": 0.0,     # 超声波/激光测距
            "weight_g": 0.0,        # 水杯重量
            "battery_mv": 0,        # 电池电压
        }
        self._sensor_queue = deque(maxlen=32)

        # 回调
        self.on_sensor_update = None
        self.on_button = None

    def connect(self) -> bool:
        if not HAS_SERIAL:
            print("[ESP32] pyserial 未安装，跳过串口连接")
            return False
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self._running = True
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            self._hb_thread = threading.Thread(target=self._hb_loop, daemon=True)
            self._hb_thread.start()
            print(f"[ESP32] 已连接 {self.port} @ {self.baud}")
            return True
        except serial.SerialException as e:
            print(f"[ESP32] 连接失败: {e}")
            return False

    def disconnect(self):
        self._running = False
        if self._ser and self._ser.is_open:
            self._ser.close()

    def send_command(self, cmd: dict):
        """发送 JSON 命令到 ESP32"""
        if not self._ser or not self._ser.is_open:
            return
        line = json.dumps(cmd, ensure_ascii=False) + "\n"
        with self._lock:
            self._ser.write(line.encode())

    # ---- 高层指令 ----

    def set_servo(self, head_angle: int = 90, arm_angle: int = 90):
        """控制舵机角度（0-180）"""
        self.send_command({"cmd": "servo", "head": head_angle, "arm": arm_angle})

    def set_led_color(self, r: int, g: int, b: int):
        """设置 LED 表情颜色"""
        self.send_command({"cmd": "led", "r": r, "g": g, "b": b})

    def set_emotion(self, emotion: str):
        """设置表情: "smile", "worried", "sleep", "surprised", "confetti" """
        emotions = {
            "smile":      {"r": 0, "g": 255, "b": 100},
            "worried":    {"r": 255, "g": 180, "b": 0},
            "sleep":      {"r": 50, "g": 50, "b": 150},
            "surprised":  {"r": 0, "g": 200, "b": 255},
            "confetti":   {"r": 255, "g": 100, "b": 255},
        }
        color = emotions.get(emotion, {"r": 255, "g": 255, "b": 255})
        self.send_command({"cmd": "led_matrix", "emotion": emotion})
        self.set_led_color(**color)

    def beep(self, freq: int = 2000, duration_ms: int = 200):
        """蜂鸣器提示音"""
        self.send_command({"cmd": "beep", "freq": freq, "dur": duration_ms})

    # ---- 内部 ----

    def _rx_loop(self):
        while self._running:
            try:
                if self._ser and self._ser.is_open and self._ser.in_waiting:
                    data = self._ser.read(self._ser.in_waiting)
                    self._rx_buffer += data
                    while b"\n" in self._rx_buffer:
                        line, self._rx_buffer = self._rx_buffer.split(b"\n", 1)
                        self._parse_line(line.decode(errors="ignore"))
            except Exception as e:
                print(f"[ESP32] RX error: {e}")
            time.sleep(0.01)

    def _parse_line(self, line: str):
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        event = msg.get("event")
        if event == "sensor":
            self.latest_sensor.update({
                "ir_presence": msg.get("ir", 0),
                "distance_cm": msg.get("distance_cm", 0.0),
                "weight_g": msg.get("weight_g", 0.0),
            })
            self._sensor_queue.append(dict(self.latest_sensor))
            if self.on_sensor_update:
                self.on_sensor_update(self.latest_sensor)

        elif event == "heartbeat":
            self.latest_sensor["battery_mv"] = msg.get("battery_mv", 0)

        elif event == "button":
            code = msg.get("code", 0)
            if self.on_button:
                self.on_button(code)

    def _hb_loop(self):
        while self._running:
            self.send_command({"cmd": "ping"})
            time.sleep(self.heartbeat_interval)

    @property
    def is_person_present(self) -> bool:
        """综合红外 + 超声波判断是否有人在桌前"""
        s = self.latest_sensor
        ir_triggered = s["ir_presence"] == 1
        # 超声波：距离在 30-120cm 之间说明有人在桌前
        dist_in_range = 30 < s["distance_cm"] < 120
        return ir_triggered and dist_in_range

    @property
    def battery_percent(self) -> int:
        """估算剩余电量百分比（基于锂电池放电曲线近似）"""
        mv = self.latest_sensor["battery_mv"]
        if mv <= 3200:
            return 0
        if mv >= 4200:
            return 100
        return int((mv - 3200) / 10)
