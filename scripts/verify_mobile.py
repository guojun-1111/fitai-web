# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

#!/usr/bin/env python3
"""V15.3 手机端验证截图：390×844 各面板 + 落地页"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_demo_shots import BASE, TMP_DIR, ensure_server

def main():
    proc = ensure_server()
    try:
        from playwright.sync_api import sync_playwright
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        init_js = "localStorage.setItem('fitai-theme','light');localStorage.setItem('fitai-onboarded','1');"

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                      device_scale_factor=2, locale="zh-CN",
                                      is_mobile=True)
            ctx.add_init_script(init_js)
            page = ctx.new_page()

            # 登录 demo
            page.goto(BASE + "/login", wait_until="domcontentloaded")
            page.wait_for_selector("#aUser", timeout=10000)
            page.fill("#aUser", "demo")
            page.fill("#aPass", "Fitai2026demo")
            page.click("#authBtn")
            page.wait_for_url("**/app**", timeout=15000)
            page.wait_for_load_state("networkidle")

            for name in ["home", "dashboard", "health"]:
                btn = page.query_selector(f'[data-panel="{name}"]')
                if btn:
                    btn.click()
                    page.wait_for_timeout(3000)
                page.screenshot(path=str(TMP_DIR / f"mobile-{name}.png"))
                print(f"· mobile {name} ✓")

            # 落地页
            page2 = ctx.new_page()
            page2.goto(BASE + "/", wait_until="domcontentloaded")
            page2.wait_for_timeout(1500)
            page2.screenshot(path=str(TMP_DIR / f"mobile-landing.png"), full_page=True)
            print("· mobile landing ✓")

            ctx.close()
            browser.close()
        print("手机端验证截图 → data/shots_tmp/mobile-*.png")
    finally:
        if proc:
            proc.terminate()

if __name__ == "__main__":
    main()
