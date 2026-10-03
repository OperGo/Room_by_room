import uuid as uuid_lib

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.dates import local_today
from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.core.shortcuts import flash_errors, owned
from apps.core.storage import private_storage
from apps.core.uploads import validate_receipt
from apps.costs.forms import PurchaseEditor
from apps.costs.models import Purchase
from apps.costs.views import _editor_context, _needs_choices, _overlaps_for

from . import jobs, services
from .extraction import extraction_status
from .models import ExtractionJob, ReceiptDocument, ReceiptDraft


class ReceiptUploadForm(forms.Form):
    receipt = forms.FileField()


def receipt_new(request):
    form = ReceiptUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            upload = form.cleaned_data["receipt"]
            try:
                validated = validate_receipt(upload)
            except ValidationError as exc:
                form.add_error("receipt", exc)
            else:
                document, draft = services.store_receipt(request.user, validated, upload.name)
                messages.success(request, "Receipt saved privately. Review it to record the purchase.")
                return redirect("receipts:review", uuid=draft.uuid)
        else:
            form.errors.clear()
            form.add_error("receipt", "Choose a photo or PDF of the receipt.")
    available, message, provider_note = extraction_status()
    return render(request, "receipts/new.html", {"form": form, "extraction_available": available,
                                                 "extraction_message": message, "provider_note": provider_note})


def _draft_initial(draft):
    data = draft.data or {}
    initial = {k: data.get(k, "") for k in ("description", "merchant", "transaction_date", "total", "notes")}
    initial["lines"] = data.get("lines") or None
    if not initial["transaction_date"]:
        initial["transaction_date"] = ""
    return initial


def _review_context(request, draft, editor, **extra):
    available, message, provider_note = extraction_status()
    job = jobs.latest_job(draft)
    recent = Purchase.objects.for_owner(request.user).filter(
        kind=Purchase.Kind.PURCHASE, status=Purchase.Status.CONFIRMED
    ).order_by("-transaction_date", "-created_at")[:30]
    context = _editor_context(
        request, editor, draft=draft, document=draft.document,
        duplicates=services.duplicate_documents(draft.document).select_related("draft")[:5],
        extraction_available=available, extraction_message=message, provider_note=provider_note,
        recent_purchases=recent, version=draft.version,
        job=job, job_state=jobs.job_state(job), extraction=(draft.data or {}).get("extraction") or {},
    )
    context.update(extra)
    return context


def receipt_review(request, uuid):
    draft = owned(ReceiptDraft, request.user, uuid=uuid)
    if draft.review_status == ReceiptDraft.ReviewStatus.CONFIRMED and hasattr(draft, "posted_purchase"):
        messages.info(request, "This receipt has already been confirmed.")
        return redirect("costs:purchase_detail", uuid=draft.posted_purchase.uuid)
    if draft.review_status == ReceiptDraft.ReviewStatus.ATTACHED and draft.attached_purchase_id:
        messages.info(request, "This receipt is attached to an existing purchase.")
        return redirect("costs:purchase_detail", uuid=draft.attached_purchase.uuid)
    editor = PurchaseEditor(request.user, initial=_draft_initial(draft))
    return render(request, "receipts/review.html", _review_context(request, draft, editor))


def _editor_snapshot(editor):
    return {**editor.header, "lines": editor.lines}


@require_POST
def receipt_save(request, uuid):
    draft = owned(ReceiptDraft, request.user, uuid=uuid)
    editor = PurchaseEditor(request.user, request.POST)
    editor.is_valid()  # parse for redisplay; drafts may be incomplete
    try:
        services.save_draft(request.user, draft, request.POST.get("version"), _editor_snapshot(editor))
    except (BusinessRuleError, StaleObjectError) as exc:
        flash_errors(request, exc)
    else:
        messages.success(request, "Draft saved. It does not count towards any totals until you confirm it.")
    return redirect("receipts:review", uuid=uuid)


@require_POST
def receipt_confirm(request, uuid):
    owner = request.user
    draft = owned(ReceiptDraft, owner, uuid=uuid)
    existing = Purchase.objects.filter(source_draft=draft).first()
    if existing:  # double tap / refresh: never post twice
        return redirect("costs:purchase_detail", uuid=existing.uuid)
    editor = PurchaseEditor(owner, request.POST)
    if not editor.is_valid():
        return render(request, "receipts/review.html", _review_context(request, draft, editor))
    overlaps = _overlaps_for(request, editor)
    if overlaps and _needs_choices(overlaps):
        return render(request, "receipts/review.html", _review_context(request, draft, editor, overlaps=overlaps))
    extraction = (draft.data or {}).get("extraction") or {}
    if extraction.get("gbp_confirmation_required") and request.POST.get("gbp_confirmed") != "1":
        editor.errors = ["Confirm that every amount you entered is in pounds sterling (GBP)."]
        return render(request, "receipts/review.html", _review_context(request, draft, editor, overlaps=overlaps))
    similar = services.find_similar_purchases(owner, editor.purchase_input, draft.document)
    acknowledged = set(request.POST.getlist("ack_duplicate"))
    if any(str(p.uuid) not in acknowledged for p, _ in similar):
        editor.errors = ["This may duplicate a purchase you already recorded. Check the list below, then either "
                         "attach the receipt to that purchase or confirm it is a separate purchase."]
        return render(request, "receipts/review.html", _review_context(
            request, draft, editor, overlaps=overlaps, similar_purchases=similar, acknowledged=acknowledged))
    try:
        purchase = services.confirm_receipt(owner, draft, editor.purchase_input, request.POST.get("version"),
                                            editor.balance_choices)
    except (BusinessRuleError, StaleObjectError) as exc:
        editor.errors = exc.messages
        draft.refresh_from_db()
        context = _review_context(request, draft, editor, overlaps=overlaps)
        if isinstance(exc, StaleObjectError):
            # Keep the user's entries; the refreshed version lets them confirm deliberately.
            context["stale"] = True
        return render(request, "receipts/review.html", context, status=409 if isinstance(exc, StaleObjectError) else 200)
    messages.success(request, "Receipt confirmed and purchase recorded.")
    return redirect("costs:purchase_detail", uuid=purchase.uuid)


@require_POST
def receipt_attach(request, uuid):
    draft = owned(ReceiptDraft, request.user, uuid=uuid)
    try:
        purchase_uuid = uuid_lib.UUID(request.POST.get("purchase", ""))
    except ValueError:
        purchase_uuid = None
    purchase = Purchase.objects.for_owner(request.user).filter(uuid=purchase_uuid).first() if purchase_uuid else None
    if purchase is None:
        messages.error(request, "Choose the purchase this receipt belongs to.")
        return redirect("receipts:review", uuid=uuid)
    try:
        services.attach_to_purchase(request.user, draft, purchase, request.POST.get("version"))
    except (BusinessRuleError, StaleObjectError) as exc:
        flash_errors(request, exc)
        return redirect("receipts:review", uuid=uuid)
    messages.success(request, "Receipt attached as evidence. No new cost was recorded.")
    return redirect("costs:purchase_detail", uuid=purchase.uuid)


@require_POST
def receipt_discard(request, uuid):
    draft = owned(ReceiptDraft, request.user, uuid=uuid)
    try:
        services.discard_draft(request.user, draft, request.POST.get("version"))
    except (BusinessRuleError, StaleObjectError) as exc:
        flash_errors(request, exc)
        return redirect("receipts:review", uuid=uuid)
    if request.GET.get("retake"):
        messages.info(request, "Previous photo discarded. Nothing was recorded.")
        return redirect("receipts:new")
    messages.success(request, "Draft discarded. The file is kept privately with no cost recorded.")
    return redirect("costs:index")


def receipt_file(request, uuid):
    document = owned(ReceiptDocument, request.user, uuid=uuid)
    storage = private_storage()
    key, mime = document.storage_key, document.mime
    if request.GET.get("preview") and document.preview_key:
        key, mime = document.preview_key, "image/jpeg"
    if not storage.exists(key):
        raise Http404
    download = request.GET.get("download") == "1"
    ext = key.rsplit(".", 1)[-1]
    response = FileResponse(storage.open(key, "rb"), content_type=mime, as_attachment=download,
                            filename=f"receipt-{document.uuid}.{ext}")
    if not download:
        response["Content-Disposition"] = "inline"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
def receipt_read(request, uuid):
    """Explicit user action: queue this receipt for automatic reading."""
    draft = owned(ReceiptDraft, request.user, uuid=uuid)
    try:
        jobs.request_reading(request.user, draft, request.POST.get("version"))
    except (BusinessRuleError, StaleObjectError) as exc:
        flash_errors(request, exc)
    else:
        messages.info(request, "Reading queued. You can keep editing; nothing is recorded until you confirm.")
    return redirect("receipts:review", uuid=uuid)


def receipt_reading_status(request, uuid):
    """Polling endpoint: job status only. It never returns or changes form values."""
    draft = owned(ReceiptDraft, request.user, uuid=uuid)
    state = jobs.job_state(jobs.latest_job(draft))
    state["draft_version"] = draft.version
    response = JsonResponse(state)
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def receipt_apply_reading(request, uuid):
    """Explicitly replace the draft's current values with a held (late) reading."""
    draft = owned(ReceiptDraft, request.user, uuid=uuid)
    job_id = request.POST.get("job", "")
    job = ExtractionJob.objects.for_owner(request.user).filter(draft=draft, pk=int(job_id)).first() \
        if job_id.isdigit() else None
    if job is None:
        raise Http404
    try:
        jobs.apply_held_result(request.user, job, request.POST.get("version"))
    except (BusinessRuleError, StaleObjectError) as exc:
        flash_errors(request, exc)
    else:
        messages.success(request, "The reading replaced the draft values. Check every value before confirming.")
    return redirect("receipts:review", uuid=uuid)
