# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""给 demo 视频混口播 + 背景音乐 → 版本化 demo_vN.mp4

用法: python scripts/add_bgm.py
输入 data/demo_video/demo_full.mp4（splice_broll.py 产出）+ narration.wav，输出 demo_v{N}.mp4（h264 + aac）。
三路混流：视频 + 口播（满音量）+ BGM（低音量 15%）。混完自动清理中间产物。
"""
import math
import re
import struct
import subprocess
import sys
import wave
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "data" / "demo_video"
SAMPLE_RATE = 44100
BGM_VOLUME = 0.15  # 背景音乐相对音量

# 和弦进行 Cmaj7 → G → Am7 → Fmaj7（C 大调 I–V–vi–IV），每和弦 4.2s
CHORDS = [
    [261.63, 329.63, 392.00, 493.88],
    [196.00, 246.94, 293.66, 392.00],
    [220.00, 261.63, 329.63, 392.00],
    [174.61, 220.00, 261.63, 329.63],
]
CHORD_LEN = 4.2
ATTACK = 0.9


def probe_duration(path: Path) -> float:
    r = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"无法解析时长 {path}: {r.stderr[-300:]}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def synth_pad(duration: float, out_wav: Path):
    n = int(SAMPLE_RATE * duration)
    left = [0.0] * n
    right = [0.0] * n
    for chord_i in range(int(math.ceil(duration / CHORD_LEN)) + 1):
        chord = CHORDS[chord_i % len(CHORDS)]
        start = chord_i * CHORD_LEN
        for f in chord:
            for buf, mult in ((left, 1.0), (right, 1.004)):
                freq = f * mult
                for j in range(int(CHORD_LEN * SAMPLE_RATE)):
                    idx = int(start * SAMPLE_RATE) + j
                    if idx >= n:
                        break
                    local = j / SAMPLE_RATE
                    env = min(1.0, local / ATTACK, (CHORD_LEN - local) / ATTACK)
                    env = max(0.0, env)
                    amp = 0.22 / (1 + (f - chord[0]) / 130.0)
                    buf[idx] += amp * env * math.sin(2 * math.pi * freq * (start + local))
    fade = int(1.5 * SAMPLE_RATE)
    for i in range(n):
        g = 1.0
        if i < fade:
            g = i / fade
        elif i > n - fade:
            g = (n - i) / fade
        left[i] *= g
        right[i] *= g
    peak = max(max(abs(x) for x in left), max(abs(x) for x in right), 1e-9)
    scale = 0.30 / peak
    with wave.open(str(out_wav), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for l, r in zip(left, right):
            frames += struct.pack("<hh", int(l * scale * 32767), int(r * scale * 32767))
        w.writeframes(bytes(frames))


def next_version() -> int:
    nums = []
    for f in VIDEO_DIR.glob("demo_v*.mp4"):
        m = re.search(r"demo_v(\d+)\.mp4", f.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def main():
    raw = VIDEO_DIR / "demo_full.mp4"
    narration = VIDEO_DIR / "narration.wav"
    if not raw.exists():
        sys.exit("未找到 demo_full.mp4，先跑 make_demo_video.py + splice_broll.py")
    if not narration.exists():
        sys.exit("未找到 narration.wav，先跑 gen_narration.py")

    dur = probe_duration(raw)
    print(f"· 视频 {dur:.2f}s，合成 BGM ...")
    bgm = VIDEO_DIR / "bgm.wav"
    synth_pad(dur, bgm)

    n = next_version()
    out = VIDEO_DIR / f"demo_v{n}.mp4"
    print(f"· ffmpeg 三路混流 → {out.name}（口播满音量 + BGM {int(BGM_VOLUME*100)}%）...")
    fc = (f"[1:a]volume=1.0[n];[2:a]volume={BGM_VOLUME}[b];"
          f"[n][b]amix=inputs=2:duration=longest:normalize=0[a]")
    r = subprocess.run(
        [FFMPEG, "-y", "-i", str(raw), "-i", str(narration), "-i", str(bgm),
         "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
         "-c:v", "copy",
         "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    if r.returncode != 0:
        sys.exit("ffmpeg 失败:\n" + r.stderr[-1500:])

    # 清理中间产物（保留 demo_v{N}.mp4 + narration_timing.json）
    for f in (raw, bgm, narration, VIDEO_DIR / "demo_raw.webm"):
        if f.exists():
            f.unlink()
    print(f"\n完成 → {out}  ({out.stat().st_size // 1024} KB)")
    print("上传 YouTube 或嵌入 README 用这个 mp4")


if __name__ == "__main__":
    main()
