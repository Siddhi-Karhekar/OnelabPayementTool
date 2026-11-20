"""Generate October 2026 platform transactions and bank settlements, with planted gaps.

Run `python -m src.generate_data` to write data/transactions.csv,
data/settlements.csv and data/planted_gaps.json.
"""
import json
import random
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.money import PAISA, bank_round

N_ROUNDING, N_LATE, N_REFUNDS = 50, 3, 10
ORPHAN_ORIGINAL_ID = "TXN-9999"  # an id that never exists


def _random_time(rng, first_day, last_day):
    """Random datetime in October 2026 between two day numbers (inclusive)."""
    day = rng.randint(first_day, last_day)
    return datetime(2026, 10, day, rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59))


def _clean_amount(rng):
    """A normal payment amount with at most 2 decimals (settles exactly)."""
    return (Decimal(rng.randint(10_000, 500_000)) / 100).quantize(PAISA)


def _rounding_amount(rng):
    """A 4-decimal amount ending in .xx5x, so half-up rounding always goes up."""
    rupees = Decimal(rng.randint(100, 5_000))
    paise = Decimal(rng.randint(0, 99)) / 100
    amount = rupees + paise + Decimal("0.005") + Decimal(rng.randint(0, 9)) / 10_000
    return amount.quantize(Decimal("0.0001"))


def _payment(rng, kind, created_at, amount, lag_days):
    """One payment row plus the date it settles."""
    return {"kind": kind, "created_at": created_at, "amount": amount, "type": "payment",
            "original": None, "settle_on": created_at.date() + timedelta(days=lag_days)}


def _build_rows(rng, n, plant_gaps):
    """Build payment/refund rows (before ids are assigned)."""
    n_special = (N_ROUNDING + N_LATE + 1) if plant_gaps else 0
    rows = []
    # Normal payments are made on 1–29 Oct so a 1–2 day lag always settles in October.
    for _ in range(n - N_REFUNDS - n_special):
        rows.append(_payment(rng, "normal", _random_time(rng, 1, 29), _clean_amount(rng), rng.randint(1, 2)))
    if plant_gaps:
        for _ in range(N_ROUNDING):
            rows.append(_payment(rng, "rounding", _random_time(rng, 1, 29), _rounding_amount(rng), rng.randint(1, 2)))
        for _ in range(N_LATE):
            rows.append(_payment(rng, "late", _random_time(rng, 31, 31), _clean_amount(rng), rng.randint(1, 2)))
    # Genuine full refunds of earlier normal payments, settled as negative bank rows.
    early = [r for r in rows if r["kind"] == "normal" and r["created_at"].day <= 25]
    for original in rng.sample(early, N_REFUNDS):
        created = original["created_at"] + timedelta(days=rng.randint(1, 3))
        rows.append({"kind": "refund", "created_at": created, "amount": -original["amount"], "type": "refund",
                     "original": original, "settle_on": created.date() + timedelta(days=1)})
    if plant_gaps:
        # Orphan refund: points at a sale that does not exist. Assumption: the processor
        # cannot refund a non-existent capture, so there is no bank settlement for it.
        rows.append({"kind": "orphan_refund", "created_at": _random_time(rng, 10, 20),
                     "amount": -_clean_amount(rng), "type": "refund", "original": "ORPHAN", "settle_on": None})
    return rows


def _to_frames(rng, rows, plant_gaps):
    """Assign ids in time order and build the two DataFrames plus the answer key."""
    rows.sort(key=lambda r: r["created_at"])
    for i, r in enumerate(rows, start=1):
        r["txn_id"] = f"TXN-{i:04d}"
    planted = {"late": [], "rounding": [], "duplicate": [], "orphan_refund": []}
    txns, setts = [], []
    for r in rows:
        if r["original"] == "ORPHAN":
            original_id = ORPHAN_ORIGINAL_ID
        else:
            original_id = r["original"]["txn_id"] if r["original"] else ""
        txns.append({"txn_id": r["txn_id"], "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                     "customer_id": f"CUST-{rng.randint(1, 120):03d}", "amount": r["amount"],
                     "type": r["type"], "original_txn_id": original_id})
        if r["kind"] in planted:
            planted[r["kind"]].append(r["txn_id"])
        if r["settle_on"] is not None:
            setts.append({"txn_id": r["txn_id"], "settled_date": r["settle_on"].isoformat(),
                          "amount": bank_round(r["amount"])})
    setts.sort(key=lambda s: (s["settled_date"], s["txn_id"]))
    if plant_gaps:
        # Duplicate: re-send one normal October settlement under a new settlement id.
        normal_ids = {r["txn_id"] for r in rows if r["kind"] == "normal"}
        dup = rng.choice([s for s in setts if s["txn_id"] in normal_ids])
        setts.append(dict(dup))
        planted["duplicate"].append(dup["txn_id"])
    for i, s in enumerate(setts, start=1):
        s["settlement_id"] = f"SET-{i:04d}"
    settlements = pd.DataFrame(setts)[["settlement_id", "txn_id", "settled_date", "amount"]]
    return pd.DataFrame(txns), settlements, planted


def generate(seed=42, n=300, plant_gaps=True):
    """Return (transactions_df, settlements_df, planted) for October 2026.

    planted maps each gap type to the exact txn_ids planted (the answer key).
    With plant_gaps=False every transaction settles exactly, in October.
    """
    rng = random.Random(seed)
    rows = _build_rows(rng, n, plant_gaps)
    return _to_frames(rng, rows, plant_gaps)


def save(transactions, settlements, planted, out_dir="data"):
    """Write the two CSVs and the answer key JSON."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    transactions.to_csv(out / "transactions.csv", index=False)
    settlements.to_csv(out / "settlements.csv", index=False)
    (out / "planted_gaps.json").write_text(json.dumps(planted, indent=2))


if __name__ == "__main__":
    t, s, p = generate()
    save(t, s, p)
    print(f"Wrote {len(t)} transactions, {len(s)} settlements. Planted: "
          + ", ".join(f"{k}={len(v)}" for k, v in p.items()))
