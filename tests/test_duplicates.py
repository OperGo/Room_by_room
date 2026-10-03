"""Duplicate warnings: similarity is a warning that needs server-validated acknowledgement, never proof."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.costs.models import Purchase, PurchaseEvidence
from apps.costs.selectors import overall_summary
from apps.costs.services import post_purchase
from apps.receipts.models import ReceiptDraft
from apps.receipts.services import find_similar_purchases

from .conftest import image_bytes, line, purchase_input, to, upload

pytestmark = pytest.mark.django_db


def new_draft(client, content=None):
    client.post(reverse("receipts:new"), {"receipt": upload("r.jpg", content or image_bytes(color="white"))})
    return ReceiptDraft.objects.order_by("-id").first()


def payload(project, merchant="Timber Co", date="2026-09-12", total="32.00", version=1):
    return {"version": str(version), "merchant": merchant, "transaction_date": date, "total": total,
            "line-0-description": "MDF", "line-0-amount": total, "line-0-alloc-0-dest": f"project:{project.uuid}"}


@pytest.fixture
def existing(owner, office):
    return post_purchase(owner, purchase_input([line("MDF", "32.00", [to(office, "32.00")])], merchant="TIMBER CO.",
                                               date=datetime.date(2026, 9, 11)))


def test_similar_purchase_requires_acknowledgement(client_owner, owner, office, existing):
    draft = new_draft(client_owner)
    response = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), payload(office))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Possible duplicate" in body and "This may duplicate a purchase" in body and str(existing.uuid) in body
    assert Purchase.objects.count() == 1
    # A forged acknowledgement for a different purchase does not count.
    forged = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]),
                               {**payload(office), "ack_duplicate": "00000000-0000-0000-0000-000000000000"})
    assert forged.status_code == 200 and Purchase.objects.count() == 1
    # Explicit acknowledgement: a legitimate identical purchase is allowed.
    ok = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), {**payload(office), "ack_duplicate": str(existing.uuid)})
    assert ok.status_code == 302
    assert Purchase.objects.count() == 2 and overall_summary(owner).total == Decimal("64.00")


def test_attach_route_adds_no_cost_instead(client_owner, owner, office, existing):
    draft = new_draft(client_owner)
    client_owner.post(reverse("receipts:attach", args=[draft.uuid]), {"purchase": str(existing.uuid), "version": "1"})
    assert Purchase.objects.count() == 1 and overall_summary(owner).total == Decimal("32.00")
    assert PurchaseEvidence.objects.filter(purchase=existing).count() == 1


def test_similarity_rules(owner, office, intruder, existing):
    def similar(**kw):
        defaults = dict(merchant="Timber Co", date=datetime.date(2026, 9, 12), total="32.00")
        defaults.update(kw)
        data = purchase_input([line("x", defaults["total"], [to(office, defaults["total"])])],
                              merchant=defaults["merchant"], date=defaults["date"])
        return [p for p, _ in find_similar_purchases(owner, data)]

    assert similar() == [existing]
    assert similar(merchant="") == [existing]  # unknown merchant still warns
    assert similar(total="32.01") == []
    assert similar(date=datetime.date(2026, 9, 20)) == []
    assert similar(merchant="Paint Shop") == []
    from apps.costs.services import void_purchase

    void_purchase(owner, existing, existing.version, "test")
    assert similar() == []
    # Owner-scoped: another user's identical purchase is never shown.
    from apps.projects.models import Project

    theirs = Project.objects.create(owner=intruder, title="Theirs")
    post_purchase(intruder, purchase_input([line("MDF", "32.00", [to(theirs, "32.00")])], merchant="Timber Co"))
    assert similar() == []


def test_same_file_already_evidencing_a_purchase_warns(client_owner, owner, office):
    content = image_bytes(color="blue")
    first = new_draft(client_owner, content)
    client_owner.post(reverse("receipts:confirm", args=[first.uuid]), payload(office, merchant="A", total="10.00"))
    second = new_draft(client_owner, content)
    response = client_owner.post(reverse("receipts:confirm", args=[second.uuid]),
                                 payload(office, merchant="Different", date="2026-01-01", total="99.00"))
    assert b"The same receipt file is already attached" in response.content
    assert Purchase.objects.count() == 1
