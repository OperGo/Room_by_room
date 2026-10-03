from decimal import Decimal

import pytest
from django.urls import reverse

from apps.costs.models import Purchase
from apps.costs.selectors import overall_summary
from apps.shopping.models import ShoppingItem

pytestmark = pytest.mark.django_db


def test_add_item_and_group(client_owner, owner, office):
    client_owner.post(reverse("shopping:create"), {"description": "MDF sheet", "quantity": "2", "unit": "sheets",
                                                   "project": office.pk, "retailer": "Timber Co"})
    client_owner.post(reverse("shopping:create"), {"description": "Masking tape", "quantity": "1"})
    assert ShoppingItem.objects.filter(owner=owner).count() == 2
    by_project = client_owner.get(reverse("shopping:list")).content.decode()
    assert "Office" in by_project and "Shared" in by_project
    by_retailer = client_owner.get(reverse("shopping:list"), {"group": "retailer"}).content.decode()
    assert "Timber Co" in by_retailer and "Any retailer" in by_retailer


def test_quantity_must_be_positive(client_owner, owner):
    response = client_owner.post(reverse("shopping:create"), {"description": "Bad", "quantity": "0"})
    assert response.status_code == 200
    assert not ShoppingItem.objects.exists()


def test_identical_names_are_not_merged(client_owner, owner):
    for _ in range(2):
        client_owner.post(reverse("shopping:create"), {"description": "Filler", "quantity": "1"})
    assert ShoppingItem.objects.filter(description="Filler").count() == 2


def test_marking_bought_creates_no_expense(client_owner, owner, office):
    item = ShoppingItem.objects.create(owner=owner, description="Primer", project=office)
    response = client_owner.post(reverse("shopping:toggle_bought", args=[item.uuid]), follow=True)
    item.refresh_from_db()
    assert item.is_bought
    assert Purchase.objects.count() == 0
    assert overall_summary(owner).total == Decimal("0.00")
    assert b"No cost was recorded" in response.content
    assert b"Bought" in response.content


def test_record_purchase_from_item_links_and_prevents_double(client_owner, owner, office):
    item = ShoppingItem.objects.create(owner=owner, description="Primer", project=office)
    form = client_owner.get(reverse("costs:purchase_create"), {"shopping": item.uuid}).content.decode()
    assert "Primer" in form and f'value="{item.pk}"' in form
    response = client_owner.post(reverse("costs:purchase_create"), {
        "description": "Primer", "transaction_date": "2026-09-20", "total": "35.00",
        "line-0-description": "Primer", "line-0-amount": "35.00", "line-0-alloc-0-dest": f"project:{office.uuid}",
        "line-0-shopping": str(item.pk),
    })
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.purchase_line is not None and item.is_bought
    # Second attempt shows the existing purchase instead of creating another.
    again = client_owner.get(reverse("costs:purchase_create"), {"shopping": item.uuid})
    assert again.status_code == 302
    assert Purchase.objects.count() == 1
    # A linked item cannot be un-ticked from the list.
    client_owner.post(reverse("shopping:toggle_bought", args=[item.uuid]))
    item.refresh_from_db()
    assert item.is_bought


def test_shopping_item_linked_only_once_across_purchases(owner, office):
    from apps.core.exceptions import BusinessRuleError
    from apps.costs.services import post_purchase

    from .conftest import line, purchase_input, to

    item = ShoppingItem.objects.create(owner=owner, description="Primer", project=office)
    post_purchase(owner, purchase_input([line("Primer", "35.00", [to(office, "35.00")], shopping_item_ids=[item.pk])]))
    with pytest.raises(BusinessRuleError):
        post_purchase(owner, purchase_input([line("Primer", "35.00", [to(office, "35.00")], shopping_item_ids=[item.pk])]))
    assert Purchase.objects.count() == 1


def test_deleting_item_keeps_purchase(client_owner, owner, office):
    from apps.costs.services import post_purchase

    from .conftest import line, purchase_input, to

    item = ShoppingItem.objects.create(owner=owner, description="Primer", project=office)
    post_purchase(owner, purchase_input([line("Primer", "35.00", [to(office, "35.00")], shopping_item_ids=[item.pk])]))
    client_owner.post(reverse("shopping:delete", args=[item.uuid]))
    assert overall_summary(owner).total == Decimal("35.00")
