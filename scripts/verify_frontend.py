# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""V15.2 验证截图：空账号看空态/CTA + demo 账号看浅色图表配色。输出到 data/shots_tmp/verify-*"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_demo_shots import BASE, TMP_DIR, ensure_server, ensure_user, seed, click_panel, api_post

EMPTY_USER = "empty_verify"
EMPTY_PASS = "Fitai2026empty"


def login_as(page, user, pwd):
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.wait_for_selector("#aUser", timeout=10000)
    # 切到注册 tab 注册, 已存在则直接登录
    page.fill("#aUser", user)
    page.fill("#aPass", pwd)
    page.click("#authBtn")
    page.wait_for_url("**/app**", timeout=15000)
    page.wait_for_load_state("networkidle")


def ensure_empty_user():
    code, _ = api_post("/api/auth/login", {"username": EMPTY_USER, "password": EMPTY_PASS})
    if code != 200:
        code2, body = api_post("/api/auth/register",
                               {"username": EMPTY_USER, "password": EMPTY_PASS, "email": None})
        if code2 not in (200, 201):
            sys.exit(f"空账号注册失败: {code2} {body}")
        print("· 空账号已注册")


def main():
    proc = ensure_server()
    try:
        ensure_empty_user()
        uid = ensure_user()
        seed(uid)

        from playwright.sync_api import sync_playwright
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        init_js = "localStorage.setItem('fitai-theme','light');localStorage.setItem('fitai-onboarded','1');"

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                      device_scale_factor=2, locale="zh-CN")
            ctx.add_init_script(init_js)

            # ── 空账号: 空态 + CTA ──
            page = ctx.new_page()
            login_as(page, EMPTY_USER, EMPTY_PASS)
            for name in ["dashboard", "health", "home"]:
                click_panel(page, name)
                page.wait_for_timeout(2500)
                page.screenshot(path=str(TMP_DIR / f"verify-empty-{name}.png"))
                print(f"· 空账号 {name} ✓")

            # ── demo 账号: 浅色图表配色（新 context, 避免沿用空账号会话）──
            ctx2 = browser.new_context(viewport={"width": 1440, "height": 900},
                                       device_scale_factor=2, locale="zh-CN")
            ctx2.add_init_script(init_js)
            page2 = ctx2.new_page()
            login_as(page2, "demo", "Fitai2026demo")
            for name in ["dashboard", "health", "home", "exercises", "insights"]:
                click_panel(page2, name)
                if name == "insights":
                    page2.wait_for_timeout(12000)
                else:
                    page2.wait_for_timeout(3000)
                page2.screenshot(path=str(TMP_DIR / f"verify-demo-{name}.png"))
                print(f"· demo {name} ✓")

            # ── demo 深色对照（home + health）──
            page2.evaluate("() => { localStorage.setItem('fitai-theme','dark'); window.setTheme && window.setTheme('dark'); }")
            for name in ["health", "home"]:
                click_panel(page2, name)
                page2.wait_for_timeout(3000)
                page2.screenshot(path=str(TMP_DIR / f"verify-dark-{name}.png"))
                print(f"· 深色 {name} ✓")

            ctx.close()
            ctx2.close()
            browser.close()
        print("验证截图完成 → data/shots_tmp/verify-*.png")
    finally:
        if proc:
            proc.terminate()
            print("· 已停止临时服务器")


if __name__ == "__main__":
    main()
