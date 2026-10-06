import uuid as uuid_lib

from django.contrib import messages
from django.http import Http404
from django.db.models import OuterRef, Subquery
from django.shortcuts import redirect, render

from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.core.models import ChangeEvent
from apps.core.money import ZERO, to_money
from apps.core.shortcuts import parse_uuid, owned
from apps.projects.models import Project
from apps.receipts.models import ExtractionJob, ReceiptDraft
from apps.shopping.models import ShoppingItem

from . import selectors, services
from .forms import CostFilterForm, PurchaseEditor, ReasonForm, RefundForm, destination_options, owned_project_key
from .models import CostAllocation, OpeningBalanceDecision, Purchase


def cost_index(request):
    owner = request.user
    form = CostFilterForm(owner, request.GET or None)
    filters = {}
    if form.is_valid():
        d = form.cleaned_data
        if d["project"]:
            filters["project"] = Project.objects.for_owner(owner).filter(uuid=parse_uuid(d["project"])).first()
        filters["merchant"] = d["merchant"]
        filters["date_from"] = d["date_from"]
        filters["date_to"] = d["date_to"]
    filters = {k: v for k, v in filters.items() if v}
    summary = selectors.overall_summary(owner, **filters)
    purchases = list(selectors.filtered_purchases(owner, **filters).order_by("-transaction_date", "-created_at")[:200])
    projects = list(Project.objects.for_owner(owner).exclude(status=Project.Status.ARCHIVED).order_by("title"))
    nets = selectors.project_net_costs(owner, projects)
    project_rows = []
    for project in projects:
        net = nets[project.pk]
        project_rows.append({
            "project": project, "net": net,
            "remaining": project.budget - net if project.budget is not None else None,
        })
    latest_job = ExtractionJob.objects.filter(draft=OuterRef("pk")).order_by("-created_at", "-id")
    drafts = [_draft_row(d) for d in (
        ReceiptDraft.objects.for_owner(owner).filter(review_status=ReceiptDraft.ReviewStatus.DRAFT)
        .select_related("document").order_by("-created_at")
        .annotate(job_status=Subquery(latest_job.values("status")[:1]))
    )]
    return render(request, "costs/index.html", {
        "form": form, "summary": summary, "purchases": purchases, "drafts": drafts,
        "project_rows": project_rows, "filtered": bool(filters),
        "filter_project": filters.get("project"),
    })


def _editor_context(request, editor, **extra):
    include = [p for p in Project.objects.for_owner(request.user).filter(status=Project.Status.ARCHIVED).values_list("pk", flat=True)]
    context = {
        "editor": editor,
        "destinations": destination_options(request.user, include_ids=include),
        "line_types": [c for c in services.PurchaseLine.LineType.choices if c[0] != "refund"],
        "categories": services.PurchaseLine.Category.choices,
        "overlaps": [],
    }
    context.update(extra)
    return context


def _overlaps_for(request, editor, correcting=None):
    if editor.purchase_input is None:
        return []
    overlaps = services.find_overlaps(request.user, editor.purchase_input, correcting=correcting)
    for overlap in overlaps:
        overlap.choice = editor.raw_choice(overlap.balance.uuid)
    return overlaps


def _needs_choices(overlaps):
    return any(getattr(o, "choice", None) is None or o.choice.decision not in OpeningBalanceDecision.Decision.values
               for o in overlaps)


DRAFT_STATES = {  # latest reading job status -> (label, badge style); display only
    ExtractionJob.Status.QUEUED: ("Waiting to read", "badge-outline"),
    ExtractionJob.Status.PROCESSING: ("Reading", "badge-outline"),
    ExtractionJob.Status.SUCCEEDED: ("Read · check", "badge-warning"),
    ExtractionJob.Status.FAILED: ("Couldn’t read", "badge-error"),
}


def _draft_row(draft):
    """Display values for a receipt draft row. Draft values are shown, never counted: totals come only
    from confirmed records (selectors)."""
    data = draft.data or {}
    total = None
    try:
        total = to_money(str(data.get("total") or "")) if data.get("total") else None
    except ValueError:
        total = None  # the owner may have saved an unfinished value; show nothing rather than a guess
    label, style = DRAFT_STATES.get(draft.job_status, ("Draft", "badge-draft"))
    return {"draft": draft, "merchant": (data.get("merchant") or "").strip(), "total": total,
            "state": label, "state_style": style}


def purchase_create(request):
    owner = request.user
    bulk = {"assign_action": request.get_full_path(),
            "bulk_default": request.POST.get("bulk_dest") or owned_project_key(owner, request.GET.get("project"))}
    shopping_item = None
    if request.GET.get("shopping"):
        shopping_item = ShoppingItem.objects.for_owner(owner).filter(uuid=parse_uuid(request.GET["shopping"])).select_related(
            "purchase_line__purchase", "project").first()
        if shopping_item and shopping_item.purchase_line_id:
            messages.info(request, "That item is already linked to this purchase, so another one was not created.")
            return redirect("costs:purchase_detail", uuid=shopping_item.purchase_line.purchase.uuid)
    if request.method == "POST":
        editor = PurchaseEditor(owner, request.POST)
        submission_key = _submission_key(request)
        if request.POST.get("assign_unassigned"):
            # Without JavaScript: fill unassigned items and show the form again. Nothing is recorded.
            editor.is_valid()
            editor.errors = []
            try:
                count = editor.assign_unassigned(request.POST.get("bulk_dest", ""))
                messages.info(request, f"Assigned {count} item{'' if count == 1 else 's'}. Nothing is recorded "
                                       "until you choose Record purchase.")
            except ValueError:
                editor.errors = ["Choose a project to assign the unassigned items to."]
            return render(request, "costs/purchase_form.html", _editor_context(
                request, editor, overlaps=[], submission_key=submission_key, creating=True,
                **bulk))
        if editor.is_valid():
            overlaps = _overlaps_for(request, editor)
            if overlaps and _needs_choices(overlaps):
                return render(request, "costs/purchase_form.html", _editor_context(
                    request, editor, overlaps=overlaps, submission_key=submission_key, creating=True, **bulk))
            try:
                purchase = services.post_purchase(owner, editor.purchase_input, submission_key=submission_key,
                                                  balance_choices=editor.balance_choices)
            except BusinessRuleError as exc:
                editor.errors = exc.messages
                return render(request, "costs/purchase_form.html", _editor_context(
                    request, editor, overlaps=overlaps, submission_key=submission_key, creating=True, **bulk))
            messages.success(request, "Purchase recorded.")
            return redirect("costs:purchase_detail", uuid=purchase.uuid)
        return render(request, "costs/purchase_form.html", _editor_context(
            request, editor, overlaps=[], submission_key=submission_key, creating=True, **bulk))

    initial = {"transaction_date": ""}
    project = None
    if request.GET.get("project"):
        project = Project.objects.for_owner(owner).filter(uuid=parse_uuid(request.GET["project"])).first()
    default_dest = f"project:{project.uuid}" if project else ""
    initial["default_destination"] = default_dest
    if shopping_item:
        dest = f"project:{shopping_item.project.uuid}" if shopping_item.project else ""
        line = PurchaseEditor.blank_line(dest)
        line.update({"description": shopping_item.description, "quantity": f"{shopping_item.quantity.normalize():f}",
                     "shopping": str(shopping_item.pk)})
        initial.update({"description": shopping_item.description, "merchant": shopping_item.retailer, "lines": [line]})
    from apps.core.dates import local_today

    initial["transaction_date"] = local_today().isoformat()
    editor = PurchaseEditor(owner, initial=initial)
    return render(request, "costs/purchase_form.html", _editor_context(
        request, editor, submission_key=uuid_lib.uuid4(), creating=True, shopping_item=shopping_item, **bulk))


def _submission_key(request):
    try:
        return uuid_lib.UUID(request.POST.get("submission_key", ""))
    except ValueError:
        return None


def purchase_detail(request, uuid):
    purchase = owned(Purchase, request.user, uuid=uuid)
    lines = purchase.lines.prefetch_related("allocations__project", "shopping_items")
    refunds = purchase.refunds.all().order_by("transaction_date")
    history = ChangeEvent.objects.filter(owner=request.user, subject_type="purchase", subject_id=str(purchase.uuid))
    refundable = services.refundable_by_destination(purchase) if not purchase.is_refund else {}
    return render(request, "costs/purchase_detail.html", {
        "purchase": purchase, "lines": lines, "refunds": refunds, "history": history,
        "evidence": purchase.evidence.select_related("document"),
        "decisions": purchase.balance_decisions.select_related("balance__project"),
        "can_refund": purchase.kind == Purchase.Kind.PURCHASE and not purchase.is_void and any(v > 0 for v in refundable.values()),
        "net_after_refunds": purchase.total - sum((r.total for r in refunds if not r.is_void), ZERO),
    })


def purchase_edit(request, uuid):
    owner = request.user
    purchase = owned(Purchase, owner, uuid=uuid)
    if purchase.is_void or purchase.is_refund:
        messages.error(request, "Void records and refunds cannot be corrected.")
        return redirect("costs:purchase_detail", uuid=uuid)
    if request.method == "POST":
        editor = PurchaseEditor(owner, request.POST)
        version = request.POST.get("version")
        reason = request.POST.get("reason", "")
        ctx = {"purchase": purchase, "version": version, "reason": reason}
        if editor.is_valid():
            overlaps = _overlaps_for(request, editor, correcting=purchase)
            if overlaps and _needs_choices(overlaps):
                return render(request, "costs/purchase_form.html", _editor_context(request, editor, overlaps=overlaps, **ctx))
            try:
                services.correct_purchase(owner, purchase, version, editor.purchase_input, reason,
                                          balance_choices=editor.balance_choices)
            except (BusinessRuleError, StaleObjectError) as exc:
                editor.errors = exc.messages
                return render(request, "costs/purchase_form.html", _editor_context(request, editor, overlaps=overlaps, **ctx))
            messages.success(request, "Purchase corrected. The previous version is kept in its history.")
            return redirect("costs:purchase_detail", uuid=uuid)
        return render(request, "costs/purchase_form.html", _editor_context(request, editor, **ctx))
    editor = PurchaseEditor(owner, initial={
        "description": purchase.description, "merchant": purchase.merchant,
        "transaction_date": purchase.transaction_date.isoformat(), "total": str(purchase.total),
        "notes": purchase.notes, "lines": PurchaseEditor.lines_from_purchase(purchase),
    })
    return render(request, "costs/purchase_form.html", _editor_context(
        request, editor, purchase=purchase, version=purchase.version))


def purchase_void(request, uuid):
    purchase = owned(Purchase, request.user, uuid=uuid)
    form = ReasonForm(request.POST or None, initial={"version": purchase.version})
    if request.method == "POST" and form.is_valid():
        try:
            services.void_purchase(request.user, purchase, form.cleaned_data["version"], form.cleaned_data["reason"])
        except (BusinessRuleError, StaleObjectError) as exc:
            for m in exc.messages:
                form.add_error(None, m)
        else:
            messages.success(request, "Marked void. It no longer counts towards totals but stays in the history.")
            return redirect("costs:purchase_detail", uuid=uuid)
    return render(request, "costs/void_form.html", {"form": form, "purchase": purchase})


def purchase_refund(request, uuid):
    owner = request.user
    purchase = owned(Purchase, owner, uuid=uuid)
    if purchase.is_refund or purchase.is_void:
        raise Http404
    refundable = services.refundable_by_destination(purchase)
    labels = {}
    for alloc in CostAllocation.objects.filter(line__purchase=purchase).select_related("project"):
        labels[alloc.destination_key()] = alloc.destination_label()
    rows = [{"key": k, "label": labels[k], "max": v, "value": ""} for k, v in refundable.items() if v > 0]
    from apps.core.dates import local_today

    form = RefundForm(request.POST or None, initial={"transaction_date": local_today()})
    errors = []
    if request.method == "POST":
        amounts = {}
        for row in rows:
            raw = (request.POST.get(f"amount-{row['key']}") or "").strip()
            row["value"] = raw
            if raw:
                try:
                    amounts[row["key"]] = to_money(raw)
                except ValueError as exc:
                    errors.append(f"{row['label']}: {exc}")
        if form.is_valid() and not errors:
            try:
                refund = services.refund_purchase(
                    owner, purchase, transaction_date=form.cleaned_data["transaction_date"], amounts=amounts,
                    description=form.cleaned_data["description"], notes=form.cleaned_data["notes"],
                    submission_key=_submission_key(request),
                )
            except BusinessRuleError as exc:
                errors.extend(exc.messages)
            else:
                messages.success(request, "Refund recorded.")
                return redirect("costs:purchase_detail", uuid=refund.uuid)
    return render(request, "costs/refund_form.html", {
        "form": form, "purchase": purchase, "rows": rows, "errors": errors,
        "submission_key": request.POST.get("submission_key") or uuid_lib.uuid4(),
    })
