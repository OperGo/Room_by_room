"""Transactional services for confirmed financial records.

Every function here runs in a single database transaction and locks the rows
it changes (``select_for_update``; effective on PostgreSQL). Validation
failures raise ``BusinessRuleError`` before anything is written, so a failed
attempt leaves zero confirmed cost.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError, StaleObjectError, parse_version
from apps.core.models import record_change
from apps.core.money import ZERO, format_gbp, money_sum
from apps.projects.models import Project

from .models import CostAllocation, OpeningBalanceDecision, OpeningCostBalance, Purchase, PurchaseLine

SHARED = CostAllocation.Destination.SHARED_TOOLS
UNALLOCATED = CostAllocation.Destination.UNALLOCATED
PROJECT = CostAllocation.Destination.PROJECT
LT = PurchaseLine.LineType
NON_NEGATIVE_TYPES = {LT.ITEM, LT.UNITEMISED, LT.SHIPPING, LT.REFUND}


# --------------------------------------------------------------------------- inputs


@dataclass
class AllocationInput:
    destination: str
    amount: Decimal
    project: Project | None = None

    @property
    def key(self):
        return f"project:{self.project.uuid}" if self.project else self.destination

    @property
    def label(self):
        return self.project.title if self.project else dict(CostAllocation.Destination.choices)[self.destination]


@dataclass
class LineInput:
    description: str
    amount: Decimal
    allocations: list[AllocationInput]
    line_type: str = LT.ITEM
    category: str = PurchaseLine.Category.MATERIAL
    quantity: Decimal = Decimal("1")
    unit_price: Decimal | None = None
    shopping_item_ids: list[int] = field(default_factory=list)


@dataclass
class PurchaseInput:
    description: str
    transaction_date: object
    total: Decimal
    lines: list[LineInput]
    merchant: str = ""
    notes: str = ""


@dataclass
class BalanceChoice:
    balance_uuid: str
    decision: str  # "additional" or "replace"
    amount: Decimal = ZERO


@dataclass
class Overlap:
    balance: OpeningCostBalance
    project_amount: Decimal  # this purchase's net allocation to the balance's project


# --------------------------------------------------------------------------- validation


def validate_purchase_input(owner, data: PurchaseInput):
    """Return a list of user-facing problems. Empty list means the input reconciles."""
    errors = []
    if not data.description.strip():
        errors.append("Add a short description.")
    if data.transaction_date is None:
        errors.append("Add the purchase date.")
    if data.total is None or data.total < 0:
        errors.append("A purchase total cannot be negative.")
    if not data.lines:
        errors.append("Add at least one line.")
    if len(data.lines) > settings.RECEIPT_MAX_LINES:
        errors.append(f"A purchase can have at most {settings.RECEIPT_MAX_LINES} lines.")
    for index, line in enumerate(data.lines, start=1):
        name = f"Line {index}"
        if not line.description.strip():
            errors.append(f"{name}: add a description.")
        if line.quantity is None or line.quantity <= 0:
            errors.append(f"{name}: quantity must be positive.")
        if line.line_type == LT.DISCOUNT and line.amount >= 0:
            errors.append(f"{name}: a discount must be a negative amount.")
        if line.line_type in NON_NEGATIVE_TYPES and line.amount < 0:
            errors.append(f"{name}: use a discount or adjustment line for negative amounts.")
        if not line.allocations:
            errors.append(f"{name}: choose where this cost belongs.")
            continue
        for alloc in line.allocations:
            if alloc.project is not None and alloc.project.owner_id != owner.pk:
                errors.append(f"{name}: unknown project.")
            if alloc.destination == PROJECT and alloc.project is None:
                errors.append(f"{name}: choose a project.")
            if line.amount > 0 and alloc.amount < 0 or line.amount < 0 and alloc.amount > 0:
                errors.append(f"{name}: split amounts must have the same sign as the line.")
        allocated = money_sum(a.amount for a in line.allocations)
        if allocated != line.amount:
            errors.append(
                f"{name}: allocations add up to {format_gbp(allocated)} but the line is {format_gbp(line.amount)}."
            )
        keys = [a.key for a in line.allocations]
        if len(keys) != len(set(keys)):
            errors.append(f"{name}: each destination can appear only once in a split.")
    if data.total is not None and data.lines:
        lines_total = money_sum(line.amount for line in data.lines)
        if lines_total != data.total:
            errors.append(
                f"Items add up to {format_gbp(lines_total)} but the purchase total is {format_gbp(data.total)}. "
                "Add missing items or correct the amounts."
            )
    if not errors:
        for key, amount in destination_totals_from_input(data).items():
            if amount < 0:
                errors.append("A discount cannot make a destination's share of this purchase negative.")
                break
    return errors


def destination_totals_from_input(data: PurchaseInput):
    totals = defaultdict(lambda: ZERO)
    for line in data.lines:
        for alloc in line.allocations:
            totals[alloc.key] += alloc.amount
    return dict(totals)


def project_amounts_from_input(data: PurchaseInput):
    totals = defaultdict(lambda: ZERO)
    for line in data.lines:
        for alloc in line.allocations:
            if alloc.project is not None:
                totals[alloc.project.pk] += alloc.amount
    return totals


def find_overlaps(owner, data: PurchaseInput, lock=False, correcting=None):
    """Opening balances whose covered period includes this purchase's date.

    ``correcting`` (display only) treats that purchase's existing replacements
    as already reversed, matching what ``correct_purchase`` will do.
    """
    if data.transaction_date is None:
        return []
    project_amounts = project_amounts_from_input(data)
    if not project_amounts:
        return []
    restored = defaultdict(lambda: ZERO)
    if correcting is not None:
        for d in OpeningBalanceDecision.objects.filter(purchase=correcting, reversed_at__isnull=True):
            restored[d.balance_id] += d.amount_replaced
    qs = OpeningCostBalance.objects.filter(
        project__owner=owner,
        project_id__in=list(project_amounts),
        coverage_through__gte=data.transaction_date,
    ).select_related("project").order_by("id")
    if lock:
        qs = qs.select_for_update()
    overlaps = []
    for balance in qs:
        balance.amount += restored[balance.pk]
        if balance.amount > 0 and project_amounts[balance.project_id] > 0:
            overlaps.append(Overlap(balance=balance, project_amount=project_amounts[balance.project_id]))
    return overlaps


def _resolve_choices(overlaps, choices):
    """Match each overlap to an explicit decision; raise if any is missing or invalid."""
    by_uuid = {str(c.balance_uuid): c for c in (choices or [])}
    resolved = []
    replaced_by_project = defaultdict(lambda: ZERO)
    for overlap in overlaps:
        choice = by_uuid.get(str(overlap.balance.uuid))
        if choice is None or choice.decision not in OpeningBalanceDecision.Decision.values:
            raise BusinessRuleError(
                f"This purchase falls inside the period covered by the {overlap.balance.project.title} opening balance. "
                "Choose whether it is additional spending or replaces part of that estimate."
            )
        if choice.decision == OpeningBalanceDecision.Decision.REPLACE:
            if choice.amount is None or choice.amount <= 0:
                raise BusinessRuleError("Enter how much of the opening balance this purchase replaces.")
            if choice.amount > overlap.balance.amount:
                raise BusinessRuleError(
                    f"Only {format_gbp(overlap.balance.amount)} of that opening balance remains; it cannot go negative."
                )
            replaced_by_project[overlap.balance.project_id] += choice.amount
            if replaced_by_project[overlap.balance.project_id] > overlap.project_amount:
                raise BusinessRuleError("You cannot replace more of an opening balance than this purchase allocates to that project.")
        resolved.append((overlap, choice))
    return resolved


# --------------------------------------------------------------------------- posting


def _create_lines(purchase, data: PurchaseInput, owner):
    from apps.shopping.models import ShoppingItem

    for position, line in enumerate(data.lines):
        row = PurchaseLine.objects.create(
            purchase=purchase,
            position=position,
            description=line.description.strip()[:160],
            line_type=line.line_type,
            category=line.category,
            quantity=line.quantity,
            unit_price=line.unit_price,
            amount=line.amount,
        )
        CostAllocation.objects.bulk_create(
            CostAllocation(line=row, destination=PROJECT if a.project else a.destination, project=a.project, amount=a.amount)
            for a in line.allocations
        )
        if line.shopping_item_ids:
            items = list(
                ShoppingItem.objects.select_for_update().filter(owner=owner, pk__in=line.shopping_item_ids)
            )
            for item in items:
                if item.purchase_line_id and item.purchase_line_id != row.pk:
                    raise BusinessRuleError(f"“{item.description}” is already linked to a purchase.")
                item.purchase_line = row
                if item.purchased_at is None:
                    item.purchased_at = timezone.now()
                item.version += 1
                item.save(update_fields=["purchase_line", "purchased_at", "version", "updated_at"])


def _apply_balance_choices(purchase, resolved, owner):
    for overlap, choice in resolved:
        balance = overlap.balance
        amount = choice.amount if choice.decision == OpeningBalanceDecision.Decision.REPLACE else ZERO
        OpeningBalanceDecision.objects.create(
            purchase=purchase, balance=balance, decision=choice.decision, amount_replaced=amount
        )
        if amount:
            before = {"amount": str(balance.amount)}
            balance.amount -= amount
            balance.version += 1
            balance.save(update_fields=["amount", "version", "updated_at"])
            record_change(
                owner, balance, "replaced_by_purchase", before, {"amount": str(balance.amount)},
                f"{format_gbp(amount)} replaced by purchase “{purchase.description}”.",
            )


def _reverse_balance_decisions(purchase, owner, reason):
    decisions = list(
        OpeningBalanceDecision.objects.select_for_update()
        .filter(purchase=purchase, reversed_at__isnull=True)
        .order_by("balance_id")
    )
    balance_ids = [d.balance_id for d in decisions]
    balances = {b.pk: b for b in OpeningCostBalance.objects.select_for_update().filter(pk__in=balance_ids).order_by("id")}
    for decision in decisions:
        if decision.amount_replaced:
            balance = balances[decision.balance_id]
            before = {"amount": str(balance.amount)}
            balance.amount += decision.amount_replaced
            balance.version += 1
            balance.save(update_fields=["amount", "version", "updated_at"])
            record_change(owner, balance, "replacement_reversed", before, {"amount": str(balance.amount)}, reason)
        decision.reversed_at = timezone.now()
        decision.save(update_fields=["reversed_at"])


def purchase_summary(purchase):
    lines = []
    for line in purchase.lines.all().prefetch_related("allocations__project"):
        lines.append({
            "description": line.description,
            "type": line.line_type,
            "category": line.category,
            "quantity": str(line.quantity),
            "amount": str(line.amount),
            "allocations": [{"to": a.destination_label(), "amount": str(a.amount)} for a in line.allocations.all()],
        })
    return {
        "description": purchase.description,
        "merchant": purchase.merchant,
        "date": purchase.transaction_date.isoformat() if purchase.transaction_date else None,
        "total": str(purchase.total),
        "status": purchase.status,
        "lines": lines,
    }


def post_purchase(owner, data: PurchaseInput, *, submission_key=None, source_draft=None, balance_choices=None,
                  draft_version=None):
    """Create one confirmed purchase. Idempotent per submission key and per receipt draft.

    When posting from a receipt draft, ``draft_version`` must match the locked
    draft's version, unless the draft was already confirmed (then the existing
    purchase is returned so retries stay idempotent).
    """
    try:
        with transaction.atomic():
            if submission_key:
                existing = Purchase.objects.filter(owner=owner, submission_key=submission_key).first()
                if existing:
                    return existing
            if source_draft is not None:
                from apps.receipts.models import ReceiptDraft

                draft = ReceiptDraft.objects.select_for_update().get(pk=source_draft.pk, owner=owner)
                existing = Purchase.objects.filter(source_draft=draft).first()
                if existing:
                    return existing
                if draft.review_status != ReceiptDraft.ReviewStatus.DRAFT:
                    raise BusinessRuleError("This receipt has already been handled.")
                if parse_version(draft_version) != draft.version:
                    raise StaleObjectError(
                        "This receipt draft was changed elsewhere since you opened it. "
                        "Your entries are shown below; review them against the latest draft and confirm again."
                    )
            errors = validate_purchase_input(owner, data)
            if errors:
                raise BusinessRuleError(errors)
            resolved = _resolve_choices(find_overlaps(owner, data, lock=True), balance_choices)
            purchase = Purchase.objects.create(
                owner=owner,
                kind=Purchase.Kind.PURCHASE,
                description=data.description.strip()[:160],
                merchant=data.merchant.strip()[:120],
                transaction_date=data.transaction_date,
                total=data.total,
                notes=data.notes,
                submission_key=submission_key,
                source_draft=source_draft,
            )
            _create_lines(purchase, data, owner)
            _apply_balance_choices(purchase, resolved, owner)
            if source_draft is not None:
                from apps.costs.models import PurchaseEvidence

                PurchaseEvidence.objects.get_or_create(purchase=purchase, document=draft.document)
                draft.review_status = ReceiptDraft.ReviewStatus.CONFIRMED
                draft.version += 1
                draft.save(update_fields=["review_status", "version", "updated_at"])
            record_change(owner, purchase, "created", {}, purchase_summary(purchase))
            return purchase
    except IntegrityError:
        # A concurrent duplicate submission won the race; return what it created.
        if submission_key:
            existing = Purchase.objects.filter(owner=owner, submission_key=submission_key).first()
            if existing:
                return existing
        if source_draft is not None:
            existing = Purchase.objects.filter(source_draft_id=source_draft.pk).first()
            if existing:
                return existing
        raise


def _lock_purchase(owner, purchase, expected_version=None):
    locked = Purchase.objects.select_for_update().get(pk=purchase.pk, owner=owner)
    if expected_version is not None and int(expected_version) != locked.version:
        raise StaleObjectError()
    return locked


def destination_totals(purchase):
    """Net allocated amount per destination key for one purchase or refund."""
    totals = defaultdict(lambda: ZERO)
    for alloc in CostAllocation.objects.filter(line__purchase=purchase).select_related("project"):
        totals[alloc.destination_key()] += alloc.amount
    return dict(totals)


def refunded_by_destination(original, exclude=None):
    totals = defaultdict(lambda: ZERO)
    refunds = original.refunds.filter(status=Purchase.Status.CONFIRMED)
    if exclude is not None:
        refunds = refunds.exclude(pk=exclude.pk)
    for alloc in CostAllocation.objects.filter(line__purchase__in=refunds).select_related("project"):
        totals[alloc.destination_key()] += alloc.amount
    return dict(totals)


def refundable_by_destination(original):
    paid = destination_totals(original)
    refunded = refunded_by_destination(original)
    return {key: amount - refunded.get(key, ZERO) for key, amount in paid.items()}


def correct_purchase(owner, purchase, expected_version, data: PurchaseInput, reason, balance_choices=None):
    """Replace a confirmed purchase's details and lines. Requires a reason; keeps history."""
    if not (reason or "").strip():
        raise BusinessRuleError("Explain why this purchase is being corrected.")
    with transaction.atomic():
        locked = _lock_purchase(owner, purchase, expected_version)
        if locked.is_void:
            raise BusinessRuleError("A void purchase cannot be corrected.")
        if locked.is_refund:
            raise BusinessRuleError("Refunds cannot be edited; void the refund and record it again.")
        errors = validate_purchase_input(owner, data)
        if errors:
            raise BusinessRuleError(errors)
        # Refunds already recorded must still fit inside the corrected allocations.
        refunded = refunded_by_destination(locked)
        new_totals = destination_totals_from_input(data)
        for key, amount in refunded.items():
            if new_totals.get(key, ZERO) < amount:
                raise BusinessRuleError(
                    "Refunds already recorded against this purchase would exceed the corrected amounts. "
                    "Void those refunds first."
                )
        before = purchase_summary(locked)
        _reverse_balance_decisions(locked, owner, f"Purchase corrected: {reason}")
        resolved = _resolve_choices(find_overlaps(owner, data, lock=True), balance_choices)
        # Remember shopping links by line position so they survive the rewrite.
        links = defaultdict(list)
        for line in locked.lines.all():
            for item in line.shopping_items.all():
                links[line.position].append(item.pk)
        for position, ids in links.items():
            if position < len(data.lines):
                data.lines[position].shopping_item_ids = list(set(data.lines[position].shopping_item_ids) | set(ids))
        locked.lines.all().delete()
        locked.description = data.description.strip()[:160]
        locked.merchant = data.merchant.strip()[:120]
        locked.transaction_date = data.transaction_date
        locked.total = data.total
        locked.notes = data.notes
        locked.version += 1
        locked.save()
        _create_lines(locked, data, owner)
        _apply_balance_choices(locked, resolved, owner)
        record_change(owner, locked, "corrected", before, purchase_summary(locked), reason)
        return locked


def void_purchase(owner, purchase, expected_version, reason):
    """Mark a confirmed purchase or refund void. It stays visible with its reason."""
    if not (reason or "").strip():
        raise BusinessRuleError("Explain why this record is being voided.")
    with transaction.atomic():
        locked = _lock_purchase(owner, purchase, expected_version)
        if locked.is_void:
            return locked
        if locked.refunds.filter(status=Purchase.Status.CONFIRMED).exists():
            raise BusinessRuleError("Void the refunds linked to this purchase first.")
        _reverse_balance_decisions(locked, owner, f"Purchase voided: {reason}")
        before = purchase_summary(locked)
        locked.status = Purchase.Status.VOID
        locked.void_reason = reason.strip()
        locked.voided_at = timezone.now()
        locked.version += 1
        locked.save(update_fields=["status", "void_reason", "voided_at", "version", "updated_at"])
        record_change(owner, locked, "voided", before, {"status": "void"}, reason)
        return locked


def refund_purchase(owner, original, *, transaction_date, amounts, description="", notes="", submission_key=None):
    """Record a refund linked to ``original``.

    ``amounts`` maps destination keys (``project:<uuid>``, ``shared_tools``,
    ``unallocated``) to positive refund amounts. Each is capped at what the
    original allocated there minus earlier refunds.
    """
    amounts = {k: v for k, v in amounts.items() if v}
    if not amounts:
        raise BusinessRuleError("Enter the amount refunded.")
    if any(v < 0 for v in amounts.values()):
        raise BusinessRuleError("Refund amounts are entered as positive numbers.")
    if transaction_date is None:
        raise BusinessRuleError("Add the refund date.")
    try:
        with transaction.atomic():
            if submission_key:
                existing = Purchase.objects.filter(owner=owner, submission_key=submission_key).first()
                if existing:
                    return existing
            locked = _lock_purchase(owner, original)
            if locked.is_void or locked.is_refund:
                raise BusinessRuleError("Refunds can only be recorded against a confirmed purchase.")
            if transaction_date < locked.transaction_date:
                raise BusinessRuleError("A refund cannot be dated before the original purchase.")
            remaining = refundable_by_destination(locked)
            allocations = []
            projects = {f"project:{a.project.uuid}": a.project for a in
                        CostAllocation.objects.filter(line__purchase=locked, project__isnull=False).select_related("project")}
            for key, amount in amounts.items():
                if key not in remaining:
                    raise BusinessRuleError("A refund can only reduce destinations the original purchase was allocated to.")
                if amount > remaining[key]:
                    label = projects[key].title if key in projects else dict(CostAllocation.Destination.choices)[key]
                    raise BusinessRuleError(
                        f"{label}: at most {format_gbp(remaining[key])} of this purchase can still be refunded."
                    )
                if key in projects:
                    allocations.append(AllocationInput(PROJECT, amount, projects[key]))
                else:
                    allocations.append(AllocationInput(key, amount))
            total = money_sum(amounts.values())
            refund = Purchase.objects.create(
                owner=owner,
                kind=Purchase.Kind.REFUND,
                description=(description or f"Refund: {locked.description}").strip()[:160],
                merchant=locked.merchant,
                transaction_date=transaction_date,
                total=total,
                original_purchase=locked,
                notes=notes,
                submission_key=submission_key,
            )
            line = PurchaseLine.objects.create(
                purchase=refund, description=refund.description, line_type=LT.REFUND,
                category=PurchaseLine.Category.OTHER, amount=total,
            )
            CostAllocation.objects.bulk_create(
                CostAllocation(line=line, destination=PROJECT if a.project else a.destination, project=a.project, amount=a.amount)
                for a in allocations
            )
            record_change(owner, refund, "refund_recorded", {}, purchase_summary(refund), notes)
            return refund
    except IntegrityError:
        if submission_key:
            existing = Purchase.objects.filter(owner=owner, submission_key=submission_key).first()
            if existing:
                return existing
        raise


# --------------------------------------------------------------------------- opening balances


def create_opening_balance(owner, project, *, amount, coverage_through, note=""):
    if project.owner_id != owner.pk:
        raise BusinessRuleError("Unknown project.")
    if amount is None or amount < 0:
        raise BusinessRuleError("An opening balance cannot be negative.")
    if coverage_through is None:
        raise BusinessRuleError("Add the date this estimate covers spending up to.")
    with transaction.atomic():
        balance = OpeningCostBalance.objects.create(
            project=project, original_amount=amount, amount=amount, coverage_through=coverage_through, note=note
        )
        record_change(owner, balance, "created", {}, {"amount": str(amount), "coverage_through": coverage_through.isoformat()}, note)
        return balance


def update_opening_balance(owner, balance, expected_version, *, amount, coverage_through, note, reason):
    if not (reason or "").strip():
        raise BusinessRuleError("Explain why this opening balance is changing.")
    if amount is None or amount < 0:
        raise BusinessRuleError("An opening balance cannot be negative.")
    with transaction.atomic():
        locked = OpeningCostBalance.objects.select_for_update().get(pk=balance.pk, project__owner=owner)
        if int(expected_version) != locked.version:
            raise StaleObjectError()
        replaced = money_sum(
            locked.decisions.filter(reversed_at__isnull=True).values_list("amount_replaced", flat=True)
        )
        if amount < replaced:
            raise BusinessRuleError(
                f"{format_gbp(replaced)} of this estimate has already been replaced by itemised purchases; "
                "the estimate cannot be lower than that."
            )
        before = {"original_amount": str(locked.original_amount), "amount": str(locked.amount),
                  "coverage_through": locked.coverage_through.isoformat(), "note": locked.note}
        locked.original_amount = amount
        locked.amount = amount - replaced
        locked.coverage_through = coverage_through
        locked.note = note
        locked.version += 1
        locked.save()
        record_change(owner, locked, "corrected", before,
                      {"original_amount": str(amount), "amount": str(locked.amount),
                       "coverage_through": coverage_through.isoformat(), "note": note}, reason)
        return locked


def replace_opening_balance(owner, purchase, balance, amount, reason=""):
    """Retrospectively mark part of an opening balance as replaced by an existing purchase."""
    with transaction.atomic():
        locked_purchase = _lock_purchase(owner, purchase)
        locked = OpeningCostBalance.objects.select_for_update().get(pk=balance.pk, project__owner=owner)
        if locked_purchase.is_void or locked_purchase.is_refund:
            raise BusinessRuleError("Only a confirmed purchase can replace an opening balance.")
        if locked_purchase.transaction_date > locked.coverage_through:
            raise BusinessRuleError("This purchase is outside the period the opening balance covers.")
        project_amount = destination_totals(locked_purchase).get(f"project:{locked.project.uuid}", ZERO)
        already = money_sum(
            OpeningBalanceDecision.objects.filter(purchase=locked_purchase, reversed_at__isnull=True,
                                                  balance__project=locked.project).values_list("amount_replaced", flat=True)
        )
        if amount <= 0 or amount > locked.amount or amount + already > project_amount:
            raise BusinessRuleError("That replacement amount is not available.")
        OpeningBalanceDecision.objects.filter(purchase=locked_purchase, balance=locked, reversed_at__isnull=True,
                                              decision=OpeningBalanceDecision.Decision.ADDITIONAL).update(reversed_at=timezone.now())
        resolved = [(Overlap(locked, project_amount), BalanceChoice(str(locked.uuid), OpeningBalanceDecision.Decision.REPLACE, amount))]
        _apply_balance_choices(locked_purchase, resolved, owner)
        return locked
