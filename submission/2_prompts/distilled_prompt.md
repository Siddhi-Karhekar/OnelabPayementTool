Build "Month-End Reconciliation Assistant": a Streamlit app that finds and explains why a payments platform's transactions don't match bank settlements. Keep code simple and readable — a reviewer should understand any file in 2 minutes.

STACK: Python 3.11, pandas, Streamlit, Plotly, pytest. No database, no auth.

ASSUMPTIONS (also show these in the app)
1. Single currency INR. Reconciliation month: October 2026.
2. One settlement record per transaction, linked by txn_id, settled 1–2 days after payment.
3. Platform stores amounts to 4 decimals; the bank settles each amount rounded HALF-UP to 2 decimals. All money uses Python Decimal (never float, never round()). CSVs are read with dtype=str and converted to Decimal explicitly.
4. Refunds are negative transactions with type="refund" and an original_txn_id.
5. Per-row rounding tolerance: ≤ ₹0.01.
6. Matching is at the transaction level against the processor's itemised settlement report. Real banks deposit in batches; deposit-level matching is out of scope and listed as the next step. Fees, FX and chargebacks are out of scope.

1. DATA GENERATOR — src/generate_data.py
generate(seed=42, n=300, plant_gaps=True) -> (transactions_df, settlements_df, planted: dict)
- transactions: txn_id, created_at, customer_id, amount, type (payment|refund), original_txn_id
- settlements: settlement_id, txn_id, settled_date, amount
- Plant exactly:
  a) LATE: 3 payments on Oct 31 that settle Nov 1–2.
  b) ROUNDING: 50 payments with 4-decimal amounts ending in .xx5x (e.g. 199.9950, 349.4957) so every row rounds UP under half-up. Each row differs by < ₹0.01; total drift ≈ ₹0.25.
  c) DUPLICATE: 1 settlement row duplicated (same txn_id, new settlement_id).
  d) ORPHAN REFUND: 1 refund whose original_txn_id does not exist.
- All other amounts have at most 2 decimals so they settle exactly.
- planted dict records the exact txn_ids of each planted gap (this is the answer key).
- plant_gaps=False must produce perfectly matching data.
- Also save to data/transactions.csv, data/settlements.csv, data/planted_gaps.json.

2. RECONCILIATION ENGINE — src/reconcile.py
reconcile(transactions_df, settlements_df, month="2026-10") -> dict with:
- platform_total, bank_total, total_gap (all Decimal)
- gaps: DataFrame [category, txn_id, platform_amount, bank_amount, impact, explanation, suggested_action]
- bridge: impact per category + unexplained residual (must be ₹0.00 on generated data)
Check order: duplicates → orphan refunds → late settlements → rounding → unexplained. Each record is classified once, in the first category it matches.
Each explanation is a plain-English sentence with real dates and amounts, e.g. "TXN-0482 was paid on 31 Oct but settled on 1 Nov, so ₹1,250.00 falls into November."
Suggested actions:
- Late → "Accrue as in-transit; confirm against November statement"
- Rounding → "Book to rounding adjustment account"
- Duplicate → "Raise with bank; reverse duplicate credit"
- Orphan refund → "Investigate: refund issued without a matching sale"

3. TESTS — tests/test_reconcile.py (one-line comment on each saying what it proves)
- One test per gap type: detected txn_ids == planted txn_ids
- Clean data (plant_gaps=False) → zero gaps in every category
- Rounding: every row diff ≤ ₹0.01 but the total > ₹0.20
- Rounding direction: every planted rounding row has bank_amount > platform_amount (drift doesn't cancel)
- Bridge residual == ₹0.00 across seeds 1, 42, 99
- Edge case: a duplicate that is also late is counted once, in the correct category
- Decimal safety: no float values in any money column

4. APP — app.py
- Sidebar: "Generate sample data" (seed input) or upload two CSVs; assumptions in an expander.
- Top: 3 metric cards — Platform total, Bank total, Gap.
- Plotly waterfall: Platform total → each gap category → Bank total.
- One-line summary: "₹X gap = ₹A late + ₹B rounding + ₹C duplicate + ₹D orphan refund + ₹0.00 unexplained".
- Self-check panel (generated data only): "Planted vs Detected 4/4 ✅", one row per gap type.
- Tabs per gap category: gaps table with explanation and suggested action.
- Download full gap report as CSV.
- Format all money as ₹ with thousands separators and 2 decimals.

5. FILES: src/, tests/, data/, app.py, requirements.txt (pinned), README.md

WORKING STYLE
Build in order: generator → engine → tests → app. Run pytest after each stage and fix failures before moving on. Commit after each working stage with a clear message. If you change an assumption, say so explicitly. Keep functions short with brief docstrings.

STRETCH (only if all tests pass and I explicitly ask): group settlements into daily batch deposits and add a deposit-level view with one test. Do not build this unless asked.