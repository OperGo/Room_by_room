"""Owner isolation: a second user can never see or change the owner's records."""

import pytest
from django.urls import reverse

from apps.costs.models import Purchase
from apps.costs.services import create_opening_balance, post_purchase
from apps.projects import services as ps
from apps.projects.models import Project, Task
from apps.receipts.services import store_receipt
from apps.core.uploads import validate_receipt
from apps.shopping.models import ShoppingItem

from .conftest import image_bytes, line, purchase_input, to, upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner_records(owner, private_storage_tmp):
    import datetime
    from decimal import Decimal

    project = Project.objects.create(owner=owner, title="Private office")
    task = ps.save_task(owner, Task(project=project, title="Secret task"))
    validated = validate_receipt(upload("r.jpg", image_bytes()))
    photo = ps.add_photo(owner, project, validated)
    document, draft = store_receipt(owner, validated, "r.jpg")
    purchase = post_purchase(owner, purchase_input([line("Quokka board", "32.00", [to(project, "32.00")])], description="Quokka purchase"))
    item = ShoppingItem.objects.create(owner=owner, description="Zebra caulk", project=project)
    balance = create_opening_balance(owner, project, amount=Decimal("10.00"), coverage_through=datetime.date(2020, 1, 1))
    return dict(project=project, task=task, photo=photo, document=document, draft=draft, purchase=purchase, item=item, balance=balance)


GET_URLS = [
    ("projects:detail", "project"), ("projects:edit", "project"), ("projects:task_create", "project"),
    ("projects:photo_upload", "project"), ("projects:opening_balance_create", "project"),
    ("projects:opening_balance_edit", "balance"),
    ("projects:task_detail", "task"), ("projects:task_edit", "task"), ("projects:task_dependencies", "task"),
    ("projects:photo_file", "photo"),
    ("shopping:edit", "item"),
    ("costs:purchase_detail", "purchase"), ("costs:purchase_edit", "purchase"), ("costs:purchase_void", "purchase"),
    ("costs:purchase_refund", "purchase"),
    ("receipts:review", "draft"), ("receipts:file", "document"),
]

POST_URLS = [
    ("projects:status", "project", {"status": "archived"}), ("projects:task_complete", "task", {}),
    ("projects:task_status", "task", {"status": "cancelled"}), ("projects:task_weekend", "task", {}),
    ("projects:photo_delete", "photo", {}), ("projects:photo_cover", "photo", {}),
    ("shopping:toggle_bought", "item", {}), ("shopping:delete", "item", {}),
    ("costs:purchase_void", "purchase", {"reason": "x", "version": 1}),
    ("receipts:confirm", "draft", {}), ("receipts:save", "draft", {}), ("receipts:discard", "draft", {}),
    ("receipts:attach", "draft", {}),
]


@pytest.mark.parametrize("name,key", GET_URLS)
def test_other_user_gets_404(client, intruder, owner_records, name, key):
    client.force_login(intruder)
    response = client.get(reverse(name, args=[owner_records[key].uuid]))
    assert response.status_code == 404


@pytest.mark.parametrize("name,key,data", POST_URLS)
def test_other_user_cannot_post(client, intruder, owner_records, name, key, data):
    client.force_login(intruder)
    response = client.post(reverse(name, args=[owner_records[key].uuid]), data)
    assert response.status_code == 404


def test_other_user_actions_change_nothing(client, intruder, owner_records):
    client.force_login(intruder)
    for name, key, data in POST_URLS:
        client.post(reverse(name, args=[owner_records[key].uuid]), data)
    project = owner_records["project"]
    project.refresh_from_db()
    assert project.status == "active"
    assert Purchase.objects.get(pk=owner_records["purchase"].pk).status == "confirmed"
    assert ShoppingItem.objects.filter(pk=owner_records["item"].pk).exists()


def test_other_user_lists_are_empty(client, intruder, owner_records):
    client.force_login(intruder)
    for name in ("core:home", "projects:list", "shopping:list", "costs:index"):
        body = client.get(reverse(name)).content
        for secret in (b"Private office", b"Zebra caulk", b"Quokka", b"Secret task"):
            assert secret not in body


def test_intruder_cannot_allocate_to_owner_project(client, intruder, owner_records):
    client.force_login(intruder)
    project = owner_records["project"]
    response = client.post(reverse("costs:purchase_create"), {
        "description": "Sneaky", "transaction_date": "2026-09-01", "total": "5.00",
        "line-0-description": "x", "line-0-amount": "5.00", "line-0-alloc-0-dest": f"project:{project.uuid}",
    })
    assert response.status_code == 200
    assert b"Unknown project" in response.content
    assert not Purchase.objects.filter(owner=intruder).exists()


def test_intruder_cannot_link_owner_shopping_item(client, intruder, owner_records):
    client.force_login(intruder)
    response = client.post(reverse("costs:purchase_create"), {
        "description": "Sneaky", "transaction_date": "2026-09-01",
        "line-0-description": "x", "line-0-amount": "5.00", "line-0-alloc-0-dest": "unallocated",
        "line-0-shopping": str(owner_records["item"].pk),
    })
    assert response.status_code == 302
    owner_records["item"].refresh_from_db()
    assert owner_records["item"].purchase_line is None


def test_anonymous_redirected_to_sign_in(client, owner_records):
    for name, key in GET_URLS:
        response = client.get(reverse(name, args=[owner_records[key].uuid]))
        assert response.status_code == 302 and "/account/sign-in/" in response["Location"]
    for name in ("core:home", "projects:list", "shopping:list", "costs:index", "receipts:new"):
        assert client.get(reverse(name)).status_code == 302


def test_private_files_have_no_public_url(owner_records, settings):
    from apps.core.storage import private_storage

    with pytest.raises(NotImplementedError):
        private_storage().url(owner_records["document"].storage_key)
    assert str(settings.PRIVATE_STORAGE_ROOT) not in [str(p) for p in settings.STATICFILES_DIRS]


def test_no_admin_or_signup(client):
    assert client.get("/admin/").status_code in (302, 404)
    assert client.get("/account/sign-up/").status_code in (302, 404)


def test_sign_in_and_out(client, owner):
    response = client.post(reverse("accounts:login"), {"username": "owner", "password": "correct-horse-battery"})
    assert response.status_code == 302
    assert client.get(reverse("core:home")).status_code == 200
    client.post(reverse("accounts:logout"))
    assert client.get(reverse("core:home")).status_code == 302


def test_csrf_enforced(owner):
    from django.test import Client

    c = Client(enforce_csrf_checks=True)
    c.force_login(owner)
    response = c.post(reverse("projects:create"), {"title": "No token", "status": "active"})
    assert response.status_code == 403


def test_healthz_is_public_and_reveals_nothing(client, owner_records):
    response = client.get("/healthz/")
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    assert b"Private office" not in response.content
