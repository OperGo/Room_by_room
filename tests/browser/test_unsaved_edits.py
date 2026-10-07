"""Receipt review: "Unsaved changes" indicator and leave warning (CTO plan, 7 October)."""
import io
from decimal import Decimal

import pytest
from PIL import Image
from playwright.sync_api import Error as PlaywrightError, expect

from apps.costs.models import Purchase
from apps.costs.selectors import overall_summary
from apps.projects.models import Project

from .conftest import sign_in

pytestmark = pytest.mark.django_db(transaction=True)
PHONE = {"width": 390, "height": 844}


@pytest.fixture
def phone(browser):
    context = browser.new_context(viewport=PHONE, has_touch=True, is_mobile=True)
    yield context.new_page()
    context.close()


@pytest.fixture
def office(owner):
    return Project.objects.create(owner=owner, title="Office")


def open_draft(page, live_server, owner, context=None, read=False):
    from apps.core.uploads import validate_receipt
    from apps.receipts.services import store_receipt
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = io.BytesIO()
    Image.new("RGB", (300, 500), "white").save(buf, format="JPEG")
    _, draft = store_receipt(owner, validate_receipt(SimpleUploadedFile("r.jpg", buf.getvalue())), "r.jpg")
    if context:
        type(draft).objects.filter(pk=draft.pk).update(context_project=context)  # started from the project
        draft.refresh_from_db()
    if read:  # fake extractor: five unassigned items
        from apps.receipts import jobs
        jobs.request_reading(owner, draft, draft.version)
        jobs.process_available()
    sign_in(page, live_server)
    page.goto(f"{live_server.url}/receipts/{draft.uuid}/")
    return draft


class Dialogs(list):
    """Records every dialog as (type, message); accepts or dismisses according to .accept."""

    def __init__(self, page, accept):
        super().__init__()
        self.accept = accept
        page.on("dialog", self._handle)

    def _handle(self, dialog):
        self.append((dialog.type, dialog.message))
        dialog.accept() if self.accept else dialog.dismiss()


def record_dialogs(page, accept):
    return Dialogs(page, accept)


def closed_soon(page, seconds=2):
    # Playwright's sync API handles events (dialogs, close) only inside its own calls, so poll with them.
    for _ in range(int(seconds * 10)):
        try:
            page.wait_for_timeout(100)
        except PlaywrightError:
            return True
        if page.is_closed():
            return True
    return False


def fill_valid(page, project):
    page.fill("#f-merchant", "Hardware Co")
    page.fill("#f-date", "2026-09-26")
    page.fill("#f-total", "9.99")
    page.fill("#l0-desc", "Screws")
    page.fill("#l0-amt", "9.99")
    page.select_option("#l0-a0-dest", f"project:{project.uuid}")


def test_typing_shows_indicator_and_back_link_asks_before_leaving(phone, live_server, owner, office):
    open_draft(phone, live_server, owner)
    badge = phone.locator(".badge-unsaved")
    expect(badge).to_be_hidden()
    phone.fill("#f-merchant", "Typed merchant")
    expect(badge).to_be_visible()
    expect(badge).to_have_text("Unsaved changes")
    expect(phone.locator(".unsaved-note-inline")).to_be_visible()
    expect(phone.locator("[data-unsaved-live]")).to_have_text("Unsaved changes. Press Save draft to keep them.")

    seen = record_dialogs(phone, accept=False)
    url = phone.url
    phone.locator(".back-link").click()
    phone.wait_for_timeout(300)
    assert seen and seen[0][0] == "confirm" and "unsaved changes will be lost" in seen[0][1]
    assert phone.url == url  # stayed
    expect(phone.locator("#f-merchant")).to_have_value("Typed merchant")

    seen.accept = True
    phone.locator("nav.bottom-nav").get_by_text("Costs").click()
    phone.wait_for_url(f"{live_server.url}/costs/")
    assert [kind for kind, _ in seen] == ["confirm", "confirm"]  # no extra browser-level prompt


@pytest.mark.parametrize("action", ["assign", "add_item", "split", "remove_line"])
def test_shortcut_and_structural_edits_show_indicator(phone, live_server, owner, office, action, settings):
    settings.RECEIPT_EXTRACTOR = "fake"
    open_draft(phone, live_server, owner, context=office, read=action == "assign")
    badge = phone.locator(".badge-unsaved")
    expect(badge).to_be_hidden()
    if action == "assign":
        expect(phone.locator("#bulk-dest")).to_have_value(f"project:{office.uuid}")  # preselected: no edit yet
        phone.get_by_role("button", name="Assign", exact=True).click()
        expect(phone.locator("[data-bulk-note]")).to_contain_text("Assigned 5 items to Office")
    elif action == "add_item":
        phone.get_by_role("button", name="Add item", exact=True).click()
    elif action == "split":
        line = phone.locator("[data-line]").nth(0)
        line.locator("summary").click()
        line.get_by_role("button", name="Split between projects").click()
    else:
        phone.get_by_role("button", name="Add item", exact=True).click()
        phone.locator("[data-line]").nth(1).locator("[data-remove-line]").evaluate("b => b.click()")
    expect(badge).to_be_visible()
    assert Purchase.objects.count() == 0


def test_save_and_confirm_never_warn(phone, live_server, owner, office):
    open_draft(phone, live_server, owner)
    seen = record_dialogs(phone, accept=False)
    phone.fill("#f-merchant", "Saved merchant")
    phone.get_by_role("button", name="Save draft for later").click()
    expect(phone.get_by_text("Draft saved.")).to_be_visible()
    expect(phone.locator(".badge-unsaved")).to_be_hidden()
    fill_valid(phone, office)
    phone.get_by_role("button", name="Confirm purchase").click()
    expect(phone.get_by_text("Receipt confirmed and purchase recorded.")).to_be_visible()
    assert seen == []
    assert Purchase.objects.count() == 1 and overall_summary(owner).total == Decimal("9.99")


def test_refused_confirmation_shows_indicator_and_keeps_values(phone, live_server, owner, office):
    open_draft(phone, live_server, owner)
    fill_valid(phone, office)
    phone.fill("#f-total", "12.00")  # items no longer match the total: the server refuses
    phone.get_by_role("button", name="Confirm purchase").click()
    expect(phone.locator("#f-total")).to_have_value("12.00")
    expect(phone.locator(".badge-unsaved")).to_be_visible()
    assert Purchase.objects.count() == 0
    seen = record_dialogs(phone, accept=False)
    phone.locator(".back-link").click()
    phone.wait_for_timeout(300)
    assert [kind for kind, _ in seen] == ["confirm"]


def test_browser_close_or_reload_warns_only_while_unsaved(phone, live_server, owner, office):
    open_draft(phone, live_server, owner)
    seen = record_dialogs(phone, accept=False)
    phone.fill("#f-merchant", "Typed merchant")
    phone.close(run_before_unload=True)
    assert not closed_soon(phone)  # the prompt was dismissed: the page stays
    assert [kind for kind, _ in seen] == ["beforeunload"]


def test_saved_page_closes_without_warning(phone, live_server, owner, office):
    open_draft(phone, live_server, owner)
    seen = record_dialogs(phone, accept=True)
    phone.fill("#f-merchant", "Saved merchant")
    phone.get_by_role("button", name="Save draft for later").click()
    expect(phone.get_by_text("Draft saved.")).to_be_visible()
    phone.close(run_before_unload=True)
    assert closed_soon(phone)
    assert seen == []


def test_stale_version_recovery_still_saves_without_warning(phone, live_server, owner, office):
    from apps.receipts.models import ReceiptDraft

    draft = open_draft(phone, live_server, owner)
    ReceiptDraft.objects.filter(pk=draft.pk).update(version=draft.version + 1)  # changed elsewhere
    seen = record_dialogs(phone, accept=True)
    phone.fill("#f-merchant", "My version")
    phone.get_by_role("button", name="Save draft for later").click()
    expect(phone.get_by_text("Not saved yet: this draft changed since you opened it")).to_be_visible()
    expect(phone.locator(".badge-unsaved")).to_be_visible()
    phone.get_by_role("button", name="Save draft (keep my version)").click()
    expect(phone.get_by_text("Draft saved.")).to_be_visible()
    assert seen == []
    assert ReceiptDraft.objects.get(pk=draft.pk).data["merchant"] == "My version"


def test_desktop_sign_out_asks_before_discarding_edits(browser, live_server, owner, office):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    open_draft(page, live_server, owner)
    seen = record_dialogs(page, accept=False)
    page.fill("#f-merchant", "Typed merchant")
    url = page.url
    page.locator("nav.side-nav").get_by_role("button", name="Sign out").click()
    page.wait_for_timeout(300)
    assert [kind for kind, _ in seen] == ["confirm"] and page.url == url
    expect(page.locator("#f-merchant")).to_have_value("Typed merchant")
    context.close()
