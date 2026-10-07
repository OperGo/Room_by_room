"""Receipt reading: connection feedback while polling (CTO plan, 7 October).

A lost connection is never an extraction failure: polling keeps going with back-off, the page never reloads or
changes typed values, and nothing is queued or recorded by the browser.
"""
import io
from decimal import Decimal

import pytest
from PIL import Image
from playwright.sync_api import expect

from apps.costs.models import Purchase
from apps.costs.selectors import overall_summary
from apps.projects.models import Project

from .conftest import sign_in

pytestmark = pytest.mark.django_db(transaction=True)
NOTICE = "Connection problem: can’t check the reading right now."


@pytest.fixture
def phone(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    page = context.new_page()
    yield page
    context.close()


def start_reading(page, live_server, owner, settings):
    from apps.core.uploads import validate_receipt
    from apps.receipts.services import store_receipt
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.RECEIPT_EXTRACTOR = "fake"
    Project.objects.create(owner=owner, title="Office")
    buf = io.BytesIO()
    Image.new("RGB", (300, 500), "white").save(buf, format="JPEG")
    _, draft = store_receipt(owner, validate_receipt(SimpleUploadedFile("r.jpg", buf.getvalue())), "r.jpg")
    sign_in(page, live_server)
    page.goto(f"{live_server.url}/receipts/{draft.uuid}/")
    page.get_by_role("button", name="Read receipt automatically").click()
    expect(page.get_by_text("Waiting to read the receipt…")).to_be_visible()
    return draft


def jobs_for(draft):
    from apps.receipts.models import ExtractionJob
    return list(ExtractionJob.objects.filter(draft=draft).values_list("status", flat=True))


def test_offline_shows_notice_keeps_values_and_clears_when_back(phone, live_server, owner, settings):
    from apps.receipts.jobs import process_available

    draft = start_reading(phone, live_server, owner, settings)
    phone.fill("#f-merchant", "Typed while offline")
    notice = phone.locator("[data-reading-connection]")
    expect(notice).to_be_hidden()
    phone.context.set_offline(True)
    expect(notice).to_contain_text(NOTICE, timeout=30000)  # after three failed checks (about 17 s)
    expect(notice).to_be_visible()
    assert phone.locator("[data-reading]").get_attribute("aria-live") == "polite"
    expect(phone.locator("[data-reading-label]")).to_have_text("Waiting to read the receipt…")  # not "failed"
    expect(phone.locator("#f-merchant")).to_have_value("Typed while offline")
    assert jobs_for(draft) == ["queued"] and Purchase.objects.count() == 0

    phone.context.set_offline(False)  # the browser's online event retries at once
    expect(notice).to_be_hidden(timeout=5000)
    process_available()
    expect(phone.get_by_text("Reading finished.").first).to_be_visible(timeout=15000)
    expect(phone.locator("#f-merchant")).to_have_value("Typed while offline")
    assert jobs_for(draft) == ["succeeded"] and overall_summary(owner).total == Decimal("0.00")


def test_server_errors_show_notice_then_untouched_page_loads_reading(phone, live_server, owner, settings):
    from apps.receipts.jobs import process_available

    draft = start_reading(phone, live_server, owner, settings)
    calls = []

    def unavailable(route):
        calls.append(route.request.url)
        route.fulfill(status=503, content_type="text/html", body="<h1>Service unavailable</h1>")
    phone.route("**/reading.json", unavailable)
    notice = phone.locator("[data-reading-connection]")
    expect(notice).to_contain_text(NOTICE, timeout=30000)
    assert len(calls) == 3  # bounded: the notice follows the third failure; no burst of retries
    process_available()  # the reading finishes while the page cannot see it
    phone.unroute("**/reading.json")
    # Next retry (up to 30 s later) succeeds: the untouched page shows the completed reading, as before.
    expect(phone.get_by_text("Synthetic test reading")).to_be_visible(timeout=40000)
    expect(phone.locator("[data-reading-connection]")).to_have_count(0)  # completed panel has no notice
    assert jobs_for(draft) == ["succeeded"] and Purchase.objects.count() == 0


def test_one_failed_check_shows_nothing(phone, live_server, owner, settings):
    start_reading(phone, live_server, owner, settings)
    state = {"failed": 0}

    def flaky(route):
        if state["failed"] == 0:
            state["failed"] += 1
            route.abort()
        else:
            route.continue_()
    phone.route("**/reading.json", flaky)
    phone.wait_for_timeout(9000)  # first check at 2 s fails, retry 5 s later succeeds
    assert state["failed"] == 1
    expect(phone.locator("[data-reading-connection]")).to_be_hidden()
    expect(phone.locator("[data-reading-label]")).to_have_text("Waiting to read the receipt…")
