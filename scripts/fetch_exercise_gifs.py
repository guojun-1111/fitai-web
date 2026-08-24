# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""预下载 demo 需要展示的动作 GIF 到本地 static/exercise-gifs/，避免录制时外链 CDN 加载慢。

用法: python scripts/fetch_exercise_gifs.py
- 从 https://static.exercisedb.dev/media/{media_id}.gif 下载 8 个与叙事相关的热门动作
- 幂等：已存在的文件跳过；下载到 static/exercise-gifs/{media_id}.gif
- 服务端通过 server.py 的 /{path:path} 兜底直接 serve，无需额外配置
"""
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "exercise-gifs"
CDN = "https://static.exercisedb.dev/media/{}.gif"

# (exercise_id, media_id, 名称) —— 覆盖胸/腿/背/臂/核心，契合 demo 叙事
EXERCISES = [
    ("0662", "I4hDWkc", "push-up 俯卧撑"),
    ("0413", "HsvHqgf", "dumbbell squat 哑铃深蹲"),
    ("0031", "25GPyDY", "barbell curl 杠铃弯举"),
    ("0025", "EIeI8Vf", "barbell bench press 杠铃卧推"),
    ("0032", "ila4NZS", "barbell deadlift 杠铃硬拉"),
    ("0652", "lBDjFxJ", "pull-up 引体向上"),
    ("0735", "Bn6TXyO", "sit-up 仰卧起坐"),
    ("0464", "CosupLu", "plank 平板支撑"),
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = skipped = failed = 0
    for eid, media_id, name in EXERCISES:
        out = OUT_DIR / f"{media_id}.gif"
        if out.exists() and out.stat().st_size > 0:
            print(f"· 跳过 {name:<20} {media_id}.gif（已存在）")
            skipped += 1
            continue
        url = CDN.format(media_id)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
            out.write_bytes(data)
            print(f"· 下载 {name:<20} {media_id}.gif  {len(data)//1024} KB")
            done += 1
        except Exception as e:
            print(f"! 失败 {name} ({media_id}): {e}")
            failed += 1
    print(f"\n完成：下载 {done}，跳过 {skipped}，失败 {failed} → {OUT_DIR}")


if __name__ == "__main__":
    main()
