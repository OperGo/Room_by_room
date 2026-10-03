"""Sprint 2 receipt-reading screenshots, using the FAKE (synthetic) extractor.

Run against a dev server started with RECEIPT_EXTRACTOR=fake and the same DATABASE_URL:
    RECEIPT_EXTRACTOR=fake DJANGO_DEBUG=1 DATABASE_URL=... python scripts/screenshots_sprint2.py --password ...
The worker steps run in this process (claim / run / fail), so each state is captured deterministically.
Every reading shown is synthetic and labelled as such in the UI.
"""

import argparse
import copy
import datetime
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

from django.utils import timezone  # noqa: E402
from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from apps.core.management.commands.seed_demo import sample_receipt_image  # noqa: E402
from apps.receipts import jobs  # noqa: E402
from apps.receipts.extraction import SAMPLE_RESULT, ExtractionError, FakeExtractor  # noqa: E402

OUT = ROOT / "docs" / "screenshots" / "sprint2"
WIDTHS = {"390": (390, 844), "768": (768, 1024), "1440": (1440, 900)}
TMP = Path(os.environ.get("TMPDIR", "/tmp")) / "rbr-shots"


def receipt_file(name, tint):
    """The synthetic sample receipt, re-encoded so each scenario has its own checksum."""
    TMP.mkdir(exist_ok=True)
    image = Image.open(io.BytesIO(sample_receipt_image().content)).convert("RGB")
    for x in range(12):  # a small corner mark makes each file's bytes (and checksum) distinct
        for y in range(12):
            image.putpixel((x, y), tint)
    path = TMP / name
    image.save(path, format="JPEG", quality=88)
    return path


def upload(page, base, path):
    page.goto(f"{base}/receipts/new/")
    page.set_input_files("input[aria-label='Upload a receipt image']", str(path))
    page.wait_for_url("**/receipts/*/")
    return page.url.rstrip("/").split("/")[-1]


def shot(page, name, selector=None):
    page.wait_for_load_state("networkidle")
    if selector:
        page.locator(selector).first.scroll_into_view_if_needed()
        page.wait_for_timeout(150)
    else:
        page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=OUT / f"{name}.png")


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
    hallway = Project.objects.get(owner__username=args.username, title="Hallway refresh")
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

            # 1. Offer → queued → processing → ready → fully reconciled → confirmed.
            upload(page, base, receipt_file(f"ok-{label}.jpg", (250, 40 * index, 0)))
            shot(page, f"offer-{label}")
            page.get_by_role("button", name="Read receipt automatically").click()
            page.get_by_text("Waiting to read the receipt…").wait_for()
            shot(page, f"queued-{label}")
            job, token = jobs.claim_next_job()
            page.reload()
            page.get_by_text("Reading the receipt…").wait_for()
            shot(page, f"processing-{label}")
            jobs.run_claimed_job(job, token)
            page.get_by_text("Synthetic test reading").wait_for(timeout=20000)  # polling reloads the untouched page
            shot(page, f"ready-{label}")
            for i in range(5):
                page.select_option(f"#l{i}-a0-dest", "shared_tools" if i == 4 else f"project:{office.uuid}")
            line = page.locator("[data-line]").nth(2)
            line.locator("summary").click()
            line.get_by_role("button", name="Split between projects").click()
            page.fill("#l2-a0-amt", "5.00")
            page.select_option("#l2-a1-dest", f"project:{hallway.uuid}")
            page.fill("#l2-a1-amt", "3.50")
            page.locator("#f-merchant").blur()
            shot(page, f"reconciled-{label}", "[data-reconcile]")
            page.get_by_role("button", name="Confirm purchase").click()
            page.wait_for_load_state("networkidle")
            if page.locator("#duplicates").count():
                shot(page, f"duplicate-warning-{label}", "#duplicates")
                page.locator("#duplicates input[type=checkbox]").evaluate_all("els => els.forEach(e => e.checked = true)")
                page.get_by_role("button", name="Confirm purchase").click()
            page.get_by_text("Receipt confirmed and purchase recorded.").wait_for()
            shot(page, f"confirmed-purchase-{label}")
            page.goto(f"{base}/projects/{office.uuid}/?tab=costs")
            shot(page, f"office-costs-{label}")
            page.goto(f"{base}/costs/")
            shot(page, f"costs-{label}")

            # 2. Failure after the bounded retry.
            upload(page, base, receipt_file(f"fail-{label}.jpg", (0, 40 * index, 250)))
            page.get_by_role("button", name="Read receipt automatically").click()
            page.get_by_text("Waiting to read the receipt…").wait_for()
            FakeExtractor.queue.extend([ExtractionError("timeout", "Reading timed out.", retryable=True)] * 2)
            jobs.process_available()
            jobs.process_available(now=timezone.now() + datetime.timedelta(seconds=40))
            page.reload()
            shot(page, f"failed-{label}")

            # 3. Foreign currency warning (amounts not prefilled as GBP).
            upload(page, base, receipt_file(f"eur-{label}.jpg", (0, 250, 40 * index)))
            page.get_by_role("button", name="Read receipt automatically").click()
            page.get_by_text("Waiting to read the receipt…").wait_for()
            foreign = copy.deepcopy(SAMPLE_RESULT)
            foreign["currency"] = "EUR"
            FakeExtractor.queue.append(foreign)
            jobs.process_available()
            page.reload()
            shot(page, f"foreign-{label}")
            shot(page, f"foreign-confirm-{label}", ".gbp-check")

            # 4. Unreconciled reading (delivery missing): flagged, never balanced.
            upload(page, base, receipt_file(f"gap-{label}.jpg", (120, 40 * index, 120)))
            page.get_by_role("button", name="Read receipt automatically").click()
            page.get_by_text("Waiting to read the receipt…").wait_for()
            gap = copy.deepcopy(SAMPLE_RESULT)
            gap["adjustments"] = []
            FakeExtractor.queue.append(gap)
            jobs.process_available()
            page.reload()
            shot(page, f"unreconciled-{label}")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
