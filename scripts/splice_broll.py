# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""把可灵 AI 片段拼进 demo_raw.webm → demo_full.mp4（纯视频，无音轨）

用法: python scripts/splice_broll.py（先跑 make_demo_video.py 生成 demo_raw.webm）
- 读 narration_timing.json 算每个镜头的起止时间
- 把 segment 0（开场）替换成 broll/clip_intro.mp4、segment 7（机器人）替换成 broll/clip_robot.mp4
- 中间 + 结尾从 demo_raw.webm 切出，统一重编码为 h264 1440x900 30fps，concat 成 demo_full.mp4
- 缺某个 AI 片段时回退用录制里的占位卡，不报错
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
GAP = 0.4

# 统一缩放 + 居中填充到 1440x900（16:9 的可灵片段上下会留窄黑边）
SCALE_VF = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"


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


def make_part(src: Path, out: Path, start, end):
    """从 src 切 [start, end) 并统一重编码。end=None 表示到片尾。"""
    cmd = [FFMPEG, "-y", "-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(src), "-vf", SCALE_VF, "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def make_clip_part(src: Path, out: Path, target: float):
    """把 AI 片段统一重编码，并对齐到 target 秒（长的裁剪、短的补最后一帧）。"""
    src_dur = probe_duration(src)
    vf = SCALE_VF
    if src_dur < target - 0.05:
        vf += f",tpad=stop_mode=clone:stop_duration={target - src_dur:.3f}"
    cmd = [FFMPEG, "-y", "-i", str(src)]
    if src_dur > target + 0.05:
        cmd += ["-t", f"{target:.3f}"]
    cmd += ["-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def concat_parts(parts, out: Path):
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
    bounds = segment_bounds(timing)
    panels = [t["panel"] for t in timing]
    # 定位 intro(0) / robot(7) 边界
    intro_b = bounds[0]
    robot_i = panels.index("robot") if "robot" in panels else None
    robot_b = bounds[robot_i] if robot_i is not None else None

    tmp = VIDEO_DIR / "tmp_parts"
    tmp.mkdir(exist_ok=True)
    parts = []

    # 1) 开场：AI 片段或占位卡
    clip_intro = BROLL_DIR / "clip_intro.mp4"
    p0 = tmp / "p0_intro.mp4"
    if clip_intro.exists():
        print(f"· 用 clip_intro.mp4（对齐 {intro_b[1] - intro_b[0]:.2f}s）...")
        make_clip_part(clip_intro, p0, intro_b[1] - intro_b[0])
    else:
        print("· 缺 clip_intro.mp4，回退用录制里的开场卡")
        make_part(raw, p0, intro_b[0], intro_b[1])
    parts.append(p0)

    # 2) 中间段（home..dashboard，即 bounds[1] 起点到 robot 起点）
    mid_start = bounds[1][0]
    mid_end = robot_b[0] if robot_b else bounds[-2][1]
    p1 = tmp / "p1_middle.mp4"
    print(f"· 切中间段 [{mid_start:.2f}s, {mid_end:.2f}s) ...")
    make_part(raw, p1, mid_start, mid_end)
    parts.append(p1)

    # 3) 机器人：AI 片段或占位卡
    if robot_b:
        clip_robot = BROLL_DIR / "clip_robot.mp4"
        p2 = tmp / "p2_robot.mp4"
        if clip_robot.exists():
            print(f"· 用 clip_robot.mp4（对齐 {robot_b[1] - robot_b[0]:.2f}s）...")
            make_clip_part(clip_robot, p2, robot_b[1] - robot_b[0])
        else:
            print("· 缺 clip_robot.mp4，回退用录制里的机器人卡")
            make_part(raw, p2, robot_b[0], robot_b[1])
        parts.append(p2)

        # 4) 结尾段（outro）
        p3 = tmp / "p3_outro.mp4"
        print(f"· 切结尾段 [{robot_b[1]:.2f}s, {bounds[-1][1]:.2f}s) ...")
        make_part(raw, p3, robot_b[1], bounds[-1][1])
        parts.append(p3)
    else:
        # 无 robot 段（异常），直接把结尾也并入中间
        print("· 未找到 robot 段，结尾并入中间")
        # 已含在 mid_end = bounds[-2][1]；补上 outro
        p3 = tmp / "p3_outro.mp4"
        make_part(raw, p3, bounds[-2][1], bounds[-1][1])
        parts.append(p3)

    out = VIDEO_DIR / "demo_full.mp4"
    print("· concat 成 demo_full.mp4 ...")
    concat_parts(parts, out)

    # 清理临时分片
    for f in tmp.glob("p*.mp4"):
        f.unlink()
    tmp.rmdir()
    print(f"\n完成 → {out}  ({out.stat().st_size // 1024} KB)")
    print("下一步: python scripts/add_bgm.py")


if __name__ == "__main__":
    main()
