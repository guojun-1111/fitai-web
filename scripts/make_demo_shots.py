# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""落地页截图生成器：造 90 天演示数据 → Edge 无头截真实界面 → static/img/*.webp

用法: python scripts/make_demo_shots.py
幂等: 每次运行先清空 demo 用户旧数据再重新造。只影响 demo 账号, 不动其他用户数据。
"""
import json
import random
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fitai.db"
IMG_DIR = ROOT / "static" / "img"
TMP_DIR = ROOT / "data" / "shots_tmp"
BASE = "http://127.0.0.1:8000"
DEMO_USER = "demo"
DEMO_PASS = "Fitai2026demo"

DESKTOP_SHOTS = ["dashboard", "health", "insights", "chat"]
MOBILE_SHOTS = ["home", "chat"]


# ── 服务器 ──────────────────────────────────────────────────────

def server_alive() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_server():
    """返回 (proc or None)。已在跑就复用, 否则起一个不带 reload 的 uvicorn。"""
    if server_alive():
        print("· 复用已运行的本地服务器")
        return None
    print("· 启动本地服务器 ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        if server_alive():
            print("· 服务器就绪")
            return proc
        time.sleep(1)
    proc.kill()
    sys.exit("服务器启动超时")


# ── 账号 ────────────────────────────────────────────────────────

def api_post(path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def ensure_user() -> int:
    code, _ = api_post("/api/auth/login", {"username": DEMO_USER, "password": DEMO_PASS})
    if code != 200:
        code2, body2 = api_post("/api/auth/register",
                                {"username": DEMO_USER, "password": DEMO_PASS, "email": None})
        if code2 not in (200, 201):
            sys.exit(f"demo 账号登录/注册均失败: login={code} register={code2} {body2}")
        print("· demo 账号已注册")
    conn = sqlite3.connect(str(DB), timeout=30)
    uid = conn.execute("SELECT id FROM users WHERE username=?", (DEMO_USER,)).fetchone()[0]
    conn.close()
    print(f"· demo user_id={uid}")
    return uid


# ── 种子数据 ────────────────────────────────────────────────────

def seed(uid: int):
    rng = random.Random(42)
    conn = sqlite3.connect(str(DB), timeout=60)
    cur = conn.cursor()
    tables = ["health_data", "health_daily_summary", "workout_logs", "workout_sessions",
              "nutrition_logs", "body_metrics", "chat_history", "user_profile"]
    for t in tables:
        cur.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))

    today = date.today()
    SRC = "apple_health"
    meals = [
        ("早餐", "燕麦牛奶+水煮蛋+香蕉", 420, 18, 58, 12),
        ("午餐", "鸡胸肉糙米饭+西兰花", 560, 42, 62, 14),
        ("晚餐", "三文鱼沙拉+红薯", 480, 35, 40, 18),
        ("早餐", "全麦面包+酸奶+蓝莓", 380, 15, 52, 10),
        ("午餐", "牛肉意面+蔬菜汤", 620, 38, 70, 20),
        ("晚餐", "虾仁蒸蛋+杂粮饭+时蔬", 450, 30, 48, 12),
    ]
    workouts = {0: ("跑步", 35), 2: ("力量训练", 50), 4: ("跑步", 40), 5: ("骑行", 55)}

    for t in range(90):
        d = today - timedelta(days=89 - t)
        ds = d.isoformat()
        wd = d.weekday()
        weekend = wd >= 5

        steps = int(max(2800, min(14500, 8200 + t * 8 + rng.gauss(0, 1500)) * (0.72 if weekend else 1)))
        hr = round(60 + rng.gauss(0, 3.5) - (1 if weekend else 0), 1)
        sleep_h = max(5.5, min(9.0, 7.3 + rng.gauss(0, 0.55) - (0.4 if wd in (4, 5) else 0)))
        sleep = int(sleep_h * 60)  # App 约定: 睡眠按分钟存储
        cal = int(2350 + steps * 0.045 + rng.gauss(0, 110))
        weight = round(72.8 - 0.016 * t + rng.gauss(0, 0.18), 1)
        bf = round(19.8 - 0.021 * t + rng.gauss(0, 0.15), 1)
        bp = int(118 + rng.gauss(0, 5))
        glu = round(5.0 + rng.gauss(0, 0.35), 1)

        rows = [("steps", steps, "步"), ("heart_rate", hr, "bpm"), ("sleep", sleep, "分钟"),
                ("calories", cal, "kcal"), ("weight", weight, "kg"), ("body_fat", bf, "%"),
                ("blood_pressure_sys", bp, "mmHg"), ("blood_glucose", glu, "mmol/L")]
        for dt_, val, unit in rows:
            cur.execute("INSERT OR REPLACE INTO health_data (user_id,date,source_platform,data_type,value,unit) VALUES (?,?,?,?,?,?)",
                        (uid, ds, SRC, dt_, val, unit))
            cur.execute("INSERT OR REPLACE INTO health_daily_summary (user_id,date,data_type,value,unit,source_platform) VALUES (?,?,?,?,?,?)",
                        (uid, ds, dt_, val, unit, SRC))

        if wd in workouts:
            wtype, mins = workouts[wd]
            cur.execute("INSERT INTO workout_logs (user_id,date,exercise_name,duration_minutes,notes) VALUES (?,?,?,?,?)",
                        (uid, ds, wtype, mins, "演示数据"))
            if wtype == "力量训练":
                cur.execute("INSERT INTO workout_logs (user_id,date,exercise_name,sets,reps,weight_kg) VALUES (?,?,?,?,?,?)",
                            (uid, ds, "卧推", 4, 8, 60))
                cur.execute("INSERT INTO workout_logs (user_id,date,exercise_name,sets,reps,weight_kg) VALUES (?,?,?,?,?,?)",
                            (uid, ds, "深蹲", 4, 10, 70))
            avg_hr = 142 if wtype != "力量训练" else 118
            cur.execute("""INSERT INTO workout_sessions
                (user_id,date,workout_type,start_time,end_time,duration_seconds,avg_heart_rate,max_heart_rate,calories_burned,device_name)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (uid, ds, wtype, ds + "T07:30:00", ds + "T08:05:00",
                         mins * 60, avg_hr, avg_hr + 26, mins * 9, "Apple Watch"))

        for i in range(3):
            pool = [meals[0::3], meals[1::3], meals[2::3]][i]  # 早/午/晚餐各自池
            mtype, name, kcal, p, c, f = pool[t % len(pool)]
            cur.execute("INSERT INTO nutrition_logs (user_id,date,meal_type,food_name,calories,protein_g,carbs_g,fat_g) VALUES (?,?,?,?,?,?,?,?)",
                        (uid, ds, mtype, name, kcal, p, c, f))

        if t % 7 == 0:
            cur.execute("INSERT INTO body_metrics (user_id,date,weight_kg,body_fat_pct) VALUES (?,?,?,?)",
                        (uid, ds, weight, bf))

    # 今天也安排一次训练, 让连续训练天数 > 0
    if today.weekday() not in workouts:
        ds = today.isoformat()
        cur.execute("INSERT INTO workout_logs (user_id,date,exercise_name,duration_minutes,notes) VALUES (?,?,?,?,?)",
                    (uid, ds, "跑步", 30, "演示数据"))
        cur.execute("""INSERT INTO workout_sessions
            (user_id,date,workout_type,start_time,end_time,duration_seconds,avg_heart_rate,max_heart_rate,calories_burned,device_name)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (uid, ds, "跑步", ds + "T07:30:00", ds + "T08:00:00", 1800, 140, 166, 270, "Apple Watch"))

    cur.execute("""INSERT INTO user_profile (user_id,name,birth_year,gender,height_cm,weight_kg,fitness_goal,activity_level)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (uid, "演示用户", 1995, "male", 175, 71.4, "减脂", "moderate"))
    conn.commit()
    n = cur.execute("SELECT COUNT(*) FROM health_data WHERE user_id=?", (uid,)).fetchone()[0]
    conn.close()
    print(f"· 种子完成: health_data {n} 行 (90 天 x 8 指标)")


# ── 截图 ────────────────────────────────────────────────────────

CHAT_DEMO = [
    ("user", "我这周的训练和睡眠怎么样?"),
    ("assistant", "你这周完成了 4 次训练: 2 次跑步、1 次力量、1 次骑行, 总时长 180 分钟, 比上周多 12%。\n睡眠平均 7.1 小时, 其中 3 天超过 7.5 小时。不过周五只睡了 6.2 小时, 第二天静息心率升高了 3 bpm。\n建议: 周末保持 23:30 前入睡, 下周可以把一次跑步换成间歇训练。"),
    ("user", "那我明天练什么比较好?"),
    ("assistant", "根据你的恢复数据(静息心率 58 bpm, 已连续 2 天下降), 明天适合中等强度训练:\n· 慢跑 30 分钟, 心率控制在 130-140 bpm\n· 或上肢力量训练 40 分钟\n练后补充 25g 蛋白质, 你今天的蛋白质摄入还差 18g。"),
]

INJECT_CHAT_JS = """
(msgs) => {
  const box = document.getElementById('chat-messages');
  if (!box) return 'no-box';
  box.innerHTML = '';
  for (const [role, text] of msgs) {
    const div = document.createElement('div');
    div.className = 'message ' + role;
    const av = document.createElement('div');
    av.className = 'msg-avatar';
    av.textContent = role === 'user' ? '我' : 'AI';
    const body = document.createElement('div');
    body.className = 'msg-content';
    body.innerText = text;
    div.appendChild(av); div.appendChild(body);
    box.appendChild(div);
  }
  box.scrollTop = 0;
  return 'ok';
}
"""


def click_panel(page, name: str):
    page.evaluate(f"""() => {{
      const btn = document.querySelector('[data-panel="{name}"]') ||
                  document.querySelector(`[onclick*="{name}"]`);
      if (btn) btn.click();
    }}""")
    page.wait_for_timeout(400)


def login(page):
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.wait_for_selector("#aUser", timeout=10000)
    page.fill("#aUser", DEMO_USER)
    page.fill("#aPass", DEMO_PASS)
    page.click("#authBtn")
    page.wait_for_url("**/app**", timeout=15000)
    page.wait_for_load_state("networkidle")


def shoot():
    from playwright.sync_api import sync_playwright
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    init_js = "localStorage.setItem('fitai-theme','light');localStorage.setItem('fitai-onboarded','1');"

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        # ── 桌面 ──
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  device_scale_factor=2, locale="zh-CN")
        ctx.add_init_script(init_js)
        page = ctx.new_page()
        login(page)

        for name in DESKTOP_SHOTS:
            click_panel(page, name)
            if name in ("dashboard", "health"):
                try:
                    page.wait_for_selector(f"#panel-{name} canvas", timeout=15000)
                except Exception:
                    pass
            if name == "insights":
                page.wait_for_timeout(12000)  # PC-stable 因果计算较慢
            else:
                page.wait_for_timeout(2500)
            if name == "chat":
                page.evaluate(INJECT_CHAT_JS, CHAT_DEMO)
                page.wait_for_timeout(500)
            if name == "dashboard":
                # 隐藏依赖外部接口的视频区 + demo 下为空的分区, 保留图表和 What-If
                page.evaluate("""() => {
                  ['video-grid', 'achievements-row', 'exercise-stats'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.style.display = 'none';
                  });
                  document.querySelectorAll('#panel-dashboard .section-title').forEach(el => {
                    const t = el.textContent;
                    if (t.includes('视频') || t.includes('徽章') || t.includes('动作统计')) el.style.display = 'none';
                  });
                }""")
                page.wait_for_timeout(300)
            page.screenshot(path=str(TMP_DIR / f"shot-{name}.png"))
            print(f"· 桌面 {name} ✓")
        ctx.close()

        # ── 手机 ──
        mctx = browser.new_context(viewport={"width": 390, "height": 844},
                                   device_scale_factor=2, locale="zh-CN", is_mobile=True)
        mctx.add_init_script(init_js)
        mp = mctx.new_page()
        login(mp)
        for name in MOBILE_SHOTS:
            click_panel(mp, name)
            mp.wait_for_timeout(3000)
            if name == "chat":
                mp.evaluate(INJECT_CHAT_JS, CHAT_DEMO)
                mp.wait_for_timeout(500)
            mp.screenshot(path=str(TMP_DIR / f"shot-m-{name}.png"))
            print(f"· 手机 {name} ✓")
        mctx.close()
        browser.close()


def to_webp():
    from PIL import Image
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    made = []
    for png in sorted(TMP_DIR.glob("shot-*.png")):
        img = Image.open(png)
        target_w = 780 if "-m-" in png.stem else 1600
        if img.width > target_w:
            img = img.resize((target_w, int(img.height * target_w / img.width)), Image.LANCZOS)
        out = IMG_DIR / (png.stem + ".webp")
        img.save(out, "WEBP", quality=80, method=6)
        made.append((out.name, out.stat().st_size // 1024, img.size))
        png.unlink()
    return made


def main():
    proc = ensure_server()
    try:
        uid = ensure_user()
        seed(uid)
        # 清服务端缓存, 让新数据立刻可见
        api_post("/api/auth/login", {"username": DEMO_USER, "password": DEMO_PASS})
        shoot()
        made = to_webp()
        print("\n生成完毕 → static/img/")
        for name, kb, size in made:
            print(f"  {name}  {kb} KB  {size[0]}x{size[1]}")
    finally:
        if proc:
            proc.terminate()
            print("· 已停止临时服务器")


if __name__ == "__main__":
    main()
