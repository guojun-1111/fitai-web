# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""给 demo 视频混口播 + 背景音乐 → 版本化 demo_vN.mp4

用法: python scripts/add_bgm.py
输入 data/demo_video/demo_full.mp4（splice_broll.py 产出）+ narration.wav，输出 demo_v{N}.mp4（h264 + aac）。
三路混流：视频 + 口播（满音量）+ BGM（温暖 Pad + 低音贝斯 + 心跳脉冲 + 闪烁琶音，~22% 音量）。
若 data/demo_video/broll/bgm.mp3 存在则用它当 BGM（跳过合成）。混完保留 demo_full.mp4 + narration.wav 便于快速迭代。
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
BGM_VOLUME = 0.22  # 背景音乐相对音量（可听见、但不压口播）

# 和弦进行 Cmaj7 → G → Am7 → Fmaj7（C 大调 I–V–vi–IV）
CHORDS = [
    [261.63, 329.63, 392.00, 493.88],
    [196.00, 246.94, 293.66, 392.00],
    [220.00, 261.63, 329.63, 392.00],
    [174.61, 220.00, 261.63, 329.63],
]
BASS_ROOTS = [65.41, 98.00, 110.00, 87.31]  # C2 G2 A2 F2
CHORD_LEN = 5.0
ATTACK = 1.2
RELEASE = 1.2
HEART_PERIOD = 0.94   # ~64 BPM 心跳
PI2 = 2 * math.pi


def probe_duration(path: Path) -> float:
    r = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"无法解析时长 {path}: {r.stderr[-300:]}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _add_pluck(mix, t0, freq, amp, n):
    """闪烁琶音单音：高八度弹拨，快衰减。"""
    dur = 0.4
    start = int(t0 * SAMPLE_RATE)
    if start >= n:
        return
    dph = PI2 * freq / SAMPLE_RATE
    ph = 0.0
    sin = math.sin
    for j in range(int(dur * SAMPLE_RATE)):
        idx = start + j
        if idx >= n:
            break
        env = math.exp(-(j / SAMPLE_RATE) / 0.12)
        mix[idx] += amp * env * sin(ph)
        ph += dph


def _add_thump(mix, t0, amp, n):
    """心跳单跳：低频正弦 80→48Hz 快降频 + 指数衰减。"""
    dur = 0.12
    start = int(t0 * SAMPLE_RATE)
    if start >= n:
        return
    sin = math.sin
    for j in range(int(dur * SAMPLE_RATE)):
        idx = start + j
        if idx >= n:
            break
        local = j / SAMPLE_RATE
        phase = PI2 * (80.0 * local - 20.0 * (local * local) / dur)
        env = math.exp(-local / 0.05)
        mix[idx] += amp * env * sin(phase)


def synth_score(duration: float, out_wav: Path):
    """温暖氛围 BGM：暖 Pad + 低音贝斯 + 心跳脉冲 + 闪烁琶音，前奏淡入尾奏淡出。"""
    n = int(SAMPLE_RATE * duration)
    mix = [0.0] * n
    sin = math.sin
    nchords = int(math.ceil(duration / CHORD_LEN))

    # 1. 暖 Pad：每音 2 个失谐正弦（合唱感），慢 attack/release，低音更响高音滚降
    for ci in range(nchords):
        chord = CHORDS[ci % len(CHORDS)]
        root = chord[0]
        start = int(ci * CHORD_LEN * SAMPLE_RATE)
        for f in chord:
            amp = 0.16 / (1 + (f - root) / 130.0)
            for det in (0.997, 1.003):
                freq = f * det
                ph = PI2 * freq * (ci * CHORD_LEN)
                dph = PI2 * freq / SAMPLE_RATE
                for j in range(int(CHORD_LEN * SAMPLE_RATE)):
                    idx = start + j
                    if idx >= n:
                        break
                    local = j / SAMPLE_RATE
                    env = min(1.0, local / ATTACK, (CHORD_LEN - local) / RELEASE)
                    if env > 0:
                        mix[idx] += amp * env * sin(ph)
                    ph += dph

    # 2. 低音贝斯：根音正弦，柔和贯穿
    for ci in range(nchords):
        f = BASS_ROOTS[ci % len(BASS_ROOTS)]
        start = int(ci * CHORD_LEN * SAMPLE_RATE)
        ph = PI2 * f * (ci * CHORD_LEN)
        dph = PI2 * f / SAMPLE_RATE
        for j in range(int(CHORD_LEN * SAMPLE_RATE)):
            idx = start + j
            if idx >= n:
                break
            local = j / SAMPLE_RATE
            env = min(1.0, local / 0.8, (CHORD_LEN - local) / 1.0)
            if env > 0:
                mix[idx] += 0.20 * env * sin(ph)
            ph += dph

    # 3. 心跳脉冲：lub-dub 双跳
    beat = 0.0
    while beat < duration - 0.5:
        _add_thump(mix, beat, 0.50, n)         # lub
        _add_thump(mix, beat + 0.28, 0.32, n)  # dub
        beat += HEART_PERIOD

    # 4. 闪烁琶音：高八度稀疏弹拨，密度随推进增加
    spacing0, spacing1 = 0.95, 0.55
    t = 1.5
    note_i = 0
    while t < duration - 1.0:
        chord = CHORDS[int(t // CHORD_LEN) % len(CHORDS)]
        freq = chord[note_i % len(chord)] * 2.0
        _add_pluck(mix, t, freq, 0.07, n)
        progress = t / duration
        t += spacing0 - (spacing0 - spacing1) * progress
        note_i += 1

    # 前奏淡入 + 尾奏淡出
    fade_in = int(2.0 * SAMPLE_RATE)
    fade_out = int(2.5 * SAMPLE_RATE)
    for i in range(n):
        g = 1.0
        if i < fade_in:
            g = i / fade_in
        elif i > n - fade_out:
            g = (n - i) / fade_out
        mix[i] *= g

    peak = max(max(abs(x) for x in mix), 1e-9)
    scale = 0.6 / peak
    haas = int(0.0005 * SAMPLE_RATE)  # ~0.5ms 哈斯延迟做立体声宽度
    with wave.open(str(out_wav), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for i in range(n):
            l = int(mix[i] * scale * 32767)
            r = int(mix[i - haas] * scale * 32767) if i >= haas else l
            l = max(-32767, min(32767, l))
            r = max(-32767, min(32767, r))
            frames += struct.pack("<hh", l, r)
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
    bgm = VIDEO_DIR / "bgm.wav"

    real = VIDEO_DIR / "broll" / "bgm.mp3"
    if real.exists():
        print(f"· 视频 {dur:.2f}s，检测到真实音乐 {real.name}，跳过合成 ...")
        subprocess.run(
            [FFMPEG, "-y", "-i", str(real),
             "-af", f"atrim=0:{dur:.3f},afade=t=in:d=2,afade=t=out:st={dur - 2.5:.3f}:d=2.5",
             "-ar", "44100", "-ac", "2", str(bgm)],
            check=True, capture_output=True,
        )
    else:
        print(f"· 视频 {dur:.2f}s，合成 BGM（Pad + 贝斯 + 心跳 + 琶音）...")
        synth_score(dur, bgm)

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

    # 清理中间产物（保留 demo_full.mp4 + narration.wav 便于快速迭代 BGM）
    for f in (bgm, VIDEO_DIR / "demo_raw.webm"):
        if f.exists():
            f.unlink()
    print(f"\n完成 → {out}  ({out.stat().st_size // 1024} KB)")
    print("上传 YouTube 或嵌入 README 用这个 mp4")


if __name__ == "__main__":
    main()
