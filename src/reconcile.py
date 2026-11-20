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

from src.money import TOLERANCE, ZERO, fmt_inr

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
PLATFORM_DUPLICATE_ACTION = "Reverse the duplicate platform entry"
UNKNOWN_CREDIT_ACTION = "Investigate unknown bank credit; do not book until matched"
PRIOR_MONTH_ACTION = "Clear against the earlier month's in-transit accrual"
GAP_COLUMNS = ["category", "txn_id", "platform_amount", "bank_amount", "impact", "explanation", "suggested_action"]


# ---------- helpers ----------

def _day(iso: str) -> str:
    """'2026-10-31...' -> '31 Oct'."""
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {d:%b}"


def _total(values) -> Decimal:
    return sum(values, ZERO)


# ---------- classification ----------

def _classify(txn, setts, in_month, known_ids, month):
    """Return the category for one txn_id, or None if it matches.

    txn: this id's platform rows in the month (None if none); setts: all its bank rows;
    known_ids: every txn_id in the full transactions file (any month).
    """
    platform = _total(txn.amount) if txn is not None else ZERO
    impact = _total(setts.loc[in_month, "amount"]) - platform
    if len(setts) > 1 or (txn is not None and len(txn) > 1):
        return "duplicate"
    if txn is not None and txn.type.iloc[0] == "refund" and txn.original_txn_id.iloc[0] not in known_ids:
        return "orphan_refund"
    if txn is not None and len(setts) == 1 and not in_month.any() and setts.settled_date.iloc[0][:7] > month:
        return "late"
    if txn is not None and len(setts) == 1 and ZERO < abs(impact) <= TOLERANCE:
        return "rounding"
    if impact != ZERO:
        return "unexplained"
    return None


# ---------- explanations: (sentence, suggested action) ----------

def _explain_duplicate(txn_id, txn, setts, platform, bank, impact):
    if len(txn) > 1:
        one = txn.amount.iloc[0]
        return (f"{txn_id} appears {len(txn)} times in the platform records ({fmt_inr(one)} each, "
                f"{fmt_inr(platform)} booked) but the bank settled {fmt_inr(bank)} in the month, "
                f"a difference of {fmt_inr(impact)}.", PLATFORM_DUPLICATE_ACTION)
    rows = ", ".join(f"{r.settlement_id} on {_day(r.settled_date)}" for r in setts.itertuples())
    return (f"{txn_id} ({fmt_inr(platform)}, paid {_day(txn.created_at.iloc[0])}) was settled {len(setts)} times "
            f"({rows}); the bank credited {fmt_inr(bank)} in the month against {fmt_inr(platform)} booked, "
            f"a difference of {fmt_inr(impact)}.", ACTIONS["duplicate"])


def _explain_orphan(txn_id, txn, setts, platform, impact):
    original = txn.original_txn_id.iloc[0] or "(blank)"
    if setts.empty:
        bank_side = f"The bank shows no matching debit, so the books are {fmt_inr(impact)} below the bank."
    else:
        bank_side = (f"The bank debited {fmt_inr(-_total(setts.amount))} on {_day(setts.settled_date.iloc[0])}, "
                     f"so it nets to {fmt_inr(impact)} in the gap, but money left with no matching sale.")
    return (f"{txn_id} is a {fmt_inr(-platform)} refund on {_day(txn.created_at.iloc[0])} for {original}, "
            f"which does not exist in the platform records. {bank_side}", ACTIONS["orphan_refund"])


def _explain_bank_only(txn_id, bank, all_txns):
    """A settlement in the month with no platform transaction in the month."""
    elsewhere = all_txns[all_txns.txn_id == txn_id]
    if not elsewhere.empty:
        paid = elsewhere.created_at.iloc[0]
        return (f"Bank settled {fmt_inr(bank)} for {txn_id}, which was paid on {_day(paid)} {paid[:4]}, "
                f"outside this month.", PRIOR_MONTH_ACTION)
    return (f"Bank settled {fmt_inr(bank)} for {txn_id}, which does not exist anywhere in the platform records.",
            UNKNOWN_CREDIT_ACTION)


def _explain(category, txn_id, txn, setts, platform, bank, impact, all_txns):
    """Plain-English sentence with real dates and amounts, plus the suggested action."""
    if category == "duplicate":
        return _explain_duplicate(txn_id, txn, setts, platform, bank, impact)
    if category == "orphan_refund":
        return _explain_orphan(txn_id, txn, setts, platform, impact)
    if category == "late":
        return (f"{txn_id} was paid on {_day(txn.created_at.iloc[0])} but settled on "
                f"{_day(setts.settled_date.iloc[0])}, so {fmt_inr(platform)} falls into November.", ACTIONS["late"])
    if category == "rounding":
        return (f"{txn_id} was booked at {fmt_inr(platform, 4)} but the bank settled {fmt_inr(bank)} "
                f"(rounded half-up), a difference of {fmt_inr(impact, 4)}.", ACTIONS["rounding"])
    if txn is None:
        return _explain_bank_only(txn_id, bank, all_txns)
    if setts.empty:
        return f"{txn_id} ({fmt_inr(platform)}, paid {_day(txn.created_at.iloc[0])}) has no settlement at all.", \
            ACTIONS["unexplained"]
    return f"{txn_id} was booked at {fmt_inr(platform, 4)} but the bank settled {fmt_inr(bank)}.", \
        ACTIONS["unexplained"]


def _gap_rows(month_txns, all_txns, settlements, month):
    """One gap row per txn_id that does not match."""
    in_month_setts = settlements.settled_date.str[:7] == month
    ids = sorted(set(month_txns.txn_id) | set(settlements.loc[in_month_setts, "txn_id"]))
    known_ids = set(all_txns.txn_id)
    txn_groups = dict(tuple(month_txns.groupby("txn_id")))
    sett_groups = dict(tuple(settlements.groupby("txn_id")))
    empty = settlements.iloc[0:0]
    rows = []
    for txn_id in ids:
        txn = txn_groups.get(txn_id)
        setts = sett_groups.get(txn_id, empty)
        in_month = setts.settled_date.str[:7] == month
        category = _classify(txn, setts, in_month, known_ids, month)
        if category is None:
            continue
        platform = _total(txn.amount) if txn is not None else ZERO
        bank = _total(setts.loc[in_month, "amount"])
        explanation, action = _explain(category, txn_id, txn, setts, platform, bank, bank - platform, all_txns)
        rows.append({"category": category, "txn_id": txn_id, "platform_amount": platform, "bank_amount": bank,
                     "impact": bank - platform, "explanation": explanation, "suggested_action": action})
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def reconcile(transactions_df, settlements_df, month="2026-10"):
    """Reconcile one month. Returns totals, a gaps table and a bridge (impact per category)."""
    month_txns = transactions_df[transactions_df.created_at.str[:7] == month]
    settled_in_month = settlements_df[settlements_df.settled_date.str[:7] == month]
    platform_total = _total(month_txns.amount)
    bank_total = _total(settled_in_month.amount)
    total_gap = bank_total - platform_total
    gaps = _gap_rows(month_txns, transactions_df, settlements_df, month)
    bridge = {c: _total(gaps.loc[gaps.category == c, "impact"]) for c in CATEGORIES}
    bridge["unexplained"] = total_gap - _total(bridge.values())
    return {"platform_total": platform_total, "bank_total": bank_total,
            "total_gap": total_gap, "gaps": gaps, "bridge": bridge}


def exception_split(result) -> dict:
    """Gross exceptions = sum of |impact| over every gap row, split by what finance must do.

    timing = late (reverses next month); action = duplicate + orphan refund;
    booked = rounding (to the adjustment account); unexplained = anything else.
    Uses per-row absolute values, so offsetting rows inside one category can't hide each other.
    """
    gaps = result["gaps"]

    def gross(categories):
        return _total(abs(v) for v in gaps.loc[gaps.category.isin(categories), "impact"])

    split = {"timing": gross(["late"]), "action": gross(["duplicate", "orphan_refund"]),
             "booked": gross(["rounding"]), "unexplained": gross(["unexplained"])}
    split["gross"] = _total(split.values())
    return split


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
