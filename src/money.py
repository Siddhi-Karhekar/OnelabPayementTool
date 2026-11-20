"""Money helpers. All amounts are Decimal; floats are never used for money."""
from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0")
PAISA = Decimal("0.01")
TOLERANCE = Decimal("0.01")  # max per-row rounding difference


def to_money(value) -> Decimal:
    """Convert a CSV string (or Decimal) to Decimal. Rejects floats."""
    if isinstance(value, float):
        raise TypeError("Floats are not allowed for money; pass a string.")
    return Decimal(str(value).strip())


def bank_round(amount: Decimal) -> Decimal:
    """Round the way the bank does: half-up to 2 decimals."""
    return amount.quantize(PAISA, rounding=ROUND_HALF_UP)


def fmt_inr(amount: Decimal, places: int = 2) -> str:
    """Format as ₹ with thousands separators, e.g. -₹1,250.00."""
    q = amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "-" if q < 0 else ""
    return f"{sign}₹{abs(q):,.{places}f}"
