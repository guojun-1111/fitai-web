# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
语音合成模块 — 支持 Edge-TTS（在线）和 pyttsx3（离线）
"""
import time
import threading
import subprocess
import tempfile
import os

from config import config


class TTSEngine:
    """中文语音合成，生成音频并播放"""

    def __init__(self):
        self.engine = config.tts_engine
        self.voice = config.tts_voice
        self.rate = config.tts_rate
        self._enabled = self.engine != "none"
        self._playing = False
        self._queue = []
        self._lock = threading.Lock()

        if self.engine == "pyttsx3":
            self._init_pyttsx3()

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._tts = pyttsx3.init()
            self._tts.setProperty("rate", 160)
            # 在树莓派上需要 voices 支持中文
            voices = self._tts.getProperty("voices")
            for v in voices:
                if "chinese" in v.name.lower() or "zh" in v.id.lower():
                    self._tts.setProperty("voice", v.id)
                    break
        except Exception as e:
            print(f"[TTS] pyttsx3 初始化失败: {e}")
            self.engine = "none"

    def speak(self, text: str, block: bool = False):
        """语音播报一段文字"""
        if not self._enabled:
            print(f"[TTS] {text}")
            return

        if block:
            self._speak_sync(text)
        else:
            threading.Thread(target=self._speak_sync, args=(text,), daemon=True).start()

    def _speak_sync(self, text: str):
        with self._lock:
            self._playing = True

        try:
            if self.engine == "edge":
                self._speak_edge(text)
            elif self.engine == "pyttsx3":
                self._speak_pyttsx3(text)
            else:
                print(f"[TTS] {text}")
        except Exception as e:
            print(f"[TTS] 播放失败: {e}")
        finally:
            with self._lock:
                self._playing = False

    def _speak_edge(self, text: str):
        """使用 Edge-TTS CLI 生成音频并播放"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            cmd = [
                "edge-tts",
                "--text", text,
                "--voice", self.voice,
                "--rate", self.rate,
                "--write-media", tmp_path,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode != 0:
                print(f"[TTS] Edge-TTS 生成失败: {result.stderr.decode()}")
                os.unlink(tmp_path)
                return

            # 播放：优先用 ffplay（静默），回退到 pygame
            for player in [
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp_path],
                ["mpg123", "-q", tmp_path],
            ]:
                try:
                    subprocess.run(player, timeout=30)
                    break
                except FileNotFoundError:
                    continue

            os.unlink(tmp_path)
        except Exception as e:
            print(f"[TTS] Edge-TTS error: {e}")

    def _speak_pyttsx3(self, text: str):
        if hasattr(self, "_tts"):
            self._tts.say(text)
            self._tts.runAndWait()

    @property
    def is_speaking(self) -> bool:
        return self._playing
