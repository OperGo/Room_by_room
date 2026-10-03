"""Confirmed financial records.

Local invariants are database constraints; cross-row invariants (line totals
reconcile to the purchase total, allocations equal their line, refund caps)
are enforced inside the transactional services in ``services.py``.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class PurchaseQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(owner=user)

    def confirmed(self):
        return self.filter(status=Purchase.Status.CONFIRMED)


class Purchase(models.Model):
    class Kind(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        REFUND = "refund", "Refund"

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        VOID = "void", "Void"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="purchases")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PURCHASE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    description = models.CharField(max_length=160)
    merchant = models.CharField(max_length=120, blank=True)
    transaction_date = models.DateField()
    currency = models.CharField(max_length=3, default="GBP")
    # Always positive or zero; refunds are subtracted in reporting.
    total = models.DecimalField(max_digits=10, decimal_places=2)
    original_purchase = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="refunds"
    )
    notes = models.TextField(blank=True)
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    # Idempotency: a form submission token, and the receipt draft it came from.
    submission_key = models.UUIDField(null=True, blank=True)
    source_draft = models.OneToOneField(
        "receipts.ReceiptDraft", null=True, blank=True, on_delete=models.PROTECT, related_name="posted_purchase"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    objects = PurchaseQuerySet.as_manager()

    class Meta:
        ordering = ["-transaction_date", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="purchase_total_non_negative"),
            models.CheckConstraint(condition=Q(currency="GBP"), name="purchase_currency_gbp"),
            models.CheckConstraint(
                condition=Q(kind="purchase", original_purchase__isnull=True) | Q(kind="refund", total__gt=0),
                name="purchase_refund_shape",
            ),
            models.CheckConstraint(
                condition=Q(status="confirmed") | ~Q(void_reason=""), name="purchase_void_needs_reason"
            ),
            models.UniqueConstraint(fields=["owner", "submission_key"], name="purchase_unique_submission"),
        ]

    def __str__(self):
        return f"{self.description} {self.total}"

    @property
    def is_refund(self):
        return self.kind == self.Kind.REFUND

    @property
    def is_void(self):
        return self.status == self.Status.VOID


class PurchaseLine(models.Model):
    class Category(models.TextChoices):
        MATERIAL = "material", "Material"
        TOOL = "tool", "Tool"
        LABOUR = "labour", "Labour"
        OTHER = "other", "Other"

    class LineType(models.TextChoices):
        ITEM = "item", "Item"
        UNITEMISED = "unitemised", "Unitemised purchase"
        SHIPPING = "shipping", "Shipping"
        DISCOUNT = "discount", "Discount"
        ROUNDING = "rounding", "Rounding"
        ADJUSTMENT = "adjustment", "Other adjustment"
        REFUND = "refund", "Refund"

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=160)
    line_type = models.CharField(max_length=12, choices=LineType.choices, default=LineType.ITEM)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.MATERIAL)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Descriptive only; totals use the line amount."
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Signed line total (discounts negative).")

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="line_quantity_positive"),
            models.CheckConstraint(condition=~Q(line_type="discount") | Q(amount__lt=0), name="line_discount_negative"),
            models.CheckConstraint(
                condition=~Q(line_type__in=["item", "unitemised", "shipping", "refund"]) | Q(amount__gte=0),
                name="line_item_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.description} {self.amount}"


class AllocationQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(line__purchase__owner=user)

    def confirmed(self):
        return self.filter(line__purchase__status=Purchase.Status.CONFIRMED)


class CostAllocation(models.Model):
    class Destination(models.TextChoices):
        PROJECT = "project", "Project"
        SHARED_TOOLS = "shared_tools", "Shared tools"
        UNALLOCATED = "unallocated", "Unallocated"

    line = models.ForeignKey(PurchaseLine, on_delete=models.CASCADE, related_name="allocations")
    destination = models.CharField(max_length=14, choices=Destination.choices)
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    objects = AllocationQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(destination="project") & Q(project__isnull=False)) | (~Q(destination="project") & Q(project__isnull=True)),
                name="allocation_project_matches_destination",
            ),
        ]

    def destination_key(self):
        return f"project:{self.project.uuid}" if self.project_id else self.destination

    def destination_label(self):
        return self.project.title if self.project_id else self.get_destination_display()


class OpeningCostBalance(models.Model):
    """An estimated historical cost for a project, without itemised evidence."""

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="opening_balances")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    original_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Remaining estimate after replacements.")
    coverage_through = models.DateField(help_text="Spending up to and including this date is covered by the estimate.")
    note = models.TextField(blank=True)
    is_estimate = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["coverage_through", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="opening_balance_non_negative"),
            models.CheckConstraint(condition=Q(original_amount__gte=0), name="opening_balance_original_non_negative"),
            models.CheckConstraint(condition=Q(amount__lte=F("original_amount")), name="opening_balance_not_above_original"),
        ]


class OpeningBalanceDecision(models.Model):
    """Records how a purchase in an opening balance's covered period was treated."""

    class Decision(models.TextChoices):
        ADDITIONAL = "additional", "Additional spending"
        REPLACE = "replace", "Replaces part of the estimate"

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="balance_decisions")
    balance = models.ForeignKey(OpeningCostBalance, on_delete=models.CASCADE, related_name="decisions")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    amount_replaced = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount_replaced__gte=0), name="decision_amount_non_negative"),
            models.CheckConstraint(
                condition=Q(decision="replace", amount_replaced__gt=0) | Q(decision="additional", amount_replaced=0),
                name="decision_amount_matches_kind",
            ),
        ]


class PurchaseEvidence(models.Model):
    """Links a receipt document to a purchase. Evidence never creates cost."""

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="evidence")
    document = models.ForeignKey("receipts.ReceiptDocument", on_delete=models.CASCADE, related_name="evidence_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["purchase", "document"], name="unique_purchase_evidence")]
