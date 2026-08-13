# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
屏幕显示 & 表情动画引擎
针对 2.4" SPI LCD (320×240)，用 PyGame 渲染
"""
import time
import threading
import math

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

from config import config


class DisplayEngine:
    """机器人屏幕表情渲染器"""

    def __init__(self, headless: bool = False):
        cfg = config.display
        self.width = cfg.screen_width
        self.height = cfg.screen_height
        self.headless = headless

        self._current_emotion = "smile"
        self._anim_frame = 0
        self._anim_start = time.time()
        self._lock = threading.Lock()
        self._surface = None
        self._clock = None

    def init(self):
        """初始化 PyGame 窗口（树莓派上用 framebuffer 或直接 SPI 屏驱动）"""
        if self.headless or not HAS_PYGAME:
            print("[Display] 无头模式，跳过 PyGame 初始化")
            return

        pygame.init()
        # 在树莓派上，设置环境变量 SDL_FBDEV=/dev/fb1 可输出到 SPI 屏幕
        import os
        if "SDL_FBDEV" not in os.environ:
            os.environ["SDL_FBDEV"] = "/dev/fb1"  # SPI 屏幕通常是 fb1
        self._surface = pygame.display.set_mode((self.width, self.height), pygame.NOFRAME)
        pygame.mouse.set_visible(False)
        self._clock = pygame.time.Clock()

    def update(self):
        """每帧调用一次，更新动画"""
        if self.headless or not self._surface:
            return

        with self._lock:
            self._anim_frame += 1
            self._draw_face()
            pygame.display.flip()
            if self._clock:
                self._clock.tick(15)  # 15 FPS，省 CPU

    def set_emotion(self, emotion: str):
        """切换表情: smile, worried, sleep, surprised, confetti, idle_blink"""
        with self._lock:
            self._current_emotion = emotion
            self._anim_start = time.time()

    # ---- 内部绘制 ----

    def _draw_face(self):
        if not self._surface:
            return
        bg = (30, 30, 40)
        self._surface.fill(bg)

        cx, cy = self.width // 2, self.height // 2
        elapsed = time.time() - self._anim_start

        emotion = self._current_emotion
        if emotion == "smile":
            self._draw_eyes(cx, cy - 40, "normal", elapsed)
            self._draw_mouth(cx, cy + 40, "smile", elapsed)
        elif emotion == "worried":
            self._draw_eyes(cx, cy - 40, "wide", elapsed)
            self._draw_mouth(cx, cy + 40, "frown", elapsed)
        elif emotion == "sleep":
            self._draw_eyes(cx, cy - 40, "closed", elapsed)
            self._draw_mouth(cx, cy + 50, "o", elapsed)
        elif emotion == "surprised":
            self._draw_eyes(cx, cy - 40, "wide", elapsed)
            self._draw_mouth(cx, cy + 45, "o", elapsed)
        elif emotion == "confetti":
            self._draw_confetti_particles(elapsed)
            self._draw_eyes(cx, cy - 40, "happy", elapsed)
            self._draw_mouth(cx, cy + 40, "big_smile", elapsed)
        else:  # idle_blink
            self._draw_eyes(cx, cy - 40, "normal", elapsed)
            self._draw_mouth(cx, cy + 40, "smile", elapsed)

    def _draw_eyes(self, cx, cy, style, t):
        """画双眼"""
        eye_gap = 35
        eye_r = 12
        white = (255, 255, 255)
        pupil_color = (60, 60, 80)

        for ex in [cx - eye_gap, cx + eye_gap]:
            if style == "closed":
                # 眯成一条线
                pygame.draw.ellipse(self._surface, (180, 180, 200),
                                    (ex - eye_r, cy - 3, eye_r * 2, 6))
            elif style == "wide":
                # 大眼睛
                pygame.draw.circle(self._surface, white, (ex, cy), eye_r + 3)
                pygame.draw.circle(self._surface, pupil_color, (ex, cy), eye_r - 3)
            elif style == "happy":
                # 弯月眼 ^_^
                pygame.draw.ellipse(self._surface, (180, 180, 220),
                                    (ex - eye_r, cy - 3, eye_r * 2, 8))
            else:
                # 正常眼 + 眨眼
                blink = ((t * 100) % 300) < 10  # 每 3 秒眨一次
                if blink:
                    pygame.draw.ellipse(self._surface, (200, 200, 220),
                                        (ex - eye_r, cy - 1, eye_r * 2, 3))
                else:
                    pygame.draw.circle(self._surface, white, (ex, cy), eye_r)
                    pygame.draw.circle(self._surface, pupil_color, (ex, cy), eye_r - 4)

    def _draw_mouth(self, cx, cy, style, t):
        """画嘴巴"""
        if style == "smile":
            rect = (cx - 15, cy - 5, 30, 15)
            pygame.draw.arc(self._surface, (200, 200, 220), rect, 0.2, math.pi - 0.2, 3)
        elif style == "big_smile":
            rect = (cx - 20, cy - 10, 40, 25)
            pygame.draw.arc(self._surface, (200, 200, 220), rect, 0.1, math.pi - 0.1, 3)
        elif style == "frown":
            rect = (cx - 15, cy + 5, 30, 15)
            pygame.draw.arc(self._surface, (200, 200, 220), rect, math.pi + 0.2, -0.2, 3)
        elif style == "o":
            r = 10 if style == "o" else 14
            pygame.draw.circle(self._surface, (80, 80, 100), (cx, cy), r)

    def _draw_confetti_particles(self, t):
        """庆祝撒花粒子（简化版）"""
        import random
        seed = int(t * 10)
        rng = random.Random(seed)
        colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255),
                   (255, 255, 100), (255, 100, 255)]
        for _ in range(20):
            x = rng.randint(0, self.width)
            y = (rng.randint(0, self.height) + int(t * 80)) % self.height
            color = rng.choice(colors)
            pygame.draw.circle(self._surface, color, (x, y), rng.randint(2, 5))

    def quit(self):
        if HAS_PYGAME:
            pygame.quit()
