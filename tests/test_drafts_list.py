"""Costs → Receipts to review: rows show merchant, draft total and reading state (assessment gap 5).

Display only: draft values never enter recorded costs."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.costs.selectors import overall_summary
from apps.receipts import jobs
from apps.receipts.extraction import ExtractionError, FakeExtractor
from apps.receipts.models import ReceiptDraft

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fake_extractor(settings):
    settings.RECEIPT_EXTRACTOR = "fake"


def new_draft(client, name="IMG_0042.jpg"):
    client.post(reverse("receipts:new"), {"receipt": upload(name, image_bytes())})
    return ReceiptDraft.objects.order_by("-pk").first()


def drafts_section(client):
    page = client.get(reverse("costs:index")).content.decode()
    return page.split('id="drafts"')[1].split("</section>")[0]


def test_untouched_draft_falls_back_to_file_name(client_owner):
    new_draft(client_owner)
    section = drafts_section(client_owner)
    assert "Receipt" in section and "IMG_0042.jpg" in section and ">Draft<" in section
    assert "Draft · not counted" in section


def test_saved_values_show_merchant_and_draft_total_but_never_count(client_owner, owner):
    draft = new_draft(client_owner)
    draft.data = {"merchant": "Timber Yard", "total": "31.17"}
    draft.save()
    section = drafts_section(client_owner)
    assert "Timber Yard · £31.17" in section and "draft total, not counted" in section
    assert "IMG_0042.jpg" not in section  # the merchant identifies it now
    assert overall_summary(owner).total == Decimal("0.00")


@pytest.mark.parametrize("total", ["abc", "1.234", "   "])
def test_unfinished_total_is_not_shown(client_owner, total):
    draft = new_draft(client_owner)
    draft.data = {"merchant": "Timber Yard", "total": total}
    draft.save()
    section = drafts_section(client_owner)
    assert "Timber Yard" in section and "£" not in section


def test_reading_states(client_owner, owner):
    waiting = new_draft(client_owner, "a.jpg")
    jobs.request_reading(owner, waiting, waiting.version)
    assert "Waiting to read" in drafts_section(client_owner)
    jobs.process_available()  # fake extractor: SAMPLE_RESULT applied to the untouched draft
    section = drafts_section(client_owner)
    assert "Read · check" in section and "Sample Hardware Co · £31.17" in section
    failed = new_draft(client_owner, "b.jpg")
    FakeExtractor.queue.append(ExtractionError("rejected", "Nope."))
    jobs.request_reading(owner, failed, failed.version)
    jobs.process_available()
    assert "Couldn’t read" in drafts_section(client_owner)
    assert overall_summary(owner).total == Decimal("0.00")


def test_only_the_owners_drafts_are_listed(client_owner, intruder):
    from django.test import Client

    other = Client()
    other.force_login(intruder)
    theirs = new_draft(other, "theirs.jpg")
    theirs.data = {"merchant": "Their Shop", "total": "9.99"}
    theirs.save()
    new_draft(client_owner, "mine.jpg")
    section = drafts_section(client_owner)
    assert "mine.jpg" in section and "Their Shop" not in section and "theirs.jpg" not in section
