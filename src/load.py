"""Read and validate uploaded CSVs. Bad input raises DataError with a readable message."""
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd

TRANSACTION_COLUMNS = ["txn_id", "created_at", "customer_id", "amount", "type", "original_txn_id"]
SETTLEMENT_COLUMNS = ["settlement_id", "txn_id", "settled_date", "amount"]
MAX_ERRORS_SHOWN = 5


class DataError(ValueError):
    """Raised when an uploaded file can't be reconciled safely."""


def parse_amount(text: str) -> Decimal:
    """'₹1,25,000.50' -> Decimal('125000.50'). Strips ₹, commas and spaces; nothing else."""
    cleaned = text.replace("₹", "").replace(",", "").replace(" ", "").strip()
    if not cleaned:
        raise ValueError("blank")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not a number: {text!r}") from None


def _is_iso_date(value: str) -> bool:
    """True for '2026-10-31' or '2026-10-31 18:00:00' (a real calendar date)."""
    try:
        date.fromisoformat(value.strip()[:10])
        return len(value.strip()) >= 10
    except ValueError:
        return False


def _problems(df, name, rows_with_issue):
    """Format up to MAX_ERRORS_SHOWN problems as 'row N: reason' (row 2 = first data row)."""
    shown = [f"row {i + 2}: {reason}" for i, reason in rows_with_issue[:MAX_ERRORS_SHOWN]]
    more = len(rows_with_issue) - len(shown)
    return f"{name}: " + "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def _read(file, name, required, date_column):
    """Read as strings, check columns, parse amounts and dates. Extra columns are ignored."""
    try:
        df = pd.read_csv(file, dtype=str, keep_default_na=False)
    except Exception as e:  # empty file, binary file, broken quoting
        raise DataError(f"{name}: could not read as CSV ({e}).") from None
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataError(f"{name}: missing column(s) {', '.join(missing)}. Expected: {', '.join(required)}.")
    issues = []
    amounts = []
    for i, text in enumerate(df["amount"]):
        try:
            amounts.append(parse_amount(text))
        except ValueError as e:
            issues.append((i, f"amount is {e}"))
            amounts.append(None)
    for i, value in enumerate(df[date_column]):
        if not _is_iso_date(value):
            issues.append((i, f"{date_column} {value!r} is not YYYY-MM-DD"))
    for i, value in enumerate(df["txn_id"]):
        if not value.strip():
            issues.append((i, "txn_id is blank"))
    if issues:
        raise DataError(_problems(df, name, sorted(issues)))
    df["amount"] = amounts
    return df


def read_transactions(file) -> pd.DataFrame:
    """Read and validate a transactions CSV. Amounts become Decimal."""
    df = _read(file, "transactions.csv", TRANSACTION_COLUMNS, "created_at")
    bad_types = [(i, f"type {v!r} is not payment/refund") for i, v in enumerate(df["type"])
                 if v not in ("payment", "refund")]
    if bad_types:
        raise DataError(_problems(df, "transactions.csv", bad_types))
    return df


def read_settlements(file) -> pd.DataFrame:
    """Read and validate a settlements CSV. Amounts become Decimal."""
    return _read(file, "settlements.csv", SETTLEMENT_COLUMNS, "settled_date")
