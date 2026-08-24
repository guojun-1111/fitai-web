# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""Demo 视频录制器 v9（Siri 式移动圆球讲解员 + 新手旅程）：读 narration_timing.json → Edge 无头录真实界面 → webm

用法: python scripts/make_demo_video.py（先跑 gen_narration.py 生成口播与 timing）
输出 data/demo_video/demo_raw.webm（随后 splice_broll.py 拼可灵真人镜头 → add_bgm.py 混音 → demo_v9.mp4）。

新手旅程：晨起纠结(可灵) → 引导定计划 → 健身房迷茫(可灵) → 动作库 → AI 纠正 → AI 教练 →
健康恢复 → 因果洞察 → What-If → 开源结尾。
一个 Siri 式发光圆球讲解员全程随讲解移动（圆球 + 说话波浪 + 旁白字幕），边讲边指到当前导航功能。
只影响 demo 账号。
"""
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import imageio_ffmpeg

from make_demo_shots import (
    ROOT, BASE, DEMO_USER, DEMO_PASS, ensure_server, ensure_user, seed,
    click_panel, api_post, login,
)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO_DIR = ROOT / "data" / "demo_video"
BROLL_DIR = VIDEO_DIR / "broll"
DB = ROOT / "data" / "fitai.db"
VIEW_W, VIEW_H = 1440, 900
GAP = 0.6
INIT_JS = "localStorage.setItem('fitai-theme','dark');localStorage.setItem('fitai-onboarded','1');"

# 登录时盖住表单的全屏暗色遮罩（登录完移除）
COVER_JS = """
document.addEventListener('DOMContentLoaded', () => {
  const el = document.createElement('div');
  el.id = 'demo-cover';
  el.style.cssText = 'position:fixed;inset:0;z-index:20000;pointer-events:none;background:linear-gradient(160deg,#0f172a 0%,#1e293b 100%);';
  document.body.appendChild(el);
});
"""

# 可灵真人镜头段（splice 时替换成 broll/*.mp4，录制时只占位 + 圆球讲解）
BROLL_PANELS = {"morning", "gym"}

OUTRO_HTML = """
<div style="display:flex;flex-direction:column;align-items:center;">
  <div style="width:96px;height:96px;border-radius:24px;display:flex;align-items:center;justify-content:center;
       background:linear-gradient(145deg,#3dd68c 0%,#2bb673 100%);color:#fff;
       box-shadow:0 12px 40px rgba(61,214,140,0.45);margin-bottom:26px;">
    <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round"><path d="M14.4 14.4 9.6 9.6"/><path d="M18.657 21.485a2 2 0 1 1-2.829-2.828l-1.767 1.768a2 2 0 1 1-2.829-2.829l6.364-6.364a2 2 0 1 1 2.829 2.829l-1.768 1.767a2 2 0 1 1 2.828 2.829z"/><path d="m21.5 21.5-1.4-1.4"/><path d="M3.9 3.9 2.5 2.5"/><path d="M6.404 12.768a2 2 0 1 1-2.829-2.829l1.768-1.767a2 2 0 1 1-2.828-2.829l2.828-2.828a2 2 0 1 1 2.829 2.828l1.767-1.768a2 2 0 1 1 2.829 2.829z"/></svg>
  </div>
  <div style="font-size:56px;font-weight:750;letter-spacing:-1px;">FitAI</div>
  <div style="font-size:22px;margin-top:10px;opacity:0.85;letter-spacing:1px;">Your intelligent fitness coach.</div>
  <a href="https://github.com/guojun-1111/fitai-web" target="_blank" rel="noopener"
     style="margin-top:34px;display:inline-flex;align-items:center;gap:10px;padding:14px 30px;border-radius:999px;
       background:#fff;color:#0f172a;font-size:19px;font-weight:650;text-decoration:none;
       box-shadow:0 10px 34px rgba(255,255,255,0.18);">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56v-1.96c-3.2.7-3.88-1.54-3.88-1.54-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.68 0-1.25.45-2.28 1.18-3.08-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.9 10.9 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.76.11 3.05.73.8 1.18 1.83 1.18 3.08 0 4.41-2.7 5.38-5.26 5.67.41.36.78 1.06.78 2.14v3.17c0 .31.21.68.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z"/></svg>
    Star on GitHub
  </a>
  <div style="font-size:17px;margin-top:20px;opacity:0.75;">github.com/guojun-1111/fitai-web</div>
  <div style="font-size:14px;margin-top:10px;opacity:0.5;">MIT (algorithms) + AGPL-3.0 (platform)</div>
</div>
"""

SHOW_CARD_JS = """
(html) => {
  let el = document.getElementById('demo-card');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-card';
    el.style.cssText = 'position:fixed;inset:0;z-index:9400;display:flex;flex-direction:column;' +
      'align-items:center;justify-content:center;color:#fff;' +
      'background:linear-gradient(160deg,#0f172a 0%,#1e293b 100%);' +
      'font-family:-apple-system,Segoe UI,Roboto,sans-serif;text-align:center;';
    document.body.appendChild(el);
  }
  el.innerHTML = html;
  el.style.display = 'flex';
}
"""

HIDE_CARD_JS = "() => { const e = document.getElementById('demo-card'); if (e) e.style.display='none'; }"

FADE_BLACK_JS = """
() => {
  let el = document.getElementById('demo-fade');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-fade';
    el.style.cssText = 'position:fixed;inset:0;z-index:9600;background:#000;opacity:0;' +
      'transition:opacity 1.4s ease;pointer-events:none;';
    document.body.appendChild(el);
  }
  requestAnimationFrame(() => { el.style.opacity = '1'; });
}
"""

FADE_TAIL = 1.5  # 片尾淡出到黑秒数

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


def orb_say(page, headline, zh, x=None, y=None):
    page.evaluate("([h,z,x,y]) => window.orbSay(h,z,x,y)", [headline, zh, x, y])


def orb_point(page, panel, headline, zh):
    page.evaluate("([s,h,z]) => window.orbPointAt(s,h,z)",
                  [f'.nav-btn[data-panel="{panel}"]', headline, zh])


def scroll_active(page, dy):
    page.evaluate(f"() => {{ const p = document.querySelector('.panel.active'); if (p) p.scrollTop += {dy}; }}")


def seed_plan(uid: int):
    """生成一份 7 天训练计划，让「计划」面板有内容。"""
    from fitai.analysis.daily_planner import generate_daily_plan
    plan_data = generate_daily_plan(
        goal="减脂", frequency=3, pain_point="不知道练什么",
        equipment="哑铃", experience_level="beginner", time_per_session="45",
    )
    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("DELETE FROM training_plans WHERE user_id=?", (uid,))
    conn.execute(
        "INSERT INTO training_plans (user_id, name, goal, weeks, plan_data) VALUES (?,?,?,?,?)",
        (uid, "减脂·7天计划", "减脂", 1, json.dumps(plan_data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    print("· 训练计划已生成")


def warm(browser, has_camera):
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
        page.wait_for_timeout(8000)
    ctx.close()
    print("· 预热完成")


def prepare_squat_y4m() -> Path | None:
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


def _play_panel(page, panel, has_camera):
    if panel == "plan":
        click_panel(page, "plan")
        page.wait_for_timeout(1500)
        scroll_active(page, 200)
        page.wait_for_timeout(300)
    elif panel == "exercise-library":
        page.wait_for_timeout(800)  # 本地 GIF 秒加载
        page.evaluate("() => window._showExlibDetail('0662')")  # 点开「俯卧撑」详情
        page.wait_for_timeout(1400)  # 大 GIF + 动作指导停留
        page.evaluate("() => { const m = document.getElementById('exlib-modal'); if (m) m.style.display='none'; }")
    elif panel == "pose":
        click_panel(page, "pose")
        page.wait_for_timeout(700)
        page.evaluate("() => { const b = document.querySelector('.ex-btn[data-ex=\"squat\"]'); if (b) b.click(); }")
        page.wait_for_timeout(300)
        if has_camera:
            page.evaluate("() => { const b = document.getElementById('pose-start-btn'); if (b) b.click(); }")
            page.wait_for_timeout(2000)
        else:
            page.evaluate(POSE_FALLBACK_JS)
            page.wait_for_timeout(800)
    elif panel == "chat":
        click_panel(page, "chat")
        page.wait_for_timeout(500)
        page.fill("#chat-input", CHAT_QUESTION)
        page.wait_for_timeout(400)
        page.click("#send-btn")
        page.wait_for_timeout(900)
        page.evaluate(APPEND_ASSISTANT_JS, CHAT_REPLY)
        page.wait_for_timeout(400)
    elif panel == "health":
        click_panel(page, "health")
        page.wait_for_timeout(800)
        scroll_active(page, 300)
        page.wait_for_timeout(200)
        page.evaluate("() => { const c = document.querySelector('.health-stat-clickable[data-metric=\"heart_rate\"]'); if (c) c.click(); }")
        page.wait_for_timeout(600)
    elif panel == "insights":
        click_panel(page, "insights")
        page.wait_for_timeout(2000)
    elif panel == "dashboard":
        click_panel(page, "dashboard")
        page.wait_for_timeout(1000)
        page.evaluate(HIDE_DASHBOARD_EMPTY)
        scroll_active(page, 500)
        page.wait_for_timeout(400)
        page.evaluate("""() => {
          const s = document.getElementById('whatif-slider');
          s.value = 600;
          s.dispatchEvent(new Event('input', {bubbles:true}));
          const v = document.getElementById('whatif-value');
          if (v) v.textContent = '600分钟';
        }""")
        page.wait_for_timeout(400)
        page.evaluate("() => { const b = document.getElementById('whatif-btn'); if (b) b.click(); }")
        page.wait_for_timeout(1300)


def record():
    timing = json.loads((VIDEO_DIR / "narration_timing.json").read_text(encoding="utf-8"))
    orb_js = (VIDEO_DIR / "orb.js").read_text(encoding="utf-8")
    exlib_js = (VIDEO_DIR / "exlib_demo.js").read_text(encoding="utf-8")
    from playwright.sync_api import sync_playwright
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    for old in VIDEO_DIR.glob("*.webm"):
        old.unlink()

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
        ctx.add_init_script(INIT_JS)
        ctx.add_init_script(COVER_JS)
        page = ctx.new_page()
        rec_t0 = time.time()  # 视频录制从 context 创建即开始，这里对齐 webm 时间轴

        print("· 登录（遮罩已覆盖）...")
        login(page)
        page.evaluate("() => { const e = document.getElementById('demo-cover'); if (e) e.remove(); }")
        page.evaluate(orb_js)  # 注入移动圆球讲解器
        page.evaluate(exlib_js)  # 注入动作库 GIF 本地化
        page.wait_for_timeout(400)

        bounds = []
        for i, seg in enumerate(timing):
            bounds.append(round(time.time() - rec_t0, 3))
            panel = seg["panel"]
            dur = seg["duration"]
            zh = seg["zh"]
            headline = seg["headline"]
            print(f"· [{i}] {panel} ({dur}s) ...")

            if panel in BROLL_PANELS:
                page.evaluate(SHOW_CARD_JS, '<div style="font-size:0;">&nbsp;</div>')
                orb_say(page, headline, zh, VIEW_W / 2, VIEW_H * 0.84)
                page.wait_for_timeout(int(dur * 1000))
                page.evaluate(HIDE_CARD_JS)
            elif panel == "outro":
                page.evaluate(SHOW_CARD_JS, OUTRO_HTML)
                orb_say(page, headline, zh, VIEW_W / 2, VIEW_H * 0.84)
                page.wait_for_timeout(int((dur - FADE_TAIL) * 1000))
                page.evaluate(FADE_BLACK_JS)
                page.wait_for_timeout(int(FADE_TAIL * 1000))
                page.evaluate(HIDE_CARD_JS)
            else:
                t0 = time.time()
                click_panel(page, panel)
                page.wait_for_timeout(300)
                orb_point(page, panel, headline, zh)
                _play_panel(page, panel, y4m is not None)
                remain = max(0, dur - (time.time() - t0))
                page.wait_for_timeout(int(remain * 1000))
            if i < len(timing) - 1:
                page.wait_for_timeout(int(GAP * 1000))

        bounds.append(round(time.time() - rec_t0, 3))
        (VIDEO_DIR / "segment_bounds.json").write_text(
            json.dumps(bounds, ensure_ascii=False), encoding="utf-8")
        print(f"· 真实分段边界（{len(bounds)-1} 段）: {bounds}")

        ctx.close()
        browser.close()

    if y4m:
        y4m.unlink()
    webm = sorted(VIDEO_DIR.glob("*.webm"))[-1]
    raw = VIDEO_DIR / "demo_raw.webm"
    webm.rename(raw)
    print(f"\n完成 → {raw}  ({raw.stat().st_size // 1024} KB)")
    print("下一步: python scripts/splice_broll.py")


def main():
    proc = ensure_server()
    try:
        uid = ensure_user()
        seed(uid)
        seed_plan(uid)
        api_post("/api/auth/login", {"username": DEMO_USER, "password": DEMO_PASS})  # 清缓存
        record()
    finally:
        if proc:
            proc.terminate()
            print("· 已停止临时服务器")


if __name__ == "__main__":
    main()
