"""Purchase editor parsing.

The purchase editor posts a flat set of fields (``line-0-amount``,
``line-0-alloc-1-dest`` ...). Small progressive JavaScript adds rows; without
JavaScript the server always renders spare rows so the form still works.
"""

import datetime
import uuid
from decimal import Decimal, InvalidOperation

from django import forms

from apps.core.money import to_money
from apps.projects.models import Project

from .models import CostAllocation, PurchaseLine
from .services import AllocationInput, BalanceChoice, LineInput, PurchaseInput

SHARED = CostAllocation.Destination.SHARED_TOOLS
UNALLOCATED = CostAllocation.Destination.UNALLOCATED


def destination_options(owner, include_ids=()):
    projects = Project.objects.for_owner(owner).exclude(status=Project.Status.ARCHIVED)
    extra = Project.objects.for_owner(owner).filter(pk__in=include_ids, status=Project.Status.ARCHIVED)
    options = [(f"project:{p.uuid}", p.title) for p in projects.order_by("title")]
    options += [(f"project:{p.uuid}", f"{p.title} (archived)") for p in extra]
    options += [(SHARED, "Shared tools"), (UNALLOCATED, "Unallocated")]
    return options


def resolve_destination(owner, value):
    """Map a posted destination key to (destination, project). Unknown keys raise ValueError."""
    if value == SHARED:
        return SHARED, None
    if value == UNALLOCATED:
        return UNALLOCATED, None
    if value and value.startswith("project:"):
        try:
            project_uuid = uuid.UUID(value.split(":", 1)[1])
        except ValueError as exc:
            raise ValueError("Unknown project.") from exc
        project = Project.objects.for_owner(owner).filter(uuid=project_uuid).first()
        if project is None:
            raise ValueError("Unknown project.")
        return CostAllocation.Destination.PROJECT, project
    raise ValueError("Choose where this cost belongs.")


def _indexes(post, prefix):
    found = set()
    for key in post:
        if key.startswith(prefix):
            head = key[len(prefix):].split("-", 1)[0]
            if head.isdigit():
                found.add(int(head))
    return sorted(found)


def _parse_date(value):
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _parse_quantity(value):
    try:
        quantity = Decimal((value or "1").strip() or "1")
    except InvalidOperation:
        return None
    return quantity if quantity.is_finite() else None


class PurchaseEditor:
    """Parses and re-renders the purchase/receipt editor."""

    def __init__(self, owner, data=None, *, initial=None):
        self.owner = owner
        self.data = data
        self.errors = []
        self.header = {}
        self.lines = []
        self.balance_choices = []
        self.purchase_input = None
        if data is None:
            self._load_initial(initial or {})

    # ----------------------------------------------------------------- rendering helpers

    def _load_initial(self, initial):
        self.header = {
            "description": initial.get("description", ""),
            "merchant": initial.get("merchant", ""),
            "transaction_date": initial.get("transaction_date", ""),
            "total": initial.get("total", ""),
            "notes": initial.get("notes", ""),
        }
        self.lines = initial.get("lines") or [self.blank_line(initial.get("default_destination", ""))]

    @staticmethod
    def blank_line(destination=""):
        return {
            "description": "", "line_type": PurchaseLine.LineType.ITEM, "category": PurchaseLine.Category.MATERIAL,
            "quantity": "1", "unit_price": "", "amount": "", "shopping": "",
            "allocations": [{"dest": destination, "amount": ""}],
        }

    @staticmethod
    def lines_from_purchase(purchase):
        lines = []
        for line in purchase.lines.all().prefetch_related("allocations__project", "shopping_items"):
            allocations = [{"dest": a.destination_key(), "amount": str(a.amount)} for a in line.allocations.all()]
            if len(allocations) == 1:
                allocations[0]["amount"] = ""
            lines.append({
                "description": line.description, "line_type": line.line_type, "category": line.category,
                "quantity": f"{line.quantity.normalize():f}", "unit_price": str(line.unit_price or ""),
                "amount": str(line.amount), "allocations": allocations,
                "shopping": ",".join(str(i.pk) for i in line.shopping_items.all()),
            })
        return lines

    # ----------------------------------------------------------------- parsing

    def is_valid(self):
        post = self.data
        self.header = {k: (post.get(k) or "").strip() for k in ("description", "merchant", "transaction_date", "total", "notes")}
        errors = []
        transaction_date = _parse_date(self.header["transaction_date"])
        if transaction_date is None:
            errors.append("Enter the purchase date.")
        total = None
        if self.header["total"]:
            try:
                total = to_money(self.header["total"])
            except ValueError as exc:
                errors.append(f"Total: {exc}")
        line_inputs = []
        for i in _indexes(post, "line-"):
            p = f"line-{i}-"
            raw = {
                "description": (post.get(p + "description") or "").strip(),
                "line_type": post.get(p + "line_type") or PurchaseLine.LineType.ITEM,
                "category": post.get(p + "category") or PurchaseLine.Category.MATERIAL,
                "quantity": (post.get(p + "quantity") or "1").strip(),
                "unit_price": (post.get(p + "unit_price") or "").strip(),
                "amount": (post.get(p + "amount") or "").strip(),
                "shopping": (post.get(p + "shopping") or "").strip(),
                "allocations": [],
            }
            for j in _indexes(post, f"{p}alloc-"):
                raw["allocations"].append({
                    "dest": post.get(f"{p}alloc-{j}-dest") or "",
                    "amount": (post.get(f"{p}alloc-{j}-amount") or "").strip(),
                })
            raw["allocations"] = [a for a in raw["allocations"] if a["dest"] or a["amount"]] or [{"dest": "", "amount": ""}]
            if not raw["description"] and not raw["amount"]:
                continue  # an untouched spare row
            self.lines.append(raw)
            name = f"Line {len(self.lines)}"
            if raw["line_type"] not in PurchaseLine.LineType.values or raw["line_type"] == PurchaseLine.LineType.REFUND:
                errors.append(f"{name}: choose a line type.")
                continue
            if raw["category"] not in PurchaseLine.Category.values:
                errors.append(f"{name}: choose a category.")
                continue
            try:
                amount = to_money(raw["amount"])
            except ValueError as exc:
                errors.append(f"{name}: {exc}")
                continue
            quantity = _parse_quantity(raw["quantity"])
            if quantity is None or quantity <= 0 or quantity != quantity.quantize(Decimal("0.001")):
                errors.append(f"{name}: quantity must be a positive number.")
                continue
            unit_price = None
            if raw["unit_price"]:
                try:
                    unit_price = to_money(raw["unit_price"])
                except ValueError as exc:
                    errors.append(f"{name} unit price: {exc}")
                    continue
            allocations = []
            single = len(raw["allocations"]) == 1
            for alloc in raw["allocations"]:
                try:
                    destination, project = resolve_destination(self.owner, alloc["dest"])
                except ValueError as exc:
                    errors.append(f"{name}: {exc}")
                    break
                if single and not alloc["amount"]:
                    alloc_amount = amount
                else:
                    try:
                        alloc_amount = to_money(alloc["amount"])
                    except ValueError as exc:
                        errors.append(f"{name} split: {exc}")
                        break
                allocations.append(AllocationInput(destination, alloc_amount, project))
            else:
                shopping_ids = [int(x) for x in raw["shopping"].split(",") if x.strip().isdigit()]
                line_inputs.append(LineInput(
                    description=raw["description"], amount=amount, allocations=allocations,
                    line_type=raw["line_type"], category=raw["category"], quantity=quantity,
                    unit_price=unit_price, shopping_item_ids=shopping_ids,
                ))
        if not self.lines:
            errors.append("Add at least one line.")
            self.lines = [self.blank_line()]
        if total is None and not errors and line_inputs:
            # Leaving the total blank means "the lines are the total".
            total = sum((li.amount for li in line_inputs), Decimal("0.00"))
            self.header["total"] = str(total)
        elif total is None and not errors:
            errors.append("Enter the total.")
        for key in post:
            if key.startswith("balance-") and key.endswith("-decision"):
                balance_uuid = key[len("balance-"):-len("-decision")]
                decision = post.get(key)
                amount_raw = (post.get(f"balance-{balance_uuid}-amount") or "").strip()
                amount = Decimal("0.00")
                if decision == "replace":
                    try:
                        amount = to_money(amount_raw)
                    except ValueError as exc:
                        errors.append(f"Opening balance replacement: {exc}")
                self.balance_choices.append(BalanceChoice(balance_uuid, decision, amount))
        self.errors = errors
        if errors:
            return False
        description = self.header["description"] or self.header["merchant"] or (
            line_inputs[0].description if line_inputs else "") or "Purchase"
        self.purchase_input = PurchaseInput(
            description=description, merchant=self.header["merchant"],
            transaction_date=transaction_date, total=total, notes=self.header["notes"], lines=line_inputs,
        )
        return True

    def raw_choice(self, balance_uuid):
        for choice in self.balance_choices:
            if str(choice.balance_uuid) == str(balance_uuid):
                return choice
        return None


class RefundForm(forms.Form):
    transaction_date = forms.DateField(label="Refund date", widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(max_length=160, required=False, label="Description")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Note")


class ReasonForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Reason", max_length=1000)


class OpeningBalanceForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, label="Estimated amount (£)")
    coverage_through = forms.DateField(
        label="Covers spending up to and including", widget=forms.DateInput(attrs={"type": "date"})
    )
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Note")
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Reason for change")
    version = forms.IntegerField(required=False, widget=forms.HiddenInput)


class CostFilterForm(forms.Form):
    project = forms.ChoiceField(required=False)
    merchant = forms.ChoiceField(required=False, label="Retailer")
    date_from = forms.DateField(required=False, label="From", widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, label="To (inclusive)", widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, owner, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Purchase

        self.fields["project"].choices = [("", "All projects")] + [
            (str(p.uuid), p.title) for p in Project.objects.for_owner(owner).order_by("title")
        ]
        merchants = (
            Purchase.objects.for_owner(owner).exclude(merchant="").order_by("merchant")
            .values_list("merchant", flat=True).distinct()
        )
        self.fields["merchant"].choices = [("", "All retailers")] + [(m, m) for m in merchants]
