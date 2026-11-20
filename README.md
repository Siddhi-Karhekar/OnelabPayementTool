# Month-End Reconciliation Assistant

A payments platform records each transaction the moment a customer pays. The bank settles the funds 1–2 days later. At month end, every transaction should have a matching settlement, but the totals don't agree.

This tool generates realistic test data for **October 2026**, plants four kinds of gap in it, and then finds and explains every gap. It also proves it found them by checking against an answer key.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src.generate_data      # writes data/*.csv and data/planted_gaps.json
pytest -v                        # 29 tests
streamlit run app.py
```

## What the app shows

- **Platform total, bank total and Gap (Bank − Platform)** as metric cards.
- A **waterfall bridge** from the platform total, through each gap category, to the bank total.
- A one-line summary, e.g. `Gap (Bank − Platform): ₹4,148.20 = -₹3,513.85 late settlement + ₹0.23 rounding + ₹4,241.90 duplicate + ₹3,419.92 orphan refund + ₹0.00 unexplained`.

**Sign convention:** every gap and impact is **Bank − Platform**. Negative = money the platform recorded that the bank hasn't paid yet; positive = money the bank paid that the platform didn't expect.
- A **self-check** (generated data only) comparing planted and detected gaps, one row per gap type.
- A tab per category, listing each gap with a plain-English explanation and a suggested action.
- A **CSV download** of the full gap report.

## Assumptions

1. Single currency INR. Reconciliation month: October 2026.
2. One settlement record per transaction, linked by `txn_id`, settled 1–2 days after payment.
3. The platform stores amounts to 4 decimals. The bank settles each amount rounded **half-up** to 2 decimals. All money uses Python `Decimal`, never float and never `round()`. CSVs are read with `dtype=str` and converted to `Decimal` explicitly.
4. Refunds are negative transactions with `type="refund"` and an `original_txn_id`.
5. Per-row rounding tolerance: ≤ ₹0.01.
6. Matching is at the transaction level, against the processor's itemised settlement report. Fees, FX and chargebacks are out of scope.
7. **(Added)** A refund with no original sale isn't processed by the bank, so it has no settlement row. This makes the orphan refund show up in the bridge, as books ₹X below the bank, rather than netting to zero. The detection rule ("`original_txn_id` doesn't exist") works whether or not a settlement exists.
8. **(Added, generator simplification)** Ordinary sample payments are created on 1–29 Oct, so a 1–2 day lag always settles inside October. The only month-end spill is the three planted late payments.

## Upload validation (`src/load.py`)

Uploaded CSVs are checked before anything is reconciled. Problems show as one red message in the app (first 5 problems with row numbers, plus a count), never as a stack trace.

- **Extra columns** are ignored. **Missing columns** are named in the error.
- **Amounts:** `₹` symbols, spaces and thousands commas (including Indian grouping like `1,25,000.50`) are stripped. Blank or non-numeric amounts are rejected with their row number.
- **Dates** must be ISO (`YYYY-MM-DD`, optionally with a time) and real calendar dates. A non-ISO date like `01/10/2026` is rejected rather than silently dropping the row out of the month.
- **`type`** must be exactly `payment` or `refund`.

## How the engine works (`src/reconcile.py`)

For every `txn_id`:

`impact = (bank amount settled in October) − (platform amount booked in October)`

So `platform_total + Σ impact = bank_total` holds exactly. Each `txn_id` is classified **once**, in the first category it matches:

| Order | Category | Rule | Suggested action |
|---|---|---|---|
| 1 | Duplicate | more than one settlement row **or** more than one platform row for the `txn_id` | Bank side: raise with bank; reverse duplicate credit. Platform side: reverse the duplicate platform entry |
| 2 | Orphan refund | refund whose `original_txn_id` doesn't exist in the **whole** transactions file (any month) | Investigate: refund issued without a matching sale |
| 3 | Late | booked in October, only settlement is in a later month | Accrue as in-transit; confirm against November statement |
| 4 | Rounding | 0 < \|impact\| ≤ ₹0.01 | Book to rounding adjustment account |
| 5 | Unexplained | any other non-zero impact: missing settlement, amount mismatch, or a bank-only settlement. Bank-only rows say whether the `txn_id` belongs to another month or doesn't exist anywhere | Investigate manually / clear against the earlier month's accrual / investigate unknown bank credit, don't book until matched |

The **bridge** sums impact per category. The unexplained residual is `total gap − the four categories`, and it is ₹0.00 on generated data.

## Planted gaps (`src/generate_data.py`)

| Gap | What's planted |
|---|---|
| Late | 3 payments on 31 Oct that settle on 1–2 Nov |
| Rounding | 50 payments ending in `.xx5x` at 4 dp (e.g. `199.9950`). Half-up rounding always goes **up**, so each row is off by under ₹0.01 but the drift doesn't cancel (≈ ₹0.23 total) |
| Duplicate | 1 settlement row re-sent with the same `txn_id` and a new `settlement_id` |
| Orphan refund | 1 refund pointing to `TXN-9999`, which doesn't exist |

`data/planted_gaps.json` is the answer key. `generate(plant_gaps=False)` produces perfectly matching data.

## Tests (`tests/`)

- Each gap type: detected `txn_id`s == planted `txn_id`s.
- Clean data has zero gaps.
- Rounding: every row ≤ ₹0.01, but the total is > ₹0.20.
- Rounding direction: bank > platform on every planted row.
- Bridge residual is ₹0.00 on seeds 1, 42 and 99.
- A duplicate that is also late is counted once, as a duplicate.
- An orphan refund the bank does settle (₹0 net gap) is still flagged as an orphan.
- A settlement for a `txn_id` that doesn't exist is unexplained (an unknown bank credit), and raises the residual by exactly its amount.
- An October settlement of a September payment is explained as belonging to another month.
- A `txn_id` recorded twice on the platform is a duplicate, not unexplained.
- A refund of a previous month's sale is not an orphan.
- Upload validation (`tests/test_load.py`): extra column, missing column, blank amount, ₹ and commas, non-numeric amount, non-ISO date, impossible date, unknown type, many errors summarised.
- Decimal safety: no floats in money columns, including after a CSV round trip.

## Display notes

Money is shown as ₹ with thousands separators and 2 decimals. The **Rounding** tab shows 4 decimals instead, because the differences are sub-paisa and would all display as ₹0.01. The waterfall's y-axis is zoomed to the gap range. Floats are used only for drawing the chart, never for calculation.

## Decisions I made

- **Orphan refund has no bank record:** the bank can't refund a sale that never happened, so the planted orphan shows up in the bridge. Detection doesn't depend on this: if the processor does push it through, the refund nets to ₹0 in the gap but is still flagged as an orphan, and `test_orphan_refund_flagged_even_when_bank_settles_it` covers that case.
- **Normal sample payments are dated 1–29 Oct (generator simplification):** otherwise a 30 Oct payment with a 2-day lag would become an extra, unplanned late settlement and break the answer key. The cost is that the sample data hides the natural month-end edge case, where ordinary 30–31 Oct payments spill into November. The engine's late rule would catch them, but only the 3 planted 31 Oct payments exercise it.
- **The Rounding tab shows 4 decimals:** the differences are under one paisa, so at 2 decimals every row would display as ₹0.01 and hide the point.
- **The waterfall's y-axis is zoomed to the gap range:** starting from ₹0, the ₹0.23 rounding bar and even the ₹3–4k bars were invisible next to the ₹7 lakh totals.
- **Added `src/money.py` and generator tests:** one place for Decimal parsing, half-up rounding and ₹ formatting keeps money handling consistent, and testing the generator lets pytest run after the first stage and proves the answer key is trustworthy.

## Known limitations

In production, banks deposit batched and netted amounts (payments minus refunds in one credit), so transaction-level matching would need a deposit-to-batch layer before it could reconcile against the actual bank statement. Processors usually deduct fees before settlement, so every row would differ by the fee and be misreported as unexplained unless fees are modelled explicitly. Partial settlements, chargebacks and timezone cut-offs (e.g. a payment at 1 Nov 02:00 IST is still 31 Oct in UTC) would also be misclassified, because the engine assumes one full settlement per transaction and a single time zone.

## Next step: deposit-level matching

Real banks deposit in batches: one credit per day covering many transactions. This tool models the processor's itemised settlement report, which is what you actually reconcile against in practice. The next step is full deposit-level matching: group settlements into daily batch deposits, check that each deposit equals the sum of its itemised rows, then drill into any batch that's off.
