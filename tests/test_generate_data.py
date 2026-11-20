"""Sanity checks on the generator itself (the answer key must be trustworthy)."""
from decimal import Decimal

from src.generate_data import generate


def test_planted_counts():
    # Proves exactly the specified number of each gap is planted.
    _, _, planted = generate(seed=42)
    assert {k: len(v) for k, v in planted.items()} == {"late": 3, "rounding": 50, "duplicate": 1, "orphan_refund": 1}


def test_size_and_reproducible():
    # Proves n is respected and the same seed gives identical data.
    t1, s1, _ = generate(seed=7)
    t2, s2, _ = generate(seed=7)
    assert len(t1) == 300
    assert t1.equals(t2) and s1.equals(s2)


def test_clean_data_settles_exactly_in_october():
    # Proves plant_gaps=False gives 2-decimal amounts, one settlement each, all in October.
    t, s, planted = generate(plant_gaps=False)
    assert all(a == a.quantize(Decimal("0.01")) for a in t.amount)
    assert s.txn_id.is_unique and set(s.txn_id) == set(t.txn_id)
    assert s.settled_date.str.startswith("2026-10").all()
    assert not any(planted.values())
