# CLAUDE.md - peasforex

Developer context for Claude (and humans) working on this app.

---
## Code quality bar (read before writing code)

Write **production-grade, robust** code that uses the **simplest approach meeting the requirement**. Sophistication in the requirement is the ceiling; sophistication in the implementation is the floor — match them.

Before writing code, check in order:
1. **Reuse over net-new** — existing ERPNext Currency Exchange, existing Forex Rate Log, existing `resolve()` entry point.
2. **Prune hypothetical-future abstractions** — delete Manager/Handler/Service classes without a second caller.
3. **Prune defensive code for impossible states** — framework-trusted inputs don't need null guards; `try/except Exception: pass` is a red flag.
4. **Keep specified edge cases tight** — Spot vs Ask precedence, bidirectional pair lookup, month-end closing rate are the REAL complexity; don't bury them under theatre.

A property setter beats a client script. A custom field beats a custom DocType. A `before_validate` hook beats overriding the doctype class. Three similar lines beats a premature abstraction.

---
## What this app does

peasforex integrates Alpha Vantage FX data into ERPNext for PEAS, and
layers a Spot/Ask rate resolver over standard multi-currency transaction
doctypes (PI / PE / JE / Employee Advance / Expense Claim).

- Daily sync fetches Ask Rate from CURRENCY_EXCHANGE_RATE.
- Monthly sync fetches Closing + Monthly Average from FX_DAILY.
- Stored in Forex Rate Log. Ask Rate is copied to ERPNext's Currency
  Exchange so native transaction rate lookups work.
- On opted-in transaction doctypes, a `before_validate` hook populates
  the native rate field with Spot (if one was manually logged today)
  or Ask (fallback), and stamps the actually-used source for audit.

---
## Rate terminology (canonical)

| Type | Where it comes from | Stored where | Consumed how |
|---|---|---|---|
| **Ask Rate** | Alpha Vantage CURRENCY_EXCHANGE_RATE (field 9), daily; also the label used for historical mid-market from FX_DAILY per PEAS convention | Forex Rate Log **and** Currency Exchange | Transactions default to this via the resolver |
| **Spot Rate** | Manual entry only — actual rate agreed with the bank | Forex Rate Log only | Resolver picks this when user wants a negotiated rate; also reused within the day after a Manual override |
| **Closing** | Month-end close, mid-market. Source: FX_DAILY | Forex Rate Log only | Balance Sheet translation (future integration) |
| **Monthly Average** | Average of daily closes, mid-market. Source: FX_DAILY | Forex Rate Log only | P&L translation (future integration) |
| **Central Bank Rate** | Manual, sourced from BoU / BoZ / BoG / Manual | Forex Rate Log only | Audit evidence; can be forced in the resolver if explicitly picked |

**Spot vs Ask note**: In finance, Spot means the actual bank transaction
rate, NOT the indicative provider rate. The system previously labelled
Alpha Vantage rates as Spot incorrectly; renamed in April 2026 (code,
data, UI, reports, dashboards all updated).

---
## Known gap - historical ask rates

Alpha Vantage FX_DAILY is mid-market OHLC only. No ask/bid available
historically. Going forward, daily ask rates come from
CURRENCY_EXCHANGE_RATE (field 9). Monthly-average ask rates are
derivable only from accumulated daily ask records going forward.
Historical backfill of *true* ask rates is NOT possible — backfilled
rates are mid-market labelled as Ask Rate by PEAS convention.

**OPEN ITEM:** Sibeti to sign off on mid-market rates being acceptable
for grant reporting. Raised April 2026.

---
## Architecture

```
Alpha Vantage
    CURRENCY_EXCHANGE_RATE (daily)   --> ask_price (field 9)
    FX_DAILY               (monthly) --> close (mid-market)

peasforex/tasks/sync_forex.py
    sync_daily_spot_rates()          [function name unchanged; now writes Ask Rate]
        --> Forex Rate Log (Ask Rate, forward + reverse)
        --> Currency Exchange (forward + reverse)

    sync_monthly_rates()
        --> Forex Rate Log (Closing + Monthly Average, forward + reverse)
        --> Currency Exchange (Closing, forward + reverse)

    backfill_historical_rates(months=6)
        --> Forex Rate Log (Ask Rate — PEAS convention for mid-market, forward + reverse)

Transaction-side resolver
    peasforex/rates.py
        ADAPTERS registry (per-doctype field mapping)
        resolve(from, to, date, source) -> (rate, actual_source, rate_date)
        apply(doc) -> doc_events hook entry point

    Hooked on: Purchase Invoice, Payment Entry, Journal Entry,
               Employee Advance

    Expense Claim (labelled "Accountability" in the PEAS UI when
    custom_claim_type = "Advance Accountability"): handled client-side by
    peas_hr "Expense Claim Scripts V3" — per-row currency inherited from
    parent.custom_currency + per-row rate via peasforex.rates.resolve_whitelisted.
    Accountability is the same Expense Claim doctype, not a separate one.

Bidirectional
    A->B creates B->A at 1/rate. Gated on
    Forex Settings.create_bidirectional_rates.
```

---
## Custom fields added by peasforex (April 2026)

| Doctype | Field | Purpose |
|---|---|---|
| Purchase Invoice | `custom_forex_rate_source`, `custom_forex_rate_applied_date` | Rate methodology + lookup date on parent |
| Payment Entry | same | parent |
| Journal Entry | `custom_forex_rate_source` (**parent — planned move to per-row**, see docs/spot_ask_integration_plan.md W2), `custom_forex_rate_applied_date` (parent) | |
| Employee Advance | `custom_forex_rate_source`, `custom_forex_rate_applied_date` (shown when multi-currency) | parent |
| Expense Claim Detail | `custom_forex_rate_source` | per-row |
| Expense Breakdown | `custom_currency`, `custom_exchange_rate`, `custom_amount_in_base_currency` | per-row; child of Employee Advance (`custom_expenses`) and Petty Cash Request (`expense_breakdown`) |

---
## Key files

| Path | Purpose |
|---|---|
| `peasforex/rates.py` | Central resolver + `apply` hook + adapter registry |
| `peasforex/hooks.py` | `doc_events` registration for the 4 opted-in doctypes |
| `peasforex/fixtures/custom_field.json` | The 12 custom fields above |
| `peasforex/tasks/sync_forex.py` | All sync logic |
| `peasforex/api/alpha_vantage.py` | AV API client |
| `peasforex/peasforex/doctype/forex_rate_log/` | Rate history store |
| `peasforex/peasforex/doctype/forex_settings/` | Config singleton |
| `peasforex/peasforex/doctype/forex_sync_log/` | Sync operation log |
| `peasforex/peasforex/doctype/currency_pair/` | Configured pairs child |
| `peasforex/peasforex/doctype/fs_rate_demo/` | Sibeti's FS period-rate picker (exported from DB to source Apr 2026) |
| `peasforex/peasforex/report/exchange_rate_history/` | Rate history report |
| `peasforex/peasforex/page/prudency_calculator/` | Sarah's grant prudency calculator |
| `peasforex/tests/test_forex_ui.py` | Original 11-assertion UI test (kept as smoke test) |
| `peasforex/tests/test_forex_stories.py` | 120-assertion user-story suite (30 stories) |
| `peasforex/tests/generate_report.py` | HTML report generator with embedded acceptance criteria + audit |
| `peasforex/tests/report.html` | Generated report (regenerable via `--no-run` from cache) |
| `docs/spot_ask_integration_plan.md` | **Current** implementation plan for remaining polish items |

External touch: `peas_hr` app's "Expense Claim Scripts V3" Client Script
was updated in April 2026 to (a) hard-lock row currency when parent is
set, (b) filter advance picker to matching multi-currency EAs,
(c) inherit rate from linked Employee Advance into all expense lines,
(d) fall through to `peasforex.rates.resolve_whitelisted` when no
advance is linked.

**IMPORTANT — Client Script ownership (July 2026):** "Expense Claim
Scripts V3", "Employee Advance Scripts", "Payment Entry FX Rate" and
friends are shipped in `peas_hr/fixtures/client_script.json` (+
`install_data/`). They are NOT DB-only: any patch applied directly to a
site's Client Script record is silently reverted by the next
`bench migrate` / fixture sync. Fix them in the peas_hr fixture JSON.
The `custom_forex_rate_source` Property Setters (default "Live Rate",
"Auto" removed from UI options) also live in peas_hr fixtures, layered
over peasforex's Custom Fields — "Auto" is server-internal only.

---
## Configured pairs (April 2026)

GBP→UGX, GBP→ZMW, GBP→GHS, GBP→USD, GBP→CHF,
USD→UGX, USD→ZMW, DKK→GBP, EUR→GBP.
All reverse pairs auto-generated.

---
## Completed (April 2026)

- [x] Clear legacy Spot records and re-run backfill as Ask Rate — 2472
  auto-Spot rows renamed; backfill code writes Ask Rate directly; 4
  read-side consumers updated to default to Ask Rate.
- [x] UI terminology — Ask Rate label in forms/reports — rate_type
  default order, help-panel HTML, Exchange Rate History filter,
  Forex Sync Log sync_type (963 legacy rows renamed, schema/code
  mismatch closed), Currency Pair checkbox label.
- [x] Spot rate integration in transactions — resolver + hooks + custom
  fields + EC V3 inheritance + 80-assertion test suite.
- [x] FS Rate Demo promoted from DB-only custom doctype to peasforex
  source tree; `bs_rate_type` Spot option renamed to Ask Rate.

## In progress

- [ ] **See `docs/spot_ask_integration_plan.md`** for pending polish work:
  user-friendly field descriptions, JE source field move to per-row,
  Story 22 realistic-flow rewrite, preserve-records-by-default in test
  suite with records linked in the HTML report.

## Open / not scheduled

- [ ] PEAS sign-off on mid-market rates for grant reporting (Sibeti).
- [ ] Forex Rate Type DocType — replace hardcoded Select with Link
  (lets Karly add new rate types without schema changes).
- [ ] JE revaluation / translation semantics — month-end close flows
  using Closing and Monthly Average rates. Separate design round.
- [ ] Per-company gating of rate logic — global toggles today; may need
  per-company rules (PEAS Global GBP-base may skip Spot entirely).
- [ ] App-boundary migration (reviewed July 2026, decision pending):
  peasforex keeps rate infrastructure + accounting doctypes (PI/SI/PE/JE);
  HR consumers move to peas_hr — `breakdown.py` (merge into peas_hr
  `expense_hooks.py`), EA/PCR doc_events entries, `employee_advance.js` +
  `petty_cash_request.js`, EA/ECD forex Custom Fields; Expense Breakdown
  Custom Fields become real doctype fields in peas_hr. peas_hr's
  PI/SI/PE/JE Property Setters fold down into peasforex's custom_field
  defaults (kills peas_hr's `rename_ask_rate_to_live_rate` patch). Audit
  peas_hr's "Payment Entry FX Rate" fixture vs peasforex `payment_entry.js`
  for duplicate resolver logic.
- [ ] Deploy to `peasglobal.jh.frappe.cloud`.

---
## Running locally

```
bench --site peas-dev.localhost execute peasforex.tasks.sync_forex.sync_daily_spot_rates
bench --site peas-dev.localhost execute peasforex.tasks.sync_forex.sync_monthly_rates
bench --site peas-dev.localhost execute peasforex.tasks.sync_forex.backfill_historical_rates

pip install playwright && playwright install chromium
python3 peasforex/tests/test_forex_ui.py        # 11-assertion smoke test
python3 peasforex/tests/test_forex_stories.py   # 80-assertion user-story suite
python3 peasforex/tests/generate_report.py      # runs suite + writes report.html
python3 peasforex/tests/generate_report.py --no-run   # regenerates report from last cached output
```

Optional: `PEASFOREX_PRESERVE=1 python3 peasforex/tests/test_forex_stories.py`
leaves test-created records in the DB for manual review (prints `/app/…`
URLs at the end). Cleanup is the default today — changing to
preserve-on-success per `docs/spot_ask_integration_plan.md` W4.

---
## Test suites

### `test_forex_ui.py` — technical/data integrity smoke
11 assertions. Kept as a short-running baseline. Covers: Ask Rate count
for today, GBP→UGX CE=FRL integrity, PI conversion_rate auto-fill.

### `test_forex_stories.py` — user-story suite (120 assertions, 30 stories)

| # | Actor | Story | Mode |
|---|---|---|---|
| 1 | Karly | Forex Settings configuration | UI |
| 2 | Robert | Daily sync + Forex Rate Log | API |
| 3 | Robert | Purchase Invoice auto-populates rate | UI |
| 4 | Robert | Override with negotiated Spot Rate | Hybrid |
| 5 | Sibeti | Closing + Monthly Average in FRL (not CE) | API |
| 6 | Robert | Central Bank Rate entry for audit | API |
| 7 | Sarah | Prudency Calculator loads | UI |
| 8 | Sibeti | FS Rate Demo form loads with Ask Rate option | UI |
| 9 | — | Admin access to finance surfaces | UI |
| 10 | Karly | Sync log health (no silent errors) | API |
| 11 | Robert | Payment Entry auto-populates (UI set_value chain) | UI |
| 12 | Sibeti | JE accepts resolver rate on multi-currency row | UI |
| 13 | Robert | Date-sensitive rate lookup across 3 dates | API |
| 14 | Robert | Spot Rate first-use + deduplication + no CE leak | API |
| 15 | — | Diagnostic: no auto-written Spot from AV | API |
| 16 | Sibeti | Central Bank Rate does not pollute CE | API |
| 17 | — | Resolver contract: Auto / Spot / Ask / Manual rules | API |
| 18 | Robert | Employee Advance rate resolves + source stamped on save | UI |
| 19 | Robert | EC parent-currency hard lock on rows (L1/L2/L3) | UI |
| 20 | Robert | EC inherits rate from linked Employee Advance | UI |
| 21 | Robert | Payment Entry saves with resolved rate + source | UI |
| 22 | Sibeti | Journal Entry multi-currency resolves per-row | Hybrid (see plan W3) |
| 23 | Robert | Sales Invoice auto-populates rate | UI |
| 24 | Sibeti | JE submit writes stamped rate to GL Entry | UI |
| 25 | Robert | EC Company Card claim + multi-currency line | UI |
| 26 | UG officer | GBP EA with 3 breakdown lines, resolver stamp | UI |
| 27 | UG finance | PE books the GBP advance payout | UI |
| 28 | UG officer | EC accountability settles the GBP advance | UI |
| 29 | UG officer | Regression: EA breakdown rows inherit parent rate on save | UI |
| 30 | UG finance | Regression: submitted EA not dirtied by client scripts; update-after-submit saves clean | UI |

Expected result: **120 passed / 0 failed / 0 skipped**. Runs against
peas-dev (BASE_URL default `http://peas-dev.localhost:8020`). Note: the
bench dev servers resolve the site from the process's FRAPPE_SITE env,
NOT the Host header — :8020 is peas-dev, :8021 is peas-expense-test.

Report file: `peasforex/tests/report.html`. Renders user-story narrative
+ Given/When/Then acceptance criteria + per-assertion results +
session audit. After plan W4 lands, it will also embed clickable
links to the records each story created.
