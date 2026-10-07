"""Reading status polling: the contract the connection feedback relies on (CTO plan, 7 October)."""
import pytest
from django.urls import reverse

from apps.costs.models import Purchase
from apps.receipts import jobs
from apps.receipts.models import ExtractionJob, ReceiptDraft

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fake_extractor(settings):
    settings.RECEIPT_EXTRACTOR = "fake"


def queued_draft(client, owner):
    client.post(reverse("receipts:new"), {"receipt": upload("r.jpg", image_bytes())})
    draft = ReceiptDraft.objects.latest("pk")
    jobs.request_reading(owner, draft, draft.version)
    return draft


def test_waiting_panel_has_an_empty_connection_line(client_owner, owner):
    draft = queued_draft(client_owner, owner)
    html = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert '<p class="small reading-connection" data-reading-connection></p>' in html
    assert 'data-status="queued" aria-live="polite"' in html


def test_completed_panel_has_no_connection_line(client_owner, owner):
    draft = queued_draft(client_owner, owner)
    jobs.process_available()
    html = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "data-reading-connection" not in html and "Synthetic test reading" in html


def test_status_polling_is_json_and_changes_nothing(client_owner, owner):
    draft = queued_draft(client_owner, owner)
    version = ReceiptDraft.objects.get(pk=draft.pk).version
    url = reverse("receipts:reading_status", args=[draft.uuid])
    for _ in range(5):  # repeated retries after a connection problem
        response = client_owner.get(url)
        assert response.status_code == 200 and response["Content-Type"].startswith("application/json")
        assert response["Cache-Control"] == "no-store"
    assert response.json()["status"] == "queued"
    assert ExtractionJob.objects.filter(draft=draft).count() == 1  # no extra reading queued
    assert ReceiptDraft.objects.get(pk=draft.pk).version == version and Purchase.objects.count() == 0


def test_signed_out_polling_is_not_json(client_owner, owner):
    """A sign-in redirect is treated as "can't check", never as a reading result."""
    draft = queued_draft(client_owner, owner)
    client_owner.logout()
    response = client_owner.get(reverse("receipts:reading_status", args=[draft.uuid]))
    assert response.status_code == 302 and "/account/sign-in/" in response["Location"]


def test_status_polling_is_owner_scoped(client, owner, intruder, client_owner):
    draft = queued_draft(client_owner, owner)
    client.force_login(intruder)
    assert client.get(reverse("receipts:reading_status", args=[draft.uuid])).status_code == 404
