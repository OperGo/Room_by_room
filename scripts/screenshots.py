"""Capture real rendered screenshots at phone, tablet and desktop widths.

Usage (server running with the seeded demo account):
    python scripts/screenshots.py --base-url http://127.0.0.1:8000 --username demo --password ...
Writes PNG files to docs/screenshots/:
  <screen>-<width>.png           initial viewport
  <screen>-<width>-scrolled.png  one viewport further down
  <screen>-<width>-full.png      full page (fixed/sticky bars appear mid-page; capture artefact)
  receipt-filled-<width>.png     review with items, split allocation and allocated summary (not submitted)
  receipt-error-<width>.png      the same form submitted with an unreconciled total (nothing recorded)
"""

import argparse
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

WIDTHS = {"390": (390, 844), "768": (768, 1024), "1440": (1440, 900)}
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def shoot(page, name, label):
    page.wait_for_load_state("networkidle")
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=OUT / f"{name}-{label}.png")
    height = page.viewport_size["height"]
    if page.evaluate("document.documentElement.scrollHeight") > height * 1.2:
        page.evaluate(f"window.scrollTo(0, {int(height * 0.85)})")
        page.wait_for_timeout(150)
        page.screenshot(path=OUT / f"{name}-{label}-scrolled.png")
        page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=OUT / f"{name}-{label}-full.png", full_page=True)


def fill_receipt(page, office, hallway):
    page.fill("#f-merchant", "Sample Hardware Co")
    page.fill("#f-date", "2026-09-26")
    page.fill("#f-total", "31.17")
    page.fill("#l0-desc", "Wood glue 500ml")
    page.fill("#l0-amt", "6.49")
    page.select_option("#l0-a0-dest", office)
    page.get_by_role("button", name="Add item", exact=True).click()
    page.fill("#l1-desc", "Sanding sheets 120g")
    page.fill("#l1-amt", "8.50")
    page.select_option("#l1-a0-dest", office)
    second = page.locator("[data-line]").nth(1)
    second.locator("summary").click()
    second.get_by_role("button", name="Split between projects").click()
    page.fill("#l1-a0-amt", "5.00")
    page.select_option("#l1-a1-dest", hallway)
    page.fill("#l1-a1-amt", "3.50")
    page.get_by_role("button", name="Add delivery, discount or rounding").click()
    page.fill("#l2-amt", "3.95")
    page.select_option("#l2-a0-dest", "shared_tools")
    page.locator("#f-merchant").blur()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", required=True)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    base = args.base_url
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, (w, h) in WIDTHS.items():
            context = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 800 else 1,
                                          is_mobile=w < 800, has_touch=w < 800)
            page = context.new_page()
            page.goto(f"{base}/account/sign-in/")
            page.fill("#id_username", args.username)
            page.fill("#id_password", args.password)
            page.click("button[type=submit]")
            page.wait_for_url(f"{base}/")
            page.goto(f"{base}/projects/")
            project = page.get_attribute("a.row:has-text('Office cabinetry')", "href")
            hallway_href = page.get_attribute("a.row:has-text('Hallway refresh')", "href")
            office_key = "project:" + project.strip("/").split("/")[-1]
            hallway_key = "project:" + hallway_href.strip("/").split("/")[-1]
            page.goto(f"{base}/costs/")
            review = page.get_attribute("#drafts a.row", "href")
            purchase = page.get_attribute("a:has-text('MDF, filler and primer')", "href")
            screens = {
                "home": "/", "projects": "/projects/", "project": project, "project-costs": project + "?tab=costs",
                "shopping": "/shopping/", "costs": "/costs/", "purchase": purchase, "add-receipt": "/receipts/new/",
                "receipt-review": review,
            }
            for name, path in screens.items():
                if not path or (args.only and not re.search(args.only, name)):
                    continue
                page.goto(f"{base}{path}")
                shoot(page, name, label)
            if review and (not args.only or re.search(args.only, "receipt-filled")):
                page.goto(f"{base}{review}")
                fill_receipt(page, office_key, hallway_key)
                page.locator("[data-line]").nth(1).scroll_into_view_if_needed()
                page.screenshot(path=OUT / f"receipt-filled-{label}.png")
                page.locator("[data-reconcile]").scroll_into_view_if_needed()
                page.screenshot(path=OUT / f"receipt-filled-{label}-summary.png")
                page.get_by_role("button", name="Confirm purchase").click()  # total 31.17 vs items 18.94: refused
                page.wait_for_load_state("networkidle")
                page.screenshot(path=OUT / f"receipt-error-{label}.png")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
