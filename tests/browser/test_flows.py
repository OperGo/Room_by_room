"""Small Playwright suite: real Chromium against Django's live server.

Run: pytest tests/browser -p no:cacheprovider   (uses the pre-installed Chromium)
"""

import io
from decimal import Decimal

import pytest
from PIL import Image
from playwright.sync_api import expect

from apps.costs.selectors import overall_summary, project_cost_summary
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
