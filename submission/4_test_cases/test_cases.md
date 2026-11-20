# Test cases

32 test items in 3 files, all passing (see `test_results.txt`). Parametrised tests are listed once per parameter, matching the pytest output.

**Gap type** key: Late · Rounding · Duplicate · Orphan refund · Unexplained · All (the whole bridge) · Input (upload validation) · Generator (test data).

| # | Test name | What it proves | Gap type |
|---|---|---|---|
| 1 | `test_generate_data.py::test_planted_counts` | Exactly the specified number of each gap is planted: 3 late, 50 rounding, 1 duplicate, 1 orphan refund. | Generator |
| 2 | `test_generate_data.py::test_size_and_reproducible` | `n` is respected, and the same seed gives identical data. | Generator |
| 3 | `test_generate_data.py::test_clean_data_settles_exactly_in_october` | `plant_gaps=False` gives 2-decimal amounts and one settlement per transaction, all in October. | Generator |
| 4 | `test_load.py::test_extra_column_is_ignored` | An extra column doesn't break loading or change the result. | Input |
| 5 | `test_load.py::test_missing_column_names_the_column` | A missing required column gives a clear error naming it. | Input |
| 6 | `test_load.py::test_blank_amount_reports_row` | A blank amount is rejected with its row number, not a raw `decimal.InvalidOperation`. | Input |
| 7 | `test_load.py::test_rupee_symbol_and_commas_are_parsed` | `₹1,841.60` and Indian grouping `₹1,25,000.50` parse to exact Decimals. | Input |
| 8 | `test_load.py::test_non_numeric_amount_rejected` | Junk like `12.3.4` is rejected, not silently stripped. | Input |
| 9 | `test_load.py::test_non_iso_date_rejected_not_silently_dropped` | `01/10/2026` is an error. Before the fix, the row silently fell out of October. | Input |
| 10 | `test_load.py::test_impossible_date_rejected` | A well-shaped but impossible date (`2026-13-45`) is caught at load time. | Input |
| 11 | `test_load.py::test_unknown_type_rejected` | A `type` other than `payment`/`refund` is rejected, since it would skip the orphan check. | Input |
| 12 | `test_load.py::test_many_errors_are_summarised` | A file full of errors shows the first 5 and a count, not a wall of text. | Input |
| 13 | `test_reconcile.py::test_each_gap_type_detected_exactly[late]` | Detected late `txn_id`s == planted: no misses, no false positives. | Late |
| 14 | `test_reconcile.py::test_each_gap_type_detected_exactly[rounding]` | Detected rounding `txn_id`s == planted. | Rounding |
| 15 | `test_reconcile.py::test_each_gap_type_detected_exactly[duplicate]` | Detected duplicate `txn_id`s == planted. | Duplicate |
| 16 | `test_reconcile.py::test_each_gap_type_detected_exactly[orphan_refund]` | Detected orphan-refund `txn_id`s == planted. | Orphan refund |
| 17 | `test_reconcile.py::test_clean_data_has_no_gaps` | Perfectly matching data gives zero gaps in every category and a zero total gap. | All |
| 18 | `test_reconcile.py::test_rounding_invisible_per_row_but_visible_in_total` | Every rounding row is ≤ ₹0.01, yet the total is > ₹0.20. | Rounding |
| 19 | `test_reconcile.py::test_rounding_always_goes_up` | Half-up moves every planted row the same way (bank > platform), so the drift can't cancel. | Rounding |
| 20 | `test_reconcile.py::test_bridge_residual_is_zero[1]` | The four categories fully explain the gap on seed 1: platform + gap impacts == bank, to the paisa. | All |
| 21 | `test_reconcile.py::test_bridge_residual_is_zero[42]` | Same, on seed 42. | All |
| 22 | `test_reconcile.py::test_bridge_residual_is_zero[99]` | Same, on seed 99. | All |
| 23 | `test_reconcile.py::test_duplicate_that_is_also_late_counted_once` | A bank-side duplicate that is also late appears once, as Duplicate, not also as Late. | Duplicate / Late |
| 24 | `test_reconcile.py::test_orphan_refund_flagged_even_when_bank_settles_it` | An orphan refund the bank does settle (₹0 net gap) is still flagged, not hidden. | Orphan refund |
| 25 | `test_reconcile.py::test_bank_only_settlement_is_unexplained_unknown_credit` | A settlement for a `txn_id` that exists nowhere is Unexplained, raises the residual by exactly its amount, and says not to book it. | Unexplained |
| 26 | `test_reconcile.py::test_settlement_for_prior_month_transaction_is_explained_as_such` | An October settlement of a September payment says so, instead of "does not exist". | Unexplained |
| 27 | `test_reconcile.py::test_platform_side_duplicate_is_a_duplicate` | A `txn_id` recorded twice on the platform (bank once) is a Duplicate, not Unexplained. | Duplicate |
| 28 | `test_reconcile.py::test_platform_duplicate_that_is_also_late_is_duplicate_not_late` | Guards the check order. A 31 Oct payment recorded twice on the platform is a Duplicate, not Late. With Late checked first, this is the only test that fails. | Duplicate / Late |
| 29 | `test_reconcile.py::test_refund_of_prior_month_sale_is_not_an_orphan` | The orphan check looks at every transaction, not just this month's. | Orphan refund |
| 30 | `test_reconcile.py::test_gross_exceptions_split` | Gross = timing + action + booked (+ unexplained), with Late as timing, Duplicate + Orphan refund as action and Rounding as booked. ₹11,175.9003 on seed 42. | All |
| 31 | `test_reconcile.py::test_gross_exceptions_do_not_cancel_within_a_category` | Offsetting +₹X / −₹X rows add up to ₹2X gross instead of cancelling to ₹0. | Unexplained |
| 32 | `test_reconcile.py::test_no_floats_in_money_columns` | Money stays Decimal end to end, including after a CSV round trip. | All |
