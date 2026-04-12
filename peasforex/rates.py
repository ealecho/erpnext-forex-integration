# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

"""
Central rate resolution for PEAS transaction forms.

Transaction doctypes opt in via hooks.py doc_events:
    "Purchase Invoice": {"before_validate": "peasforex.rates.apply"}

Each opted-in doctype has two PEAS custom fields:
    custom_forex_rate_source       Select (Auto / Ask Rate / Spot /
                                           Central Bank Rate / Manual / Inherited)
    custom_forex_rate_applied_date Date  (defaults to the doc's posting_date)

Resolution rules:
- Auto: try Spot for the applied date, else Ask Rate. Throws if neither.
- Spot / Ask Rate / Central Bank Rate: force that source, throw if missing.
- Manual: preserve the user-typed value; auto-log as Spot in Forex Rate Log
  so the same rate is reusable within the day (per CLAUDE.md).
- Inherited: server is a no-op. EC V3 client script handles inheritance from
  the linked Employee Advance's custom_advance_exchange_rate.

After Auto resolves, custom_forex_rate_source is rewritten to the actual
source used ("Spot" or "Ask Rate") so the saved document carries an honest
audit trail - not the literal word "Auto".
"""

import frappe
from frappe import _
from frappe.utils import nowdate


# Per-doctype field mappings. A "slot" is one (currency_field, rate_field) pair.
# Parent-level slot: from_field + rate_field read from the document itself.
# Row-level slot: same fields read from each row of the named child `table`.
# Optional `only_if` predicate gates whether the slot is processed.
ADAPTERS = {
    "Purchase Invoice": {
        "slots": [{"from_field": "currency", "rate_field": "conversion_rate"}],
    },
    "Payment Entry": {
        "slots": [
            {"from_field": "paid_from_account_currency", "rate_field": "source_exchange_rate"},
            {"from_field": "paid_to_account_currency",   "rate_field": "target_exchange_rate"},
        ],
    },
    "Journal Entry": {
        "slots": [{
            "table": "accounts",
            "from_field": "account_currency",
            "rate_field": "exchange_rate",
        }],
    },
    "Employee Advance": {
        "slots": [{
            "from_field": "custom_e_a_currency",
            "rate_field": "custom_advance_exchange_rate",
            "only_if": lambda d: bool(d.get("custom_is_multicurrency")),
        }],
    },
    "Accountability": {
        "slots": [
            {"from_field": "custom_currency", "rate_field": "custom_exchange_rate"},
            # Child slot added once Expense Breakdown schema prep lands.
        ],
    },
}


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------

def apply(doc, method=None):
    """before_validate hook: populate rate fields per the doc's source choice."""
    adapter = ADAPTERS.get(doc.doctype)
    if not adapter:
        return

    source = doc.get("custom_forex_rate_source") or "Auto"

    # Inherited: handled client-side by the EC V3 script populating rates
    # from the linked Employee Advance. Server stays out of the way.
    if source == "Inherited":
        return

    # Manual: respect user-typed rates; record them as Spot in FRL so the
    # same pair+date is reusable within the day.
    if source == "Manual":
        _log_manual_rates_as_spot(doc, adapter)
        return

    as_of = doc.get("custom_forex_rate_applied_date") \
            or doc.get("posting_date") or nowdate()
    company = doc.get("company")
    if not company:
        return
    to_currency = frappe.get_cached_value("Company", company, "default_currency")
    if not to_currency:
        return

    # Track the actually-used source when Auto is picked so we can stamp it
    # back as "Spot" or "Ask Rate" (not the literal word "Auto").
    resolved_source = None

    for slot in adapter["slots"]:
        if "only_if" in slot and not slot["only_if"](doc):
            continue
        if "table" in slot:
            for row in doc.get(slot["table"]) or []:
                used = _resolve_and_set(row, slot, to_currency, as_of, source)
                if used:
                    resolved_source = used
        else:
            used = _resolve_and_set(doc, slot, to_currency, as_of, source)
            if used:
                resolved_source = used

    if source == "Auto" and resolved_source:
        doc.custom_forex_rate_source = resolved_source


def _resolve_and_set(obj, slot, to_currency, as_of, source):
    from_currency = obj.get(slot["from_field"])
    if not from_currency or from_currency == to_currency:
        return None
    rate, actual_source, _ = resolve(from_currency, to_currency, as_of, source)
    if rate is not None:
        obj.set(slot["rate_field"], rate)
    return actual_source


# ---------------------------------------------------------------------------
# Public resolver - callable from client scripts and tests via whitelist
# ---------------------------------------------------------------------------

@frappe.whitelist()
def resolve_whitelisted(from_currency, to_currency, as_of_date, source="Auto"):
    """Whitelisted wrapper for client-side calls (EC V3 script)."""
    rate, actual_source, rate_date = resolve(from_currency, to_currency, as_of_date, source)
    return {"rate": rate, "source": actual_source, "rate_date": str(rate_date) if rate_date else None}


def resolve(from_currency, to_currency, as_of_date, source="Auto"):
    """Returns (rate, actual_source, rate_date_used).

    Throws on unresolvable forced source (Spot / Ask Rate / Central Bank Rate).
    Returns (None, source, as_of_date) for Manual / Inherited (caller handles).
    """
    if from_currency == to_currency:
        return (1.0, source, as_of_date)

    if source == "Auto":
        for candidate in ("Spot", "Ask Rate"):
            row = _lookup_frl(from_currency, to_currency, as_of_date, candidate)
            if row:
                return (row["exchange_rate"], candidate, row["rate_date"])
        # Fallback: Currency Exchange (historically the Ask home)
        ce_rate = _lookup_ce(from_currency, to_currency, as_of_date)
        if ce_rate:
            return (ce_rate, "Ask Rate", as_of_date)
        frappe.throw(_("No rate available for {0}→{1} on or before {2}").format(
            from_currency, to_currency, as_of_date))

    if source in ("Spot", "Ask Rate", "Central Bank Rate"):
        row = _lookup_frl(from_currency, to_currency, as_of_date, source)
        if row:
            return (row["exchange_rate"], source, row["rate_date"])
        # Ask Rate: also try CE as a last resort
        if source == "Ask Rate":
            ce_rate = _lookup_ce(from_currency, to_currency, as_of_date)
            if ce_rate:
                return (ce_rate, "Ask Rate", as_of_date)
        frappe.throw(_("No {0} rate available for {1}→{2} on or before {3}").format(
            source, from_currency, to_currency, as_of_date))

    # Manual / Inherited: caller handles the rate
    return (None, source, as_of_date)


def _lookup_frl(from_currency, to_currency, as_of_date, rate_type):
    rows = frappe.db.sql("""
        SELECT exchange_rate, rate_date
        FROM `tabForex Rate Log`
        WHERE from_currency = %s AND to_currency = %s
          AND rate_type = %s AND rate_date <= %s
        ORDER BY rate_date DESC LIMIT 1
    """, (from_currency, to_currency, rate_type, as_of_date), as_dict=True)
    return rows[0] if rows else None


def _lookup_ce(from_currency, to_currency, as_of_date):
    return frappe.db.get_value(
        "Currency Exchange",
        {"from_currency": from_currency, "to_currency": to_currency,
         "date": ["<=", as_of_date]},
        "exchange_rate", order_by="date DESC",
    )


# ---------------------------------------------------------------------------
# Manual override → log as Spot in FRL for reuse within the day
# ---------------------------------------------------------------------------

def _log_manual_rates_as_spot(doc, adapter):
    as_of = doc.get("custom_forex_rate_applied_date") \
            or doc.get("posting_date") or nowdate()
    company = doc.get("company")
    if not company:
        return
    to_currency = frappe.get_cached_value("Company", company, "default_currency")
    if not to_currency:
        return

    for slot in adapter["slots"]:
        if "only_if" in slot and not slot["only_if"](doc):
            continue
        if "table" in slot:
            for row in doc.get(slot["table"]) or []:
                _log_one_spot(row, slot, to_currency, as_of)
        else:
            _log_one_spot(doc, slot, to_currency, as_of)


def _log_one_spot(obj, slot, to_currency, as_of):
    from_currency = obj.get(slot["from_field"])
    rate = obj.get(slot["rate_field"])
    if not from_currency or from_currency == to_currency or not rate:
        return
    existing = frappe.db.exists("Forex Rate Log", {
        "from_currency": from_currency, "to_currency": to_currency,
        "rate_date": as_of, "rate_type": "Spot",
    })
    if existing:
        return
    try:
        frl = frappe.new_doc("Forex Rate Log")
        frl.update({
            "from_currency": from_currency, "to_currency": to_currency,
            "rate_date": as_of, "rate_type": "Spot",
            "exchange_rate": rate, "source": "Manual",
        })
        frl.flags.ignore_permissions = True
        frl.insert()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "peasforex manual Spot log failed")
