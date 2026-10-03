"""Server-side validation and normalisation of provider output into an editable draft.

Schema-valid output is not proof of accuracy. This module:
- converts amounts to Decimal (two places) and rejects junk;
- keeps unknowns empty and flags them for review;
- never prefills foreign or unknown-currency amounts as if they were GBP without a flag;
- never invents items or balancing lines, never adds included tax again;
- leaves project allocation to the owner;
- bounds lengths and rows, and masks long digit runs (card/account numbers).
"""

import datetime
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings

from apps.core.money import format_gbp

DIGIT_RUN = re.compile(r"\d[\d \-]{10,}\d")
CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
CENT = Decimal("0.01")
MAX_ABS = Decimal("99999.99")


class NormaliseError(Exception):
    pass


def _text(value, limit):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = " ".join(value.split())
    value = DIGIT_RUN.sub("••••", value)
    return value[:limit]


def parse_amount(value):
    """Return a two-place Decimal or None. Values with more than two decimals are rejected."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("£", "").replace(" ", "")
    negative = False
    if text.endswith("-"):  # some tills print 2.00-
        negative, text = True, text[:-1]
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or abs(amount) > MAX_ABS:
        return None
    try:
        if amount != amount.quantize(CENT, rounding=ROUND_HALF_UP):
            return None
        amount = amount.quantize(CENT)
    except InvalidOperation:
        return None
    return -amount if negative else amount


def _quantity(value):
    if value in (None, ""):
        return "1"
    try:
        q = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return "1"
    if not q.is_finite() or q <= 0 or q > 9999 or q != q.quantize(Decimal("0.001")):
        return "1"
    return f"{q.normalize():f}"


def _date(value, today):
    if not value:
        return "", None
    try:
        parsed = datetime.date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return "", "The receipt date could not be read."
    if parsed > today + datetime.timedelta(days=1):
        return parsed.isoformat(), "The date read from the receipt is in the future; check it."
    if parsed.year < 2000:
        return "", "The receipt date looked wrong and was left blank."
    return parsed.isoformat(), None


def _blank_line(description, line_type, category, quantity, amount, flag, foreign=""):
    return {
        "description": description, "line_type": line_type, "category": category, "quantity": quantity,
        "unit_price": "", "amount": amount, "shopping": "", "flag": flag, "foreign": foreign,
        "allocations": [{"dest": "", "amount": ""}],
    }


def normalise(raw, today=None):
    """Turn provider JSON into draft data. Raises NormaliseError if it is not usable at all."""
    if not isinstance(raw, dict):
        raise NormaliseError("Result was not an object.")
    today = today or datetime.date.today()
    items = raw.get("items") if isinstance(raw.get("items"), list) else None
    adjustments = raw.get("adjustments") if isinstance(raw.get("adjustments"), list) else []
    if items is None:
        raise NormaliseError("Result had no item list.")

    uncertain = {f for f in (raw.get("uncertain_fields") or []) if f in {"merchant", "receipt_date", "currency", "total", "items"}}
    warnings = [_text(w, 200) for w in (raw.get("warnings") or []) if isinstance(w, str) and w.strip()][:5]

    merchant = _text(raw.get("merchant"), 120)
    if not merchant:
        uncertain.add("merchant")
    date_value, date_warning = _date(raw.get("receipt_date"), today)
    if date_warning:
        warnings.append(date_warning)
    if not date_value:
        uncertain.add("receipt_date")

    currency = _text(raw.get("currency"), 10).strip().upper()
    if not CURRENCY_CODE.match(currency):
        currency = ""
    currency_status = "gbp" if currency == "GBP" else ("foreign" if currency else "unknown")
    prefill = currency_status != "foreign"
    if currency_status == "foreign":
        warnings.append(f"This receipt is in {currency}. Enter the amounts in pounds (GBP) yourself; "
                        "no exchange rate is applied.")
    elif currency_status == "unknown":
        uncertain.add("currency")
        warnings.append("No currency was shown on the receipt. Check the amounts are in pounds (GBP).")

    total = parse_amount(raw.get("total"))
    if raw.get("total") not in (None, "") and total is None:
        warnings.append("The receipt total could not be read as an amount.")
    if total is not None and total < 0:
        warnings.append("The receipt total read as negative and was left blank.")
        total = None
    if total is None:
        uncertain.add("total")

    lines, tax_notes, dropped = [], [], 0
    max_lines = settings.RECEIPT_MAX_LINES

    def add(line):
        nonlocal dropped
        if len(lines) >= max_lines:
            dropped += 1
        else:
            lines.append(line)

    known_sum, unknown_amounts = Decimal("0.00"), 0
    for item in items:
        if not isinstance(item, dict):
            continue
        amount = parse_amount(item.get("line_total"))
        flag = bool(item.get("uncertain")) or amount is None
        if amount is not None and amount < 0:
            # A negative item line is really a discount; keep its sign but label it.
            line_type, category = "discount", "other"
        else:
            line_type, category = "item", "material"
        if amount is None:
            unknown_amounts += 1
        else:
            known_sum += amount
        foreign = f"{currency} {amount}" if (not prefill and amount is not None) else ""
        add(_blank_line(_text(item.get("description"), 160) or "Item", line_type, category,
                        _quantity(item.get("quantity")), str(amount) if (prefill and amount is not None) else "", flag, foreign))

    for adj in adjustments:
        if not isinstance(adj, dict):
            continue
        kind = adj.get("kind")
        description = _text(adj.get("description"), 160)
        amount = parse_amount(adj.get("amount"))
        if kind == "tax_included_note":
            tax_notes.append(description or "Tax included in prices")
            continue  # informational only: never added again
        if kind == "discount":
            line_type = "discount"
            amount = -abs(amount) if amount is not None else None
            description = description or "Discount"
        elif kind == "delivery":
            line_type, description = "shipping", description or "Delivery"
            amount = abs(amount) if amount is not None else None
        elif kind == "rounding":
            line_type, description = "rounding", description or "Rounding"
        elif kind == "tax_added":
            line_type, description = "adjustment", description or "Tax added on top of prices"
        else:
            line_type, description = "adjustment", description or "Adjustment"
        if amount is None:
            unknown_amounts += 1
        else:
            known_sum += amount
        foreign = f"{currency} {amount}" if (not prefill and amount is not None) else ""
        add(_blank_line(description, line_type, "other", "1",
                        str(amount) if (prefill and amount is not None) else "",
                        bool(adj.get("uncertain")) or amount is None, foreign))

    if dropped:
        warnings.append(f"Only the first {max_lines} lines were kept; {dropped} more were not imported.")
    offer_unitemised = False
    reconciled = False
    if not lines:
        uncertain.add("items")
        if total is not None:
            offer_unitemised = True
            warnings.append("No items could be read. After checking the receipt you can record a single "
                            "“Unitemised purchase” line for the total.")
    elif prefill and total is not None:
        if unknown_amounts:
            warnings.append(f"{unknown_amounts} line{'s' if unknown_amounts != 1 else ''} had no readable amount.")
        elif known_sum != total:
            warnings.append(f"Items add up to {format_gbp(known_sum)} but the receipt total is {format_gbp(total)}. "
                            "Add missing items or correct the amounts.")
        else:
            reconciled = True

    return {
        "description": "",
        "merchant": merchant,
        "transaction_date": date_value,
        "total": str(total) if (prefill and total is not None) else "",
        "notes": "",
        "lines": lines,
        "extraction": {
            "currency": currency,
            "currency_status": currency_status,
            "foreign_total": f"{currency} {total}" if (not prefill and total is not None) else "",
            "receipt_number": _text(raw.get("receipt_number"), 40),
            "uncertain_fields": sorted(uncertain),
            "warnings": warnings,
            "tax_notes": tax_notes[:3],
            "reconciled": reconciled,
            "offer_unitemised": offer_unitemised,
            "gbp_confirmation_required": currency_status != "gbp",
        },
    }
