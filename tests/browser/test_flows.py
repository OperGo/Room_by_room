"""Small Playwright suite: real Chromium against Django's live server.

Run: pytest tests/browser -p no:cacheprovider   (uses the pre-installed Chromium)
"""

import io
from decimal import Decimal

import pytest
from PIL import Image
from playwright.sync_api import expect

from apps.costs.selectors import overall_summary, project_cost_summary  # noqa: F401
from apps.projects.models import Project

from .conftest import sign_in

pytestmark = pytest.mark.django_db(transaction=True)
PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1440, "height": 900}


@pytest.fixture
def phone(browser):
    context = browser.new_context(viewport=PHONE, has_touch=True, is_mobile=True)
    yield context.new_page()
    context.close()


@pytest.fixture
def desktop(browser):
    context = browser.new_context(viewport=DESKTOP)
    yield context.new_page()
    context.close()


def no_horizontal_scroll(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_phone_project_and_task_flow(phone, live_server, owner):
    page = phone
    sign_in(page, live_server)
    nav = page.locator("nav.bottom-nav")
    expect(nav).to_be_visible()
    expect(nav.locator("a[aria-current=page]")).to_have_text("Home")
    for box in [nav.locator("a").nth(i).bounding_box() for i in range(4)]:
        assert box["height"] >= 44 and box["width"] >= 44
    nav.get_by_text("Projects").click()
    expect(nav.locator("a[aria-current=page]")).to_have_text("Projects")
    page.get_by_role("link", name="New", exact=True).click()
    page.fill("#id_title", "Office cabinetry")
    page.fill("#id_room", "Office")
    page.fill("#id_budget", "1200")
    page.get_by_role("button", name="Create project").click()
    expect(page.locator("h1")).to_have_text("Office cabinetry")
    expect(page.get_by_text("No tasks yet").first).to_be_visible()
    page.get_by_role("link", name="Add a task").click()
    page.fill("#id_title", "Fill and sand joints")
    page.get_by_role("button", name="Add task").click()
    page.get_by_role("button", name="Mark “Fill and sand joints” done").click()
    expect(page.get_by_text("1 of 1 tasks complete").first).to_be_visible()
    assert no_horizontal_scroll(page)


def test_phone_receipt_upload_review_confirm(phone, live_server, owner):
    project = Project.objects.create(owner=owner, title="Office")
    page = phone
    sign_in(page, live_server)
    page.goto(f"{live_server.url}/receipts/new/")
    buf = io.BytesIO()
    Image.new("RGB", (300, 500), "white").save(buf, format="JPEG")
    page.set_input_files("input[aria-label='Upload a receipt image']",
                         files=[{"name": "receipt.jpg", "mimeType": "image/jpeg", "buffer": buf.getvalue()}])
    page.wait_for_url("**/receipts/*/")
    expect(page.get_by_text("Draft · not confirmed")).to_be_visible()
    page.fill("#f-merchant", "Hardware Co")
    page.fill("#f-date", "2026-09-26")
    page.fill("#f-total", "31.17")
    page.fill("#l0-desc", "Unitemised purchase")
    page.locator("[data-line] summary").first.click()
    page.select_option("#l0-type", "unitemised")
    page.fill("#l0-amt", "31.17")
    page.select_option("#l0-a0-dest", f"project:{project.uuid}")
    expect(page.locator("[data-reconcile-status]")).to_have_text("Matches total")
    confirm = page.get_by_role("button", name="Confirm purchase")
    confirm.dblclick()  # double tap must not double post
    expect(page.get_by_text("Receipt confirmed and purchase recorded.")).to_be_visible()
    assert page.locator("h1").inner_text() == "Hardware Co"
    assert project_cost_summary(project).net == Decimal("31.17")
    assert overall_summary(owner).total == Decimal("31.17")


def test_desktop_split_allocation(desktop, live_server, owner):
    office = Project.objects.create(owner=owner, title="Office")
    hallway = Project.objects.create(owner=owner, title="Hallway")
    page = desktop
    sign_in(page, live_server)
    expect(page.locator("nav.side-nav")).to_be_visible()
    expect(page.locator("nav.bottom-nav")).to_be_hidden()
    page.goto(f"{live_server.url}/costs/purchases/new/")
    page.fill("#f-merchant", "Timber merchant")
    page.fill("#f-total", "76.50")
    page.fill("#l0-desc", "MDF")
    page.fill("#l0-amt", "32.00")
    page.select_option("#l0-a0-dest", f"project:{office.uuid}")
    page.get_by_role("button", name="Add item", exact=True).click()
    page.fill("#l1-desc", "Filler and primer")
    page.fill("#l1-amt", "44.50")
    page.select_option("#l1-a0-dest", f"project:{office.uuid}")
    second = page.locator("[data-line]").nth(1)
    second.locator("summary").click()
    second.get_by_role("button", name="Split between projects").click()
    page.fill("#l1-a0-amt", "35.00")
    page.select_option("#l1-a1-dest", f"project:{hallway.uuid}")
    page.fill("#l1-a1-amt", "9.50")
    expect(page.locator("[data-reconcile-status]")).to_have_text("Matches total")
    page.get_by_role("button", name="Record purchase").click()
    expect(page.get_by_text("Purchase recorded.")).to_be_visible()
    assert project_cost_summary(office).net == Decimal("67.00")
    assert project_cost_summary(hallway).net == Decimal("9.50")


def test_phone_layout_without_horizontal_scroll(phone, live_server, owner):
    Project.objects.create(owner=owner, title="A very long project title that keeps going and going for the layout test")
    page = phone
    sign_in(page, live_server)
    for path in ("/", "/projects/", "/shopping/", "/costs/", "/receipts/new/", "/costs/purchases/new/"):
        page.goto(f"{live_server.url}{path}")
        assert no_horizontal_scroll(page), path


TARGETS = ("a.btn, button.btn, .icon-btn, .task-check, .shop-check, nav.bottom-nav a, .seg-full a, .tabs a, "
           "input:not([type=hidden]):not([type=file]), select, textarea, .back-link, details > summary, .text-btn")


def _small_targets(page):
    return page.evaluate("""(sel) => [...document.querySelectorAll(sel)].filter(el => {
        const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
        if (!r.width || !r.height || s.visibility === 'hidden' || el.closest('template')) return false;
        return r.height < 44 || (r.width < 44 && !el.matches('input, select, textarea'));
    }).map(el => el.outerHTML.slice(0, 90))""", TARGETS)


def _seed_review(owner):
    from apps.core.uploads import validate_receipt
    from apps.projects import services as ps
    from apps.projects.models import Task
    from apps.receipts.services import store_receipt
    from apps.shopping.models import ShoppingItem
    from django.core.files.uploadedfile import SimpleUploadedFile

    project = Project.objects.create(owner=owner, title="Office", budget=Decimal("100"))
    ps.save_task(owner, Task(project=project, title="Sand", estimated_minutes=30))
    ShoppingItem.objects.create(owner=owner, description="Caulk", project=project)
    from django.utils import timezone

    ShoppingItem.objects.create(owner=owner, description="Dust sheets", purchased_at=timezone.now())
    buf = io.BytesIO()
    Image.new("RGB", (300, 500), "white").save(buf, format="JPEG")
    _, draft = store_receipt(owner, validate_receipt(SimpleUploadedFile("r.jpg", buf.getvalue())), "r.jpg")
    return project, draft


def test_touch_targets_on_key_screens(phone, live_server, owner):
    project, draft = _seed_review(owner)
    sign_in(phone, live_server)
    for path in ("/", f"/projects/{project.uuid}/", "/shopping/", f"/receipts/{draft.uuid}/"):
        phone.goto(f"{live_server.url}{path}")
        phone.locator("details").evaluate_all("els => els.forEach(d => d.open = true)")
        assert _small_targets(phone) == [], path


def test_focused_field_not_covered_by_sticky_actions(phone, live_server, owner):
    project, draft = _seed_review(owner)
    sign_in(phone, live_server)
    phone.goto(f"{live_server.url}/receipts/{draft.uuid}/")
    for selector in ("#f-total", "#l0-amt", "#l0-a0-dest", "#f-merchant"):
        phone.focus(selector)
        phone.locator(selector).scroll_into_view_if_needed()
        covered = phone.evaluate("""(sel) => { const el = document.querySelector(sel); const r = el.getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return !(hit === el || el.contains(hit)); }""", selector)
        assert not covered, selector
    assert phone.evaluate("document.body.classList.contains('is-typing')")
    expect(phone.locator("nav.bottom-nav")).to_be_hidden()


def test_keyboard_focus_is_visible(desktop, live_server, owner):
    _seed_review(owner)
    sign_in(desktop, live_server)
    desktop.goto(f"{live_server.url}/")
    desktop.keyboard.press("Tab")  # skip link
    expect(desktop.locator(".skip-link")).to_be_focused()
    for _ in range(3):
        desktop.keyboard.press("Tab")
    outline = desktop.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    assert outline != "none"


def _reading_draft(owner):
    from apps.core.uploads import validate_receipt
    from apps.receipts.services import store_receipt
    from django.core.files.uploadedfile import SimpleUploadedFile

    project = Project.objects.create(owner=owner, title="Office")
    buf = io.BytesIO()
    Image.new("RGB", (300, 500), "white").save(buf, format="JPEG")
    _, draft = store_receipt(owner, validate_receipt(SimpleUploadedFile("r.jpg", buf.getvalue())), "r.jpg")
    return project, draft


def test_phone_reading_polls_and_loads_result_when_untouched(phone, live_server, owner, settings):
    from apps.receipts.jobs import process_available

    settings.RECEIPT_EXTRACTOR = "fake"
    project, draft = _reading_draft(owner)
    sign_in(phone, live_server)
    phone.goto(f"{live_server.url}/receipts/{draft.uuid}/")
    expect(phone.get_by_text("nothing is sent to an AI provider")).to_be_visible()
    phone.get_by_role("button", name="Read receipt automatically").click()
    expect(phone.get_by_text("Waiting to read the receipt…")).to_be_visible()
    process_available()
    # Untouched form: the page reloads itself and shows the reading.
    expect(phone.get_by_text("Synthetic test reading")).to_be_visible(timeout=15000)
    expect(phone.locator("#f-merchant")).to_have_value("Sample Hardware Co")
    expect(phone.locator("[data-reconcile-status]")).to_have_text("Choose a project for every item")


def test_phone_polling_never_replaces_typed_values(phone, live_server, owner, settings):
    from apps.receipts.jobs import process_available

    settings.RECEIPT_EXTRACTOR = "fake"
    project, draft = _reading_draft(owner)
    sign_in(phone, live_server)
    phone.goto(f"{live_server.url}/receipts/{draft.uuid}/")
    phone.get_by_role("button", name="Read receipt automatically").click()
    expect(phone.get_by_text("Waiting to read the receipt…")).to_be_visible()
    phone.fill("#f-merchant", "Typed while reading")
    process_available()
    expect(phone.get_by_text("Reading finished.").first).to_be_visible(timeout=15000)
    expect(phone.locator("#f-merchant")).to_have_value("Typed while reading")
    expect(phone.locator("[data-reading-dirty]")).to_be_visible()


# ------------------------------------------------------------------ Sprint 2A: editing during reading


def _start_reading(page, live_server, owner, settings):
    settings.RECEIPT_EXTRACTOR = "fake"
    project, draft = _reading_draft(owner)
    Project.objects.create(owner=owner, title="Hallway")
    sign_in(page, live_server)
    page.goto(f"{live_server.url}/receipts/{draft.uuid}/")
    page.get_by_role("button", name="Read receipt automatically").click()
    expect(page.get_by_text("Waiting to read the receipt…")).to_be_visible()
    return project, draft


def test_typing_during_reading_then_save_conflict_is_recoverable(phone, live_server, owner, settings):
    from apps.receipts.jobs import process_available
    from apps.receipts.models import ReceiptDraft

    project, draft = _start_reading(phone, live_server, owner, settings)
    phone.fill("#f-merchant", "Typed while reading")
    phone.fill("#l0-desc", "My own item")
    phone.fill("#l0-amt", "9.99")
    phone.select_option("#l0-a0-dest", f"project:{project.uuid}")
    process_available()
    expect(phone.locator("[data-reading-dirty]")).to_be_visible(timeout=15000)
    phone.get_by_role("button", name="Save draft for later").click()
    expect(phone.get_by_text("Not saved yet: this draft changed since you opened it")).to_be_visible()
    expect(phone.locator("#f-merchant")).to_have_value("Typed while reading")
    expect(phone.locator("#l0-amt")).to_have_value("9.99")
    phone.get_by_role("button", name="Save draft (keep my version)").click()
    expect(phone.get_by_text("Draft saved.")).to_be_visible()
    phone.reload()
    expect(phone.locator("#f-merchant")).to_have_value("Typed while reading")
    expect(phone.locator("#l0-desc")).to_have_value("My own item")
    expect(phone.locator("#l0-a0-dest")).to_have_value(f"project:{project.uuid}")
    assert ReceiptDraft.objects.get(pk=draft.pk).data["merchant"] == "Typed while reading"
    assert overall_summary(owner).total == Decimal("0.00")


def test_structural_edits_without_typing_block_auto_reload(phone, live_server, owner, settings):
    from apps.receipts.jobs import process_available

    project, draft = _start_reading(phone, live_server, owner, settings)
    phone.get_by_role("button", name="Add item", exact=True).click()
    phone.get_by_role("button", name="Add delivery, discount or rounding").click()
    phone.locator("[data-line]").nth(0).locator("[data-remove-line]").evaluate("b => b.click()")
    line = phone.locator("[data-line]").nth(0)
    line.locator("summary").click()
    line.get_by_role("button", name="Split between projects").click()
    line.locator("[data-remove-alloc]").last.click()
    count_before = phone.locator("[data-line]").count()
    process_available()
    expect(phone.locator("[data-reading-done]")).to_be_visible(timeout=15000)
    phone.wait_for_timeout(1500)
    assert phone.locator("[data-line]").count() == count_before  # no reload happened
    expect(phone.locator("[data-line] input[name$='-description']").last).to_have_value("Delivery")
    assert overall_summary(owner).total == Decimal("0.00")


def test_edit_before_read_or_retry_is_stopped_until_saved(phone, live_server, owner, settings):
    from apps.receipts.models import ExtractionJob

    settings.RECEIPT_EXTRACTOR = "fake"
    project, draft = _reading_draft(owner)
    sign_in(phone, live_server)
    phone.goto(f"{live_server.url}/receipts/{draft.uuid}/")
    phone.fill("#f-merchant", "Unsaved merchant")
    phone.get_by_role("button", name="Read receipt automatically").click()
    expect(phone.get_by_text("You have unsaved changes.")).to_be_visible()
    expect(phone.locator("#f-merchant")).to_have_value("Unsaved merchant")
    assert ExtractionJob.objects.count() == 0
    phone.get_by_role("button", name="Save draft for later").click()
    expect(phone.get_by_text("Draft saved.")).to_be_visible()
    phone.once("dialog", lambda d: d.accept())  # explicit: the reading will replace saved values
    phone.get_by_role("button", name="Read receipt automatically").click()
    expect(phone.get_by_text("Waiting to read the receipt…")).to_be_visible()
    assert ExtractionJob.objects.count() == 1
