"""Sprint 2B phone sign-out screenshots: Home at 390, 768 and 1440 px (fictional demo data).

    DJANGO_DEBUG=1 DATABASE_URL=... python manage.py runserver 127.0.0.1:8000
    python scripts/screenshots_sprint2b_signout.py --password ...
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots" / "sprint2b-signout"
WIDTHS = {"390": (390, 844), "768": (768, 1024), "1440": (1440, 900)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, (w, h) in WIDTHS.items():
            phone = w < 1024
            context = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 800 else 1,
                                          is_mobile=phone, has_touch=phone)
            page = context.new_page()
            page.goto(f"{args.base_url}/account/sign-in/")
            page.fill("#id_username", args.username)
            page.fill("#id_password", args.password)
            page.click("button[type=submit]")
            page.wait_for_url(f"{args.base_url}/")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=OUT / f"home-top-{label}.png")
            if phone:
                page.locator("section.account-row").scroll_into_view_if_needed()
                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(200)
                page.screenshot(path=OUT / f"home-foot-sign-out-{label}.png")
            else:
                page.screenshot(path=OUT / f"home-desktop-sidebar-sign-out-{label}.png")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
