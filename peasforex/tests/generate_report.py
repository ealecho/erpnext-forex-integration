"""
Generate an HTML report bundling the peasforex test-suite results and a
narrative audit of changes delivered in the April 2026 Spot rate integration.

Usage:
    python3 peasforex/tests/generate_report.py            # runs tests, writes report.html
    python3 peasforex/tests/generate_report.py --no-run   # parse last cached output only
"""

import datetime
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE = HERE / "test_forex_stories.py"
OUT = HERE / "report.html"
CACHE = HERE / ".last_run.txt"
RECORDS = HERE / ".last_run.records.json"


# ---------------------------------------------------------------------------
# Run the suite (or reuse cached output)
# ---------------------------------------------------------------------------

def run_suite() -> str:
    print("Running test_forex_stories.py ...")
    env = os.environ.copy()
    proc = subprocess.run(
        [sys.executable, str(SUITE)],
        capture_output=True, text=True, env=env,
        cwd=HERE.parent.parent,
    )
    output = proc.stdout + ("\n" + proc.stderr if proc.stderr.strip() else "")
    CACHE.write_text(output)
    return output


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

STORY_RE = re.compile(r"^\[(Story \d+|Preflight|Cleanup)\]\s*(.*)$")
ASSERT_RE = re.compile(r"^\s*\[(PASS|FAIL|SKIP)\]\s+(.+?)(?:\s+->\s+(.*))?$")
RESULT_RE = re.compile(r"^RESULT:\s+(\d+)\s+passed\s+\|\s+(\d+)\s+failed\s+\|\s+(\d+)\s+skipped\s+\|\s+(\d+)\s+total\s*$")


def parse(output: str) -> dict:
    stories = []
    current = None
    summary = {"passed": 0, "failed": 0, "skipped": 0, "total": 0}
    for raw in output.splitlines():
        line = raw.rstrip()
        m = STORY_RE.match(line)
        if m:
            if current:
                stories.append(current)
            current = {
                "name": m.group(1),
                "title": m.group(2).strip(),
                "assertions": [],
            }
            continue
        m = ASSERT_RE.match(line)
        if m and current is not None:
            current["assertions"].append({
                "state": m.group(1),
                "label": m.group(2).strip(),
                "detail": (m.group(3) or "").strip(),
            })
            continue
        m = RESULT_RE.match(line)
        if m:
            summary = {
                "passed": int(m.group(1)),
                "failed": int(m.group(2)),
                "skipped": int(m.group(3)),
                "total": int(m.group(4)),
            }
    if current:
        stories.append(current)
    return {"stories": stories, "summary": summary, "raw": output}


# ---------------------------------------------------------------------------
# Audit narrative - synchronised with CLAUDE.md pending-work ticks
# ---------------------------------------------------------------------------

ACCEPTANCE = {
    "Story 1": {
        "user_story": "As Karly (Project Champion), I want to verify Forex Settings is correctly configured so I can sign off on the integration before go-live.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "The Forex Settings configuration surface is present and loads cleanly",
                "gwt": [
                    "Given I am an Administrator",
                    "When I open Forex Settings",
                    "Then the form loads without error",
                    "And the fields api_key, enabled, create_bidirectional_rates, auto_update_currency_exchange, currency_pairs are all visible",
                ],
                "why": "If any of these core toggles are missing, Karly cannot configure the integration at all.",
            },
            {
                "title": "At least one daily-sync pair is configured, and GBP->UGX (PEAS primary) is among them",
                "gwt": [
                    "When I read the Currency Pairs table",
                    "Then at least one pair has enabled=1 AND sync_spot_daily=1",
                    "And one of those pairs is GBP->UGX",
                ],
                "why": "Daily sync is a no-op without pairs. Missing GBP->UGX would block the entire Uganda finance flow.",
            },
        ],
    },

    "Story 2": {
        "user_story": "As Robert (Uganda Finance), I want to see today's ask rates synced and internally consistent so I can trust them for transactions.",
        "mode": "API",
        "acceptance": [
            {
                "title": "Today's Ask Rate rows exist in the expected count (2 x enabled daily pairs)",
                "gwt": [
                    "Given the daily sync has run today",
                    "When I count Ask Rate rows in Forex Rate Log for today",
                    "Then the count equals 2 x (enabled daily pairs) - forward and reverse for each",
                ],
                "why": "Off-count signals a partial sync: reverse rates missing would break any transaction booked in the reverse direction.",
            },
            {
                "title": "Bidirectional rates are mutually inverse (forward x reverse == 1)",
                "gwt": [
                    "For every pair that has both directions today",
                    "When I multiply forward_rate by reverse_rate",
                    "Then the product approximates 1.0 (within 1%)",
                ],
                "why": "A drift here means the bidirectional generator has a bug; transactions booked in opposite directions would stop reconciling.",
            },
            {
                "title": "GBP->UGX is in a realistic range (3000-8000)",
                "gwt": [
                    "When I read today's GBP->UGX Ask Rate",
                    "Then it is between 3000 and 8000 UGX per GBP",
                ],
                "why": "A rate outside this band suggests a unit error (pence vs pounds, inverse stored wrong) that would silently corrupt ledger values.",
            },
            {
                "title": "Forex Sync Log records today's activity and errors carry messages",
                "gwt": [
                    "When I read Forex Sync Log entries for today",
                    "Then at least one entry exists",
                    "And any entry with status='Error' has a non-empty error_message",
                ],
                "why": "Silent failures are the worst kind. Karly's monitoring depends on errors being traceable.",
            },
        ],
    },

    "Story 3": {
        "user_story": "As Robert, I want the conversion rate on a new GBP Purchase Invoice to auto-fill so I do not have to look up today's rate manually.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "Currency Exchange has today's GBP->UGX with exactly one row per pair per day",
                "gwt": [
                    "When I count CE rows for today with from=GBP to=UGX",
                    "Then the count is exactly 1",
                ],
                "why": "Duplicate CE rows for the same day cause non-deterministic rate pickups downstream.",
            },
            {
                "title": "Purchase Invoice auto-populates conversion_rate on company=PEAS Uganda + currency=GBP, matching CE Ask within 5%",
                "gwt": [
                    "Given today's GBP->UGX rate is in CE",
                    "When I open a new Purchase Invoice and set Company=PEAS Uganda, Currency=GBP",
                    "Then conversion_rate populates automatically",
                    "And the populated rate matches today's CE Ask Rate within 5%",
                ],
                "why": "If Robert has to type the rate himself, he will occasionally mistype, producing mis-booked GL entries that cost Finance hours to reconcile.",
            },
        ],
    },

    "Story 4": {
        "user_story": "As Robert, I want to override the auto rate with the actual bank-negotiated rate (logged as a manual Spot Rate) so the document reflects the real exchange.",
        "mode": "Hybrid",
        "acceptance": [
            {
                "title": "The Purchase Invoice form exposes a populated auto-rate before Robert overrides",
                "gwt": [
                    "Given I have opened a new PI with Company=PEAS Uganda, Currency=GBP",
                    "When the form finishes loading",
                    "Then conversion_rate already carries today's rate, not blank",
                ],
                "why": "Robert must see a sensible starting point before he decides to override - a blank field invites typos.",
            },
            {
                "title": "A manual Spot Rate can be logged to Forex Rate Log and round-trips on read-back",
                "gwt": [
                    "When I insert a Forex Rate Log row with rate_type='Spot', source='Manual'",
                    "Then the insert succeeds",
                    "And reading the row back returns the same rate_type and exchange_rate",
                ],
                "why": "This is the canonical override workflow per CLAUDE.md - Spot rates are bank-negotiated and must persist so other documents today can reuse them.",
            },
        ],
    },

    "Story 5": {
        "user_story": "As Sibeti (CFO), I want Closing and Monthly Average rates in Forex Rate Log (but not in Currency Exchange) so I can prepare balance-sheet and P&L translations without polluting the transaction rate table.",
        "mode": "API",
        "acceptance": [
            {
                "title": "Closing rates exist for GBP->UGX across multiple months",
                "gwt": [
                    "When I read Forex Rate Log for rate_type='Closing', GBP->UGX",
                    "Then at least one row exists (ideally several, one per month-end)",
                ],
                "why": "Balance-sheet translation needs historical Closing rates; missing months mean Sibeti cannot consolidate that period.",
            },
            {
                "title": "Monthly Average rates exist and differ from Closing for the same months",
                "gwt": [
                    "When I read both Closing and Monthly Average for GBP->UGX",
                    "Then Monthly Average rows exist",
                    "And for months present in both, the two values differ (because they describe different things)",
                ],
                "why": "If Average matches Closing, one of them is likely bogus data - the two numbers represent distinct accounting methodologies (P&L vs B/S).",
            },
            {
                "title": "Currency Exchange carries today's Ask Rate, not Closing or Average",
                "gwt": [
                    "When I compare today's CE rate for GBP->UGX to today's FRL Ask Rate",
                    "Then they are equal (within 0.01)",
                ],
                "why": "Mixing Closing or Average into CE would make transactions use the wrong rate type. CE must stay Ask-only.",
            },
        ],
    },

    "Story 6": {
        "user_story": "As Robert, I want to manually enter a Central Bank Rate for audit, and the system must enforce Company=required for that rate type.",
        "mode": "API",
        "acceptance": [
            {
                "title": "Central Bank Rate without Company is rejected",
                "gwt": [
                    "When I attempt to insert a Forex Rate Log with rate_type='Central Bank Rate' and no company",
                    "Then the save is rejected by the validate method",
                ],
                "why": "Central Bank rates are per-company (Bank of Uganda vs Bank of Zambia). A CB rate without a company is audit-unusable and must be blocked.",
            },
            {
                "title": "Central Bank Rate with Company saves successfully",
                "gwt": [
                    "When I insert the same row with company='PEAS Uganda' set",
                    "Then the save succeeds",
                ],
                "why": "Confirms the validation does not over-reject - legitimate audit entries must land.",
            },
        ],
    },

    "Story 7": {
        "user_story": "As Sarah (Grants), I want the Prudency Calculator page to load with the inputs I need so I can compute grant-budget rates.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "The Prudency Calculator page renders its full input surface",
                "gwt": [
                    "When I open /app/prudency-calculator",
                    "Then the container is present",
                    "And Proposal Mode and Expense Planning Mode tabs are both visible",
                    "And Grant Currency and Local Currency selectors render",
                    "And the Load Rates button is visible",
                    "And the rates table scaffold + grand-average display are present",
                ],
                "why": "Any missing input blocks Sarah from producing a prudency calculation for a grant proposal - she cannot ship the grant without it.",
            },
        ],
    },

    "Story 8": {
        "user_story": "As Sibeti, I want the FS Rate Demo form to expose period + reporting currency + Balance Sheet / P&L rate type selectors so I can pick the right rates for consolidation.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "All FS Rate Demo fields render on a new record",
                "gwt": [
                    "When I open a new FS Rate Demo",
                    "Then period_start, period_end, reporting_currency, bs_rate_type, pl_rate_type and rates_html all render",
                ],
                "why": "Sibeti cannot pick rates without the selectors; missing rates_html means no output surface.",
            },
            {
                "title": "bs_rate_type offers 'Ask Rate' (post-rename) and no longer offers 'Spot'",
                "gwt": [
                    "When I read the bs_rate_type Select options",
                    "Then 'Ask Rate' is present",
                    "And 'Spot' is absent",
                ],
                "why": "Regression guard: the April 2026 terminology rename must hold here too, or Sibeti sees a stale option.",
            },
        ],
    },

    "Story 9": {
        "user_story": "As Karly, I need the full finance surface (Forex Settings, FRL list, Prudency Calculator, Forex Integration workspace) to be reachable by an Administrator so I can demo and manage the integration.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "Each finance surface loads without 404 or permission error",
                "gwt": [
                    "When I navigate in turn to Forex Settings, Forex Rate Log list, Prudency Calculator, Forex Integration workspace",
                    "Then each page loads (no 404, no permission error)",
                ],
                "why": "Broken navigation breaks demos and operational flows; these four pages are the daily surface.",
            },
        ],
    },

    "Story 10": {
        "user_story": "As Karly, I want to monitor sync health so I am confident the integration is running and can catch failures early.",
        "mode": "API",
        "acceptance": [
            {
                "title": "Forex Sync Log has activity in the last 30 days",
                "gwt": [
                    "When I count Sync Log entries in the last 30 days",
                    "Then the count is greater than zero",
                ],
                "why": "No recent entries means cron has silently stopped running - rates are stale and transactions will use old numbers.",
            },
            {
                "title": "Successes outnumber errors (integration actually works)",
                "gwt": [
                    "When I group last-30-day entries by status",
                    "Then the Success count exceeds the Error count",
                ],
                "why": "If errors dominate, the integration is broken even if it technically ran.",
            },
            {
                "title": "Every Error has a non-empty error_message",
                "gwt": [
                    "For each entry with status='Error' in the last 30 days",
                    "Then error_message is a non-empty string",
                ],
                "why": "Silent errors cannot be debugged. Karly needs enough detail to route to Alpha Vantage, networking, or PEAS-side issues.",
            },
        ],
    },

    "Story 11": {
        "user_story": "As Robert, I want a GBP->UGX internal-transfer Payment Entry to auto-fill source_exchange_rate so I do not have to look up today's rate before booking the transfer.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "PE source_exchange_rate auto-populates when paid_from=GBP bank and paid_to=UGX cash",
                "gwt": [
                    "Given a GBP Bank account and a UGX Cash account exist on PEAS Uganda",
                    "When I open a new Payment Entry, set Payment Type=Internal Transfer, Paid From=Bank GBP - UG, Paid To=Cash - UG",
                    "Then source_exchange_rate auto-populates",
                    "And the value matches today's CE Ask Rate within 5%",
                ],
                "why": "Internal transfers across currencies happen daily; manual rate lookup introduces drift between booked and actual rates.",
            },
        ],
    },

    "Story 12": {
        "user_story": "As Sibeti, I want a multi-currency Journal Entry's GBP account row to accept the resolver-sourced rate so the entry books correctly in company currency.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "JE accepts a resolver-sourced rate on a GBP account row that matches today's CE Ask (within 5%)",
                "gwt": [
                    "Given a GBP leaf account exists on PEAS Uganda",
                    "When I enable multi_currency on a new JE and add a GBP row",
                    "Then the row accepts a rate resolved via the shared endpoint",
                    "And the rate matches today's CE Ask Rate within 5%",
                ],
                "why": "Validates the underlying rate-resolution contract works for JE. Full onchange-driven auto-populate on row add is proven separately by Story 22.",
            },
        ],
        "notes": "Full grid-typing auto-populate is not reproducible from Playwright; we verify the resolver contract directly here. Story 22 covers the save-path with per-row source stamping.",
    },

    "Story 13": {
        "user_story": "As Robert, I want rate lookups routed by transaction_date so backdated or historical transactions pick up the correct historical rate.",
        "mode": "API",
        "acceptance": [
            {
                "title": "At least 2 distinct historical GBP->UGX rates exist to prove date routing",
                "gwt": [
                    "When I read Currency Exchange for GBP->UGX",
                    "Then at least 2 rows have distinct exchange_rate values on different dates",
                ],
                "why": "If rates never change, a date-routing test is meaningless. This guards against a pathological fixture.",
            },
            {
                "title": "The shared rate resolver returns the correct CE rate for each test date",
                "gwt": [
                    "When I call erpnext.setup.utils.get_exchange_rate for 3 distinct historical dates",
                    "Then each call returns the CE row's exchange_rate for that date",
                ],
                "why": "All transaction types (PI, PE, JE, SI) route through this resolver. If date routing breaks here, every transaction booked with a historical date is wrong.",
            },
        ],
    },

    "Story 14": {
        "user_story": "As Robert, I want to log a negotiated Spot Rate once per pair per day, have a second attempt be rejected (so nobody accidentally overrides it), and keep that Spot out of Currency Exchange.",
        "mode": "API",
        "acceptance": [
            {
                "title": "First manual Spot Rate write succeeds",
                "gwt": [
                    "When I insert a Spot Rate for (CHF, UGX, today) with source='Manual'",
                    "Then the row is created",
                ],
                "why": "The manual override workflow must work at all.",
            },
            {
                "title": "A second insert for the same pair+date is rejected by unique-name constraint",
                "gwt": [
                    "When I attempt a second Spot insert for the same (CHF, UGX, today)",
                    "Then the insert fails with a Duplicate Name error",
                ],
                "why": "Two conflicting Spot rates for the same pair/day would break settlement math. The composite-name uniqueness is what prevents it.",
            },
            {
                "title": "Exactly one Spot row exists for that pair/date",
                "gwt": [
                    "When I count Spot rows for (CHF, UGX, today)",
                    "Then the count is 1",
                ],
                "why": "Cross-check of the rejection - guards against silent duplicate allowance.",
            },
            {
                "title": "Manual Spot entry does not populate Currency Exchange",
                "gwt": [
                    "When I count CE rows for (CHF, UGX, today)",
                    "Then the count is 0",
                ],
                "why": "Spot is manual-only and document-scoped; leaking into CE would override today's Ask for every transaction.",
            },
        ],
    },

    "Story 15": {
        "user_story": "As Karly, I want an automated audit that catches any regression that re-introduces auto-generated Spot Rates from Alpha Vantage - Spot is defined as manual-only.",
        "mode": "API",
        "acceptance": [
            {
                "title": "No Forex Rate Log row has rate_type='Spot' with source='Alpha Vantage'",
                "gwt": [
                    "When I query FRL for rate_type='Spot' AND source='Alpha Vantage'",
                    "Then the count is zero",
                ],
                "why": "This is the terminology-rename regression guard. If the auto-backfill ever labels AV data as Spot again, this assertion fails immediately.",
            },
            {
                "title": "Ask Rate pipeline is live (records exist on at least one date)",
                "gwt": [
                    "When I count distinct rate_date values where rate_type='Ask Rate'",
                    "Then the count is at least 1",
                ],
                "why": "An empty Ask Rate set means the sync is not running at all - transactions would then fall through to CE-only or fail.",
            },
        ],
    },

    "Story 16": {
        "user_story": "As Sibeti, I want Central Bank Rate entries to stay in Forex Rate Log only so they provide audit evidence without contaminating the Currency Exchange rates transactions use.",
        "mode": "API",
        "acceptance": [
            {
                "title": "Today's CE rate for USD->UGX is unchanged after inserting a CB Rate with +15% deviation",
                "gwt": [
                    "Given a CE rate exists for USD->UGX today",
                    "When I insert a Central Bank Rate for USD->UGX at 1.15 x that rate",
                    "Then today's CE rate for USD->UGX is unchanged",
                ],
                "why": "If CB Rate leaked into CE, every transaction booked after would use the +15% number - catastrophic. This is a core isolation guarantee.",
            },
        ],
    },

    "Story 17": {
        "user_story": "As an engineer, I want the shared rates resolver to implement the agreed contract (Auto falls back Spot->Ask; explicit sources throw on missing data; Manual preserves user value) so every opt-in doctype inherits consistent behaviour.",
        "mode": "API",
        "acceptance": [
            {
                "title": "Same-currency request returns rate=1.0",
                "gwt": [
                    "When I call resolve(X, X, any_date, any_source)",
                    "Then the rate is 1.0",
                ],
                "why": "Identity guarantee; simplest sanity check of the resolver.",
            },
            {
                "title": "Auto falls back to Ask Rate when no Spot exists for the date",
                "gwt": [
                    "When I call resolve(USD, UGX, today, 'Auto') and no Spot exists for USD->UGX today",
                    "Then the returned source is 'Ask Rate' and the rate is the CE/FRL Ask Rate",
                ],
                "why": "This is the most-invoked path (default Auto). Breaks here break every transaction.",
            },
            {
                "title": "Explicit Ask Rate resolves when data is present",
                "gwt": [
                    "When I call resolve(USD, UGX, today, 'Ask Rate')",
                    "Then it returns the Ask rate with source='Ask Rate'",
                ],
                "why": "Users who pick a specific source must get that source.",
            },
            {
                "title": "Explicit Spot with no Spot row throws (fails loud)",
                "gwt": [
                    "When I call resolve(USD, UGX, today, 'Spot') and no Spot row exists",
                    "Then an exception is raised",
                ],
                "why": "Explicit intent should fail loud, not silently fall back. Otherwise Robert thinks he used Spot when he actually used Ask.",
            },
            {
                "title": "Manual returns rate=None so the caller preserves the user's typed value",
                "gwt": [
                    "When I call resolve(X, Y, any_date, 'Manual')",
                    "Then rate=None and source='Manual'",
                ],
                "why": "The resolver must not overwrite a typed rate; that is the whole point of Manual.",
            },
        ],
    },

    "Story 18": {
        "user_story": "As Robert, I want the system to pre-fill today's rate when I create a USD field advance so I do not mis-state the UGX amount booked to Staff Advances.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "Employee Advance form accepts the staged inputs and saves as Draft",
                "gwt": [
                    "Given a valid employee on PEAS Uganda",
                    "When I open a new EA and set employee, posting_date, purpose, advance_type=Float, funds_required_by_date, multi_currency=1, e_a_currency=USD, advance_amount=100, advance_account, and add an expense breakdown row",
                    "Then clicking Save persists the EA as Draft",
                ],
                "why": "End-to-end evidence that the multi-currency EA flow is saveable; any blocker here prevents field advances being issued.",
            },
            {
                "title": "custom_advance_exchange_rate auto-populates to today's USD->UGX rate (within 1%)",
                "gwt": [
                    "Given today's USD->UGX rate is resolvable",
                    "And custom_forex_rate_source=Auto",
                    "When the EA saves",
                    "Then custom_advance_exchange_rate equals today's USD->UGX rate within 1%",
                ],
                "why": "Robert skips the manual lookup. Accuracy within 1% is the tolerance auditors accept for rate-of-day entries.",
            },
            {
                "title": "custom_forex_rate_source is rewritten from 'Auto' to the actual source used (Ask Rate or Spot)",
                "gwt": [
                    "Given Robert chose Auto",
                    "When the resolver picks a concrete source",
                    "Then the saved document shows source='Ask Rate' or 'Spot', not 'Auto'",
                ],
                "why": "Auditors reading this EA six months later see which rate methodology applied. 'Auto' alone is not auditable.",
            },
        ],
    },

    "Story 19": {
        "user_story": "As Robert, I want the parent currency on a multi-currency Expense Claim to hard-lock every line's currency so I cannot accidentally create a GBP claim with USD receipts on it (which silently breaks settlement).",
        "mode": "UI",
        "acceptance": [
            {
                "title": "L1 - A new expense row inherits the parent's currency on creation",
                "gwt": [
                    "Given I set custom_is_multicurrency=1 and custom_currency=USD on a new EC",
                    "When I add a new expense line",
                    "Then the line's custom_original_currency is USD",
                ],
                "why": "Consistency baseline - rows should never start in a different currency from the claim header.",
            },
            {
                "title": "L2 - Changing the parent currency cascades to all existing rows",
                "gwt": [
                    "Given an EC with multi_currency=1, custom_currency=USD, one expense line",
                    "When I change custom_currency to EUR",
                    "Then the line's custom_original_currency updates to EUR",
                ],
                "why": "If rows do not cascade, Robert ends up with a mix of USD and EUR lines on a single claim - unbalance-able.",
            },
            {
                "title": "L3 - Row custom_original_currency is read-only when parent currency is set",
                "gwt": [
                    "Given custom_is_multicurrency=1 and custom_currency is set",
                    "When I inspect the grid docfield property for custom_original_currency",
                    "Then read_only is true",
                ],
                "why": "Soft propagation can be edited back. A read-only lock is what actually prevents the GBP/USD drift we saw in real data.",
            },
        ],
    },

    "Story 20": {
        "user_story": "As Robert, when my claim is tied to an Employee Advance I want every expense line's rate to inherit the advance's rate so the advance fully zeroes out on settlement.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "Expense line rate equals the linked EA's custom_advance_exchange_rate",
                "gwt": [
                    "Given a multi-currency EA exists with custom_advance_exchange_rate=400",
                    "When I link that EA to a new EC and add an expense line",
                    "Then the line's custom_exchange_rate is 400",
                ],
                "why": "If the claim uses a different rate than the advance, the advance balance cannot zero on full claim - Finance sees phantom residuals.",
            },
            {
                "title": "Line custom_forex_rate_source is stamped 'Inherited'",
                "gwt": [
                    "Given the EC is linked to an EA",
                    "When the expense line gets its rate",
                    "Then custom_forex_rate_source='Inherited'",
                ],
                "why": "Auditor sees 'Inherited' and knows the rate came from the advance, not a market fetch or Manual override.",
            },
        ],
    },

    "Story 21": {
        "user_story": "As Robert, I want a GBP->UGX internal-transfer Payment Entry to auto-fill the conversion rate on save so I can book the transfer without looking up today's rate on Bloomberg.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "Payment Entry form accepts UI-staged inputs and saves as Draft",
                "gwt": [
                    "Given a GBP Bank account and UGX Cash account exist on PEAS Uganda",
                    "When I open a new PE, set Internal Transfer, Paid From=Bank GBP - UG, Paid To=Cash - UG, Paid Amount=100, Reference fields, then click Save",
                    "Then a Draft PE is created",
                ],
                "why": "End-to-end proof that internal-transfer PEs flow through the customized form.",
            },
            {
                "title": "source_exchange_rate is populated (non-zero, non-1) after save",
                "gwt": [
                    "When I re-read the saved PE",
                    "Then source_exchange_rate is a number greater than 100",
                ],
                "why": "Reasonableness check: GBP->UGX is in the thousands; a 0 or 1 means the resolver did not fire.",
            },
            {
                "title": "custom_forex_rate_source is rewritten from 'Auto' to the actually-used source",
                "gwt": [
                    "Given Robert selected Auto",
                    "When the PE saves",
                    "Then custom_forex_rate_source is 'Ask Rate' or 'Spot' (never left as 'Auto')",
                ],
                "why": "Same audit-stamping contract as other transaction types - PE must not be a hole in the trail.",
            },
        ],
    },

    "Story 22": {
        "user_story": "As Sibeti, I want each row of a multi-currency Journal Entry to carry its own rate source stamp so that when the JE touches more than one currency the audit trail says which methodology applied to each row - and so the JE balances in company currency on save.",
        "mode": "Hybrid",
        "acceptance": [
            {
                "title": "Journal Entry inserts cleanly via UI-staged + client.insert save",
                "gwt": [
                    "When I open a new JE, tick multi_currency, add a GBP debit row and a balancing UGX credit row via the form, then post via the UI-triggered API save",
                    "Then the JE is created",
                ],
                "why": "The UI stage path is what Sibeti uses; this validates the full staging + save sequence works without hidden errors.",
            },
            {
                "title": "The GBP row's exchange_rate matches the resolver's preview for today (within 5%)",
                "gwt": [
                    "Given the resolver previewed a rate for GBP->UGX today",
                    "When the JE saves",
                    "Then the GBP row exchange_rate equals that preview (within 5%)",
                ],
                "why": "The rate staged must survive through the hook and end up on the saved row.",
            },
            {
                "title": "The GBP row's custom_forex_rate_source is stamped per-row from 'Auto' to 'Ask Rate' or 'Spot'",
                "gwt": [
                    "Given per-row source field (moved to Journal Entry Account)",
                    "When the resolver runs",
                    "Then the row's source is rewritten to the concrete one used",
                ],
                "why": "Multi-pair JEs need source per row. A parent-only source is dishonest when different rows use different rates.",
            },
            {
                "title": "total_debit equals total_credit in company currency - JE is submit-ready",
                "gwt": [
                    "When I read total_debit and total_credit from the saved JE",
                    "Then they are equal (within 0.01)",
                ],
                "why": "An imbalanced JE fails on submit - proves our resolver + staging produce consistent numbers on both sides.",
            },
        ],
        "notes": "Source field lives on Journal Entry Account (per-row) because the rate is per-row - source must be co-located with the rate it applied to.",
    },

    "Story 23": {
        "user_story": "As the Grants team issuing an invoice to a donor in GBP, I want the GBP->UGX conversion rate on the Sales Invoice to auto-fill so I do not have to look up today's rate manually.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "Sales Invoice conversion_rate auto-populates for Company=PEAS Uganda, Currency=GBP",
                "gwt": [
                    "Given today's GBP->UGX rate is in CE",
                    "When I open a new SI and set Company=PEAS Uganda, Currency=GBP",
                    "Then conversion_rate populates automatically",
                    "And the value matches a rate resolvable from FRL/CE for today",
                ],
                "why": "Grant invoicing shares the same rate-of-day need as vendor invoicing; parity across PI and SI means the donor billing flow does not diverge.",
            },
        ],
    },

    "Story 24": {
        "user_story": "As Sibeti, I want the rate used on a submitted multi-currency Journal Entry to be exactly what lands in the General Ledger, so reconciliation and audit hold together end-to-end.",
        "mode": "API",
        "acceptance": [
            {
                "title": "A balanced multi-currency JE inserts and submits cleanly via API",
                "gwt": [
                    "Given a balanced JE payload using today's resolver-preview rate",
                    "When I insert and then submit it",
                    "Then both calls succeed",
                ],
                "why": "Submit is where ERPNext promotes a Draft to the ledger; if this fails, no real JE ever reaches GL.",
            },
            {
                "title": "Two GL Entry rows are produced (one per account row)",
                "gwt": [
                    "When I query tabGL Entry for voucher_type='Journal Entry' and voucher_no=<name>",
                    "Then exactly 2 rows exist - one for Bank GBP - UG, one for Cash - UG",
                ],
                "why": "Missing GL rows mean the submit silently failed to post - a ledger gap that reports would not catch.",
            },
            {
                "title": "GBP account GL debit equals 100 x stamped rate (audit trail intact)",
                "gwt": [
                    "When I read the GL row for Bank GBP - UG",
                    "Then debit equals 100 x the rate the resolver stamped on the JE row",
                ],
                "why": "The audit trail only works if the source stamp on the JE row is what actually landed in the ledger. Any drift here breaks reconciliation.",
            },
            {
                "title": "UGX account GL credit balances the JE in company currency",
                "gwt": [
                    "When I read the GL row for Cash - UG",
                    "Then credit equals 100 x the stamped rate",
                ],
                "why": "Balancing check at GL level - guards against one-sided postings.",
            },
        ],
    },

    "Story 25": {
        "user_story": "As Robert, when I claim a foreign-currency expense I paid on the company credit card, the claim type should pre-configure the form (already paid, Credit Card MOP) AND the line rate should still come from the Spot/Ask resolver - the card path must not bypass the forex audit trail.",
        "mode": "UI",
        "acceptance": [
            {
                "title": "Setting custom_claim_type='Company Card Expense' auto-sets is_paid=1",
                "gwt": [
                    "When I select custom_claim_type='Company Card Expense' on a new EC",
                    "Then the V3 client script sets is_paid=1 automatically",
                ],
                "why": "Company card transactions are already settled at the card level; the EC must reflect that without manual toggling.",
            },
            {
                "title": "mode_of_payment is auto-set to 'Credit Card'",
                "gwt": [
                    "When the claim type cascade fires",
                    "Then mode_of_payment='Credit Card'",
                ],
                "why": "Finance filters company-card claims by MOP; missing it means these claims do not appear in the right reports.",
            },
            {
                "title": "A USD line on a Company Card multi-currency claim still routes through peasforex.rates",
                "gwt": [
                    "Given custom_is_multicurrency=1 and custom_currency=USD on the EC",
                    "When I add a USD line with today's expense date",
                    "Then its custom_exchange_rate auto-populates via the resolver (non-zero, non-1)",
                ],
                "why": "Company Card path must not be a forex bypass. A Credit Card USD charge still needs a source-stamped rate for audit.",
            },
            {
                "title": "The line's custom_forex_rate_source is stamped 'Ask Rate' or 'Spot' (Auto rewritten)",
                "gwt": [
                    "Given the line's source=Auto initially",
                    "When the resolver resolves",
                    "Then source is rewritten to the concrete one used",
                ],
                "why": "Same audit stamping applies to card-settled lines as to any other transaction.",
            },
        ],
    },
}


AUDIT = {
    "Code delivered": [
        ("peasforex/rates.py",
         "Central resolver. resolve(from, to, date, source) -> (rate, actual_source, rate_date). "
         "apply(doc, method) hook entry point. Adapter registry for PI / PE / JE / EA / Accountability. "
         "Auto honours Spot->Ask fallback. Explicit sources throw on missing rate. Manual preserves "
         "user-typed value and auto-logs as Spot in FRL for reuse within the day."),
        ("peasforex/hooks.py",
         "Registered before_validate doc_events for Purchase Invoice, Employee Advance, Payment Entry, "
         "Journal Entry. Accountability hook commented with restoration note - distribution_csf app not "
         "installed on this site."),
        ("peasforex/fixtures/custom_field.json",
         "13 custom fields across 6 doctypes. custom_forex_rate_source (Select: Auto / Ask Rate / Spot / "
         "Central Bank Rate / Manual / Inherited) and custom_forex_rate_applied_date on PI, EA, PE, JE. "
         "Expense Breakdown gains custom_currency + custom_exchange_rate + custom_amount_in_base_currency. "
         "Expense Claim Detail gains custom_forex_rate_source per line."),
        ("peasforex/tasks/sync_forex.py:805-819",
         "Backfill now writes rate_type='Ask Rate' (previously wrote 'Spot'). Bidirectional reverse rate "
         "also writes Ask Rate."),
        ("peasforex/api/currency_exchange.py:62",
         "get_latest_rate default rate_type changed from 'Spot' to 'Ask Rate'."),
        ("peasforex/peasforex/dashboard_chart_source/forex_rate_trends/forex_rate_trends.py",
         "'Ask Rate' prepended to VALID_RATE_TYPES. Default and fallback both changed from 'Spot' to 'Ask Rate'."),
        ("peasforex/peasforex/dashboard_chart_source/forex_latest_rates/forex_latest_rates.py",
         "SQL WHERE clause changed from rate_type='Spot' to rate_type='Ask Rate'."),
        ("peasforex/peasforex/report/exchange_rate_history/exchange_rate_history.py/.js",
         "Report filter offers Ask Rate (missing before). Chart code paths (3 sites) prefer Ask Rate over Spot. "
         "Color map keyed for both."),
        ("peasforex/peasforex/doctype/forex_rate_log/forex_rate_log.json",
         "rate_type options reordered: Ask Rate first (new default on form load)."),
        ("peasforex/peasforex/doctype/forex_sync_log/forex_sync_log.json",
         "sync_type option 'Spot (Daily)' renamed to 'Ask Rate (Daily)' - closes long-standing schema/code mismatch."),
        ("peasforex/peasforex/doctype/forex_settings/forex_settings.json",
         "'Rate Types Explained' HTML panel rewritten. Ask Rate described first; Spot correctly labelled "
         "manual-only; Closing and Monthly Average mapped to Balance Sheet and P&L."),
        ("peasforex/peasforex/doctype/currency_pair/currency_pair.json",
         "Checkbox label 'Sync Spot (Daily)' -> 'Sync Ask Rate (Daily)'. Fieldname sync_spot_daily preserved "
         "(internal only)."),
        ("peasforex/api/alpha_vantage.py:445",
         "User-facing note 'Spot rate fallback' -> 'Ask Rate fallback'."),
        ("peasforex/peasforex/doctype/fs_rate_demo/",
         "DocType exported from DB (was custom=1, PhaseOne module) to source files (custom=0, Peasforex module). "
         "Added __init__.py + fs_rate_demo.py controller. bs_rate_type option 'Spot' -> 'Ask Rate'."),
        ("peas_hr Client Script: Expense Claim Scripts V3",
         "handle_row_currency adds hard-lock via grid.update_docfield_property('custom_original_currency', "
         "'read_only', 1) when parent custom_currency is set + multi_currency=1. set_exchange_rate replaced "
         "with peasforex.rates.resolve_whitelisted call (Spot then Ask). New section: advance picker filter "
         "(multi-currency EAs only, matching custom_e_a_currency), 1-EA-per-multi-currency-EC enforcement, "
         "currency mismatch warning, line-rate inheritance from linked EA's custom_advance_exchange_rate, "
         "source stamped 'Inherited' with read-only rate."),
    ],
    "Data migrations": [
        ("Forex Rate Log", "2472 Alpha-Vantage-sourced Spot rows renamed to Ask Rate "
            "(rate_type and composite name column both updated)."),
        ("Forex Sync Log", "963 legacy 'Spot (Daily)' sync_type values renamed to 'Ask Rate (Daily)'."),
        ("FS Rate Demo", "DocType record: module PhaseOne -> Peasforex, custom=1 -> custom=0. "
            "DocField bs_rate_type options: Spot -> Ask Rate."),
    ],
    "Known deferrals": [
        ("Accountability hook + schema",
         "distribution_csf (which owns Accountability) not installed on this site. "
         "rates.py adapter entry and hooks.py comment marker ready to re-enable once the "
         "app is installed and the custom-field fixture entries are restored."),
        ("JE programmatic Inherited semantics (revaluation, translation)",
         "Current release supports Inherited as a manual/programmatic override via doc.flags. "
         "Month-end-close flows (Closing-rate revaluation, Monthly-Average translation) "
         "are a separate design round."),
        ("Forex Settings per-company rules child table",
         "Global toggles apply to all companies for now. Per-company gating (PEAS Global skips "
         "Spot logic because GBP-base) can be added without breaking the current API."),
    ],
}


# ---------------------------------------------------------------------------
# HTML emission
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
       'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 2rem;
       background: #f8f9fa; color: #212529; line-height: 1.55; }
main { max-width: 1080px; margin: 0 auto; }
header { margin-bottom: 2rem; padding: 1.25rem 1.5rem; background: white;
         border-radius: 8px; border-left: 5px solid #28a745;
         box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
header.fail { border-left-color: #dc3545; }
header h1 { margin: 0 0 .4rem 0; font-size: 1.6rem; }
header .meta { color: #6c757d; font-size: .9rem; }
header .stats { margin-top: .8rem; display: flex; gap: 1.25rem; }
header .stats .pill { padding: .25rem .75rem; border-radius: 999px;
       font-weight: 600; font-size: .85rem; }
.pill.pass { background: #d4edda; color: #155724; }
.pill.fail { background: #f8d7da; color: #721c24; }
.pill.skip { background: #fff3cd; color: #856404; }
.pill.total { background: #e9ecef; color: #495057; }
section { margin-bottom: 2rem; background: white; border-radius: 8px;
          padding: 1.25rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
section h2 { margin: 0 0 1rem 0; font-size: 1.3rem; padding-bottom: .5rem;
             border-bottom: 2px solid #e9ecef; }
.story { border: 1px solid #e9ecef; border-radius: 6px; margin-bottom: .8rem;
         padding: .75rem 1rem; }
.story h3 { margin: 0 0 .5rem 0; font-size: 1rem; font-weight: 600;
            display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
.mode { font-size: .7rem; padding: .1rem .5rem; border-radius: 3px;
        background: #e9ecef; color: #495057; font-weight: 600;
        letter-spacing: .02em; }
.user-story { background: #f8f9fc; border-left: 3px solid #6f42c1;
              padding: .5rem .75rem; margin: .5rem 0; font-size: .9rem;
              font-style: italic; color: #495057; }
.criteria { margin: .5rem 0 .75rem 0; padding-left: 1.25rem;
            font-size: .87rem; color: #495057; }
.criteria li { margin: .1rem 0; }
.criteria li.given { color: #0d6efd; }
.criteria li.when { color: #198754; }
.criteria li.then { color: #6f42c1; }
.ac-block { border: 1px solid #dee2e6; border-left: 3px solid #0d6efd;
            border-radius: 3px; padding: .55rem .8rem; margin: .5rem 0;
            background: #fbfcfd; }
.ac-title { font-weight: 600; color: #212529; font-size: .88rem;
            margin-bottom: .3rem; }
.ac-title::before { content: "AC "; color: #0d6efd; font-weight: 700; }
.ac-gwt { margin: .25rem 0; padding-left: 0; font-size: .84rem; }
.ac-gwt li { margin: .08rem 0; list-style: none; padding-left: 1.1rem;
             text-indent: -1.1rem; }
.ac-gwt li::before { content: "•   "; color: #adb5bd; }
.ac-gwt li.given::before { content: "▸ "; color: #0d6efd; font-weight: 700; }
.ac-gwt li.when::before  { content: "▸ "; color: #198754; font-weight: 700; }
.ac-gwt li.then::before  { content: "▸ "; color: #6f42c1; font-weight: 700; }
.ac-why { font-size: .8rem; color: #6c757d; font-style: italic;
          margin-top: .35rem; padding-top: .3rem; border-top: 1px dashed #e9ecef; }
.ac-why::before { content: "Why: "; color: #495057;
                  font-weight: 600; font-style: normal; }
.notes { background: #fffbf0; padding: .4rem .6rem; border-radius: 3px;
         font-size: .82rem; color: #856404; margin: .3rem 0; }
.records { margin: .5rem 0; padding: .4rem .6rem; background: #f0f9f2;
           border-left: 3px solid #28a745; border-radius: 3px; font-size: .85rem; }
.records .records-head { font-weight: 600; color: #155724; margin-bottom: .25rem; }
.records a { color: #0d6efd; text-decoration: none; font-family: 'SF Mono', Menlo, Monaco, monospace; font-size: .82rem; }
.records a:hover { text-decoration: underline; }
.records .doctype { color: #6c757d; font-weight: 600; display: inline-block; min-width: 9rem; }
.story h3 .state { font-size: .75rem; padding: .15rem .6rem; border-radius: 4px;
                   font-weight: 700; letter-spacing: .05em; }
.story h3 .state.pass { background: #d4edda; color: #155724; }
.story h3 .state.fail { background: #f8d7da; color: #721c24; }
.story h3 .state.skip { background: #fff3cd; color: #856404; }
.assertion { font-family: 'SF Mono', Menlo, Monaco, Consolas, 'Courier New',
             monospace; font-size: .85rem; padding: .25rem .5rem;
             border-radius: 3px; margin: .15rem 0;
             display: grid; grid-template-columns: 3.5rem 1fr; gap: .75rem;
             align-items: baseline; }
.assertion.pass { background: #f0f9f2; }
.assertion.fail { background: #fdf2f3; color: #721c24; }
.assertion.skip { background: #fffbf0; color: #856404; }
.assertion .tag { font-weight: 700; font-size: .75rem; opacity: .7; }
.assertion .detail { color: #6c757d; font-size: .8rem; }
.audit-item { margin-bottom: 1rem; }
.audit-item .head { font-family: 'SF Mono', Menlo, Monaco, Consolas, monospace;
                    font-weight: 600; color: #495057; font-size: .9rem; }
.audit-item .body { color: #495057; font-size: .9rem; margin-top: .25rem; }
footer { text-align: center; color: #adb5bd; font-size: .8rem;
         margin-top: 2rem; }
details summary { cursor: pointer; color: #6c757d; font-size: .85rem; }
pre.raw { background: #f1f3f5; border-radius: 4px; padding: 1rem;
          overflow: auto; font-size: .78rem; line-height: 1.4;
          max-height: 400px; }
"""


def esc(s):
    return html.escape(s or "", quote=False)


def render(parsed: dict) -> str:
    summary = parsed["summary"]
    stories = [s for s in parsed["stories"] if s["name"].startswith("Story")]
    header_cls = "fail" if summary["failed"] else ""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records_by_story = {}
    if RECORDS.exists():
        try:
            records_by_story = json.loads(RECORDS.read_text()) or {}
        except Exception:
            records_by_story = {}

    # Story cards
    story_html = []
    for s in stories:
        asserts = s["assertions"]
        # Aggregate state: fail > skip > pass
        states = {a["state"] for a in asserts}
        if "FAIL" in states:
            story_state = "fail"
        elif "SKIP" in states and not any(a["state"] == "PASS" for a in asserts):
            story_state = "skip"
        elif "SKIP" in states:
            story_state = "pass"  # mixed pass/skip treated as pass with notes
        else:
            story_state = "pass"
        story_html.append(f'<div class="story">')
        ac = ACCEPTANCE.get(s["name"])
        mode_badge = (f'<span class="mode">{esc(ac["mode"])}</span>' if ac else "")
        story_html.append(
            f'<h3><span class="state {story_state}">{story_state.upper()}</span>'
            f'{esc(s["name"])} — {esc(s["title"])}{mode_badge}</h3>')
        if ac:
            story_html.append(
                f'<div class="user-story">{esc(ac["user_story"])}</div>')

            # New structured form: a list of AC blocks, each with title/gwt/why.
            if "acceptance" in ac:
                for block in ac["acceptance"]:
                    story_html.append('<div class="ac-block">')
                    story_html.append(
                        f'<div class="ac-title">{esc(block.get("title", ""))}</div>')
                    if block.get("gwt"):
                        story_html.append('<ul class="ac-gwt">')
                        for line in block["gwt"]:
                            low = line.lower().strip()
                            cls = "given" if low.startswith(("given", "and given")) else \
                                  "when" if low.startswith(("when", "and when")) else \
                                  "then" if low.startswith(("then", "and")) else ""
                            story_html.append(f'<li class="{cls}">{esc(line)}</li>')
                        story_html.append('</ul>')
                    if block.get("why"):
                        story_html.append(
                            f'<div class="ac-why">{esc(block["why"])}</div>')
                    story_html.append('</div>')
            # Fallback: legacy flat criteria list
            elif "criteria" in ac:
                story_html.append('<ul class="criteria">')
                for line in ac["criteria"]:
                    low = line.lower().strip()
                    cls = "given" if low.startswith(("given", "and given")) else \
                          "when" if low.startswith(("when", "and when")) else \
                          "then" if low.startswith(("then", "and")) else ""
                    story_html.append(f'<li class="{cls}">{esc(line)}</li>')
                story_html.append('</ul>')

            if ac.get("notes"):
                story_html.append(f'<div class="notes"><strong>Note:</strong> {esc(ac["notes"])}</div>')
        # Records created by this story (live links)
        records = records_by_story.get(s["name"], [])
        if records:
            story_html.append('<div class="records">')
            story_html.append(f'<div class="records-head">Records created ({len(records)}) - live on peas-dev</div>')
            for rec in records:
                dt = esc(rec.get("doctype", ""))
                nm = esc(rec.get("name", ""))
                url = esc(rec.get("url", ""))
                story_html.append(
                    f'<div><span class="doctype">{dt}</span> '
                    f'<a href="{url}" target="_blank">{nm}</a></div>'
                )
            story_html.append('</div>')
        for a in asserts:
            cls = a["state"].lower()
            detail = f'<span class="detail">{esc(a["detail"])}</span>' if a["detail"] else ""
            story_html.append(
                f'<div class="assertion {cls}">'
                f'<span class="tag">{a["state"]}</span>'
                f'<span>{esc(a["label"])} {detail}</span>'
                f'</div>')
        story_html.append('</div>')

    # Audit
    audit_html = []
    for heading, items in AUDIT.items():
        audit_html.append(f'<h3 style="font-size:1rem;margin-top:1.2rem;">{esc(heading)}</h3>')
        for head, body in items:
            audit_html.append(
                f'<div class="audit-item">'
                f'<div class="head">{esc(head)}</div>'
                f'<div class="body">{esc(body)}</div>'
                f'</div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>peasforex — Test Report {datetime.date.today()}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header class="{header_cls}">
  <h1>peasforex — Test Report & Audit</h1>
  <div class="meta">
    Generated {esc(now)} &middot;
    Suite: <code>peasforex/tests/test_forex_stories.py</code> &middot;
    Site: <code>http://peas-dev.localhost:8020</code>
  </div>
  <div class="stats">
    <span class="pill total">{summary['total']} total</span>
    <span class="pill pass">{summary['passed']} passed</span>
    <span class="pill fail">{summary['failed']} failed</span>
    <span class="pill skip">{summary['skipped']} skipped</span>
  </div>
</header>

<section>
  <h2>Results by story</h2>
  {''.join(story_html)}
</section>

<section>
  <h2>Audit — Changes delivered this session</h2>
  {''.join(audit_html)}
</section>

<section>
  <h2>Raw test output</h2>
  <details>
    <summary>Show raw stdout ({len(parsed['raw'].splitlines())} lines)</summary>
    <pre class="raw">{esc(parsed['raw'])}</pre>
  </details>
</section>

<footer>
  Report generator: <code>peasforex/tests/generate_report.py</code>
</footer>
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main():
    no_run = "--no-run" in sys.argv
    if no_run and CACHE.exists():
        output = CACHE.read_text()
    else:
        output = run_suite()
    parsed = parse(output)
    html_text = render(parsed)
    OUT.write_text(html_text)
    print(f"Report: {OUT}")
    print(f"  {parsed['summary']['passed']} passed / "
          f"{parsed['summary']['failed']} failed / "
          f"{parsed['summary']['skipped']} skipped / "
          f"{parsed['summary']['total']} total")


if __name__ == "__main__":
    main()
