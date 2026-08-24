# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""把可灵真人镜头烘焙上「圆球讲解器 + 旁白字幕」→ broll/*.mp4，供 splice_broll.py 拼接。

用法: python scripts/make_scenes.py（先把可灵片段放到 data/demo_video/broll/raw/）
- 读 broll/raw/clip_morning.mp4、clip_gym.mp4，用 clip_player.html 播放 + orb.js 叠加字幕，录 ~9s → 转 mp4
- 字幕（headline + zh）来自 gen_narration.NARRATION（单一来源）
- 输出 data/demo_video/broll/clip_morning.mp4 / clip_gym.mp4（含圆球讲解器）
- 缺某段时跳过，splice_broll 会回退用 app 界面，不报错
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import imageio_ffmpeg
from gen_narration import NARRATION

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "data" / "demo_video"
BROLL_DIR = VIDEO_DIR / "broll"
RAW_DIR = BROLL_DIR / "raw"
CLIP_PLAYER = VIDEO_DIR / "clip_player.html"
W, H, FPS = 1440, 900, 30
RECORD_S = 9.0

# panel -> 输出文件名（可灵真人镜头，含圆球讲解器）
SCENE_MAP = {
    "morning": "clip_morning.mp4",
    "gym": "clip_gym.mp4",
}


def main():
    if not CLIP_PLAYER.exists():
        sys.exit("缺 clip_player.html")
    text = {seg[3]: (seg[2], seg[1]) for seg in NARRATION}  # panel -> (headline, zh)
    BROLL_DIR.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for panel, fname in SCENE_MAP.items():
            raw = RAW_DIR / fname
            if not raw.exists():
                print(f"· 跳过 {panel}（缺 raw/{fname}，回退 app 界面）")
                continue
            headline, zh = text[panel]
            url = CLIP_PLAYER.as_uri() + "?src=" + raw.as_uri()
            print(f"· [{panel}] 烘焙圆球讲解器 → {fname} ...")
            ctx = browser.new_context(
                viewport={"width": W, "height": H},
                record_video_dir=str(VIDEO_DIR),
                record_video_size={"width": W, "height": H},
            )
            page = ctx.new_page()
            video = page.video
            page.goto(url)
            page.wait_for_timeout(600)  # 视频首帧
            page.evaluate("([en, zh]) => setText(en, zh)", [headline, zh])
            page.wait_for_timeout(int(RECORD_S * 1000))
            ctx.close()
            webm = Path(video.path())
            out = BROLL_DIR / fname
            subprocess.run(
                [FFMPEG, "-y", "-i", str(webm),
                 "-vf", f"scale={W}:{H},fps={FPS}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-an", str(out)],
                check=True, capture_output=True,
            )
            webm.unlink()
        browser.close()
    print("\n完成 → broll/clip_*.mp4（含圆球讲解器）已生成")
    print("下一步: python scripts/gen_narration.py → make_demo_video.py → splice_broll.py → add_bgm.py")


if __name__ == "__main__":
    main()
