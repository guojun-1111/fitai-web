# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""把可灵真人镜头（broll/*.mp4，make_scenes.py 烘焙圆球讲解器）拼进 demo_raw.webm → demo_full.mp4（纯视频，无音轨）

用法: python scripts/splice_broll.py（先跑 make_demo_video.py 生成 demo_raw.webm + make_scenes.py 生成 broll）
- 读 narration_timing.json 算每个镜头的起止时间
- 把 morning/gym 两段替换成 broll 里的可灵真人镜头（已烘焙圆球讲解器 + 字幕）
- 其余段从 demo_raw.webm 切出（app 界面 + 圆球讲解器），统一重编码为 h264 1440x900 30fps，concat 成 demo_full.mp4
- 缺某个片段时回退用录制里的 app 界面，不报错
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "data" / "demo_video"
BROLL_DIR = VIDEO_DIR / "broll"
W, H, FPS = 1440, 900, 30
GAP = 0.6
FADE = 0.25  # 转场淡入淡出秒数（落在句间停顿里，柔和呼吸式过渡）

# 统一缩放 + 居中填充到 1440x900（16:9 的可灵片段上下会留窄黑边）
SCALE_VF = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"

# 每个镜头对应的可灵真人镜头（make_scenes.py 烘焙圆球讲解器，缺失则回退用录制里的 app 界面）
BROLL_MAP = {
    "morning": "clip_morning.mp4",
    "gym": "clip_gym.mp4",
}


def probe_duration(path: Path) -> float:
    r = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        raise RuntimeError(f"无法解析时长 {path}: {r.stderr[-300:]}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def segment_bounds(timing):
    bounds = []
    t = 0.0
    for i, seg in enumerate(timing):
        d = seg["duration"]
        bounds.append((round(t, 3), round(t + d, 3)))
        t += d + GAP
    return bounds


def load_bounds(timing):
    """优先用录制时的真实分段边界（make_demo_video.py 产出 segment_bounds.json），
    避免录制里 click/等待的固定开销累积成漂移；否则回退按旁白时长推算。"""
    real = VIDEO_DIR / "segment_bounds.json"
    if real.exists():
        starts = json.loads(real.read_text(encoding="utf-8"))
        return [(round(starts[i], 3), round(starts[i + 1], 3)) for i in range(len(starts) - 1)]
    return segment_bounds(timing)


def make_part(src: Path, out: Path, start, end):
    """从 src 切 [start, end) 并统一重编码（含淡入淡出转场）。"""
    dur = end - start
    vf = SCALE_VF + f",fade=t=in:st=0:d={FADE},fade=t=out:st={dur - FADE:.3f}:d={FADE}"
    cmd = [FFMPEG, "-y", "-ss", str(start), "-to", str(end),
           "-i", str(src), "-vf", vf, "-r", str(FPS),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-an", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def make_clip_part(src: Path, out: Path, target: float):
    """把场景片段统一重编码，并对齐到 target 秒（长的裁剪、短的补最后一帧，含淡入淡出）。"""
    src_dur = probe_duration(src)
    vf = SCALE_VF
    if src_dur < target - 0.05:
        vf += f",tpad=stop_mode=clone:stop_duration={target - src_dur:.3f}"
    vf += f",fade=t=in:st=0:d={FADE},fade=t=out:st={target - FADE:.3f}:d={FADE}"
    cmd = [FFMPEG, "-y", "-i", str(src)]
    if src_dur > target + 0.05:
        cmd += ["-t", f"{target:.3f}"]
    cmd += ["-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def concat_parts(parts, out: Path):
    """硬切串接（-c copy），各段已含句尾停顿，保证与口播精确对齐。"""
    list_file = VIDEO_DIR / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", str(out)],
        check=True, capture_output=True,
    )
    list_file.unlink()


def main():
    timing_path = VIDEO_DIR / "narration_timing.json"
    raw = VIDEO_DIR / "demo_raw.webm"
    if not timing_path.exists():
        sys.exit("缺 narration_timing.json，先跑 gen_narration.py")
    if not raw.exists():
        sys.exit("缺 demo_raw.webm，先跑 make_demo_video.py")

    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    bounds = load_bounds(timing)
    n = len(timing)

    tmp = VIDEO_DIR / "tmp_parts"
    tmp.mkdir(exist_ok=True)
    parts = []

    for i, seg in enumerate(timing):
        panel = seg["panel"]
        start, end = bounds[i]
        # 段尾含句间停顿（下一句起点），保证视频与口播总时长精确对齐
        span_end = bounds[i + 1][0] if i < n - 1 else end
        dur = span_end - start
        bfile = BROLL_MAP.get(panel)
        clip = BROLL_DIR / bfile if bfile else None
        p = tmp / f"p{i}_{panel}.mp4"
        if clip and clip.exists():
            print(f"· [{i}] {panel} → {bfile}（对齐 {dur:.2f}s）...")
            make_clip_part(clip, p, dur)
        else:
            if bfile:
                print(f"· [{i}] {panel} 缺 {bfile}，回退录制")
            print(f"· [{i}] {panel} 切录制 [{start:.2f}s, {span_end:.2f}s)...")
            make_part(raw, p, start, span_end)
        parts.append(p)

    out = VIDEO_DIR / "demo_full.mp4"
    print(f"· 硬切串接 {len(parts)} 段 → demo_full.mp4 ...")
    concat_parts(parts, out)

    for f in tmp.glob("p*.mp4"):
        f.unlink()
    tmp.rmdir()
    print(f"\n完成 → {out}  ({out.stat().st_size // 1024} KB)")
    print("下一步: python scripts/add_bgm.py")


if __name__ == "__main__":
    main()
