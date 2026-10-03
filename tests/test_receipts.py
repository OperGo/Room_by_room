import io
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.costs.models import Purchase, PurchaseEvidence
from apps.costs.selectors import overall_summary
from apps.receipts.models import ReceiptDocument, ReceiptDraft

from .conftest import image_bytes, pdf_bytes, upload

pytestmark = pytest.mark.django_db


def post_receipt(client, name, content):
    return client.post(reverse("receipts:new"), {"receipt": upload(name, content)})


@pytest.mark.parametrize("name,content_fn,mime", [
    ("r.jpg", lambda: image_bytes("JPEG"), "image/jpeg"),
    ("r.png", lambda: image_bytes("PNG"), "image/png"),
    ("r.pdf", lambda: pdf_bytes(2), "application/pdf"),
    ("IMG_0001.HEIC", lambda: image_bytes("HEIF"), "image/heic"),
])
def test_upload_supported_formats_creates_draft_only(client_owner, owner, name, content_fn, mime):
    response = post_receipt(client_owner, name, content_fn())
    assert response.status_code == 302
    document = ReceiptDocument.objects.get(owner=owner)
    assert document.mime == mime
    assert ReceiptDraft.objects.get(document=document).review_status == "draft"
    assert Purchase.objects.count() == 0
    assert overall_summary(owner).total == Decimal("0.00")
    review = client_owner.get(response["Location"])
    assert b"Draft" in review.content and b"not available yet" in review.content


def test_heic_gets_browser_preview(client_owner, owner):
    post_receipt(client_owner, "IMG.HEIC", image_bytes("HEIF"))
    document = ReceiptDocument.objects.get()
    assert document.preview_key.endswith(".jpg")
    preview = client_owner.get(reverse("receipts:file", args=[document.uuid]) + "?preview=1")
    assert preview["Content-Type"] == "image/jpeg"


def test_extension_is_not_trusted(client_owner, owner):
    response = post_receipt(client_owner, "receipt.pdf", b"MZ\x90\x00 not a pdf")
    assert b"Upload a JPEG, PNG, HEIC photo or a PDF receipt" in response.content
    response = post_receipt(client_owner, "receipt.jpg", b"%PDF-1.4 broken")
    assert b"could not be read" in response.content
    assert not ReceiptDocument.objects.exists()


def test_oversized_file_rejected(client_owner, settings):
    settings.UPLOAD_MAX_BYTES = 1000
    response = post_receipt(client_owner, "big.png", image_bytes("PNG", size=(400, 400), color="red") + b"\0" * 2000)
    assert b"larger than" in response.content
    assert not ReceiptDocument.objects.exists()


def test_password_protected_pdf_rejected(client_owner):
    response = post_receipt(client_owner, "locked.pdf", pdf_bytes(1, password="secret"))
    assert b"password-protected" in response.content


def test_pdf_page_limit(client_owner):
    response = post_receipt(client_owner, "long.pdf", pdf_bytes(6))
    assert b"at most 5 pages" in response.content


def test_decompression_bomb_rejected(client_owner, settings):
    import apps.core.uploads as uploads
    from PIL import Image

    settings.IMAGE_MAX_PIXELS = 1000
    old = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 1000
    try:
        response = post_receipt(client_owner, "huge.png", image_bytes("PNG", size=(200, 200)))
    finally:
        Image.MAX_IMAGE_PIXELS = old
    assert b"too large to process safely" in response.content
    assert uploads


def test_file_download_is_private_and_safe(client_owner, owner):
    post_receipt(client_owner, "r.pdf", pdf_bytes(1))
    document = ReceiptDocument.objects.get()
    response = client_owner.get(reverse("receipts:file", args=[document.uuid]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in response["Cache-Control"]
    download = client_owner.get(reverse("receipts:file", args=[document.uuid]) + "?download=1")
    assert download["Content-Disposition"].startswith("attachment")


def test_duplicate_checksum_warns(client_owner, owner):
    content = image_bytes("JPEG", color="blue")
    post_receipt(client_owner, "a.jpg", content)
    response = post_receipt(client_owner, "b.jpg", content)
    review = client_owner.get(response["Location"])
    assert b"This exact file was uploaded before" in review.content
    assert ReceiptDocument.objects.count() == 2  # warning, not a block


def confirm_payload(project, total="76.50", version=1):
    return {
        "version": str(version),
        "description": "Timber merchant", "merchant": "Timber Co", "transaction_date": "2026-09-12", "total": total,
        "line-0-description": "MDF", "line-0-amount": "32.00", "line-0-alloc-0-dest": f"project:{project.uuid}",
        "line-1-description": "Primer", "line-1-amount": "35.00", "line-1-alloc-0-dest": f"project:{project.uuid}",
        "line-2-description": "Filler", "line-2-amount": "9.50", "line-2-alloc-0-dest": "unallocated",
    }


def test_confirm_draft_posts_exactly_one_purchase(client_owner, owner, office):
    response = post_receipt(client_owner, "r.jpg", image_bytes())
    draft = ReceiptDraft.objects.get()
    confirm_url = reverse("receipts:confirm", args=[draft.uuid])
    first = client_owner.post(confirm_url, confirm_payload(office))
    second = client_owner.post(confirm_url, confirm_payload(office))  # double tap / refresh
    assert first.status_code == second.status_code == 302
    assert first["Location"] == second["Location"]
    assert Purchase.objects.count() == 1
    purchase = Purchase.objects.get()
    assert purchase.source_draft == draft
    assert PurchaseEvidence.objects.filter(purchase=purchase, document=draft.document).exists()
    draft.refresh_from_db()
    assert draft.review_status == "confirmed"
    assert overall_summary(owner).total == Decimal("76.50")
    # Reopening the review sends you to the purchase.
    assert client_owner.get(reverse("receipts:review", args=[draft.uuid])).status_code == 302
    assert response


def test_unreconciled_draft_is_not_posted(client_owner, owner, office):
    post_receipt(client_owner, "r.jpg", image_bytes())
    draft = ReceiptDraft.objects.get()
    response = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), confirm_payload(office, total="80.00"))
    assert response.status_code == 200
    assert b"Nothing was recorded" in response.content and b"Items add up to" in response.content
    assert Purchase.objects.count() == 0


def test_save_draft_keeps_values_without_cost(client_owner, owner, office):
    post_receipt(client_owner, "r.jpg", image_bytes())
    draft = ReceiptDraft.objects.get()
    payload = confirm_payload(office, total="99.99")
    payload["version"] = draft.version
    client_owner.post(reverse("receipts:save", args=[draft.uuid]), payload)
    draft.refresh_from_db()
    assert draft.data["merchant"] == "Timber Co" and len(draft.data["lines"]) == 3
    assert overall_summary(owner).total == Decimal("0.00")
    review = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert 'value="Timber Co"' in review and 'value="99.99"' in review
    # Stale save is refused.
    stale = client_owner.post(reverse("receipts:save", args=[draft.uuid]), payload, follow=True)
    assert b"changed since you opened it" in stale.content


def test_attach_to_existing_purchase_adds_no_cost(client_owner, owner, office):
    from apps.costs.services import post_purchase

    from .conftest import line, purchase_input, to

    purchase = post_purchase(owner, purchase_input([line("MDF", "32.00", [to(office, "32.00")])]))
    post_receipt(client_owner, "r.jpg", image_bytes())
    draft = ReceiptDraft.objects.get()
    client_owner.post(reverse("receipts:attach", args=[draft.uuid]), {"purchase": str(purchase.uuid), "version": "1"})
    client_owner.post(reverse("receipts:attach", args=[draft.uuid]), {"purchase": str(purchase.uuid), "version": "1"})
    assert Purchase.objects.count() == 1
    assert overall_summary(owner).total == Decimal("32.00")
    assert PurchaseEvidence.objects.filter(purchase=purchase).count() == 1
    draft.refresh_from_db()
    assert draft.review_status == "attached"
    # Cannot then also confirm it as a new purchase.
    client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), confirm_payload(office))
    assert Purchase.objects.count() == 1


def test_attach_rejects_garbage_and_foreign_purchase(client_owner, owner, intruder):
    from apps.costs.services import post_purchase
    from apps.projects.models import Project

    from .conftest import line, purchase_input, to

    theirs = Project.objects.create(owner=intruder, title="Theirs")
    foreign = post_purchase(intruder, purchase_input([line("X", "1.00", [to(theirs, "1.00")])]))
    post_receipt(client_owner, "r.jpg", image_bytes())
    draft = ReceiptDraft.objects.get(owner=owner)
    client_owner.post(reverse("receipts:attach", args=[draft.uuid]), {"purchase": "not-a-uuid"})
    client_owner.post(reverse("receipts:attach", args=[draft.uuid]), {"purchase": str(foreign.uuid)})
    draft.refresh_from_db()
    assert draft.review_status == "draft"
    assert not PurchaseEvidence.objects.exists()


def test_discard_draft(client_owner, owner):
    post_receipt(client_owner, "r.jpg", image_bytes())
    draft = ReceiptDraft.objects.get()
    client_owner.post(reverse("receipts:discard", args=[draft.uuid]), {"version": "1"})
    draft.refresh_from_db()
    assert draft.review_status == "discarded"
    assert ReceiptDocument.objects.count() == 1


def test_drafts_listed_separately_and_not_counted(client_owner, owner):
    post_receipt(client_owner, "r.jpg", image_bytes())
    body = client_owner.get(reverse("costs:index")).content
    assert b"Receipts to review" in body and b"Draft" in body
    assert overall_summary(owner).total == Decimal("0.00")


def test_extraction_not_configured_message(client_owner, settings):
    settings.RECEIPT_EXTRACTION_ENABLED = True
    settings.ANTHROPIC_API_KEY = ""
    body = client_owner.get(reverse("receipts:new")).content
    assert b"Automatic extraction not configured" in body


def test_receipt_page_offers_camera_upload_and_manual(client_owner):
    body = client_owner.get(reverse("receipts:new")).content.decode()
    assert 'capture="environment"' in body
    assert 'accept="application/pdf"' in body
    assert reverse("costs:purchase_create") in body


# ------------------------------------------------------------------ Sprint 1A: stale draft regression


def _draft(client_owner):
    post_receipt(client_owner, "r.jpg", image_bytes())
    return ReceiptDraft.objects.get()


def test_stale_confirm_after_save_elsewhere_creates_no_cost(client_owner, owner, office):
    draft = _draft(client_owner)
    assert draft.version == 1
    # Another tab saves the draft (version 1 -> 2).
    saved = confirm_payload(office, total="76.50", version=1)
    client_owner.post(reverse("receipts:save", args=[draft.uuid]), saved)
    draft.refresh_from_db()
    assert draft.version == 2
    # The first tab now confirms with version 1.
    payload = confirm_payload(office, version=1)
    payload["merchant"] = "Typed in the stale tab"
    response = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), payload)
    assert response.status_code == 409
    assert b"changed elsewhere since you opened it" in response.content
    assert b'value="Typed in the stale tab"' in response.content  # entries retained
    assert b'name="version" value="2"' in response.content
    assert Purchase.objects.count() == 0
    assert overall_summary(owner).total == Decimal("0.00")
    # A deliberate confirm with the current version then works exactly once.
    ok = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), confirm_payload(office, version=2))
    again = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), confirm_payload(office, version=2))
    stale_retry = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), confirm_payload(office, version=1))
    assert ok.status_code == again.status_code == stale_retry.status_code == 302
    assert ok["Location"] == again["Location"] == stale_retry["Location"]
    assert Purchase.objects.count() == 1


@pytest.mark.parametrize("version", [None, "", "abc", "0", "-1", "1.5"])
def test_confirm_with_missing_or_malformed_version_fails_cleanly(client_owner, owner, office, version):
    draft = _draft(client_owner)
    payload = confirm_payload(office)
    if version is None:
        payload.pop("version")
    else:
        payload["version"] = version
    response = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), payload)
    assert response.status_code == 409
    assert b"Nothing was recorded" in response.content
    assert Purchase.objects.count() == 0


def test_confirm_service_checks_version_under_lock(owner, office):
    from apps.core.exceptions import StaleObjectError
    from apps.receipts.models import ReceiptDocument
    from apps.receipts.services import confirm_receipt

    from .conftest import line, purchase_input, to

    document = ReceiptDocument.objects.create(owner=owner, storage_key="k", checksum="c", mime="image/jpeg", size=1)
    draft = ReceiptDraft.objects.create(owner=owner, document=document)
    ReceiptDraft.objects.filter(pk=draft.pk).update(version=3)
    data = purchase_input([line("MDF", "32.00", [to(office, "32.00")])])
    with pytest.raises(StaleObjectError):
        confirm_receipt(owner, draft, data, 2)
    assert Purchase.objects.count() == 0
    first = confirm_receipt(owner, draft, data, 3)
    assert confirm_receipt(owner, draft, data, 1).pk == first.pk  # already confirmed: idempotent


@pytest.mark.parametrize("action", ["save", "attach", "discard"])
def test_stale_save_attach_discard_are_refused(client_owner, owner, office, action):
    from apps.costs.services import post_purchase

    from .conftest import line, purchase_input, to

    purchase = post_purchase(owner, purchase_input([line("MDF", "32.00", [to(office, "32.00")])]))
    draft = _draft(client_owner)
    ReceiptDraft.objects.filter(pk=draft.pk).update(version=2)
    data = {"version": "1", "purchase": str(purchase.uuid), **confirm_payload(office, version=1)}
    response = client_owner.post(reverse(f"receipts:{action}", args=[draft.uuid]), data, follow=True)
    assert b"changed since you opened it" in response.content
    draft.refresh_from_db()
    assert draft.review_status == "draft" and draft.version == 2
    assert not PurchaseEvidence.objects.exists()
    malformed = client_owner.post(reverse(f"receipts:{action}", args=[draft.uuid]), {**data, "version": "x"}, follow=True)
    assert b"missing its version" in malformed.content
    draft.refresh_from_db()
    assert draft.review_status == "draft"
