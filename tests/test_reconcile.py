"""Tests for the reconciliation engine, checked against the generator's answer key."""
from decimal import Decimal

import pandas as pd
import pytest

from src.generate_data import generate
from src.load import read_settlements, read_transactions
from src.reconcile import CATEGORIES, reconcile

MONEY_COLUMNS = ["platform_amount", "bank_amount", "impact"]


@pytest.fixture(scope="module")
def planted_run():
    t, s, planted = generate(seed=42)
    return reconcile(t, s), planted


def detected(result, category):
    gaps = result["gaps"]
    return sorted(gaps.loc[gaps.category == category, "txn_id"])


@pytest.mark.parametrize("category", CATEGORIES)
def test_each_gap_type_detected_exactly(planted_run, category):
    # Proves each gap type finds exactly the planted txn_ids: no misses, no false positives.
    result, planted = planted_run
    assert detected(result, category) == sorted(planted[category])


def test_clean_data_has_no_gaps():
    # Proves perfectly matching data produces zero gaps in every category and a zero total gap.
    t, s, _ = generate(seed=42, plant_gaps=False)
    result = reconcile(t, s)
    assert result["gaps"].empty
    assert result["total_gap"] == Decimal("0")
    assert all(v == Decimal("0") for v in result["bridge"].values())


def test_rounding_invisible_per_row_but_visible_in_total(planted_run):
    # Proves the rounding gap is <= ₹0.01 on every row yet adds up to more than ₹0.20.
    result, _ = planted_run
    rows = result["gaps"][result["gaps"].category == "rounding"]
    assert all(abs(i) <= Decimal("0.01") for i in rows.impact)
    assert result["bridge"]["rounding"] > Decimal("0.20")


def test_rounding_always_goes_up(planted_run):
    # Proves half-up rounding moves every planted row the same way, so the drift can't cancel out.
    result, _ = planted_run
    rows = result["gaps"][result["gaps"].category == "rounding"]
    assert all(b > p for b, p in zip(rows.bank_amount, rows.platform_amount))


@pytest.mark.parametrize("seed", [1, 42, 99])
def test_bridge_residual_is_zero(seed):
    # Proves the four categories fully explain the gap: platform + bridge == bank, to the paisa.
    t, s, _ = generate(seed=seed)
    result = reconcile(t, s)
    assert result["bridge"]["unexplained"] == Decimal("0")
    assert not (result["gaps"].category == "unexplained").any()
    gap_impacts = sum(result["gaps"].impact, Decimal("0"))
    assert result["platform_total"] + gap_impacts == result["bank_total"]


def test_duplicate_that_is_also_late_counted_once():
    # Proves a record matching two categories appears once, in the first (duplicate), not also as late.
    t, s, _ = generate(seed=42, plant_gaps=False)
    txn_id = t.txn_id.iloc[-1]
    t.loc[t.txn_id == txn_id, "created_at"] = "2026-10-31 18:00:00"
    s.loc[s.txn_id == txn_id, "settled_date"] = "2026-11-01"
    extra = s[s.txn_id == txn_id].assign(settlement_id="SET-DUP1", settled_date="2026-11-02")
    result = reconcile(t, pd.concat([s, extra], ignore_index=True))
    rows = result["gaps"][result["gaps"].txn_id == txn_id]
    assert len(rows) == 1 and rows.category.iloc[0] == "duplicate"
    assert result["bridge"]["late"] == Decimal("0")
    assert result["bridge"]["unexplained"] == Decimal("0")


def test_orphan_refund_flagged_even_when_bank_settles_it():
    # Proves an orphan refund the processor pushed through (₹0 net gap) is still flagged, not hidden.
    t, s, planted = generate(seed=42)
    orphan_id = planted["orphan_refund"][0]
    refund = t[t.txn_id == orphan_id].iloc[0]
    bank_row = pd.DataFrame([{"settlement_id": "SET-ORPH", "txn_id": orphan_id,
                              "settled_date": "2026-10-16", "amount": refund.amount}])
    result = reconcile(t, pd.concat([s, bank_row], ignore_index=True))
    rows = result["gaps"][result["gaps"].txn_id == orphan_id]
    assert len(rows) == 1 and rows.category.iloc[0] == "orphan_refund"
    assert rows.impact.iloc[0] == Decimal("0")
    assert result["bridge"]["orphan_refund"] == Decimal("0")
    assert result["bridge"]["unexplained"] == Decimal("0")


def _add_settlement(s, txn_id, amount, settled_date="2026-10-10"):
    row = pd.DataFrame([{"settlement_id": "SET-X", "txn_id": txn_id, "settled_date": settled_date,
                         "amount": Decimal(amount)}])
    return pd.concat([s, row], ignore_index=True)


def test_bank_only_settlement_is_unexplained_unknown_credit():
    # Proves a settlement for a txn_id that exists nowhere lands in unexplained, with the
    # residual raised by exactly that amount and an action not to book it as revenue.
    t, s, _ = generate(seed=42)
    result = reconcile(t, _add_settlement(s, "TXN-7777", "500.00"))
    row = result["gaps"][result["gaps"].txn_id == "TXN-7777"].iloc[0]
    assert row.category == "unexplained" and row.impact == Decimal("500.00")
    assert "does not exist anywhere" in row.explanation
    assert row.suggested_action.startswith("Investigate unknown bank credit")
    assert result["bridge"]["unexplained"] == Decimal("500.00")


def test_settlement_for_prior_month_transaction_is_explained_as_such():
    # Proves an October settlement of a September payment says so, instead of 'does not exist'.
    t, s, _ = generate(seed=42)
    sept = pd.DataFrame([{"txn_id": "TXN-S001", "created_at": "2026-09-30 22:00:00", "customer_id": "CUST-001",
                          "amount": Decimal("750.00"), "type": "payment", "original_txn_id": ""}])
    result = reconcile(pd.concat([t, sept], ignore_index=True), _add_settlement(s, "TXN-S001", "750.00", "2026-10-01"))
    row = result["gaps"][result["gaps"].txn_id == "TXN-S001"].iloc[0]
    assert row.category == "unexplained"
    assert "paid on 30 Sep 2026, outside this month" in row.explanation


def test_platform_side_duplicate_is_a_duplicate():
    # Proves a txn_id recorded twice on the platform (bank once) is a duplicate, not unexplained.
    t, s, _ = generate(seed=42, plant_gaps=False)
    t2 = pd.concat([t, t[t.txn_id == "TXN-0001"]], ignore_index=True)
    result = reconcile(t2, s)
    rows = result["gaps"][result["gaps"].txn_id == "TXN-0001"]
    assert len(rows) == 1 and rows.category.iloc[0] == "duplicate"
    assert rows.impact.iloc[0] == -t.amount.iloc[0]
    assert "appears 2 times in the platform records" in rows.explanation.iloc[0]
    assert rows.suggested_action.iloc[0] == "Reverse the duplicate platform entry"
    assert result["bridge"]["unexplained"] == Decimal("0")


def test_refund_of_prior_month_sale_is_not_an_orphan():
    # Proves the orphan check looks at every transaction, not just this month's.
    t, s, _ = generate(seed=42, plant_gaps=False)
    sept = pd.DataFrame([
        {"txn_id": "TXN-S002", "created_at": "2026-09-20 10:00:00", "customer_id": "CUST-002",
         "amount": Decimal("400.00"), "type": "payment", "original_txn_id": ""},
        {"txn_id": "TXN-R002", "created_at": "2026-10-05 10:00:00", "customer_id": "CUST-002",
         "amount": Decimal("-400.00"), "type": "refund", "original_txn_id": "TXN-S002"}])
    result = reconcile(pd.concat([t, sept], ignore_index=True), _add_settlement(s, "TXN-R002", "-400.00", "2026-10-06"))
    assert result["gaps"].empty


def test_no_floats_in_money_columns(planted_run, tmp_path):
    # Proves money stays Decimal end to end, including after a CSV round trip.
    result, _ = planted_run
    for col in MONEY_COLUMNS:
        assert all(isinstance(v, Decimal) for v in result["gaps"][col])
    for key in ["platform_total", "bank_total", "total_gap"]:
        assert isinstance(result[key], Decimal)
    t, s, _ = generate(seed=42)
    t.to_csv(tmp_path / "t.csv", index=False)
    s.to_csv(tmp_path / "s.csv", index=False)
    t2, s2 = read_transactions(tmp_path / "t.csv"), read_settlements(tmp_path / "s.csv")
    assert all(isinstance(v, Decimal) for v in t2.amount) and all(isinstance(v, Decimal) for v in s2.amount)
    assert reconcile(t2, s2)["total_gap"] == result["total_gap"]
