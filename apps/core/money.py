"""Money helpers. All amounts are Decimal GBP with two decimal places."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999.99")


def to_money(value):
    """Convert ``value`` to a two-decimal Decimal. Raises ValueError for junk."""
    if value is None or value == "":
        raise ValueError("Amount is required.")
    if isinstance(value, float):
        # Never trust binary floats for money; go through their repr.
        value = repr(value)
    try:
        amount = Decimal(str(value).replace(",", "").replace("£", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Enter a valid amount.") from exc
    if not amount.is_finite():
        raise ValueError("Enter a valid amount.")
    if amount != amount.quantize(CENT, rounding=ROUND_HALF_UP):
        raise ValueError("Use at most two decimal places.")
    amount = amount.quantize(CENT)
    if abs(amount) > MAX_AMOUNT:
        raise ValueError("Amount is too large.")
    return amount


def money_sum(values):
    total = ZERO
    for value in values:
        total += value or ZERO
    return total.quantize(CENT)


def format_gbp(value, signed=False):
    if value is None:
        return "—"
    value = Decimal(value).quantize(CENT)
    sign = ""
    if value < 0:
        sign = "−"
    elif signed and value > 0:
        sign = "+"
    return f"{sign}£{abs(value):,.2f}"
