import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.costs import services
from apps.costs.models import Purchase
from apps.costs.selectors import overall_summary, project_cost_summary

pytestmark = pytest.mark.django_db


def base(project, **extra):
    data = {
        "description": "Paint", "merchant": "Paint Co", "transaction_date": "2026-09-20", "total": "30.00",
        "line-0-description": "Paint", "line-0-amount": "30.00", "line-0-line_type": "item", "line-0-category": "material",
        "line-0-alloc-0-dest": f"project:{project.uuid}",
    }
    data.update(extra)
    return data


def test_manual_purchase_without_file(client_owner, owner, office):
    import uuid

    key = str(uuid.uuid4())
    response = client_owner.post(reverse("costs:purchase_create"), base(office, submission_key=key))
    assert response.status_code == 302
    again = client_owner.post(reverse("costs:purchase_create"), base(office, submission_key=key))
    assert again["Location"] == response["Location"]
    assert Purchase.objects.count() == 1
    assert project_cost_summary(office).net == Decimal("30.00")


def test_split_line_across_projects_via_form(client_owner, owner, office, hallway):
    data = base(office, **{
        "line-0-alloc-0-amount": "20.00",
        "line-0-alloc-1-dest": f"project:{hallway.uuid}", "line-0-alloc-1-amount": "10.00",
        "line-1-description": "Delivery", "line-1-amount": "5.00", "line-1-line_type": "shipping",
        "line-1-category": "other", "line-1-alloc-0-dest": "shared_tools",
        "total": "35.00",
    })
    response = client_owner.post(reverse("costs:purchase_create"), data)
    assert response.status_code == 302
    assert project_cost_summary(office).net == Decimal("20.00")
    assert project_cost_summary(hallway).net == Decimal("10.00")
    assert overall_summary(owner).total == Decimal("35.00")


def test_blank_total_means_lines_total(client_owner, owner, office):
    client_owner.post(reverse("costs:purchase_create"), base(office, total=""))
    assert Purchase.objects.get().total == Decimal("30.00")


def test_invalid_money_input_shows_errors(client_owner, owner, office):
    response = client_owner.post(reverse("costs:purchase_create"), base(office, **{"line-0-amount": "30.001", "total": "30.001"}))
    assert response.status_code == 200
    assert b"two decimal places" in response.content
    response = client_owner.post(reverse("costs:purchase_create"), base(office, **{"line-0-alloc-0-dest": ""}))
    assert b"Choose where this cost belongs" in response.content
    assert Purchase.objects.count() == 0


def test_overlap_flow_requires_choice_then_replaces(client_owner, owner, office):
    balance = services.create_opening_balance(owner, office, amount=Decimal("500.00"),
                                              coverage_through=datetime.date(2026, 9, 30), note="Old spend")
    first = client_owner.post(reverse("costs:purchase_create"), base(office))
    assert first.status_code == 200
    assert b"This may already be in an opening balance" in first.content
    assert Purchase.objects.count() == 0
    data = base(office, **{f"balance-{balance.uuid}-decision": "replace", f"balance-{balance.uuid}-amount": "30.00"})
    second = client_owner.post(reverse("costs:purchase_create"), data)
    assert second.status_code == 302
    balance.refresh_from_db()
    assert balance.amount == Decimal("470.00")
    assert project_cost_summary(office).net == Decimal("500.00")


def test_correction_view_with_reason_and_stale_version(client_owner, owner, office, hallway):
    client_owner.post(reverse("costs:purchase_create"), base(office))
    purchase = Purchase.objects.get()
    url = reverse("costs:purchase_edit", args=[purchase.uuid])
    assert b"Correct purchase" in client_owner.get(url).content
    no_reason = client_owner.post(url, base(hallway, version=purchase.version))
    assert b"Explain why" in no_reason.content
    ok = client_owner.post(url, base(hallway, version=purchase.version, reason="Wrong room"))
    assert ok.status_code == 302
    stale = client_owner.post(url, base(office, version=purchase.version, reason="again"))
    assert b"changed since you opened it" in stale.content
    assert project_cost_summary(hallway).net == Decimal("30.00")
    assert project_cost_summary(office).net == Decimal("0.00")
    detail = client_owner.get(reverse("costs:purchase_detail", args=[purchase.uuid])).content
    assert b"Wrong room" in detail and b"Previous version" in detail


def test_refund_and_void_views(client_owner, owner, office):
    client_owner.post(reverse("costs:purchase_create"), base(office))
    purchase = Purchase.objects.get()
    over = client_owner.post(reverse("costs:purchase_refund", args=[purchase.uuid]), {
        "transaction_date": "2026-09-21", f"amount-project:{office.uuid}": "31.00",
    })
    assert b"at most" in over.content
    ok = client_owner.post(reverse("costs:purchase_refund", args=[purchase.uuid]), {
        "transaction_date": "2026-09-21", f"amount-project:{office.uuid}": "10.00",
    })
    assert ok.status_code == 302
    assert project_cost_summary(office).net == Decimal("20.00")
    refund = Purchase.objects.get(kind="refund")
    client_owner.post(reverse("costs:purchase_void", args=[refund.uuid]), {"reason": "Mistake", "version": refund.version})
    assert project_cost_summary(office).net == Decimal("30.00")


def test_cost_filters_inclusive_dates(client_owner, owner, office):
    client_owner.post(reverse("costs:purchase_create"), base(office, transaction_date="2026-09-20", description="On boundary"))
    client_owner.post(reverse("costs:purchase_create"), base(office, transaction_date="2026-09-21", description="After"))
    body = client_owner.get(reverse("costs:index"), {"date_from": "2026-09-01", "date_to": "2026-09-20"}).content.decode()
    assert "On boundary" in body and "After" not in body
    assert overall_summary(owner, date_to=datetime.date(2026, 9, 20)).total == Decimal("30.00")
    body = client_owner.get(reverse("costs:index"), {"merchant": "Paint Co", "project": str(office.uuid)}).content.decode()
    assert "On boundary" in body and "After" in body


def test_no_hard_delete_route_for_purchases():
    from django.urls import NoReverseMatch

    with pytest.raises(NoReverseMatch):
        reverse("costs:purchase_delete", args=["00000000-0000-0000-0000-000000000000"])
