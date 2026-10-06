import uuid

from django.core.files.base import ContentFile
from django.db import transaction

from apps.core.exceptions import BusinessRuleError, StaleObjectError, parse_version
from apps.core.models import record_change
from apps.core.storage import private_storage
from apps.core.uploads import MIME_HEIC, normalised_jpeg
from apps.costs.models import Purchase, PurchaseEvidence
from apps.costs.services import post_purchase

from .models import ReceiptDocument, ReceiptDraft

EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/heic": "heic", "application/pdf": "pdf"}


def store_receipt(owner, validated, original_filename="", context_project=None):
    """Store an uploaded receipt privately and open an empty draft. Creates no cost.

    ``context_project`` (the project the owner started from) is kept only if it belongs to the owner."""
    if context_project is not None and context_project.owner_id != owner.pk:
        context_project = None
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
            draft = ReceiptDraft.objects.create(owner=owner, document=document, data={},
                                                context_project=context_project)
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
        if not locked.is_open:
            raise BusinessRuleError("This receipt has already been handled.")
        if parse_version(expected_version) != locked.version:
            raise StaleObjectError()
        # Keep extraction metadata (currency, flags) when the owner saves their edits.
        if "extraction" in (locked.data or {}) and "extraction" not in data:
            # The values are now the owner's: keep currency/flags, but the reading's
            # reconciliation no longer describes them.
            extraction = {**locked.data["extraction"], "edited_by_owner": True, "reconciled": False}
            data = {**data, "extraction": extraction}
        locked.data = data
        locked.version += 1
        locked.save(update_fields=["data", "version", "updated_at"])
        return locked


def confirm_receipt(owner, draft, purchase_input, expected_version, balance_choices=None):
    """Post exactly one purchase for this draft (idempotent on retries and double taps).

    The draft version is checked under the draft row lock inside the posting transaction.
    """
    return post_purchase(owner, purchase_input, source_draft=draft, balance_choices=balance_choices,
                         draft_version=expected_version)


def attach_to_purchase(owner, draft, purchase, expected_version):
    """Attach the receipt as evidence for an existing purchase. Adds no cost."""
    with transaction.atomic():
        locked = ReceiptDraft.objects.select_for_update().get(pk=draft.pk, owner=owner)
        if locked.review_status == ReceiptDraft.ReviewStatus.ATTACHED and locked.attached_purchase_id == purchase.pk:
            return locked
        if not locked.is_open:
            raise BusinessRuleError("This receipt has already been handled.")
        if parse_version(expected_version) != locked.version:
            raise StaleObjectError()
        target = Purchase.objects.select_for_update().get(pk=purchase.pk, owner=owner)
        PurchaseEvidence.objects.get_or_create(purchase=target, document=locked.document)
        locked.review_status = ReceiptDraft.ReviewStatus.ATTACHED
        locked.attached_purchase = target
        locked.version += 1
        locked.save(update_fields=["review_status", "attached_purchase", "version", "updated_at"])
        record_change(owner, target, "evidence_attached", {}, {"document": str(locked.document.uuid)})
        return locked


def discard_draft(owner, draft, expected_version):
    with transaction.atomic():
        locked = ReceiptDraft.objects.select_for_update().get(pk=draft.pk, owner=owner)
        if not locked.is_open:
            raise BusinessRuleError("This receipt has already been handled.")
        if parse_version(expected_version) != locked.version:
            raise StaleObjectError()
        locked.review_status = ReceiptDraft.ReviewStatus.DISCARDED
        locked.version += 1
        locked.save(update_fields=["review_status", "version", "updated_at"])
        return locked


def _merchant_key(value):
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def find_similar_purchases(owner, purchase_input, document=None, window_days=3):
    """Possible duplicates: a warning, never proof. Owner-scoped, confirmed purchases only.

    Returns a list of (purchase, reason) pairs.
    """
    import datetime

    results = {}
    if document is not None:
        for evidence in PurchaseEvidence.objects.filter(
            document__owner=owner, document__checksum=document.checksum, purchase__status=Purchase.Status.CONFIRMED
        ).exclude(document=document).select_related("purchase"):
            results[evidence.purchase.pk] = (evidence.purchase, "The same receipt file is already attached to this purchase.")
    if purchase_input is not None and purchase_input.transaction_date and purchase_input.total is not None:
        delta = datetime.timedelta(days=window_days)
        key = _merchant_key(purchase_input.merchant)
        for purchase in Purchase.objects.filter(
            owner=owner, kind=Purchase.Kind.PURCHASE, status=Purchase.Status.CONFIRMED, total=purchase_input.total,
            transaction_date__range=(purchase_input.transaction_date - delta, purchase_input.transaction_date + delta),
        ):
            other = _merchant_key(purchase.merchant)
            if not key or not other or key in other or other in key:
                results.setdefault(purchase.pk, (purchase, "Same total, a similar date and merchant."))
    return sorted(results.values(), key=lambda pair: pair[0].transaction_date, reverse=True)
