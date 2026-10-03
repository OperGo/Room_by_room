"""Sprint 2A focused screenshots: editing during reading, save conflict recovery, read guard,
incomplete and malformed readings. Uses the FAKE (synthetic) extractor; no paid calls.

    RECEIPT_EXTRACTOR=fake DJANGO_DEBUG=1 DATABASE_URL=... python scripts/screenshots_sprint2a.py --password ...
"""

import argparse
import copy
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
os.environ["RECEIPT_EXTRACTOR"] = "fake"

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from apps.core.management.commands.seed_demo import sample_receipt_image  # noqa: E402
from apps.receipts import jobs  # noqa: E402
from apps.receipts.extraction import SAMPLE_RESULT, FakeExtractor, ReceiptExtractionResult  # noqa: E402

OUT = ROOT / "docs" / "screenshots" / "sprint2a"
WIDTHS = {"390": (390, 844), "768": (768, 1024), "1440": (1440, 900)}
TMP = Path(os.environ.get("TMPDIR", "/tmp")) / "rbr-shots-2a"


def receipt_file(name, tint):
    TMP.mkdir(exist_ok=True)
    image = Image.open(io.BytesIO(sample_receipt_image().content)).convert("RGB")
    for x in range(12):
        for y in range(12):
            image.putpixel((x, y), tint)
    path = TMP / name
    image.save(path, format="JPEG", quality=88)
    return path


def upload(page, base, path):
    page.goto(f"{base}/receipts/new/")
    page.set_input_files("input[aria-label='Upload a receipt image']", str(path))
    page.wait_for_url("**/receipts/*/")


def shot(page, name, selector=None):
    page.wait_for_load_state("networkidle")
    if selector:
        page.locator(selector).first.scroll_into_view_if_needed()
        page.wait_for_timeout(150)
    else:
        page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=OUT / f"{name}.png")


def start_reading(page):
    page.get_by_role("button", name="Read receipt automatically").click()
    page.get_by_text("Waiting to read the receipt…").wait_for()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    base = args.base_url
    OUT.mkdir(parents=True, exist_ok=True)
    from apps.projects.models import Project

    office = Project.objects.get(owner__username=args.username, title="Office cabinetry")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for index, (label, (w, h)) in enumerate(WIDTHS.items()):
            context = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 800 else 1,
                                          is_mobile=w < 800, has_touch=w < 800)
            page = context.new_page()
            page.goto(f"{base}/account/sign-in/")
            page.fill("#id_username", args.username)
            page.fill("#id_password", args.password)
            page.click("button[type=submit]")
            page.wait_for_url(f"{base}/")

            # A. Type during reading → reading finishes → Save draft → conflict → deliberate save.
            upload(page, base, receipt_file(f"a-{label}.jpg", (10, 40 * index, 200)))
            start_reading(page)
            page.fill("#f-merchant", "Typed while reading")
            page.fill("#l0-desc", "My own item")
            page.fill("#l0-amt", "9.99")
            page.select_option("#l0-a0-dest", f"project:{office.uuid}")
            jobs.process_available()
            page.locator("[data-reading-dirty]").wait_for(timeout=20000)
            shot(page, f"a1-finished-with-changes-{label}", "[data-reading]")
            page.get_by_role("button", name="Save draft for later").click()
            page.get_by_text("Not saved yet: this draft changed since you opened it").wait_for()
            shot(page, f"a2-save-conflict-{label}")
            shot(page, f"a3-conflict-values-kept-{label}", "[data-line]")
            page.get_by_role("button", name="Save draft (keep my version)").click()
            page.get_by_text("Draft saved.").wait_for()
            page.reload()
            shot(page, f"a4-reloaded-owner-values-{label}")

            # B. Edit before reading → Read is stopped until saved.
            upload(page, base, receipt_file(f"b-{label}.jpg", (200, 40 * index, 10)))
            page.fill("#f-merchant", "Unsaved merchant")
            page.get_by_role("button", name="Read receipt automatically").click()
            page.get_by_text("You have unsaved changes.").wait_for()
            shot(page, f"b1-read-blocked-until-saved-{label}", "[data-unsaved-note]")

            if label == "390":
                # C. Structural edits only (no typing) during reading → no auto reload.
                upload(page, base, receipt_file("c.jpg", (90, 200, 90)))
                start_reading(page)
                page.get_by_role("button", name="Add item", exact=True).click()
                page.get_by_role("button", name="Add delivery, discount or rounding").click()
                jobs.process_available()
                page.locator("[data-reading-dirty]").wait_for(timeout=20000)
                shot(page, "c1-structural-edits-kept-390", "[data-reading]")

                # D. Incomplete reading (rows beyond the cap) — never "reconciled".
                upload(page, base, receipt_file("d.jpg", (90, 90, 200)))
                start_reading(page)
                settings.RECEIPT_MAX_LINES = 3
                FakeExtractor.queue.append(copy.deepcopy(SAMPLE_RESULT))
                jobs.process_available()
                settings.RECEIPT_MAX_LINES = 100
                page.get_by_text("Synthetic test reading").wait_for(timeout=20000)
                shot(page, "d1-incomplete-reading-390")

                # E. Malformed provider output → controlled failure, manual route intact.
                upload(page, base, receipt_file("e.jpg", (200, 200, 90)))
                start_reading(page)
                bad = copy.deepcopy(SAMPLE_RESULT)
                bad["warnings"] = 1
                FakeExtractor.queue.append(lambda doc: ReceiptExtractionResult(
                    raw=bad, model_version="fake-test-extractor", usage={"input_tokens": 0, "output_tokens": 0}))
                jobs.process_available()
                page.get_by_text("Couldn’t read this receipt").wait_for(timeout=20000)
                shot(page, "e1-malformed-output-failed-390")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
