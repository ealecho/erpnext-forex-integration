# Spot/Ask Integration — Remaining Implementation Plan

**Status:** Draft, awaiting sign-off before execution.
**Last updated:** 2026-04-12
**Scope owner:** peasforex (+ one edit in peas_hr V3 client script if W2 needs downstream follow-up)

---

## Context recap — what's already live

| Capability | Status |
|---|---|
| Central resolver `peasforex.rates.resolve()` + `apply()` hook entry point | Live |
| `before_validate` hooks on PI, PE, JE, Employee Advance | Live (Accountability deferred — `distribution_csf` not installed here) |
| Custom fields `custom_forex_rate_source` + `custom_forex_rate_applied_date` on PI, PE, JE (parent), Employee Advance | Live |
| Per-line `custom_forex_rate_source` on Expense Claim Detail | Live |
| Expense Breakdown child (shared by EA + Accountability): `custom_currency`, `custom_exchange_rate`, `custom_amount_in_base_currency` | Live |
| Expense Claim V3 script modifications (hard currency lock, advance-rate inheritance, 1-EA-per-multi-currency rule, Spot→Ask resolver call, advance picker filter) | Live |
| Data migration: 2472 auto-Spot → Ask Rate; 963 Spot (Daily) sync_type → Ask Rate (Daily) | Done |
| FS Rate Demo: exported DB → source files, `bs_rate_type` Spot → Ask Rate | Done |
| Test suite: 80 assertions across 22 stories, HTML report + audit narrative | Live |

## Scope of this plan

Four work items, roughly in increasing disruptiveness. Each is small; the *order* matters because W2 changes data shape that the report and tests inspect.

- **W1** — Replace technical field descriptions with user-friendly wording.
- **W2** — Move `custom_forex_rate_source` on Journal Entry from parent to per-row (`Journal Entry Account`), to co-locate source with rate.
- **W3** — Rewrite Story 22 to follow the realistic user flow (let the hook fill the rate, compute the balancing row from what it fills — proves balance, not imbalance).
- **W4** — Default the test suite to "preserve created records on success, clean up on failure", and surface the preserved record URLs as clickable links inside the HTML report.

No new functionality. No schema breaks for PI / PE / EA / EC. Only JE schema changes (one field moves location); existing JE data unaffected (the field's current parent value is unused by any live code outside the resolver, which is being updated in lockstep).

---

## W1 — User-friendly field descriptions

### What

Rewrite the `description` attribute on each peasforex custom field. No behaviour changes.

### Before / after

| Field | Current | Proposed |
|---|---|---|
| `custom_forex_rate_source` (PI / EA / PE — single-rate docs) | "How conversion_rate is resolved. Auto: Spot then Ask Rate for the applied date. Manual: your typed rate (also logged as Spot for reuse today)." | "How today's rate is decided.<br>• **Auto** — use the bank Spot rate if one was logged today, otherwise today's indicative (Ask) rate.<br>• **Spot** — insist on the negotiated bank rate (fails if none logged).<br>• **Ask Rate** — insist on the indicative market rate.<br>• **Central Bank Rate** — use the official audit rate.<br>• **Manual** — you'll type a rate directly; we'll save it as a Spot rate so other documents today can reuse it." |
| `custom_forex_rate_applied_date` | "Date used to look up the rate. Leave blank to use posting_date." | "Which date's rate applies to this document. Leave blank to use the posting date. Set this to use yesterday's rate on a document posted today, or vice versa." |
| JE `custom_forex_rate_source` (post-W2, per-row) | "How per-row exchange_rate is resolved. Inherited: set by programmatic callers (settlement JEs)." | "How this row's rate is decided. Same options as the parent document. **Inherited** applies automatically when this JE was built from another document (e.g. a settled Expense Claim) — the rate comes from that source." |
| Expense Claim Detail `custom_forex_rate_source` | "Auto: Spot then Ask Rate for expense_date. Inherited: rate locked to the linked Employee Advance." | "How this line's rate is decided. If this claim is tied to an Employee Advance, the advance's rate is inherited (read-only) so the advance balances to zero when fully claimed. Otherwise, Auto picks the bank Spot rate first, Ask as fallback, using this line's expense date." |
| Expense Breakdown `custom_currency` | "Line currency. Defaults to parent document currency." | "Currency this expense was incurred in. Defaults to the document's currency — the system sets it for you." |
| Expense Breakdown `custom_amount_in_base_currency` | "amount x custom_exchange_rate, in the company's base currency." | "The line amount converted to company currency at this row's rate. Read-only — the system computes it." |

### Files touched

- `peasforex/fixtures/custom_field.json`

### How

Single-file edit of description strings. `bench --site <site> migrate` picks them up.

### Acceptance criteria

- Open each custom field in Customize Form → description shows the new wording.
- Hover the field's help icon in a real doc → new description appears.
- No functional change; existing `test_forex_stories.py` still 80/80.

### Risk

Low. Pure text change. Reversible.

---

## W2 — Move JE source field to per-row

### Why

The rate on a Journal Entry lives on each account row (`accounts[i].exchange_rate`). A single parent-level source field can't honestly say which rate methodology was used on which row when a multi-pair JE touches more than one currency. Source belongs next to the rate it applied to.

### What

1. Remove `custom_forex_rate_source` + `custom_forex_rate_applied_date` from **Journal Entry** parent.
2. Add `custom_forex_rate_source` to **Journal Entry Account** child, inserted after `exchange_rate`. Default `Auto`. Same options as the parent version. `custom_forex_rate_applied_date` stays on the parent (one lookup date for the whole JE is still sensible — rarely needed per-row).
3. Update `peasforex/rates.py`:
   - `ADAPTERS["Journal Entry"]` slot keeps `table: "accounts"` + `from_field` + `rate_field`.
   - `apply()` reads the source from each row's `custom_forex_rate_source`, not parent's; stamps the resolved source back onto the row.
   - Parent `custom_forex_rate_applied_date` is read and used uniformly for all rows.

### Files touched

- `peasforex/fixtures/custom_field.json` (remove 2 parent entries, add 1 child entry)
- `peasforex/rates.py` (adapter + apply logic)
- `peasforex/tests/generate_report.py` (ACCEPTANCE entry for Story 22 updates to describe per-row)

### Acceptance criteria

- JE form:
  - No `custom_forex_rate_source` at parent level.
  - `custom_forex_rate_applied_date` remains at parent.
  - Each accounts row has a Source column, next to Exchange Rate.
- On save with Auto selected on each row: the resolver stamps the row's source in-place (Spot / Ask Rate / etc.), not the parent's.
- Existing stories 17 (resolver contract) and 22 (JE save) continue to pass.

### Risk

Medium. Fixture removal of a parent field deletes existing column data. No live caller reads JE's parent source yet (only the resolver, which we're updating simultaneously), so cutover is clean in this site. If another site has relied on the parent field, they'd need to migrate values to the row level (simple SQL). Flag in changelog.

### Migration note

For any existing JE where `custom_forex_rate_source` was stored at parent level (likely only from our own test runs), values are cosmetic — they don't drive any downstream calculation. Discarding them is safe.

---

## W3 — Rewrite Story 22 to a realistic user flow

### Why

The current Story 22 seeds **both** sides of the JE (GBP debit and UGX credit) with values that assume a specific rate will win. When the hook picks a different rate at save time, one side gets recomputed (debit = account_currency × exchange_rate) and the other doesn't (balancing UGX credit stays at the pre-filled value). Result: ACC-JV-2026-00042 saved with 512,346 dr ≠ 497,569 cr — a test artifact, not a product bug. The test mis-represents the integration.

### What

Stage **only** the GBP debit side via UI set_value. Save. After save, read the GBP row's resolved rate. Then compute and stage the balancing UGX credit from that resolved rate so the JE balances. Assert balance + source stamp.

### Acceptance criteria

- Story 22 saves a JE with:
  - GBP row: `debit_in_account_currency = 100`, `exchange_rate` filled by resolver, `debit` base-currency matches.
  - UGX row: `credit_in_account_currency` computed from the **resolved** rate, `credit` base-currency matches.
  - `total_debit == total_credit` (balances — a submit-ready state, even though we keep it Draft).
  - Row-level `custom_forex_rate_source` stamped from `Auto` to the actually-used source (`Spot` or `Ask Rate`), per W2.

### Files touched

- `peasforex/tests/test_forex_stories.py` (Story 22 body)
- `peasforex/tests/generate_report.py` ACCEPTANCE entry for Story 22 updated

### Risk

Low. Test-only change.

---

## W4 — Preserve by default, link records in report

### Why

Right now the suite deletes every test-created record in the cleanup block at the end of each run. The user can't review what the tests actually produced without rerunning with `PEASFOREX_PRESERVE=1`. The report should make those records reviewable by default on a green run.

### What

1. **Suite behaviour:** default to preserve on full green, clean up only on failure. (Rationale: if tests failed, the created records may be inconsistent and should not linger. If they passed, the records are valid artifacts worth reviewing.)
2. **Report:** for every story that created records, render a "**Records created**" subsection with clickable `/app/<doctype>/<name>` links to the base URL.
3. **Report generator** records which story created which rows (already tracked via `CREATED_ROWS` — extend to keep a per-story map so the HTML can attribute each record to its story).

### Acceptance criteria

- `python3 peasforex/tests/generate_report.py` on a clean green run leaves test records in the DB.
- Failing run cleans up records (original behaviour).
- Report renders clickable URLs grouped by the story that created them, e.g. under Story 22:
  - `Journal Entry / ACC-JV-2026-00045`
- An explicit `PEASFOREX_CLEANUP_ALWAYS=1` env var lets a user force cleanup on green if they want the old behaviour.

### Files touched

- `peasforex/tests/test_forex_stories.py` (cleanup logic + per-story CREATED_ROWS tracking)
- `peasforex/tests/generate_report.py` (render records section per story)

### Risk

Low. Test infrastructure only.

---

## Execution order + why

1. **W1 (descriptions)** first — pure text, no cascade. Ships the UX fix immediately.
2. **W2 (JE per-row source)** — schema change. Must happen before W3 since Story 22's assertions read the source field from its new location.
3. **W3 (Story 22 rewrite)** — updates the test so the report stops showing an imbalanced JE as the flagship JE example.
4. **W4 (preserve + link)** — last, so the report already reflects W1–W3 outcomes when we teach it to link to records.

Each step is verified by running the full suite + `generate_report.py` before moving on.

---

## Roll-back

- W1: revert the fixture edit, migrate.
- W2: re-add the parent fields to the fixture, remove the child field, revert `rates.py`. No data loss (JE's parent-source column is cosmetic).
- W3: revert Story 22 code.
- W4: revert test + generator edits. Old `PEASFOREX_PRESERVE=1` toggle still works.

All steps are `git revert`-sized.

---

## Test plan

For each work item:
1. `bench --site peas-dev.localhost migrate` (if fixture touched).
2. `bench --site peas-dev.localhost clear-cache`.
3. `python3 peasforex/tests/generate_report.py` — expect 80+/80+ passes.
4. Inspect `report.html` — verify AC listed above.
5. Open a real record referenced in the report; verify the source stamping is visible adjacent to the rate.

After W4 is live, the end-to-end manual verification is:
- Run the report.
- Open the report in a browser.
- Click through the links in Story 18, 21, 22 — land on the real PI/EA/PE/JE records.
- Confirm `custom_forex_rate_source` shows `Spot` or `Ask Rate` (not `Auto`) on the saved documents.

---

## What this plan explicitly does NOT include

- Re-enabling the Accountability hook (gated on `distribution_csf` installation).
- JE revaluation / month-end translation semantics (separate design round).
- Per-company gating of the rate logic (all-companies-on for this release).
- Forex Rate Type DocType (Select → Link refactor) — still a separate future task.
- Submit-lifecycle assertions (current tests stop at Draft save). Submit flows exercise different code paths.

---

## Open questions for reviewer

1. **W4 default preservation:** OK to leave records in DB on green by default? Or default cleanup and opt-in to preserve with `PEASFOREX_PRESERVE=1` (current behaviour)?
2. **W2 applied_date placement:** keep on parent (one date per JE) or also move to per-row? My read is parent is fine — it's rare to want different lookup dates on rows of the same JE — but willing to move it if you want symmetry with source.
3. **W3 balancing approach:** have the test compute the UGX credit *after* reading the resolved rate from the saved GBP row? Or have the test re-stage and re-save? First is cleaner; second is more user-like but more code.
