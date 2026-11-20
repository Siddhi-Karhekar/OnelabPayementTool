"""Upload validation: bad files raise a readable DataError, never a stack trace."""
import io
from decimal import Decimal

import pytest

from src.generate_data import generate
from src.load import DataError, read_settlements, read_transactions
from src.reconcile import reconcile


@pytest.fixture(scope="module")
def csvs():
    t, s, _ = generate(seed=42)
    return t, s


def load_t(df_or_text):
    text = df_or_text if isinstance(df_or_text, str) else df_or_text.to_csv(index=False)
    return read_transactions(io.StringIO(text))


def test_extra_column_is_ignored(csvs):
    # Proves an extra column doesn't break loading or change the result.
    t, s = csvs
    loaded = load_t(t.assign(note="hello"))
    assert reconcile(loaded, s)["total_gap"] == reconcile(t, s)["total_gap"]


def test_missing_column_names_the_column(csvs):
    # Proves a missing required column gives a clear message naming it.
    t, _ = csvs
    with pytest.raises(DataError, match="missing column.*type"):
        load_t(t.drop(columns="type"))


def test_blank_amount_reports_row(csvs):
    # Proves a blank amount is rejected with its row number, not a decimal.InvalidOperation.
    t, _ = csvs
    with pytest.raises(DataError, match=r"row 2: amount is blank"):
        load_t(t.assign(amount=[""] + list(t.amount[1:])))


def test_rupee_symbol_and_commas_are_parsed(csvs):
    # Proves '₹1,841.60' and Indian grouping '₹1,25,000.50' parse to exact Decimals.
    t, _ = csvs
    text = t.to_csv(index=False).replace("1841.60", '"₹1,841.60"', 1).replace("1224.9754", '"₹1,25,000.50"', 1)
    loaded = load_t(text)
    assert loaded.amount.iloc[0] == Decimal("1841.60")
    assert loaded.amount.iloc[1] == Decimal("125000.50")


def test_non_numeric_amount_rejected(csvs):
    # Proves junk like 'abc' or '12.3.4' is rejected rather than silently stripped.
    t, _ = csvs
    with pytest.raises(DataError, match="not a number"):
        load_t(t.assign(amount=["12.3.4"] + list(t.amount[1:])))


def test_non_iso_date_rejected_not_silently_dropped(csvs):
    # Proves '01/10/2026' is an error; before the fix the row silently fell out of October.
    t, _ = csvs
    t2 = t.copy()
    t2.loc[0, "created_at"] = "01/10/2026 05:47"
    with pytest.raises(DataError, match="created_at '01/10/2026 05:47' is not YYYY-MM-DD"):
        load_t(t2)


def test_impossible_date_rejected(csvs):
    # Proves a well-shaped but impossible date (month 13) is caught at load time.
    _, s = csvs
    s2 = s.copy()
    s2.loc[0, "settled_date"] = "2026-13-45"
    with pytest.raises(DataError, match="settled_date"):
        read_settlements(io.StringIO(s2.to_csv(index=False)))


def test_unknown_type_rejected(csvs):
    # Proves a type other than payment/refund is rejected (it would skip the orphan check).
    t, _ = csvs
    t2 = t.copy()
    t2.loc[0, "type"] = "Refund "
    with pytest.raises(DataError, match="is not payment/refund"):
        load_t(t2)


def test_many_errors_are_summarised(csvs):
    # Proves a file full of errors shows the first 5 and a count, not a wall of text.
    t, _ = csvs
    with pytest.raises(DataError, match=r"and 295 more"):
        load_t(t.assign(amount=""))
