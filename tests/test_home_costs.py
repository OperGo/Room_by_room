"""Home project cards show recorded cost and budget position (CTO plan, 7 October).

Figures come from the same selector rules as the project page: opening estimates plus confirmed purchases
minus confirmed refunds. Drafts never count; a missing budget is never shown as zero."""
import datetime
import re
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.costs import services
from apps.costs.selectors import project_cost_summaries, project_cost_summary
from apps.projects.models import Project
from apps.receipts.models import ReceiptDraft

from .conftest import image_bytes, line, purchase_input, to, upload

pytestmark = pytest.mark.django_db
D = Decimal


def card(page, title):
    """Text of the Home card for ``title`` (featured or compact), tags stripped."""
    start = page.index(f">{title}<")
    end = page.find("</a>", start)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page[start:end]))


def home(client):
    return client.get(reverse("core:home")).content.decode()


def test_recorded_cost_and_budget_left(client_owner, owner, office, hallway):
    services.post_purchase(owner, purchase_input([line("Paint", "115.60", [to(office, "115.60")])]))
    text = card(home(client_owner), "Office")
    assert "Recorded £115.60" in text and "£1,084.40 left of £1,200.00 budget" in text
    assert "over" not in text


def test_over_budget_is_unambiguous(client_owner, owner):
    small = Project.objects.create(owner=owner, title="Shed", budget=D("100.00"), status=Project.Status.ACTIVE)
    services.post_purchase(owner, purchase_input([line("Timber", "150.00", [to(small, "150.00")])]))
    text = card(home(client_owner), "Shed")
    assert "Recorded £150.00" in text and "£50.00 over the £100.00 budget" in text and "left" not in text


def test_missing_budget_is_not_shown_as_zero(client_owner, owner, office, hallway):
    text = card(home(client_owner), "Hallway")
    assert "Recorded £0.00" in text and "No budget set" in text
    assert "left of" not in text and "£0.00 budget" not in text


def test_opening_estimate_is_identified_and_refunds_reduce(client_owner, owner, office, hallway):
    services.create_opening_balance(owner, hallway, amount=D("40.00"), coverage_through=datetime.date(2026, 9, 1))
    purchase = services.post_purchase(owner, purchase_input([line("Hooks", "20.00", [to(hallway, "20.00")])]))
    services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 20),
                             amounts={f"project:{hallway.uuid}": D("5.00")})
    text = card(home(client_owner), "Hallway")
    assert "Recorded £55.00 incl. £40.00 estimate" in text  # 40 + 20 - 5
    assert project_cost_summary(hallway).net == D("55.00")


def test_drafts_never_count(client_owner, owner, office, hallway):
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r.jpg", image_bytes())})
    draft = ReceiptDraft.objects.get()
    draft.data = {"merchant": "Shop", "total": "99.00", "lines": [
        {"description": "x", "amount": "99.00", "allocations": [{"dest": f"project:{office.uuid}", "amount": ""}]}]}
    draft.save()
    assert "Recorded £0.00" in card(home(client_owner), "Office")


def test_only_the_owners_projects_appear(client_owner, owner, intruder, office):
    theirs = Project.objects.create(owner=intruder, title="Their loft", budget=D("10.00"), status=Project.Status.ACTIVE)
    services.post_purchase(intruder, purchase_input([line("x", "30.00", [to(theirs, "30.00")])]))
    page = home(client_owner)
    assert "Their loft" not in page and "£30.00" not in page


def test_bulk_summaries_match_the_single_project_selector(owner, office, hallway):
    services.create_opening_balance(owner, office, amount=D("12.34"), coverage_through=datetime.date(2026, 9, 1))
    purchase = services.post_purchase(owner, purchase_input([
        line("A", "30.00", [to(office, "10.00"), to(hallway, "20.00")])]))
    services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 20),
                             amounts={f"project:{hallway.uuid}": D("2.50")})
    bulk = project_cost_summaries(owner, [office, hallway])
    for project in (office, hallway):
        assert bulk[project.pk] == project_cost_summary(project)
