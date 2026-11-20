# Submission: Month-End Reconciliation Assistant

A payments platform records each transaction instantly. The bank settles 1–2 days later, and at month end the two don't match. This project generates October 2026 test data with four planted gap types (late settlement, rounding drift, duplicate, orphan refund), then finds, explains and bridges every gap in a Streamlit app.

## Assumptions

Copied from the project [README](../README.md#assumptions).

1. Single currency INR. Reconciliation month: October 2026.
2. One settlement record per transaction, linked by `txn_id`, settled 1–2 days after payment.
3. The platform stores amounts to 4 decimals. The bank settles each amount rounded **half-up** to 2 decimals. All money uses Python `Decimal`, never float and never `round()`. CSVs are read with `dtype=str` and converted to `Decimal` explicitly.
4. Refunds are negative transactions with `type="refund"` and an `original_txn_id`.
5. Per-row rounding tolerance: ≤ ₹0.01.
6. Matching is at the transaction level, against the processor's itemised settlement report. Fees, FX and chargebacks are out of scope.
7. **(Added)** A refund with no original sale isn't processed by the bank, so it has no settlement row. This makes the orphan refund show up in the bridge, as books ₹X below the bank, rather than netting to zero. The detection rule ("`original_txn_id` doesn't exist") works whether or not a settlement exists.
8. **(Added, generator simplification)** Ordinary sample payments are created on 1–29 Oct, so a 1–2 day lag always settles inside October. The only month-end spill is the three planted late payments.

---

## 1. Brainstorming thread

The unedited conversation where the business and data assumptions were worked out before any code: matching keys, settlement lag, rounding, refunds, duplicates, and whether to model batched deposits.

- [1_brainstorming_thread/PLACEHOLDER.md](1_brainstorming_thread/PLACEHOLDER.md): chat share link and PDF export to be added.

## 2. Prompts

The raw prompt as first written, and the distilled build prompt given to Claude to build the tool. The distilled prompt fixes the stack, the assumptions, the exact gaps to plant, the engine's check order and the tests.

- [2_prompts/raw_prompt.md](2_prompts/raw_prompt.md): to be added.
- [2_prompts/distilled_prompt.md](2_prompts/distilled_prompt.md): the build spec, copied byte-for-byte from the file given to Claude.

## 3. Claude Code thread

The full build thread, including wrong turns. A summary of the real corrections is in [Wrong turns & corrections](#wrong-turns--corrections) below.

- [3_claude_code_thread/PLACEHOLDER.md](3_claude_code_thread/PLACEHOLDER.md): `/export` output to be added.

## 4. Test cases

32 pytest items, all passing. They cover each planted gap against the answer key, the bridge residual on three seeds, check-order edge cases, upload validation and Decimal safety.

- [4_test_cases/test_cases.md](4_test_cases/test_cases.md): test name, what it proves, gap type.
- [4_test_cases/test_results.txt](4_test_cases/test_results.txt): latest `pytest -v` output.

## 5. Working output

The Streamlit app shows platform and bank totals, the Bank − Platform gap, gross exceptions, a waterfall bridge, a planted-vs-detected self-check, a gap table per category and a CSV export. On seed 42 it explains a ₹4,148.20 net gap (₹11,175.90 gross) with ₹0.00 unexplained.

- [5_working_output/links.md](5_working_output/links.md): deployed app, GitHub repo and demo video URLs to be added.
- [5_working_output/production_gaps.md](5_working_output/production_gaps.md): what this would get wrong in production.
- Code: [`src/`](../src), [`tests/`](../tests), [`app.py`](../app.py), [project README](../README.md).

---

## Wrong turns & corrections

These are real moments from the build session, in order.

1. **Git author identity.** Claude first set the repo's git author to my name with a made-up email address. It changed this to "Claude" before the first commit.
2. **Couldn't write to GitHub or `.git`.** The GitHub repo was empty and Claude had no push access. The shell on my computer wouldn't start (not enough free disk space), and writing into `D:\Onelab\.git` was blocked. The commit history was delivered as a git bundle instead.
3. **Clean amounts written as `1841.6`.** The first generated CSV dropped trailing zeros. Fixed by quantising clean amounts to 2 decimals.
4. **Rounding amounts could lose their 4th decimal.** An amount ending in `.xx50` would have been written with 3 decimals. Caught by reading the code; fixed by quantising to 4 decimals.
5. **Summary line printed "+ -₹3,513.85".** Fixed so negative terms read "- ₹3,513.85".
6. **Waterfall bars were flattened.** With the y-axis starting at ₹0, the gap bars were invisible next to ₹7 lakh totals. Zoomed the axis to the gap range. The first screenshot after the fix still showed the old chart, because the Streamlit server had cached the script; restarting it showed the fix.
7. **Timezone example had the direction backwards.** The first draft of Known limitations said a 31 Oct 23:00 IST payment is 1 Nov in UTC. It's actually still 31 Oct in UTC (IST is ahead of UTC). Corrected before committing to "a payment at 1 Nov 02:00 IST is still 31 Oct in UTC".
8. **Sign convention was implicit.** At my request, the gap card and summary were relabelled "Gap (Bank − Platform)", with a line explaining what negative and positive mean.
9. **Orphan refund the bank does settle.** I asked whether a settled orphan refund (₹0 net gap) is still flagged. The engine already flagged it, but no test covered it. Added the test and changed the explanation so a ₹0 row doesn't look harmless. Confirmed the test fails against an engine that drops ₹0-impact rows.
10. **Generator hides the natural month-end edge case.** At my request, the 1–29 Oct payment dates are now documented as a generator simplification.
11. **Sceptical-reviewer pass found six real problems:**
    - A missing column, a blank amount, or ₹ and commas in an amount crashed the app with a stack trace.
    - A non-ISO date (`01/10/2026`) silently dropped the row out of October, with no error.
    - A `txn_id` recorded twice on the platform landed in Unexplained, not Duplicate.
    - The orphan check only looked at October's transactions, so a refund of a September sale would have been a false orphan.
    - A bank-only settlement's explanation couldn't tell an unknown credit from a prior-month payment.
    - The first version of the upload error appeared in the sidebar, out of view, leaving the main page blank. Moved it to the main area.

    All six were fixed with tests. The four new engine tests failed against the old engine.
12. **`round()` premise was only partly right.** I assumed Python's `round()` would have erased the rounding gap. Checking the data showed only 2 of the 50 planted rows are exact halves. `round()` would shrink the drift from ₹0.2303 to ₹0.2203, not erase it. It would only nearly vanish (₹0.25 → ₹0.01) if every row were an exact half.
13. **The check-order test didn't guard the order.** With Late checked before Duplicate in a copy, all 29 tests still passed, because the late rule already requires exactly one bank settlement. Added a test for a platform-side duplicate that is also late. With the swapped order, it is now the only test that fails.
14. **Five deliberate spec changes**, each explained in the project README's "Decisions I made":
    - the orphan refund has no bank record;
    - normal payments are dated 1–29 Oct;
    - the Rounding tab shows 4 decimals;
    - the waterfall axis is zoomed;
    - `money.py` and generator tests were added.
15. **Test count in this packaging request.** The packaging request said to cover "all 16 tests", but by then the suite had grown to 32 items, so [test_cases.md](4_test_cases/test_cases.md) covers all 32.
