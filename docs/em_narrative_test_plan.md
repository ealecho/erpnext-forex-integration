# Expense Management — Narrative Test Plan

**Status:** Draft for review.
**Purpose:** Replace the FX-centric coverage with a human-like, end-to-end narrative of the actual expense-management flows PEAS runs. Each phase adds one layer on top; each phase is itself end-to-end meaningful, not a Draft-save stub.

---

## Principles

1. **Each scenario tests a user journey, not a field.** Robert doesn't "save a doc"; he *requests money for a trip, gets approved, gets paid, comes back, claims against it, and the advance zeroes out*. Tests read like the journey.
2. **End-to-end = journey reaches the General Ledger** (or the leave balance, for TOIL). Draft-save is a cheap lie; Submit + GL is the truth.
3. **Phased layers, independently useful.** Phase 1 UGX-only flows prove the plumbing is sound before we bolt on budget ceilings, forex, or approvals.
4. **Human-like driving** means Playwright clicks real fields, triggers the real V3 client script, and hits the real Save/Submit/Approve buttons — not `frappe.client.insert` shortcuts. Exception: where a navigation race makes UI-save unobservable, we fall back to `frappe.client.*` AFTER staging via UI set_value (as Story 22 does).
5. **Each scenario leaves preserved records behind** on a green run — linked from the HTML report — so reviewers can click through to the real PI / EC / PE / JE / GL Entry.

---

## Phase 1 — Core expense-management flows (UGX only, no budget checks, no forex)

Pure-UGX. No multi-currency. No budget ceiling. Approval flows are driven through whatever workflow state is configured, but we don't exercise ceiling breaches. Covers the five flows from `peas_hr/expense_management.md` + one leave-track scenario.

### Scenario A — Field advance, then claim against it (Flow B)

**User story:** *As Robert (Uganda Finance), when I'm travelling for a week of school visits, I want to draw a cash advance before I go and reconcile it against my receipts when I return, so the Staff Advances ledger zeroes out without Finance chasing me.*

**End-to-end AC**
- Given Robert has no open Employee Advance balance.
- When Robert files a new Employee Advance for 500,000 UGX purpose="Field trip — Kampala schools" with an Expense Breakdown of the planned lines.
- And the EA moves through its workflow (Line Manager → Finance) and is approved.
- And Finance creates a Payment Entry that pays the advance to Robert's staff account.
- Then `tabGL Entry` for the PE shows Dr Staff Advances (11510), Cr Bank.
- And Robert's open advance balance on Staff Advances = 500,000 UGX.

- When Robert returns and files an Expense Claim `custom_claim_type = Advance Accountability`, links the advance, and attaches receipts totalling 450,000 UGX across matching lines.
- And the EC is approved and submitted.
- Then `tabGL Entry` for the EC submit shows Dr Expense accounts (per line), Cr Staff Advances 450,000.
- And Robert's Staff Advances balance = 50,000 UGX (residual).

- When Robert returns the 50,000 cash (or it's deducted from salary per the configured rule).
- Then Robert's Staff Advances balance = 0.

**Why this matters:** PEAS's single most common travel workflow. If settlement doesn't zero the advance, Finance is manually reconciling forever and salary deductions miss people.

---

### Scenario B — Out-of-pocket claim (Flow C)

**User story:** *As Sarah (Grants), when I bought office stationery with my own 80,000 UGX because petty cash was empty, I want to file an Expense Claim and be reimbursed, so I'm not carrying a cost the company owes me.*

**End-to-end AC**
- Given Sarah has no open advance.
- When Sarah files a new Expense Claim with `custom_claim_type = Out-of-Pocket`, no `advances` link, an expense line for Office Supplies at 80,000 UGX.
- And the EC is approved and submitted.
- Then `tabGL Entry` for the EC submit shows Dr Office Supplies, Cr Creditors 80,000.

- When Finance creates a Payment Entry paying Sarah 80,000.
- Then `tabGL Entry` for the PE shows Dr Creditors, Cr Bank 80,000.
- And Sarah's Creditors balance = 0.

**Why this matters:** When petty cash runs out (or someone's in the field with no card), staff shouldn't be out-of-pocket longer than the approval cycle. Broken OOP flow = staff stops fronting money = operations grind.

---

### Scenario C — Company credit card expense (Flow D)

**User story:** *As Robert, when I paid a 200,000 UGX hotel bill on the company Visa card during a trip, I want to declare the expense (with supporting receipt) so the books reflect it, but I'm owed nothing — the card already paid.*

**End-to-end AC**
- Given the company has an active Credit Card MOP and Robert is an authorised cardholder.
- When Robert files a new Expense Claim and sets `custom_claim_type = Company Card Expense`.
- Then the V3 client script auto-sets `is_paid = 1` and `mode_of_payment = Credit Card`, both read-only.
- And no Creditors balance is raised on submit.

- When Robert adds an expense line for Travel — Accommodation 200,000 UGX, attaches the hotel receipt, and submits the EC.
- Then `tabGL Entry` for the submit shows Dr Travel, Cr Credit Card Clearing 200,000.
- And no Payment Entry is expected or created.

- When the monthly card statement arrives and Finance reconciles it.
- Then Credit Card Clearing zeroes against Bank when the card bill gets paid (out of scope here — tested at bank-rec level).

**Why this matters:** Card transactions shouldn't create phantom reimbursables. A mis-configured Company Card claim would raise a Creditors balance that never gets paid — books carry a permanent error.

---

### Scenario D — Petty cash top-up (Flow E)

**User story:** *As the Kampala office admin, when our 100,000 UGX petty cash float has drawn down to 20,000 from lots of small purchases, I want to file a Petty Cash Request listing what was spent, get it approved, and see a Journal Entry created that books the expenses against Petty Cash so we can refill it from the bank.*

**End-to-end AC**
- Given the Kampala office petty cash account balance (11110) is currently 20,000 UGX.
- And the expense breakdown is mandatory on PCR (enforced in `tabDocField`, committed as peas_hr `1cb9f06`).

- When Admin files a PCR with an expense breakdown (≥1 row) totalling 80,000 UGX.
- And the PCR moves through its workflow and reaches the approved state.
- Then a Draft Journal Entry is created by the peas_hr server script (per `api.py._create_topup_je`).
- And the JE lines are: Dr each expense account per the breakdown, Cr Petty Cash (11110) 80,000 UGX.
- And the JE is linked back to the PCR via `custom_reference_pcr` or equivalent.

- When Finance submits the JE.
- Then `tabGL Entry` posts the Dr/Cr.
- And Petty Cash balance would be 20,000 − 80,000 = -60,000 (until physical cash refill).

- When Finance withdraws 80,000 from the bank and books a top-up JE: Dr Petty Cash, Cr Bank.
- Then Petty Cash balance = 100,000 (refilled).

**Why this matters:** Petty cash is where small operational errors compound. If the JE isn't auto-generated on PCR approval, admins reconcile cash drawers by hand every month.

---

### Scenario E — Fleet fuel (Flow A)

**User story:** *As Finance, when vehicle UG-VEH-002 fills up with 50,000 UGX of diesel against our fleet fuel float, I want to book the expense directly against the Fleet Fuel Float account with the vehicle tagged as an accounting dimension, so General Ledger filters per vehicle work and the float balance decreases correctly.*

**End-to-end AC**
- Given the Kampala office Fleet Fuel Float (11560) balance is 500,000 UGX.
- And Vehicle is configured as an accounting dimension (TASK-EM-07 — currently TODO per expense_management.md, **prerequisite for this scenario**).

- When Finance creates a Journal Entry, Dr Vehicle Costs (60340) 50,000, Cr Fleet Fuel Float (11560) 50,000, with Vehicle = UG-VEH-002 on the Vehicle Costs line.
- And submits it.
- Then `tabGL Entry` shows two rows, both carrying the vehicle dimension.
- And Fleet Fuel Float balance = 450,000.
- And filtering General Ledger by Vehicle=UG-VEH-002 returns the Vehicle Costs row.

**Why this matters:** Vehicle cost tracking is a compliance requirement with some donors. Without the dimension hitting GL, we cannot produce per-vehicle cost reports.

**Prerequisite:** TASK-EM-07 (Vehicle as accounting dimension). Scenario E is **blocked** until that lands.

---

### Scenario F — TOIL accrual and expiry (leave track, parallel)

**User story:** *As Robert, when I work extra hours on a weekend school event, I want to log an "Add TOIL" Attendance Request so my TOIL leave balance grows; I accept the balance expires at the end of the current leave period if I don't use it.*

**Flow (stock HRMS, PEAS-configured)**
1. Robert files an `Attendance Request` with `attendance_request_type = Add TOIL` for the date worked.
2. On submit, HRMS creates:
   - An `Attendance` record for that date (tagged as the worked day).
   - A `Compensatory Leave Request` (submitted) referencing the Attendance Request.
3. The Compensatory Leave Request triggers a `Leave Allocation` for leave type = TOIL, valid for the outstanding leave period (expires at period end).

**End-to-end AC**
- Given Robert has no open TOIL allocation today.
- When Robert submits an Attendance Request for 2026-04-12 (Saturday) with type = Add TOIL.
- Then exactly one Attendance record exists for Robert on 2026-04-12.
- And exactly one submitted Compensatory Leave Request exists referencing that Attendance Request.
- And a Leave Allocation exists for Robert, leave_type = TOIL, with from_date / to_date covering the current outstanding leave period.
- And Robert's TOIL balance for that period has increased by the allocation quantity.

- When the leave period ends and the allocation's `to_date` has passed.
- Then the balance is no longer available for new Leave Applications (expired by date validation — stock HRMS behaviour).

**Why this matters:** Weekend / overtime work is tracked operationally; staff expect their TOIL to show up, managers need to see the pending balance. A broken chain (Attendance Request submits but no allocation lands) silently under-credits staff.

---

## Phase 2 — Budget / cost-code layer

Adds on top of Phase 1. Each scenario in A–E becomes "same as before, with a budget code on every line".

- **Scenario B1** — Budget code cascade: when a staffer picks `budget_code` on an EA / EC / PCR line, the linked cost centre, department, donor, and expense account auto-fill from Cost Code Master. Covered by `peas_hr/narrative.spec.js` S1b per the md — we extend, not duplicate.
- **Scenario B2** — RGO ceiling breach: EA / EC submit blocks when the line's budget code total would exceed the RGO (role-grade-office) ceiling. Scenario walks through one successful submit within ceiling + one attempt that gets blocked with a clear error.
- **Scenario B3** — Department ceiling warn: same as B2 but a warn (not block) when the departmental total is exceeded.
- **Scenario B4** — GL dimension carries budget code: after submit, every `tabGL Entry` row for the transaction carries `budget_code`. Cross-reference against General Ledger report filtering by budget_code.

**Why phased this way:** Without Phase 1 proving the base journey, Phase 2 tests would conflate "budget breach" bugs with "flow-is-just-broken" bugs.

---

## Phase 3 — Multi-currency layer

This is where the existing `peasforex/tests/test_forex_stories.py` work becomes narrative-valuable. Each Phase 1 scenario that can be multi-currency gets a ZMW / GBP / USD variant.

- **Scenario MC1** — Field advance in USD (Flow B). Full Scenario A rerun with `custom_is_multicurrency = 1`, `custom_e_a_currency = USD`. Verifies settlement zeros out even when amounts are booked at the advance's USD→UGX rate.
- **Scenario MC2** — Out-of-pocket in GBP (Flow C). Sarah bought equipment in London on her card; files in GBP. Verifies per-line Spot→Ask resolver picks up.
- **Scenario MC3** — Company card foreign charge (Flow D). Robert paid a Zambian hotel in ZMW on the company card.
- **Scenario MC4** — JE booked at a non-base currency rate (Flow A or ad-hoc). Covered by current Story 22 + 24 — we'd rebrand it into this narrative.

Phase 3 pulls existing forex tests into the narrative framing rather than being a separate suite.

---

## Phase 4 — Approval workflows

Proves the multi-state workflow actually gates the journey. Until here we've been assuming workflow approval works.

- **Scenario W1** — EA rejected at Line Manager → back to Draft → corrected and resubmitted → approved.
- **Scenario W2** — EC auto-routes to CEO for amounts above a threshold.
- **Scenario W3** — PCR approval triggers JE creation (cross-ref with Scenario D).

---

## Where the tests live

**Proposal:** extend `peas_hr/playwright_tests/narrative.spec.js` for Phase 1 and Phase 4 — it's already the canonical narrative suite and has the infrastructure. Phase 2 probably lives there too; Phase 3 stays in `peasforex/tests/test_forex_stories.py` but gets its story narratives refactored to reference Phase 1 scenario IDs (so the coverage matrix is explicit).

Alternative — a single `tests/em/` top-level tree that imports setup from both apps. Heavier to build; cleaner as the app-count grows.

I'd default to "extend peas_hr narrative.spec.js" unless you prefer otherwise.

---

## Decisions (locked)

1. Phase 1 scope = A, B, C, D, F. Scenario E written but `test.skip`'d pending TASK-EM-07.
2. Tests extend `peas_hr/playwright_tests/narrative.spec.js`.
3. Depth = Submit + GL Entry for A–D; Attendance + Compensatory Leave Request + Leave Allocation for F.
4. Scenario E prerequisite = TASK-EM-07 Vehicle dimension is TODO → E skipped until it lands.

---

## Concrete test data on peas-dev.localhost (verified)

| Resource | Value |
|---|---|
| Company | `PEAS Uganda` |
| Employee | `HR-EMP-00004` (Active) |
| Staff Advances account | `Employee Advances - UG` |
| Bank | `Equity Bank UGX - UG` |
| Creditors | `Creditors - UG` |
| Petty Cash | `Cash - UG` (= `Company.custom_petty_cash_account`) |
| Travel expense | `Travel Expenses - UG` |
| Stationery expense | `Print and Stationery - UG` |
| Credit Card clearing | **Not configured** — PEAS may need a dedicated `Credit Card Clearing - UG` account. See Scenario C prerequisite below. |
| Mode of Payment | `Cash`, `Bank Draft`, `Credit Card` |
| Expense Claim Types | `Calls`, `Travel`, `Food`, `Medical`, `Accomodation` |
| Accounting Dimensions installed | `Budget Code`, `Department` (Vehicle not installed — EM-07 blocker) |
| EA workflow status | Not installed (TASK-EM-08 blocked); EA submits directly via docstatus=1 |

---

## Concrete per-scenario acceptance criteria (Phase 1)

### Scenario A — Field advance + claim

**Given** employee `HR-EMP-00004`, company `PEAS Uganda`, posting_date = today, Employee Advances balance = 0.

**When** I create a Draft EA with:
- `advance_amount = 500000` UGX
- `advance_account = Employee Advances - UG`
- `custom_advance_type = Float`
- `custom_funds_required_by_date = today + 7`
- `custom_expenses` = 1 row: `amount = 500000`, `description = "Field trip - Jinja schools"`, `date = today + 7`

**Then** the EA saves as Draft with a name.

**When** I submit the EA (docstatus=1, no workflow).

**When** I create a Payment Entry from the advance, `mode_of_payment = Cash`, `paid_from = Equity Bank UGX - UG`, `paid_to = Employee Advances - UG`, linked to the EA via `references[0].reference_doctype = Employee Advance`.

**And** I submit the PE.

**Then** `tabGL Entry` for this PE shows:
- 1 row Dr `Employee Advances - UG` 500,000
- 1 row Cr `Equity Bank UGX - UG` 500,000

**And** Robert's `Employee Advances - UG` balance = 500,000.

**When** I create a Draft EC with `employee = HR-EMP-00004`, `custom_claim_type = Advance Accountability`, linked to the EA in `advances[]`, expense lines totalling 450,000 (Travel 300k + Accommodation 150k).

**And** I submit the EC.

**Then** `tabGL Entry` for the EC shows:
- 1 row Dr `Travel Expenses - UG` 300,000
- 1 row Dr `Accomodation - UG` 150,000 (if exists; else a substitute expense account)
- 1 row Cr `Employee Advances - UG` 450,000

**And** Robert's `Employee Advances - UG` balance = 50,000 (residual).

**Cleanup:** preserve the EA, PE, EC on green. Link all three from the report under Scenario A.

---

### Scenario B — Out-of-pocket reimbursement

**Given** employee `HR-EMP-00004`, no open advance.

**When** I create an EC with `custom_claim_type = Out-of-Pocket`, no `advances[]`, one expense line: `expense_type = Calls` (or Travel), `amount = 80000`, `sanctioned_amount = 80000`, `expense_date = today`.

**And** I submit it.

**Then** `tabGL Entry` for the EC submit shows:
- Dr expense account (default payable-to account per expense type) 80,000
- Cr `Creditors - UG` 80,000

**When** I create a PE paying Sarah, `paid_from = Equity Bank UGX - UG`, `paid_to = Creditors - UG`, linked to the EC via `references[]`.

**And** I submit the PE.

**Then** `tabGL Entry` for the PE shows:
- Dr `Creditors - UG` 80,000
- Cr `Equity Bank UGX - UG` 80,000

**And** Sarah's `Creditors - UG` sub-balance = 0.

---

### Scenario C — Company credit-card expense

**Prerequisite check:** PEAS may need a `Credit Card Clearing - UG` account. If absent, the scenario either (a) stops at EC submit (no PE needed since `is_paid=1`) with GL going to whatever account the `Credit Card` MOP points at, or (b) the scenario is blocked until the account is added. Confirm which.

**Given** employee `HR-EMP-00004`, MOP `Credit Card` exists.

**When** I create an EC with `custom_claim_type = Company Card Expense`.

**Then** V3 script auto-sets `is_paid = 1`, `mode_of_payment = Credit Card` (both read-only).

**When** I add an expense line: `expense_type = Accomodation`, `amount = 200000`, `sanctioned_amount = 200000`, upload a receipt attachment (S-ATT), and submit.

**Then** `tabGL Entry` for the EC shows:
- Dr `Accomodation - UG` 200,000
- Cr [default account for the Credit Card MOP — TBD once reviewed] 200,000

**No PE** is created; `is_paid=1` means the card already paid.

**Assertion:** `Creditors - UG` sub-balance unchanged (the card path must not raise a reimbursable).

---

### Scenario D — Petty cash top-up

**Given** the Kampala Petty Cash account `Cash - UG` has balance = X (read current balance at test start; don't hard-code).

**When** I create a PCR with expense_breakdown listing 3 items totalling 80,000, submit to the approval path (workflow transition to "Paid" per the peas_hr petty-cash spec).

**Then** a Draft JE is auto-created by `peas_hr.api._create_topup_je` (or equivalent server script on the workflow transition).

**And** the JE has:
- Dr (per breakdown line) against the expense account on that line, totalling 80,000
- Cr `Cash - UG` 80,000

**When** I submit the JE.

**Then** `tabGL Entry` for the JE shows the same debits/credit.

**And** `Cash - UG` balance = X − 80,000.

---

### Scenario E — Fleet fuel [SKIP pending EM-07]

Written as `test.skip('Vehicle accounting dimension not installed')`. When EM-07 lands (Vehicle added to `tabAccounting Dimension`), un-skip and assert the Vehicle dimension is carried into GL Entry.

---

### Scenario F — TOIL (Attendance Request → Attendance + Compensatory Leave Request → Leave Allocation)

**Given** employee `HR-EMP-00004`, no existing Leave Allocation for leave_type = TOIL covering today.

**When** I file an Attendance Request with `employee = HR-EMP-00004`, `from_date = from_date = last Saturday`, `to_date = last Saturday`, `attendance_request_type = Add TOIL` (or whichever PEAS-configured field), and submit it.

**Then** exactly one Attendance record exists for employee + that date.

**And** exactly one submitted Compensatory Leave Request exists referencing the Attendance Request.

**And** a Leave Allocation exists for employee, leave_type = TOIL, `from_date` ≤ today ≤ `to_date` covering the outstanding leave period.

**And** the employee's TOIL balance in `frappe.client.get_value('Leave Ledger Entry', …)` or `leave_allocation.total_leaves_allocated` reflects the new accrual.

**And** on calling `employee.get_leave_balance('TOIL')` (or the equivalent HRMS helper), the returned balance has grown by the accrual quantity.

**Expiry assertion (if quick to verify):** the allocation `to_date` is set to the period end (read from Leave Period / Leave Policy in use). Actual forfeiture happens by date; tested implicitly because new `Leave Application` against an expired allocation fails validation.

---

## Execution order

1. Build Scenario A first — flagship, exercises EA + PE + EC + GL end-to-end. Working A = infrastructure proven.
2. B + C + D follow in parallel once A's helpers (submit EA, create PE, submit EC, query GL) are extracted.
3. F is a separate track (Attendance Request → HRMS leave stack) — can run in parallel with A.
4. E stays skipped until EM-07.

---

## Go / no-go

This is the last review checkpoint. If the concrete data above checks out (especially the **Credit Card Clearing account question in Scenario C**), reply "go" and I'll build Scenario A end-to-end, verify green, then move to B/C/D/F in sequence.
