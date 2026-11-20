"""Reconcile platform transactions against the bank's itemised settlements for one month.

Every txn_id is classified once, in the first category it matches:
duplicate -> orphan_refund -> late -> rounding -> unexplained.
impact = (bank amount settled in the month) - (platform amount booked in the month),
so platform_total + sum(impacts) == bank_total exactly.
Sign convention: every gap and impact is Bank − Platform. Negative = recorded on the
platform but not yet paid by the bank; positive = paid by the bank but not expected.
"""
from datetime import date
from decimal import Decimal

import pandas as pd

from src.money import TOLERANCE, ZERO, fmt_inr, to_money

CATEGORIES = ["late", "rounding", "duplicate", "orphan_refund"]
LABELS = {"late": "Late settlement", "rounding": "Rounding", "duplicate": "Duplicate",
          "orphan_refund": "Orphan refund", "unexplained": "Unexplained"}
ACTIONS = {
    "late": "Accrue as in-transit; confirm against November statement",
    "rounding": "Book to rounding adjustment account",
    "duplicate": "Raise with bank; reverse duplicate credit",
    "orphan_refund": "Investigate: refund issued without a matching sale",
    "unexplained": "Investigate manually",
}
GAP_COLUMNS = ["category", "txn_id", "platform_amount", "bank_amount", "impact", "explanation", "suggested_action"]


# ---------- loading ----------

def read_transactions(file) -> pd.DataFrame:
    """Read a transactions CSV as strings and convert amount to Decimal."""
    df = pd.read_csv(file, dtype=str, keep_default_na=False)
    df["amount"] = df["amount"].map(to_money)
    return df


def read_settlements(file) -> pd.DataFrame:
    """Read a settlements CSV as strings and convert amount to Decimal."""
    df = pd.read_csv(file, dtype=str, keep_default_na=False)
    df["amount"] = df["amount"].map(to_money)
    return df


# ---------- helpers ----------

def _day(iso: str) -> str:
    """'2026-10-31...' -> '31 Oct'."""
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {d:%b}"


def _total(values) -> Decimal:
    return sum(values, ZERO)


# ---------- classification ----------

def _classify(txn, setts, in_month, all_txn_ids, month):
    """Return the category for one txn_id, or None if it matches."""
    platform = _total(txn.amount) if txn is not None else ZERO
    bank = _total(setts.loc[in_month, "amount"])
    impact = bank - platform
    if len(setts) > 1:
        return "duplicate"
    if txn is not None and (txn.type == "refund").any():
        original = txn.original_txn_id.iloc[0]
        if original not in all_txn_ids:
            return "orphan_refund"
    if txn is not None and len(setts) == 1 and not in_month.any() and setts.settled_date.iloc[0][:7] > month:
        return "late"
    if txn is not None and len(setts) == 1 and ZERO < abs(impact) <= TOLERANCE:
        return "rounding"
    if impact != ZERO:
        return "unexplained"
    return None


def _explain(category, txn_id, txn, setts, platform, bank, impact):
    """Plain-English sentence with real dates and amounts."""
    paid = _day(txn.created_at.iloc[0]) if txn is not None else None
    if category == "late":
        return (f"{txn_id} was paid on {paid} but settled on {_day(setts.settled_date.iloc[0])}, "
                f"so {fmt_inr(platform)} falls into November.")
    if category == "rounding":
        return (f"{txn_id} was booked at {fmt_inr(platform, 4)} but the bank settled {fmt_inr(bank)} "
                f"(rounded half-up), a difference of {fmt_inr(impact, 4)}.")
    if category == "duplicate":
        rows = ", ".join(f"{r.settlement_id} on {_day(r.settled_date)}" for r in setts.itertuples())
        return (f"{txn_id} ({fmt_inr(platform)}, paid {paid}) was settled {len(setts)} times ({rows}); "
                f"the bank credited {fmt_inr(bank)} in the month against {fmt_inr(platform)} booked, "
                f"a difference of {fmt_inr(impact)}.")
    if category == "orphan_refund":
        original = txn.original_txn_id.iloc[0] or "(blank)"
        bank_side = (f"The bank shows no matching debit, so the books are {fmt_inr(impact)} below the bank."
                     if setts.empty else f"The bank debited {fmt_inr(-_total(setts.amount))}.")
        return (f"{txn_id} is a {fmt_inr(-platform)} refund on {paid} for {original}, "
                f"which does not exist in the platform records. {bank_side}")
    if txn is None:
        return f"Bank settled {fmt_inr(bank)} for {txn_id}, but there is no platform transaction for it this month."
    if setts.empty:
        return f"{txn_id} ({fmt_inr(platform)}, paid {paid}) has no settlement at all."
    return f"{txn_id} was booked at {fmt_inr(platform, 4)} but the bank settled {fmt_inr(bank)}."


def _gap_rows(txns, settlements, month):
    """One gap row per txn_id that does not match."""
    in_month_setts = settlements.settled_date.str[:7] == month
    ids = sorted(set(txns.txn_id) | set(settlements.loc[in_month_setts, "txn_id"]))
    all_txn_ids = set(txns.txn_id)
    txn_groups = dict(tuple(txns.groupby("txn_id")))
    sett_groups = dict(tuple(settlements.groupby("txn_id")))
    empty = settlements.iloc[0:0]
    rows = []
    for txn_id in ids:
        txn = txn_groups.get(txn_id)
        setts = sett_groups.get(txn_id, empty)
        in_month = setts.settled_date.str[:7] == month
        category = _classify(txn, setts, in_month, all_txn_ids, month)
        if category is None:
            continue
        platform = _total(txn.amount) if txn is not None else ZERO
        bank = _total(setts.loc[in_month, "amount"])
        rows.append({"category": category, "txn_id": txn_id, "platform_amount": platform,
                     "bank_amount": bank, "impact": bank - platform,
                     "explanation": _explain(category, txn_id, txn, setts, platform, bank, bank - platform),
                     "suggested_action": ACTIONS[category]})
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def reconcile(transactions_df, settlements_df, month="2026-10"):
    """Reconcile one month. Returns totals, a gaps table and a bridge (impact per category)."""
    txns = transactions_df[transactions_df.created_at.str[:7] == month]
    settled_in_month = settlements_df[settlements_df.settled_date.str[:7] == month]
    platform_total = _total(txns.amount)
    bank_total = _total(settled_in_month.amount)
    total_gap = bank_total - platform_total
    gaps = _gap_rows(txns, settlements_df, month)
    bridge = {c: _total(gaps.loc[gaps.category == c, "impact"]) for c in CATEGORIES}
    bridge["unexplained"] = total_gap - _total(bridge.values())
    return {"platform_total": platform_total, "bank_total": bank_total,
            "total_gap": total_gap, "gaps": gaps, "bridge": bridge}


def summary_line(result) -> str:
    """'Gap (Bank − Platform): ₹X = ₹A late + ₹B rounding + ...' in one line."""
    b = result["bridge"]
    parts = ""
    for i, c in enumerate([*CATEGORIES, "unexplained"]):
        amount, label = b[c], LABELS[c].lower()
        if i == 0:
            parts = f"{fmt_inr(amount)} {label}"
        else:
            parts += f" {'-' if amount < 0 else '+'} {fmt_inr(abs(amount))} {label}"
    return f"Gap (Bank − Platform): {fmt_inr(result['total_gap'])} = {parts}"
