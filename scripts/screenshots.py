"""Capture real rendered screenshots of the key screens at phone, tablet and desktop widths.

Usage (server running with the seeded demo account):
    python scripts/screenshots.py --base-url http://127.0.0.1:8000 --username demo --password ...
Writes PNG files to docs/screenshots/.
"""

import argparse
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

WIDTHS = {"390": (390, 844), "768": (768, 1024), "1440": (1440, 900)}
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", required=True)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, (w, h) in WIDTHS.items():
            context = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 800 else 1)
            page = context.new_page()
            page.goto(f"{args.base_url}/account/sign-in/")
            page.fill("#id_username", args.username)
            page.fill("#id_password", args.password)
            page.click("button[type=submit]")
            page.wait_for_url(f"{args.base_url}/")
            screens = {"home": "/"}
            page.goto(f"{args.base_url}/projects/")
            screens["project"] = page.get_attribute("a.row:has-text('Office cabinetry')", "href")
            screens["projects"] = "/projects/"
            screens["shopping"] = "/shopping/"
            screens["costs"] = "/costs/"
            page.goto(f"{args.base_url}/costs/")
            review = page.get_attribute("#drafts a.row", "href")
            if review:
                screens["receipt-review"] = review
            screens["add-receipt"] = "/receipts/new/"
            screens["project-costs"] = screens["project"] + "?tab=costs"
            page.goto(f"{args.base_url}/costs/")
            screens["purchase"] = page.get_attribute("a:has-text('MDF, filler and primer')", "href")
            for name, path in screens.items():
                if args.only and not re.search(args.only, name):
                    continue
                page.goto(f"{args.base_url}{path}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=OUT / f"{name}-{label}.png", full_page=False)
                page.screenshot(path=OUT / f"{name}-{label}-full.png", full_page=True)
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
