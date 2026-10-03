import uuid

from django.core.files.base import ContentFile
from django.db import transaction

from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.core.models import record_change
from apps.core.storage import private_storage
from apps.core.uploads import MIME_HEIC, normalised_jpeg
from apps.costs.models import Purchase, PurchaseEvidence
from apps.costs.services import post_purchase

from .models import ReceiptDocument, ReceiptDraft

EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/heic": "heic", "application/pdf": "pdf"}


def store_receipt(owner, validated, original_filename=""):
    """Store an uploaded receipt privately and open an empty draft. Creates no cost."""
    storage = private_storage()
    base = f"receipts/{owner.pk}/{uuid.uuid4().hex}"
    key = storage.save(f"{base}.{EXTENSIONS[validated.mime]}", ContentFile(validated.content))
    preview_key = ""
    try:
        if validated.mime == MIME_HEIC:
            preview_key = storage.save(f"{base}-preview.jpg", ContentFile(normalised_jpeg(validated.content)))
        with transaction.atomic():
            document = ReceiptDocument.objects.create(
                owner=owner, storage_key=key, preview_key=preview_key,
                original_filename=(original_filename or "")[-120:], checksum=validated.checksum,
                mime=validated.mime, size=validated.size, page_count=validated.page_count,
            )
            draft = ReceiptDraft.objects.create(owner=owner, document=document, data={})
        return document, draft
    except Exception:
        storage.delete(key)
        if preview_key:
            storage.delete(preview_key)
        raise


def duplicate_documents(document):
    """Earlier uploads with byte-identical content (a warning, never a block)."""
    return ReceiptDocument.objects.filter(owner=document.owner, checksum=document.checksum).exclude(pk=document.pk)


def save_draft(owner, draft, expected_version, data):
    with transaction.atomic():
        locked = ReceiptDraft.objects.select_for_update().get(pk=draft.pk, owner=owner)
        if expected_version is not None and int(expected_version) != locked.version:
            raise StaleObjectError()
        if not locked.is_open:
            raise BusinessRuleError("This receipt has already been handled.")
        locked.data = data
        locked.version += 1
        locked.save(update_fields=["data", "version", "updated_at"])
        return locked


def confirm_receipt(owner, draft, purchase_input, balance_choices=None):
    """Post exactly one purchase for this draft (idempotent on retries and double taps)."""
    return post_purchase(owner, purchase_input, source_draft=draft, balance_choices=balance_choices)


def attach_to_purchase(owner, draft, purchase):
    """Attach the receipt as evidence for an existing purchase. Adds no cost."""
    with transaction.atomic():
        locked = ReceiptDraft.objects.select_for_update().get(pk=draft.pk, owner=owner)
        if locked.review_status == ReceiptDraft.ReviewStatus.ATTACHED and locked.attached_purchase_id == purchase.pk:
            return locked
        if not locked.is_open:
            raise BusinessRuleError("This receipt has already been handled.")
        target = Purchase.objects.select_for_update().get(pk=purchase.pk, owner=owner)
        PurchaseEvidence.objects.get_or_create(purchase=target, document=locked.document)
        locked.review_status = ReceiptDraft.ReviewStatus.ATTACHED
        locked.attached_purchase = target
        locked.version += 1
        locked.save(update_fields=["review_status", "attached_purchase", "version", "updated_at"])
        record_change(owner, target, "evidence_attached", {}, {"document": str(locked.document.uuid)})
        return locked


def discard_draft(owner, draft):
    with transaction.atomic():
        locked = ReceiptDraft.objects.select_for_update().get(pk=draft.pk, owner=owner)
        if not locked.is_open:
            raise BusinessRuleError("This receipt has already been handled.")
        locked.review_status = ReceiptDraft.ReviewStatus.DISCARDED
        locked.version += 1
        locked.save(update_fields=["review_status", "version", "updated_at"])
        return locked
