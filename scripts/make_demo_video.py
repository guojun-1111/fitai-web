# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""Demo 视频录制器 v3（动态实操 + 中英双语字幕 + 假摄像头姿势识别）：读 narration_timing.json → Edge 无头录真实界面 → webm

用法: python scripts/make_demo_video.py（先跑 gen_narration.py 生成口播与 timing）
输出 data/demo_video/demo_raw.webm（随后 splice_broll.py 拼 AI 片段 → add_bgm.py 混音 → demo_v3.mp4）。

动态实操：登录→首页健康环+滚动→动作纠正(假摄像头 MediaPipe 实时骨架)→AI 教练聊天(真实打字)→
健康数据钻取→因果洞察→What-If 拖滑杆→机器人占位→结尾卡。
只影响 demo 账号。insights 因果图计算慢，先在一个不录制的上下文里预热缓存。
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 找 make_demo_shots

import imageio_ffmpeg

from make_demo_shots import (
    ROOT, BASE, DEMO_USER, DEMO_PASS, ensure_server, ensure_user, seed,
    click_panel, api_post, login,
)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO_DIR = ROOT / "data" / "demo_video"
BROLL_DIR = VIDEO_DIR / "broll"
VIEW_W, VIEW_H = 1440, 900
GAP = 0.4  # 与 gen_narration.py 保持一致
INIT_JS = "localStorage.setItem('fitai-theme','light');localStorage.setItem('fitai-onboarded','1');"

PANEL_TITLES = {
    "home": ("Home", "首页"),
    "pose": ("Real-time Form Correction", "动作纠正"),
    "chat": ("AI Coach", "AI 教练"),
    "health": ("Recovery & Health", "健康数据"),
    "insights": ("Causal Discovery", "因果洞察"),
    "dashboard": ("What-If Counterfactuals", "因果推演"),
}

INTRO_HTML = """
<div style="font-size:58px;font-weight:700;letter-spacing:1px;">FitAI-Web</div>
<div style="font-size:26px;margin-top:18px;opacity:0.92;">Open-Source AI Fitness Coach</div>
"""

ROBOT_HTML = """
<div style="font-size:44px;font-weight:650;">Companion Robot</div>
<div style="font-size:22px;margin-top:16px;opacity:0.85;">Watches your form in real time</div>
"""

OUTRO_HTML = """
<div style="font-size:40px;font-weight:650;">FitAI-Web on GitHub</div>
<div style="font-size:24px;margin-top:16px;opacity:0.9;">github.com/guojun-1111/fitai-web</div>
<div style="font-size:17px;margin-top:12px;opacity:0.65;">MIT (algorithms) + AGPL-3.0 (platform)</div>
"""

CARD_JS = """
(html) => {
  let el = document.getElementById('demo-card');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-card';
    el.style.cssText = 'position:fixed;inset:0;z-index:10000;pointer-events:none;display:flex;flex-direction:column;' +
      'align-items:center;justify-content:center;color:#fff;' +
      'background:linear-gradient(160deg,#0f172a 0%,#1e293b 100%);' +
      'font-family:-apple-system,Segoe UI,Roboto,sans-serif;text-align:center;';
    document.body.appendChild(el);
  }
  el.innerHTML = html;
}
"""

# 中英双语字幕：英文上行（小、标签感）+ 中文下行（大、正文）
CAPTION_JS = """
([en, zh]) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-caption';
    el.style.cssText = 'position:fixed;bottom:56px;left:50%;transform:translateX(-50%);' +
      'z-index:9999;pointer-events:none;background:rgba(8,12,22,0.80);color:#fff;padding:16px 36px;border-radius:18px;' +
      'text-align:center;font-family:-apple-system,Segoe UI,Roboto,sans-serif;' +
      'backdrop-filter:blur(14px);box-shadow:0 12px 38px rgba(0,0,0,0.45);max-width:1120px;';
    document.body.appendChild(el);
  }
  el.innerHTML = '<div style="font-size:15px;font-weight:600;letter-spacing:1px;opacity:0.72;">' + en + '</div>' +
    '<div style="font-size:24px;margin-top:8px;font-weight:600;">' + zh + '</div>';
}
"""

HIDE_DASHBOARD_EMPTY = """
() => {
  ['video-grid', 'achievements-row', 'exercise-stats'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  document.querySelectorAll('#panel-dashboard .section-title').forEach(el => {
    const t = el.textContent;
    if (t.includes('视频') || t.includes('徽章') || t.includes('动作统计')) el.style.display = 'none';
  });
}
"""

# 追加一条 AI 助手消息（不覆盖已有消息），用于聊天镜头的确定性回复
CHAT_QUESTION = "How should I train tomorrow?"
CHAT_REPLY = """Based on your recovery data (resting HR 58 bpm, dropping for 2 days), tomorrow is good for moderate intensity:
- Easy run 30 min, keep HR at 130-140 bpm
- or upper-body strength 40 min

Afterwards, get 25g protein — you're 18g short today."""

APPEND_ASSISTANT_JS = """
(text) => {
  const box = document.getElementById('chat-messages');
  if (!box) return 'no-box';
  const div = document.createElement('div');
  div.className = 'message assistant';
  const av = document.createElement('div');
  av.className = 'msg-avatar';
  av.textContent = 'AI';
  const body = document.createElement('div');
  body.className = 'msg-content';
  body.innerText = text;
  div.appendChild(av); div.appendChild(body);
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return 'ok';
}
"""

# 假摄像头失败时的兜底：注入一张诊断卡（复用 pose.js showDiagnosisCard 的结构）
POSE_FALLBACK_JS = """
() => {
  const container = document.getElementById('panel-pose');
  if (!container || container.querySelector('.pose-diagnosis-card')) return 'exists';
  const card = document.createElement('div');
  card.className = 'pose-diagnosis-card';
  card.innerHTML =
    '<div class="pd-header">动作分析完成</div>' +
    '<div class="pd-body">' +
      '<div class="pd-diag">深蹲底部膝角偏大，髋部下沉不足，建议加强踝关节活动度</div>' +
      '<div class="pd-path">因果链：踝背屈受限 → 髋代偿 → 膝角过大</div>' +
      '<div class="pd-conf">置信度：82%</div>' +
      '<div class="pd-corr">纠正：箱式深蹲，控制下蹲速度</div>' +
    '</div>' +
    '<button class="pd-dismiss" onclick="this.parentElement.remove()">已了解</button>';
  container.appendChild(card);
  return 'ok';
}
"""


def show_caption(page, en, zh):
    page.evaluate(CAPTION_JS, [en, zh])


def show_card(page, html):
    page.evaluate(CARD_JS, html)


def clear_overlay(page):
    page.evaluate("() => { ['demo-caption','demo-card'].forEach(id => { const e = document.getElementById(id); if (e) e.remove(); }); }")


def scroll_active(page, dy):
    page.evaluate(f"() => {{ const p = document.querySelector('.panel.active'); if (p) p.scrollTop += {dy}; }}")


def warm(browser, has_camera):
    """在不录制的上下文里预热 insights（PC-stable）+ 动作纠正（MediaPipe 模型），进缓存后正式录制秒出。"""
    ctx = browser.new_context(viewport={"width": VIEW_W, "height": VIEW_H}, locale="zh-CN")
    if has_camera:
        ctx.grant_permissions(["camera"])
    ctx.add_init_script(INIT_JS)
    page = ctx.new_page()
    login(page)
    print("· 预热 insights（PC-stable 因果计算）...")
    click_panel(page, "insights")
    try:
        page.wait_for_selector("#panel-insights canvas", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(1200)
    if has_camera:
        print("· 预热动作纠正（MediaPipe 模型 + 假摄像头）...")
        click_panel(page, "pose")
        page.wait_for_timeout(500)
        page.evaluate("() => { const b = document.getElementById('pose-start-btn'); if (b) b.click(); }")
        page.wait_for_timeout(8000)  # 首次下载 .task + wasm + GPU 初始化
    ctx.close()
    print("· 预热完成")


def prepare_squat_y4m() -> Path | None:
    """把可灵的深蹲 mp4 转成 Playwright 假摄像头要求的 y4m。"""
    src = BROLL_DIR / "clip_squat.mp4"
    if not src.exists():
        print("· 未找到 broll/clip_squat.mp4，动作纠正将用兜底诊断卡")
        return None
    y4m = VIDEO_DIR / "clip_squat.y4m"
    print("· 转换 clip_squat.mp4 → y4m（假摄像头输入）...")
    subprocess.run(
        [FFMPEG, "-y", "-i", str(src), "-vf", "scale=480:360,format=yuv420p", "-pix_fmt", "yuv420p", str(y4m)],
        check=True, capture_output=True,
    )
    return y4m


def record():
    timing = json.loads((VIDEO_DIR / "narration_timing.json").read_text(encoding="utf-8"))
    from playwright.sync_api import sync_playwright
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    for old in VIDEO_DIR.glob("*.webm"):
        old.unlink()

    # 用 init script 在每页加载时注入开场标题卡，盖住登录画面，让视频从标题卡开始
    intro_init = INIT_JS + """
document.addEventListener('DOMContentLoaded', () => {
  const el = document.createElement('div');
  el.id = 'demo-card';
  el.style.cssText = 'position:fixed;inset:0;z-index:10000;pointer-events:none;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;background:linear-gradient(160deg,#0f172a 0%,#1e293b 100%);font-family:-apple-system,Segoe UI,Roboto,sans-serif;text-align:center;';
  el.innerHTML = """ + repr(INTRO_HTML) + """;
  document.body.appendChild(el);
});
"""

    y4m = prepare_squat_y4m()
    launch_args = ["--use-fake-device-for-media-stream"]
    if y4m:
        launch_args.append(f"--use-file-for-fake-video-capture={y4m}")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=launch_args)
        warm(browser, y4m is not None)

        ctx = browser.new_context(
            viewport={"width": VIEW_W, "height": VIEW_H},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": VIEW_W, "height": VIEW_H},
            locale="zh-CN",
        )
        if y4m:
            ctx.grant_permissions(["camera"])
        ctx.add_init_script(intro_init)
        page = ctx.new_page()

        # segment 0：开场标题卡（登录在其下完成），时长 = 口播句 0（含登录耗时）
        print("· 登录（标题卡已覆盖）...")
        t0 = time.time()
        login(page)
        login_elapsed = time.time() - t0
        intro_wait = max(0.0, timing[0]["duration"] - login_elapsed)
        print(f"· 开场标题卡 (登录 {login_elapsed:.1f}s + 等待 {intro_wait:.1f}s) ...")
        page.wait_for_timeout(int(intro_wait * 1000))
        clear_overlay(page)
        page.wait_for_timeout(int(GAP * 1000))

        # segment 1..8 逐段录制
        for i, seg in enumerate(timing[1:], start=1):
            panel = seg["panel"]
            dur = seg["duration"]
            zh = seg["zh"]
            en = seg["en"]
            print(f"· [{i}] {panel} ({dur}s) ...")

            if panel in ("intro", "robot", "outro"):
                card = {"intro": INTRO_HTML, "robot": ROBOT_HTML, "outro": OUTRO_HTML}[panel]
                show_card(page, card)
                page.wait_for_timeout(int(dur * 1000))
                clear_overlay(page)
            else:
                title, _ = PANEL_TITLES.get(panel, (panel, zh))
                show_caption(page, title, zh)
                t0 = time.time()
                _play_panel(page, panel, y4m is not None)
                elapsed = time.time() - t0
                remain = max(0.3, dur - elapsed)
                page.wait_for_timeout(int(remain * 1000))
                clear_overlay(page)
            if i < len(timing) - 1:
                page.wait_for_timeout(int(GAP * 1000))

        ctx.close()
        browser.close()

    if y4m:
        y4m.unlink()
    webm = sorted(VIDEO_DIR.glob("*.webm"))[-1]
    raw = VIDEO_DIR / "demo_raw.webm"
    webm.rename(raw)
    print(f"\n完成 → {raw}  ({raw.stat().st_size // 1024} KB)")
    print("下一步: python scripts/splice_broll.py")


def _play_panel(page, panel, has_camera):
    if panel == "home":
        click_panel(page, "home")
        page.wait_for_timeout(1800)   # 健康环加载 + 动画
        scroll_active(page, 360)
        page.wait_for_timeout(400)
    elif panel == "pose":
        click_panel(page, "pose")
        page.wait_for_timeout(800)
        page.evaluate("() => { const b = document.querySelector('.ex-btn[data-ex=\"squat\"]'); if (b) b.click(); }")
        page.wait_for_timeout(300)
        if has_camera:
            page.evaluate("() => { const b = document.getElementById('pose-start-btn'); if (b) b.click(); }")
            # 已预热，模型秒加载，等待骨架出现 + 几组计数
            page.wait_for_timeout(2500)
        else:
            page.evaluate(POSE_FALLBACK_JS)
            page.wait_for_timeout(800)
    elif panel == "chat":
        click_panel(page, "chat")
        page.wait_for_timeout(800)
        page.fill("#chat-input", CHAT_QUESTION)
        page.wait_for_timeout(600)
        page.click("#send-btn")
        page.wait_for_timeout(1500)   # 用户气泡 + 思考中
        page.evaluate(APPEND_ASSISTANT_JS, CHAT_REPLY)
        page.wait_for_timeout(500)
    elif panel == "health":
        click_panel(page, "health")
        page.wait_for_timeout(1500)   # 6 张图加载
        scroll_active(page, 300)
        page.wait_for_timeout(300)
        page.evaluate("() => { const c = document.querySelector('.health-stat-clickable[data-metric=\"heart_rate\"]'); if (c) c.click(); }")
        page.wait_for_timeout(1200)   # 详情钻取图加载
    elif panel == "insights":
        click_panel(page, "insights")
        page.wait_for_timeout(2000)   # 因果图（已预热缓存）
    elif panel == "dashboard":
        click_panel(page, "dashboard")
        page.wait_for_timeout(1000)
        page.evaluate(HIDE_DASHBOARD_EMPTY)
        scroll_active(page, 500)
        page.wait_for_timeout(400)
        # 拖滑杆 + 推演
        page.evaluate("""() => {
          const s = document.getElementById('whatif-slider');
          s.value = 600;
          s.dispatchEvent(new Event('input', {bubbles:true}));
          const v = document.getElementById('whatif-value');
          if (v) v.textContent = '600分钟';
        }""")
        page.wait_for_timeout(400)
        page.evaluate("() => { const b = document.getElementById('whatif-btn'); if (b) b.click(); }")
        page.wait_for_timeout(1300)   # 推演结果渲染


def main():
    proc = ensure_server()
    try:
        uid = ensure_user()
        seed(uid)
        api_post("/api/auth/login", {"username": DEMO_USER, "password": DEMO_PASS})  # 清缓存
        record()
    finally:
        if proc:
            proc.terminate()
            print("· 已停止临时服务器")


if __name__ == "__main__":
    main()
