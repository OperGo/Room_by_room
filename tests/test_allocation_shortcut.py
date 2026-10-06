"""Assign unassigned items to one project (assessment gap 1).

Project context travels project → upload → reading → review, owner-validated at every step; the bulk
action fills only lines with no destination and never records anything by itself.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.costs.models import CostAllocation, Purchase
from apps.costs.selectors import overall_summary, project_cost_summary
from apps.projects.models import Project
from apps.receipts import jobs
from apps.receipts.models import ExtractionJob, ReceiptDraft

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture(autouse=True)
def fake_extractor(settings):
    settings.RECEIPT_EXTRACTOR = "fake"


def key(project):
    return f"project:{project.uuid}"


def start_from(client, project=None, **extra):
    url = reverse("receipts:new") + (f"?project={project.uuid}" if project else "")
    data = {"receipt": upload("r.jpg", image_bytes())}
    if project:
        data["project"] = str(project.uuid)
    data.update(extra)
    return client.post(url, data)


def editor_post(draft, lines, **header):
    """POST fields for the review form from editor line dicts."""
    data = {"version": str(draft.version), "merchant": "Sample Hardware Co", "transaction_date": "2026-09-26",
            "total": "", **header}
    for i, line in enumerate(lines):
        data[f"line-{i}-description"] = line["description"]
        data[f"line-{i}-amount"] = line["amount"]
        data[f"line-{i}-line_type"] = line.get("line_type", "item")
        data[f"line-{i}-category"] = line.get("category", "material")
        for j, alloc in enumerate(line.get("allocations") or [{"dest": "", "amount": ""}]):
            data[f"line-{i}-alloc-{j}-dest"] = alloc["dest"]
            data[f"line-{i}-alloc-{j}-amount"] = alloc["amount"]
    return data


def read(owner, draft):
    jobs.request_reading(owner, draft, draft.version)
    jobs.process_available()
    draft.refresh_from_db()
    return draft


# ------------------------------------------------------------------ project context


def test_project_page_receipt_link_carries_the_project(client_owner, office):
    page = client_owner.get(reverse("projects:detail", args=[office.uuid]) + "?tab=costs").content.decode()
    assert f"/receipts/new/?project={office.uuid}" in page


def test_context_survives_upload_reading_and_review(client_owner, owner, office):
    page = client_owner.get(reverse("receipts:new") + f"?project={office.uuid}").content.decode()
    assert f'name="project" value="{office.uuid}"' in page and "For <strong>Office</strong>" in page
    assert f"/costs/purchases/new/?project={office.uuid}" in page  # manual entry keeps the project too
    start_from(client_owner, office)
    draft = ReceiptDraft.objects.get(owner=owner)
    assert draft.context_project == office
    # Before reading: the bulk choice and the blank manual line both start on the project.
    review = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert f'<option value="{key(office)}" selected>' in review
    assert review.count(f'<option value="{key(office)}" selected>') == 2  # bulk select + blank line
    # After an automatic reading the lines arrive unassigned; the bulk choice still offers the project.
    draft = read(owner, draft)
    assert all(not a["dest"] for line in draft.data["lines"] for a in line["allocations"])
    review = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert review.count(f'<option value="{key(office)}" selected>') == 1
    assert "Assign unassigned items to" in review
    assert Purchase.objects.count() == 0  # nothing recorded by context, reading or review


@pytest.mark.parametrize("value", ["not-a-uuid", "00000000-0000-0000-0000-000000000000", "foreign", "archived"])
def test_untrusted_project_context_is_ignored(client_owner, owner, intruder, value):
    if value == "foreign":
        value = str(Project.objects.create(owner=intruder, title="Theirs").uuid)
    elif value == "archived":
        value = str(Project.objects.create(owner=owner, title="Old", status=Project.Status.ARCHIVED).uuid)
    page = client_owner.get(reverse("receipts:new") + f"?project={value}").content.decode()
    assert 'name="project"' not in page
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r.jpg", image_bytes()), "project": value})
    draft = ReceiptDraft.objects.get(owner=owner)
    assert draft.context_project is None
    review = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "Theirs" not in review and " selected>" not in review.split("Assign unassigned items to")[1].split("</select>")[0]


def test_store_receipt_refuses_a_foreign_context_project(owner, intruder):
    from apps.core.uploads import validate_receipt
    from apps.receipts.services import store_receipt

    theirs = Project.objects.create(owner=intruder, title="Theirs")
    _, draft = store_receipt(owner, validate_receipt(upload("r.jpg", image_bytes())), "r.jpg", context_project=theirs)
    assert draft.context_project is None


def test_retake_keeps_the_project_context(client_owner, owner, office):
    start_from(client_owner, office)
    draft = ReceiptDraft.objects.get(owner=owner)
    response = client_owner.post(reverse("receipts:discard", args=[draft.uuid]) + "?retake=1", {"version": draft.version})
    assert response["Location"] == reverse("receipts:new") + f"?project={office.uuid}"


# ------------------------------------------------------------------ assigning


def test_one_project_receipt_needs_one_assignment(client_owner, owner, office):
    start_from(client_owner, office)
    draft = read(owner, ReceiptDraft.objects.get(owner=owner))
    data = editor_post(draft, draft.data["lines"], total=draft.data["total"], bulk_dest=key(office),
                       assign_unassigned="1")
    response = client_owner.post(reverse("receipts:save", args=[draft.uuid]), data)
    assert response.status_code == 302
    draft.refresh_from_db()
    assert {a["dest"] for line in draft.data["lines"] for a in line["allocations"]} == {key(office)}
    assert Purchase.objects.count() == 0  # assigning saves the draft only
    confirm = editor_post(draft, draft.data["lines"], total=draft.data["total"])
    assert client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), confirm).status_code == 302
    assert project_cost_summary(office).net == D("31.17") == overall_summary(owner).total


def test_assign_fills_only_unset_lines_and_keeps_splits(client_owner, owner, office, hallway):
    start_from(client_owner)
    draft = ReceiptDraft.objects.get(owner=owner)
    lines = [
        {"description": "Chosen", "amount": "10.00", "allocations": [{"dest": key(hallway), "amount": ""}]},
        {"description": "Unset", "amount": "4.00", "allocations": [{"dest": "", "amount": ""}]},
        {"description": "Split", "amount": "8.00", "allocations": [{"dest": key(office), "amount": "5.00"},
                                                                  {"dest": "", "amount": "3.00"}]},
        {"description": "Shared", "amount": "2.00", "allocations": [{"dest": "shared_tools", "amount": ""}]},
    ]
    data = editor_post(draft, lines, bulk_dest=key(office), assign_unassigned="1")
    client_owner.post(reverse("receipts:save", args=[draft.uuid]), data)
    draft.refresh_from_db()
    saved = {line["description"]: line["allocations"] for line in draft.data["lines"]}
    assert saved["Chosen"] == [{"dest": key(hallway), "amount": ""}]
    assert saved["Unset"] == [{"dest": key(office), "amount": ""}]
    assert saved["Split"] == [{"dest": key(office), "amount": "5.00"}, {"dest": "", "amount": "3.00"}]  # untouched
    assert saved["Shared"] == [{"dest": "shared_tools", "amount": ""}]


@pytest.mark.parametrize("bulk", ["", "project:00000000-0000-0000-0000-000000000000", "foreign"])
def test_assign_refuses_unknown_or_foreign_destinations(client_owner, owner, intruder, bulk):
    if bulk == "foreign":
        bulk = key(Project.objects.create(owner=intruder, title="Theirs"))
    start_from(client_owner)
    draft = ReceiptDraft.objects.get(owner=owner)
    lines = [{"description": "Unset", "amount": "4.00", "allocations": [{"dest": "", "amount": ""}]}]
    response = client_owner.post(reverse("receipts:save", args=[draft.uuid]),
                                 editor_post(draft, lines, bulk_dest=bulk, assign_unassigned="1"), follow=True)
    assert b"Choose a project to assign the unassigned items to." in response.content
    draft.refresh_from_db()
    assert draft.data["lines"][0]["allocations"] == [{"dest": "", "amount": ""}]  # saved as typed, nothing assigned
    assert CostAllocation.objects.count() == 0


def test_reading_that_finishes_after_owner_edits_is_held_and_context_kept(client_owner, owner, office, hallway):
    start_from(client_owner, office)
    draft = ReceiptDraft.objects.get(owner=owner)
    jobs.request_reading(owner, draft, draft.version)
    # While the reading is queued, the owner assigns their own lines and saves.
    lines = [{"description": "Typed", "amount": "9.00", "allocations": [{"dest": key(hallway), "amount": ""}]}]
    client_owner.post(reverse("receipts:save", args=[draft.uuid]), editor_post(draft, lines))
    jobs.process_available()
    draft.refresh_from_db()
    job = ExtractionJob.objects.get()
    assert job.status == "succeeded" and job.result_state == "held"  # never overwrites the owner's edits
    assert draft.data["lines"][0]["allocations"] == [{"dest": key(hallway), "amount": ""}]
    assert draft.context_project == office
    review = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert review.split("Assign unassigned items to")[1].count(f'<option value="{key(office)}" selected>') >= 1


def test_missing_destinations_are_reported_once_without_hiding_other_errors(client_owner, owner, office):
    start_from(client_owner)
    draft = ReceiptDraft.objects.get(owner=owner)
    lines = [
        {"description": "Bad amount", "amount": "1.234", "allocations": [{"dest": key(office), "amount": ""}]},
        {"description": "No project", "amount": "2.00", "allocations": [{"dest": "", "amount": ""}]},
        {"description": "Also none", "amount": "3.00", "allocations": [{"dest": "", "amount": ""}]},
    ]
    page = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), editor_post(draft, lines)).content.decode()
    assert "Line 1:" in page and "two decimal places" in page
    assert "Choose a project for items 2 and 3." in page
    assert "Choose where this cost belongs" not in page
    assert Purchase.objects.count() == 0


def test_manual_purchase_assign_without_javascript_records_nothing(client_owner, owner, office):
    import uuid

    submission_key = str(uuid.uuid4())
    url = reverse("costs:purchase_create") + f"?project={office.uuid}"
    page = client_owner.get(url).content.decode()
    # The bulk choice and the first blank line both start on the project (as before for Add purchase).
    assert page.split("Assign unassigned items to")[1].count(f'<option value="{key(office)}" selected>') == 2
    data = {"submission_key": submission_key, "merchant": "Paint Co", "transaction_date": "2026-09-20", "total": "",
            "line-0-description": "Paint", "line-0-amount": "30.00", "line-0-alloc-0-dest": "",
            "line-1-description": "Brush", "line-1-amount": "5.00", "line-1-alloc-0-dest": "",
            "bulk_dest": key(office), "assign_unassigned": "1"}
    page = client_owner.post(url, data).content.decode()
    assert Purchase.objects.count() == 0
    assert page.count(f'<option value="{key(office)}" selected>') == 3  # bulk select + both lines
    assert f'value="{submission_key}"' in page
