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


# ------------------------------------------------------------------ CTO review of 7 October: poller hardening

# Replaces fetch for the status endpoint only. window.__mode picks the behaviour; calls and the peak number of
# requests in flight are counted so overlapping checks would show up.
FETCH_STUB = """
(() => {
  const real = window.fetch.bind(window);
  Object.assign(window, { __calls: 0, __active: 0, __maxActive: 0, __mode: "real", __payloads: [] });
  const json = { "Content-Type": "application/json" };
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (!url.includes("reading.json")) return real(input, init);
    window.__calls += 1; window.__active += 1; window.__maxActive = Math.max(window.__maxActive, window.__active);
    let open = true;
    const done = () => { if (open) { open = false; window.__active -= 1; } };
    const signal = init && init.signal;
    const onAbort = (fail) => signal && signal.addEventListener("abort", () => { done(); fail(new DOMException("aborted", "AbortError")); });
    switch (window.__mode) {
      case "fail": done(); return Promise.reject(new TypeError("Failed to fetch"));
      case "stall": return new Promise((_, reject) => onAbort(reject));  // no headers, ever
      case "stall-body":  // headers arrive at once; the body never finishes
        return Promise.resolve(new Response(new ReadableStream({ start(c) {
          c.enqueue(new TextEncoder().encode('{"status": "succ')); onAbort((e) => c.error(e)); } }), { status: 200, headers: json }));
      case "payload": {
        done();
        const body = window.__payloads[(window.__calls - 1) % window.__payloads.length];
        return Promise.resolve(new Response(body, { status: 200, headers: json }));
      }
      default: return real(input, init).finally(done);
    }
  };
})();
"""


def start_stubbed(page, live_server, owner, settings, mode, payloads=()):
    page.clock.install()
    page.add_init_script(FETCH_STUB)
    draft = start_reading(page, live_server, owner, settings)
    page.evaluate("([mode, payloads]) => { window.__mode = mode; window.__payloads = payloads; window.__marker = 1; }",
                  [mode, list(payloads)])
    page.clock.pause_at((page.evaluate("Date.now()") + 50) / 1000)  # seconds; from here time moves only by run_for
    return draft


def stub(page, name):
    return page.evaluate(f"window.{name}")


def assert_untouched(page, draft, merchant=None):
    assert page.evaluate("window.__marker") == 1  # same document: no reload happened
    if merchant is not None:
        expect(page.locator("#f-merchant")).to_have_value(merchant)
    assert jobs_for(draft) == ["queued"] and Purchase.objects.count() == 0


def test_stalled_body_times_out_and_counts_as_a_failed_check(phone, live_server, owner, settings):
    draft = start_stubbed(phone, live_server, owner, settings, "stall-body")
    phone.fill("#f-merchant", "Typed during a stall")
    notice = phone.locator("[data-reading-connection]")
    # Checks at 2 s, then 5 s and 10 s after each 15 s timeout: the third timeout shows the notice.
    for wait, calls in [(2000, 1), (15000, 1), (5000, 2), (15000, 2), (10000, 3)]:
        phone.clock.run_for(wait)
        assert stub(phone, "__calls") == calls
        expect(notice).to_be_hidden()
    phone.clock.run_for(15000)
    expect(notice).to_contain_text(NOTICE)
    assert stub(phone, "__maxActive") == 1 and stub(phone, "__active") == 0  # each stalled body was aborted
    assert_untouched(phone, draft, "Typed during a stall")


@pytest.mark.parametrize("payloads", [
    ["null", "{}", '{"status": "bogus"}'],
    ['{"status": null}', "[]", '{"status": "none"}'],
    ['"succeeded"', "not json", '{"state": "succeeded"}'],
])
def test_invalid_status_payloads_never_reload_or_finish(phone, live_server, owner, settings, payloads):
    draft = start_stubbed(phone, live_server, owner, settings, "payload", payloads)  # untouched form: a result would reload
    notice = phone.locator("[data-reading-connection]")
    for wait in (2000, 5000, 10000):
        phone.clock.run_for(wait)
    expect(notice).to_contain_text(NOTICE)
    assert stub(phone, "__calls") == 3
    expect(phone.locator("[data-reading-label]")).to_have_text("Waiting to read the receipt…")
    expect(phone.locator("[data-reading-done]")).to_be_hidden()
    assert_untouched(phone, draft)
    # A valid answer clears the notice and polling carries on normally.
    phone.evaluate("window.__mode = 'real'")
    phone.clock.run_for(20000)
    expect(notice).to_be_hidden()
    assert_untouched(phone, draft)


def test_online_events_during_a_request_never_overlap(phone, live_server, owner, settings):
    draft = start_stubbed(phone, live_server, owner, settings, "fail")
    phone.fill("#f-merchant", "Typed before going online")
    phone.clock.run_for(2000)  # first check fails: online events may now retry early
    assert stub(phone, "__calls") == 1
    phone.evaluate("window.__mode = 'stall'")
    phone.clock.run_for(5000)  # second check is in flight and hangs
    assert stub(phone, "__calls") == 2 and stub(phone, "__active") == 1
    for _ in range(5):
        phone.evaluate("window.dispatchEvent(new Event('online'))")
        phone.clock.run_for(100)
    assert stub(phone, "__calls") == 2 and stub(phone, "__maxActive") == 1  # no overlapping request
    phone.clock.run_for(15000)  # the hung check times out; the next one follows the back-off, not the events
    assert stub(phone, "__calls") == 2 and stub(phone, "__active") == 0
    phone.evaluate("window.__mode = 'real'")
    phone.evaluate("window.dispatchEvent(new Event('online'))")  # idle again: online retries at once
    phone.clock.run_for(100)
    expect(phone.locator("[data-reading-connection]")).to_be_hidden()
    assert stub(phone, "__calls") == 3 and stub(phone, "__maxActive") == 1
    assert_untouched(phone, draft, "Typed before going online")


def test_ten_minute_stop_says_checking_has_stopped(phone, live_server, owner, settings):
    draft = start_stubbed(phone, live_server, owner, settings, "fail")
    phone.fill("#f-merchant", "Typed while offline")
    for _ in range(25):
        phone.clock.run_for(30000)
    notice = phone.locator("[data-reading-connection]")
    expect(notice).to_contain_text("Connection problem: stopped checking the reading. Refresh the page later")
    expect(notice).not_to_contain_text("Still trying")
    expect(phone.locator("[data-reading-label]")).to_have_text("Still not finished. Refresh later, or enter the details yourself.")
    calls = stub(phone, "__calls")
    phone.evaluate("window.__mode = 'real'; window.dispatchEvent(new Event('online'))")  # stopped stays stopped
    phone.clock.run_for(120000)
    assert stub(phone, "__calls") == calls
    assert_untouched(phone, draft, "Typed while offline")
