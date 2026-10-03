"""Sprint 2A closeout focused screenshots: an editor returned by the server (validation error)
starts dirty, so a reading finishing meanwhile never reloads it, and Read/Retry stay blocked until saved.
Uses the FAKE (synthetic) extractor and drives jobs in-process; no paid calls.

    RECEIPT_EXTRACTOR=fake DJANGO_DEBUG=1 DATABASE_URL=... python scripts/screenshots_sprint2a_closeout.py --password ...
"""

import argparse
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

from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from apps.core.management.commands.seed_demo import sample_receipt_image  # noqa: E402
from apps.receipts import jobs  # noqa: E402
from apps.receipts.extraction import ExtractionError, FakeExtractor  # noqa: E402

OUT = ROOT / "docs" / "screenshots" / "sprint2a-closeout"
WIDTHS = {"390": (390, 844), "1440": (1440, 900)}
TMP = Path(os.environ.get("TMPDIR", "/tmp")) / "rbr-shots-2a-closeout"


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


def submit_invalid_confirm(page, project):
    page.fill("#f-merchant", "Typed while reading")
    page.fill("#f-date", "2026-09-27")
    page.fill("#f-total", "99.00")  # items add up to £9.99: the server returns the editor with an error
    page.fill("#l0-desc", "My own item")
    page.fill("#l0-amt", "9.99")
    page.select_option("#l0-a0-dest", f"project:{project.uuid}")
    page.get_by_role("button", name="Confirm purchase").click()
    page.locator("#editor-errors").wait_for()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    base = args.base_url
    OUT.mkdir(parents=True, exist_ok=True)
    from apps.projects.models import Project

    project = Project.objects.filter(owner__username=args.username).order_by("created_at").first()
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

            # A. Reading in progress → confirm with a validation error → the returned editor starts dirty →
            #    the reading finishes → no reload, every value kept.
            upload(page, base, receipt_file(f"a-{label}.jpg", (20, 60 * index, 180)))
            start_reading(page)
            job, token = jobs.claim_next_job()  # the worker has the job: "processing"
            submit_invalid_confirm(page, project)
            page.get_by_text("Reading the receipt…").wait_for()
            shot(page, f"a1-returned-editor-while-reading-{label}")
            page.evaluate("window.__noReload = true")
            jobs.run_claimed_job(job, token)
            page.locator("[data-reading-dirty]").wait_for(timeout=20000)
            page.wait_for_timeout(1500)
            assert page.evaluate("window.__noReload === true"), "page reloaded"
            shot(page, f"a2-reading-finished-no-reload-{label}", "[data-reading]")
            shot(page, f"a3-returned-values-kept-{label}", "[data-line]")

            if label == "390":
                # B. Failed reading → returned editor → "Try reading again" is blocked until saved.
                upload(page, base, receipt_file("b.jpg", (180, 60, 20)))
                start_reading(page)
                FakeExtractor.queue.append(ExtractionError("refusal", "The provider declined to read this receipt."))
                jobs.process_available()
                page.reload()
                page.get_by_role("button", name="Try reading again").wait_for()
                submit_invalid_confirm(page, project)
                page.get_by_role("button", name="Try reading again").click()
                page.get_by_text("You have unsaved changes.").first.wait_for()
                shot(page, "b1-returned-editor-retry-blocked-390", "[data-unsaved-note]:visible")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
