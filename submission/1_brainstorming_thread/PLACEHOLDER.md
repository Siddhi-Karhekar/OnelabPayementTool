# Payments reconciliation assessment

*Project: Onelab*

---

## User

I'm doing a 2-hour assessment. A payments company's books don't balance at month end. The platform records every transaction instantly when a customer pays; the bank settles funds 1–2 days later. At month end every transaction should have a matching settlement, but they don't match. I need to generate my own test data, plant 4 gap types (a transaction that settled the following month, a rounding difference that only shows when summed, a duplicate entry in one dataset, a refund with no matching original transaction), and build a tool that finds and explains the gaps.

Before any code: what are the key assumptions I need to make about the data and the business? List them with 2–3 options each and the trade-offs. https://github.com/Siddhi-Karhekar/OnelabPayementTool

## Claude

*Laying out refund and duplicate handling choices*

The four planted gaps only show up if a few assumptions are fixed first. Below are the ones that matter, each with options, trade-offs and the option I'd pick for a 2-hour build. I haven't opened your repo. If it has a brief with constraints (language, format), those override these picks.

### 1. How a settlement links to a transaction

This is the most important decision, because every detector depends on it.

- **A. Shared ID (1:1).** Each bank row carries the `txn_id`. Pro: exact matching, simple logic, easy to explain. Con: real banks rarely give you this cleanly.
- **B. Batched settlements.** One bank deposit per day covers many transactions, linked by a `batch_id` or a settlement report. Pro: realistic, and rounding drift appears naturally at batch level. Con: matching has two levels (transaction→batch, batch→bank), which takes more time.
- **C. No shared key, fuzzy match** on amount, a date window and maybe the customer. Pro: the most realistic for raw bank statements. Con: the matches are ambiguous and give false positives, and it's hard to finish in 2 hours.

Pick A, and keep a separate `settlement_id` on the bank side. Mention B as the production extension.

### 2. Settlement lag and the month-end cutoff

- **A. Fixed calendar lag of 1–2 days, random.** Pro: simple. Con: ignores weekends.
- **B. Business-day lag (T+1/T+2, skipping weekends and holidays).** Pro: realistic. A Friday transaction settling on Monday is common. Con: you need a calendar, and more transactions spill across month-end.
- **C. Variable lag with outliers (occasionally 3–5 days).** Pro: tests how robust the tool is. Con: blurs what counts as late versus missing.

You also need to decide which date defines the month. I'd use the transaction date (the books) for "what should settle" and give the bank data a lookahead window (for example, the first 5 days of next month). That's how a transaction that settled next month gets classified as a timing difference, not a missing settlement. Pick A, plus the lookahead window.

### 3. Time zone

- **A. Everything in one time zone (UTC or IST).** Pro: no boundary bugs. Con: hides a real cause of month-end mismatches.
- **B. Platform in UTC, bank in IST.** Pro: realistic. A 31st 20:00 UTC transaction is already the 1st in IST. Con: creates extra cross-month cases you didn't plant.

Pick A and say so in your write-up. Mention B as a known real-world cause.

### 4. Amount representation and the rounding rule

This is what makes the "only shows when summed" gap work.

- **A. Platform keeps sub-cent precision** (e.g. 3–4 decimals from fee or FX calculations), bank rounds each row to 2 dp. Pro: each row differs by less than 0.01, so row matching passes but the totals drift. That's exactly the planted gap. Con: you must explain why the platform has extra precision.
- **B. Both sides use 2 dp, but the bank rounds at batch level.** Pro: realistic. Con: only works with batching (option 1B).
- **C. Integer minor units (paise/cents) everywhere.** Pro: the correct engineering practice, with no float errors. Con: rounding gaps can't happen unless you add a conversion step, so you'd have to fake one.

Related choice, the tolerance policy: exact match, per-row tolerance (±0.01), or per-row tolerance plus an aggregate check. Pick A, with per-row tolerance of ±0.01 and a separate check on the summed difference. The rounding gap is a pattern of many small differences that add up, not one bad row, so the tool needs both checks. Use `Decimal` in the code, never floats.

### 5. Gross vs net (fees)

- **A. Bank settles the gross amount.** Pro: amounts compare directly. Con: less realistic.
- **B. Bank settles net of fees, with a fee column.** Pro: realistic and still checkable (`gross − fee = net`). Con: more columns, more logic.
- **C. Net of fees, fee not shown.** Pro: the most realistic. Con: every row mismatches, and the planted gaps get buried.

Pick A. State that fees are out of scope, or settled separately.

### 6. How refunds are modelled

- **A. Refund as a row in the transactions table** with a negative amount, `type=REFUND` and an `original_txn_id`. Pro: one table, an easy orphan check. Con: mixes two concepts in one table.
- **B. A separate refunds table.** Pro: cleaner. Con: one more dataset to generate and join.
- **C. Refunds netted inside settlement batches.** Pro: realistic. Con: needs batching, and an orphan refund is much harder to spot.

You also need a rule for orphan scope. Is the original missing everywhere, or just outside this month's data? Load the previous month too, or flag the two cases differently ("original not found" vs "original outside the window"). Also decide whether refunds appear in the bank data as debits. Pick A: one prior month of history, and refunds settle as negative bank rows.

### 7. What counts as a duplicate

- **A. Same ID appears twice.** Pro: unambiguous. Con: only catches exact replays.
- **B. Same content with a different ID** (same customer, amount and timestamp within N seconds, e.g. a webhook retry). Pro: realistic. Con: risk of flagging genuine repeat purchases.
- **C. Both, with confidence levels** (exact vs likely).

Also decide which side has the duplicate: a platform double-record or a bank double-settlement. They have opposite money impact. Pick C if time allows, otherwise A. Plant the duplicate on one side only and say which.

### 8. Transaction status and scope

- **A. Every transaction is successful and should settle.** Pro: simple. Con: unrealistic.
- **B. Include a status (SUCCESS / FAILED / PENDING),** where only SUCCESS should settle. Pro: realistic, and shows filtering judgement. Con: adds noise.

Pick B, but keep FAILED rows rare. Volume: a few hundred to a few thousand rows, one currency (INR), one merchant account.

### 9. Test data generation and proving the tool works

- **A. A hand-written fixture.** Pro: fast. Con: looks toy-like.
- **B. A seeded random generator.** Pro: reproducible and realistic in volume. Con: you need a way to know what was planted.
- **C. A seeded generator that also writes an answer key** (`planted_gaps.csv`). Pro: the tool's output can be checked automatically against what you planted, and that comparison is strong evidence for an assessor. Con: about 15 extra minutes.

Pick C.

### 10. Source of truth and output

Which side is authoritative? The platform is the ledger (what we're owed); the bank is the cash (what we got). The report should state each gap as its effect on the books: amount, direction and type.

Output options: a CLI summary plus a CSV of gaps (fastest), an HTML report (more readable), or a small web UI (impressive but risky in 2 hours). Pick CLI + CSV. Each gap row gets a category, the IDs involved, the amount, and a plain-English explanation (e.g. "Settled 2026-11-01, the day after month-end. Timing difference, not a loss.").

**Suggested time split:** 20 min on assumptions and schema, 30 on the generator, 50 on the reconciliation logic, 20 on the report and README.

Put these choices, with a sentence each on why, at the top of your README. In assessments like this, stated and justified assumptions often count as much as the code. Calling out the simplifications (1C, 3B, 5C) as real-world causes you chose to leave out shows you understand the domain.

---

## User

I'll go with: single currency INR, one settlement per transaction linked by txn_id, October 2026 as the month, platform stores 4 decimals and the bank rounds to 2, refunds are negative transactions with an original_txn_id.

But I'm worried about one thing: real banks batch settlements into one deposit. Should I model batching? What's the cost in build time vs the value? Be honest.

## Claude

*Weighing batch-level totals against the cost of full batching*

No, don't model full batching. It would cost you about half your build time and add little to what's actually being assessed.

### Why it doesn't add much here

- **The brief describes per-transaction matching.** It says "every transaction should have a matching settlement." That's 1:1 matching, so batching solves a problem you weren't asked to solve.
- **None of your four planted gaps need it.** The next-month settlement, rounding, duplicate and orphan refund all work at the transaction level.
- **It can actually get in the way.** With batching, a duplicate on the bank side becomes a batch that's too large rather than a clear duplicate row, so it's harder to spot and harder to explain. The rounding drift can also blend into ordinary batch-level differences.

### What it would cost

| Piece | Extra time |
|---|---|
| Generator: group settlements into daily batches, write deposit totals | ~15 min |
| Matcher: two levels (deposit to batch, batch to transactions), with a drill-down when a batch is off | ~25–35 min |
| Report: explain gaps at both levels | ~10 min |
| Debugging how the two levels interact | ~10+ min |

That's about 60 minutes out of 120, and the likely result is four half-finished detectors instead of four solid ones. Reviewers penalise unfinished core work much more than missing realism.

### The cheap middle option (about 15 min, only if you're ahead)

This matches how processors like Razorpay or Stripe work in practice. The bank statement shows one lump sum per day, and a separate settlement report lists each transaction in it.

1. Keep your settlement file per transaction, as you planned, and add a `batch_id` column. Batch by settlement date.
2. Generate a small `bank_deposits.csv` with one row per batch and its total.
3. Add one check: the sum of settlement rows per batch should equal the deposit amount.

Your transaction-level matching doesn't change at all, so the four detectors are untouched. You still show you know real deposits are batched. It also gives the rounding gap a second, realistic place to show up: per-row rounding adds up to a batch total that doesn't match the platform's sum.

### My recommendation

1. Build all four detectors at the transaction level first.
2. If they're working and tested against your answer key by about the 80-minute mark, add the middle option.
3. Either way, put a line in the README: "Real banks deposit in batches; this models the processor's itemised settlement report, which is what you reconcile against in practice. Full deposit-level matching is the next step." That explains the choice and takes 30 seconds.

One thing to settle with your rounding choice: decide whether the bank rounds half-up or uses banker's rounding. Then make sure the planted drift comes from many rows that each round in the same direction, for example amounts ending in `.xx5x`. Otherwise the rounding errors can cancel out and your planted gap disappears.

---

## User

*Attachment: Pasted text.txt*

Agreed. Decisions:

1. Transaction-level matching only for the core build. Batch/deposit-level matching is a stretch goal only if all tests pass by the 80-minute mark — otherwise it goes in the README as the next step, using your wording.
2. Bank rounds HALF-UP to 2 decimals. I'll use Python's Decimal with ROUND_HALF_UP, not round(), because round() uses banker's rounding and floats would introduce their own errors.
3. Planted rounding rows will have amounts ending in .xx5x at 4 decimals (e.g. 199.9950, 349.4957) so every row rounds up by the same direction. 50 rows × ~₹0.005 ≈ ₹0.25 total drift, while no single row is off by more than ₹0.01.

## Claude

*Planning the late-payment and duplicate test cases*

I'll check your Onelab folder and the repo, then build the app in your order: generator, engine, tests, app. I'll run pytest after each stage.

*Used Add repo, updated tasks, and 5 more steps*

The repo is empty, and Claude can read it but not push to it from here. I'll build and commit locally, then copy the project into `D:\Onelab`. Starting with the generator.

*Created 10 files, edited 4 files, and 33 more steps*

The Month-End Reconciliation Assistant is built and in `D:\Onelab`. All 15 tests pass. It finds all 4 planted gap types exactly and explains the whole gap, with ₹0.00 left unexplained. I also checked 30 different random seeds and every one matched the answer key exactly.

On the default data (seed 42), the app's summary line reads:

> ₹4,148.20 gap = -₹3,513.85 late settlement + ₹0.23 rounding + ₹4,241.90 duplicate + ₹3,419.92 orphan refund + ₹0.00 unexplained

I opened the app in a browser and checked it: the totals cards, the waterfall chart, the "4/4 ✅" self-check, the gap tabs and the CSV download all work.

**Where I changed or added to your spec (all listed in the README):**

- **Orphan refund has no bank record.** I assumed the bank can't refund a sale that never happened, so it never pays out. If the bank did pay it, the refund would cancel out to ₹0 and disappear from the gap total. The detection rule works either way.
- **Normal sample payments are dated 1–29 Oct.** Otherwise a payment on 30 Oct with a 2-day delay would accidentally become an extra, unplanned late settlement.
- **The Rounding tab shows 4 decimals.** These differences are under one paisa, so at 2 decimals every row would just show ₹0.01.
- **The waterfall chart's axis is zoomed in.** Starting from ₹0, the ₹0.23 rounding bar was invisible.
- **Two extra pieces:** a small `money.py` helper file, and 3 tests on the data generator itself, so I could run pytest after the first stage as your working style asks.

**Git:** there are 5 commits, one per stage. Two things to fix before you submit:

- **Pushing:** I couldn't push to your GitHub repo because Claude doesn't have write access to it.
- **The commits don't have your name on them yet.** Writing directly into `D:\Onelab\.git` was blocked, so the history is in `onelab-history.bundle` (a single file holding all 5 commits). To load it and push, run this in `D:\Onelab`:

```bash
git init -b main
git fetch onelab-history.bundle main
git reset FETCH_HEAD
git remote add origin https://github.com/Siddhi-Karhekar/OnelabPayementTool.git
git push -u origin main
```

Then delete the bundle file. The commits are authored as "Claude", so if you want them under your name, run `git rebase -r --root --exec "git commit --amend --no-edit --reset-author"` before pushing.

To run it: `pip install -r requirements.txt`, then `pytest -v`, then `streamlit run app.py`. Your Windows Python needs to be 3.11 or newer.

I didn't build the batch-deposit stretch goal, as you said. The README describes it as the next step.

---

## User

Three small changes:

1. Make the sign convention explicit everywhere: label the gap card and summary line "Gap (Bank − Platform)", and add one line under the summary: "Negative = money the platform recorded that the bank hasn't paid yet; positive = money the bank paid that the platform didn't expect."
2. Run pytest -v and save the output to 04_tests/test_results.txt.
3. In the README, add a "Decisions I made" section using the 5 spec changes you listed (orphan refund has no bank record, payments dated 1–29 Oct, 4-decimal rounding tab, zoomed waterfall axis, money.py + generator tests), one line each with the reason. Also add a "Known limitations" section with exactly 3 sentences on what this would get wrong in production: batched/netted deposits, processor fees deducted before settlement, and partial settlements/chargebacks/timezone cut-offs.

Commit after.

## Claude

*Adding a caption below the summary, then committing and updating the bundle*

I'll make the three changes, run the tests and save the output, commit, then copy the updated files to `D:\Onelab`.

*Edited a file, ran 2 commands*

I need to fix my timezone example: 31 Oct 23:00 IST is still 31 Oct in UTC. The correct direction is early 1 Nov IST, which is still 31 Oct in UTC.

*Edited a file, ran 2 commands, saved files to your computer*

I've made all three changes and committed them; `D:\Onelab` has the updated files. All 15 tests still pass.

1. **Sign convention:** the gap card now reads "Gap (Bank − Platform)". The summary line reads "Gap (Bank − Platform): ₹4,148.20 = -₹3,513.85 late settlement + …", with your explanation line underneath. I also put the convention in the reconciliation code's header comment and in the README.
2. **Test output:** the `pytest -v` results are in `04_tests/test_results.txt`, showing 15 passed. The header includes my workspace path, not yours. Re-run it on your machine before submitting if you want your own path in the file.
3. **README:** I added "Decisions I made" with one line per change and its reason. "Known limitations" is exactly three sentences, on netted batch deposits, fees deducted before settlement, and partial settlements, chargebacks and timezone cut-offs.

`onelab-history.bundle` now has all 6 commits. The same commands as before load it. If you already ran them, just run these two lines in `D:\Onelab` to pick up the new commit:

```bash
git fetch onelab-history.bundle main
git reset FETCH_HEAD
```

---

## User

Reviewing your 5 spec changes:

- Orphan refund with no bank record: I agree a bank wouldn't settle a refund for a sale it never saw, but in reality the processor might still push it through. If that happens, the refund cancels to ₹0 in the total gap — does the engine still flag it as an orphan, and is there a test for that case? If not, add one.
- Payments dated 1–29 Oct: fine, but that means the generator hides the natural month-end edge case. Note it in the README as a generator simplification.
- 4-decimal rounding tab, zoomed waterfall, money.py: agreed.

## Claude

*Testing orphan refund detection after a new settlement*

I'll check how the engine handles a settled orphan refund, add the test, update the README, and re-run the tests.

*Edited 3 files, ran 2 commands*

I checked that the new test actually catches the bug it's meant to: with an engine that skips ₹0-impact rows, only this test fails. Now updating the test count, saving the results and committing.

*Ran a command, saved files to your computer*

Yes, the engine already flagged a bank-settled orphan refund, but there was no test for it, so I added one. The README now notes the 1–29 Oct generator simplification, all 16 tests pass, and the updated files are in `D:\Onelab`.

**Orphan refund the processor pushes through:** the engine flags a refund as an orphan because its `original_txn_id` doesn't exist, not because of a money difference. A settled orphan refund still shows up in the Orphan refund tab, with ₹0 impact. I changed its explanation so a ₹0 row doesn't look harmless. It now reads "The bank debited ₹3,419.92 on 16 Oct, so it nets to ₹0.00 in the gap, but money left with no matching sale."

The new test is `test_orphan_refund_flagged_even_when_bank_settles_it`. It adds a matching bank debit to the planted orphan refund, then checks three things:

- It's still flagged once, as an orphan refund.
- Its impact is ₹0.
- The bridge still has ₹0.00 unexplained.

I also checked the test against a broken version of the engine that drops ₹0-impact rows: this test is the only one that fails, so it guards against exactly that mistake.

**1–29 Oct dates:** in the README this is now marked as a generator simplification, both in the assumptions list and in "Decisions I made". It says the sample data hides ordinary 30–31 Oct payments spilling into November. The engine's late-settlement rule would catch those, but only the 3 planted 31 Oct payments test it.

`04_tests/test_results.txt` is updated (16 passed), and `onelab-history.bundle` now has all 7 commits. To pick up the new commits, run the same `git fetch onelab-history.bundle main` and `git reset FETCH_HEAD` in `D:\Onelab`.

---

## User

Try to break the engine as a sceptical reviewer would:

1. Upload CSVs with an extra column, a missing column, blank amounts, and amounts with ₹ symbols or commas. The app should show a clear error, not a stack trace.
2. A settlement whose txn_id doesn't exist in transactions at all — which category does it land in? Is that right?
3. A transaction that appears twice in the platform data (not the bank) — is it caught?

Fix anything fragile, add a test for each fix, run pytest, and commit.

## Claude

*Created 3 files, edited 2 files, and 16 more steps*

I found six real problems, fixed all of them, and added 13 tests. All 29 tests pass, the changes are committed, and the updated files are in `D:\Onelab`. I also ran the four new engine tests against the old engine, and all four failed there, so they catch real bugs.

**1. Bad uploads.** Before the fix, a missing column, a blank amount or an amount with ₹ and commas each crashed the app with a raw Python error. A date like 01/10/2026 was worse: no error at all, and the row quietly dropped out of October, so the totals were wrong without warning. A new loader (`src/load.py`) now checks every file first:

| Bad input | What happens now |
|---|---|
| Extra column | Ignored |
| Missing column | Error names the column |
| Blank or non-numeric amount | Error gives the row number |
| ₹1,250.00 or ₹1,25,000.50 | Accepted and read exactly. Junk like 12.3.4 is still rejected |
| 01/10/2026 or an impossible date like 2026-13-45 | Error gives the row number |
| `type` not exactly `payment` or `refund` | Error, because the orphan check depends on this column |

Errors show as one red message in the main area, listing the first 5 problems and a count of the rest. I uploaded broken files in a browser to check: you see the message and no stack trace.

**2. A settlement whose txn_id doesn't exist lands in Unexplained, and I think that's right.** It isn't one of the four known patterns, so it should push the unexplained amount above ₹0.00 and stand out. What was missing was a useful explanation: the engine said "no platform transaction this month" whether the ID came from another month or didn't exist anywhere. It now separates the two:

- **Doesn't exist anywhere:** "Investigate unknown bank credit; do not book until matched."
- **From another month** (say, a September payment settled on 1 Oct): says when it was paid, and suggests clearing it against that month's in-transit entry.

**3. A transaction recorded twice on the platform was not caught as a duplicate.** It landed in Unexplained, because the engine only counted bank rows. It's now a Duplicate, with its own explanation ("appears 2 times in the platform records…") and action ("Reverse the duplicate platform entry").

**A bug I found while doing this:** the orphan-refund check only looked at October's transactions. So a refund in October for a September sale would have been wrongly flagged as an orphan. It now checks every transaction in the file.

**One gap I haven't fixed:** a double-recorded payment that got two different IDs (for example, a retried webhook). One copy has no settlement, so it shows as Unexplained with "has no settlement at all", not as a duplicate. Catching it means guessing from same customer, same amount, a few minutes apart, which can flag genuine repeat purchases. I didn't add that without asking. It's worth mentioning in your write-up as a known gap.

To pick up the new commit, run `git fetch onelab-history.bundle main` and `git reset FETCH_HEAD` in `D:\Onelab`.

---

## User

Explain in plain English, as if to a finance interviewer:

1. Why duplicates are checked before late settlements — what breaks if I swap the order?
2. Why Python's round() would have made the rounding gap disappear.
3. Walk through how the ₹4,148.20 gap is built up, line by line.

## Claude

*Ran 2 commands*

I checked all three answers against the code and data. Two of them don't quite match the premise, so I've flagged that where it comes up.

### 1. Why duplicates are checked before late settlements

A single transaction can match more than one rule. Say a payment is made on 31 Oct and also recorded twice. It's both late and duplicated, and the engine gives each transaction one label: the first rule that matches. So the order decides two things, what story we tell about the gap and what action finance takes.

Duplicates go first because the other rules assume one payment has one settlement. "Late" means the money is coming, just next month, so accrue it and wait. That's only true if the record itself is right. A duplicate is an error, not a timing difference, and labelling it "late" tells finance to wait for money that will never arrive.

**What breaks if you swap them:** I swapped the order in a copy of the code and tested it.

- A payment of ₹209.34 on 31 Oct, recorded twice on the platform, gets labelled Late: "₹418.68 falls into November, accrue as in-transit."
- So finance accrues ₹418.68. In November the bank pays ₹209.34, and the error shows up a month late as a new, confusing difference.
- With the current order it's labelled Duplicate: "reverse the duplicate platform entry." That's fixed in October.

Something I should be upfront about: with the order swapped, all 29 tests still passed. The bank-side "duplicate that is also late" test passes either way, because the late rule only fires when there's exactly one bank settlement. So the order does matter, but only for platform-side duplicates, and no test covers that case yet. I can add one so a swap fails the tests.

### 2. Why Python's round() matters, and where the premise is off

In this data, `round()` would not have made the gap disappear. It would have shrunk it a little, from ₹0.23 to ₹0.22. Here's why.

Python's `round()` has two quirks:

- **Banker's rounding:** exact halves go to the nearest even digit. `round(0.125, 2)` gives 0.12 but `round(0.375, 2)` gives 0.38. Half the ties go down and half go up, so they cancel out. Banks round halves up every time, so they all add up.
- **Floats can't store most decimals exactly:** 2.675 is stored as 2.67499999…, so `round(2.675, 2)` gives 2.67 instead of 2.68.

Both quirks only affect exact halves, amounts ending in `.xx50`. In my data only 2 of the 50 planted rows are exact halves. The other 48, like ₹1,224.9754, are clearly above half, so every method rounds them up. When I tested 50 amounts that were all exact halves, the bank's method gave ₹0.25 of drift and `round()` gave ₹0.01. That's the case where the gap really would vanish.

Here's the point for an interviewer. The engine never rounds anything itself; it compares the bank's real figures to the books. The rounding method only matters when simulating the bank in the test data. If that simulation used `round()`, the test data would describe a bank that doesn't exist. Separately, adding thousands of float amounts creates its own small drift, so you couldn't tell a real rounding gap from computer noise. Using `Decimal` with half-up rounding avoids both problems.

### 3. How the ₹4,148.20 gap builds up

Read the gap as Bank minus Platform. A minus sign means the books expect money the bank hasn't paid. A plus sign means the bank has more than the books expect.

| Step | Amount | Running total | What it means |
|---|---|---|---|
| Platform total | | ₹732,113.69 | What the books say October should bring in |
| Late settlements | −₹3,513.85 | ₹728,599.84 | Three payments made on 31 Oct (₹209.34 + ₹3,106.26 + ₹198.25) that the bank paid on 2 Nov. Timing only, and it reverses in November |
| Rounding | +₹0.23 | ₹728,600.07 | 50 payments the bank rounded up by less than a paisa each. Too small to see per row, only visible in the total |
| Duplicate | +₹4,241.90 | ₹732,841.97 | TXN-0283 was paid out twice on 30 Oct: the bank sent ₹8,483.80 against ₹4,241.90 booked. That's money we must return |
| Orphan refund | +₹3,419.92 | ₹736,261.89 | The books record a ₹3,419.92 refund for a sale (TXN-9999) that doesn't exist. The bank never paid it out, so the books are lower than the bank |
| Unexplained | ₹0.00 | ₹736,261.89 | Equals the bank total, so everything is accounted for |

To the exact paisa: −3,513.85 + 0.2303 + 4,241.90 + 3,419.92 = ₹4,148.2003.

A finance interviewer will care about this: the net gap of ₹4,148 hides about ₹11,176 of problems in total, because the late item and the other three partly cancel each other out. Only the ₹3,513.85 of late settlements fixes itself, and the ₹0.23 of rounding just gets booked. The duplicate (₹4,241.90 owed back to the bank) and the orphan refund (a control failure to investigate) need someone to act. The net figure alone would make month-end look better than it is.

---

## User

Good catches — you're right that round() would only shrink the gap here, not erase it; I'll use your explanation instead.

Two changes:

1. Add the missing test: a platform-side duplicate that is also late must be labelled Duplicate, not Late. Then prove it works: swap the check order in a temporary copy and confirm this test (and only the expected tests) fail. Restore the order.
2. Add a "Gross exceptions" metric next to the gap card: sum of absolute impacts across all categories (≈ ₹11,176 on seed 42), with the caption "Net gap hides offsetting issues — ₹X needs action, ₹Y is timing only." Split it as: timing only = late settlements; needs action = duplicate + orphan refund; booked = rounding.

Run pytest, update 04_tests/test_results.txt, commit.

## Claude

*Deciding how to sum gross exceptions per row*

I'll add the test, prove it with a swapped-order copy, then add the gross exceptions metric.

*Edited 2 files, read 2 files, and 6 more steps*

I've added the check-order test and the Gross exceptions card. All 32 tests pass, `04_tests/test_results.txt` is updated, the change is committed, and the updated files are in `D:\Onelab`.

**1. Check-order test:** `test_platform_duplicate_that_is_also_late_is_duplicate_not_late`. It takes a planted 31 Oct late payment, records it twice on the platform, and checks the result is labelled Duplicate (action "Reverse the duplicate platform entry"), not Late.

To prove it works, I swapped the order in a temporary copy so Late is checked before Duplicate. Exactly one test failed, this new one, and the other 29 passed. Before this test existed, the same swap passed everything. The swap was only ever in the temporary copy, which I've deleted, so the real code still checks Duplicate first.

**2. Gross exceptions card:** it sits next to the gap card. On seed 42 it shows ₹11,175.90, with the caption "Net gap hides offsetting issues — ₹7,661.82 needs action, ₹3,513.85 is timing only." I checked it in the browser.

Three choices I made that you may want to check:

- **Where the rounding figure shows:** your caption has no slot for the booked amount (₹0.23 rounding), so it's in the card's ⓘ tooltip, along with the full split.
- **Per-row, not per-category, totals:** the gross figure adds up the absolute value of each gap row. So a +₹500 and a −₹500 row in the same category count as ₹1,000 rather than cancelling to zero. A test covers this.
- **Unexplained amounts:** your split had no bucket for these. When there are any, they're still counted in the gross figure, and the caption adds "₹X is unexplained", so the three figures always add up to the gross total. On generated data this never shows.

The README describes the card and both new tests. To pick up the commit, run `git fetch onelab-history.bundle main` and `git reset FETCH_HEAD` in `D:\Onelab`.

---

## User

Checked all three choices — agreed. Per-row absolute totals is the right call; offsetting errors shouldn't net to zero in an exceptions figure. Rounding in the tooltip and the conditional "unexplained" line are fine.

## Claude

Good, nothing to change then. The code in `D:\Onelab` and `onelab-history.bundle` are both up to date.

Before you submit, you still need to get the 9 commits onto GitHub from your machine, since Claude can't push to your repo. In `D:\Onelab`, if you haven't already set it up, run these:

```bash
git init -b main
git fetch onelab-history.bundle main
git reset FETCH_HEAD
git remote add origin https://github.com/Siddhi-Karhekar/OnelabPayementTool.git
git push -u origin main
```

If you already ran the earlier steps, just run the `fetch`, `reset` and `push` lines. Then delete the bundle file. Running `pytest -v > 04_tests/test_results.txt` once on your machine will also replace my workspace path in that file with yours.

---

## User

Package the project for submission, matching the assessment's "What to Submit" list exactly. Create a submission/ folder in the repo:

```
submission/
├── README.md                  ← index: one section per deliverable 1–5, in order, each with a 2–3 line description and links to the files
├── 1_brainstorming_thread/
│   └── PLACEHOLDER.md         ← "Add brainstorm chat share link + PDF export here (unedited)"
├── 2_prompts/
│   ├── raw_prompt.md          ← leave a placeholder; I will paste my exact raw prompt
│   └── distilled_prompt.md    ← copy the exact first prompt I gave you in this session, verbatim, no edits
├── 3_claude_code_thread/
│   └── PLACEHOLDER.md         ← "Add /export output here (full thread, wrong turns included)"
├── 4_test_cases/
│   ├── test_cases.md          ← table: test name | what it proves | gap type. Cover all 16 tests.
│   └── test_results.txt       ← copy of the latest pytest -v output
└── 5_working_output/
    ├── links.md               ← placeholders for: deployed app URL, GitHub repo URL, demo video URL
    └── production_gaps.md     ← the exact 3 sentences on what this gets wrong in production (same as README "Known limitations")
```

Also:

1. In submission/README.md, add a short "Assumptions" section at the top (copied from the project README) — the brief explicitly says to state assumptions.
2. Add a "Wrong turns & corrections" section listing real moments from this session where something was wrong or changed (e.g. the timezone example correction, the orphan-refund ₹0 case and its new test, the sign-convention labelling, the spec changes you made). Only list things that actually happened — do not invent any.
3. Create a script make_zip.py that zips the project into onelab_submission.zip, excluding .git, .claude, \_\_pycache\_\_, .pytest_cache, \*.bundle and the zip itself. Run it and confirm the zip contents.
4. List every placeholder I still need to fill, in order.

Commit after.

## Claude

*Fixing the rounding and output details*

I'll check the current test list and grab the original spec file so the prompt copy is byte-exact.

*Ran a command*

The suite now has 32 test items, not 16, so the table will cover all 32. Pulling the exact Assumptions and Known limitations text from the README:

*Created 3 files, ran 5 commands, saved files to your computer*

The `submission/` folder is built, committed, and copied into `D:\Onelab`. All 32 tests still pass. `make_zip.py` ran: it zipped 27 files, and none of the excluded items got in.

**Decisions you should check:**

- **`distilled_prompt.md` holds the build spec you attached, not your literal first message.** Your first message in this session was the brainstorming question about assumptions, which belongs to deliverable 1. The spec file is clearly the distilled prompt, so I copied that file byte-for-byte. If you really did want the first message there, tell me and I'll swap it.
- **The test table covers 32 tests, not 16.** The suite grew to 32 during the session. The "Wrong turns" list notes this.
- **The zip also leaves out `.venv/`, `venv/` and `*.pyc`.** Otherwise a virtual environment in `D:\Onelab` would bloat it.
- **I didn't copy the zip to your machine.** The placeholders are still empty, so run `python make_zip.py` in `D:\Onelab` once they're filled. It's also listed in `.gitignore` so it won't get committed.

"Wrong turns & corrections" has 15 items, all from this session: the backwards timezone example, the settled orphan refund that had no test, the order test that didn't actually guard the order, the `round()` premise, the six problems from the reviewer pass, and so on.

**Placeholders to fill, in order:**

1. `submission/1_brainstorming_thread/PLACEHOLDER.md`: the brainstorm chat share link and PDF export.
2. `submission/2_prompts/raw_prompt.md`: your exact raw prompt.
3. `submission/3_claude_code_thread/PLACEHOLDER.md`: the `/export` output of this thread.
4. `submission/5_working_output/links.md`, three items:
   - the deployed app URL;
   - the GitHub repo URL;
   - the demo video URL.

For the deployed app you'll need to push to GitHub first: run the `git fetch onelab-history.bundle main` and `git reset FETCH_HEAD` lines, then push, in `D:\Onelab`. Streamlit Community Cloud can deploy `app.py` straight from the repo. After filling the placeholders, run `pytest -v > submission/4_test_cases/test_results.txt` on your machine so the file shows your own run, then run `python make_zip.py`.