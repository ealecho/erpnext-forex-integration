# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

"""
Central rate resolution for PEAS transaction forms.

Transaction doctypes opt in via hooks.py doc_events:
    "Purchase Invoice": {"before_validate": "peasforex.rates.apply"}

Each opted-in doctype has two PEAS custom fields:
    custom_forex_rate_source       Select (Live Rate / Spot /
                                           Central Bank Rate / Manual / Inherited)
    custom_forex_rate_applied_date Date  (defaults to the doc's posting_date)

Resolution rules:
- Live Rate: look up Ask Rate in Forex Rate Log (carries forward if today's
  hasn't synced yet), fallback to Currency Exchange. Throws if neither.
- Spot / Central Bank Rate: force that source, throw if missing in FRL.
- Manual: preserve the user-typed value. Nothing is logged to FRL.
- Inherited: server is a no-op. EC V3 client script handles inheritance from
  the linked Employee Advance's custom_advance_exchange_rate.
- Auto (internal): try Spot, else Live Rate. Not a visible UI option; used
  server-side as the default when no source is recorded.

"Live Rate" is the user-facing label for what is stored internally as
"Ask Rate" in Forex Rate Log. The boundary functions (_to_internal /
_to_display) translate at the API surface; resolve() uses "Ask Rate"
throughout and never sees "Live Rate".

After Auto resolves, custom_forex_rate_source is rewritten to the actual
source used ("Spot" or "Live Rate") so the saved document carries an honest
audit trail.
"""

import frappe
from frappe import _
from frappe.utils import nowdate


# ---------------------------------------------------------------------------
# "Live Rate" ↔ "Ask Rate" translation
# "Ask Rate" is the internal FRL rate_type. "Live Rate" is what users see.
# All code outside this file uses "Live Rate"; resolve() uses "Ask Rate".
# ---------------------------------------------------------------------------

def _to_internal(source):
    return "Ask Rate" if source == "Live Rate" else source


def _to_display(source):
    return "Live Rate" if source == "Ask Rate" else source


# ---------------------------------------------------------------------------
# Client-callable: save a user-declared Spot or Central Bank Rate to FRL
# ---------------------------------------------------------------------------

@frappe.whitelist()
def save_rate_to_frl(from_currency, to_currency, rate_date, rate_type, exchange_rate):
    """Save an explicitly declared Spot or Central Bank Rate to Forex Rate Log.

    Called from client scripts when the user selects Spot or Central Bank Rate
    as source, no FRL entry exists for that date, and the user enters the rate
    manually. Saving here means the same rate is available for subsequent
    lookups on the same date (e.g. other PEs or JEs that day).
    """
    frappe.has_permission("Forex Rate Log", "write", throw=True)
    rate_type_internal = _to_internal(rate_type)
    if rate_type_internal not in ("Spot", "Central Bank Rate"):
        frappe.throw(_("Only Spot and Central Bank Rate can be saved to Forex Rate Log via this method."))

    existing = frappe.db.exists("Forex Rate Log", {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate_date": rate_date,
        "rate_type": rate_type_internal,
    })
    if existing:
        return {"name": existing, "status": "exists"}

    frl = frappe.new_doc("Forex Rate Log")
    frl.update({
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate_date": rate_date,
        "rate_type": rate_type_internal,
        "exchange_rate": float(exchange_rate),
        "source": "Manual",
    })
    frl.flags.ignore_permissions = True
    frl.insert()
    frappe.db.commit()
    return {"name": frl.name, "status": "created"}


# Per-doctype field mappings. A "slot" is one (currency_field, rate_field) pair.
# Parent-level slot: from_field + rate_field read from the document itself.
# Row-level slot: same fields read from each row of the named child `table`.
# Optional `only_if` predicate gates whether the slot is processed.
ADAPTERS = {
    "Purchase Invoice": {
        "slots": [{"from_field": "currency", "rate_field": "conversion_rate"}],
    },
    "Sales Invoice": {
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
    # Expense Claim (labelled "Accountability" in the PEAS UI via
    # custom_claim_type = "Advance Accountability") is NOT in this registry:
    # peas_hr's "Expense Claim Scripts V3" client script owns row-currency
    # + per-row rate resolution there, calling peasforex.rates.resolve_whitelisted
    # directly. Adding a server-side adapter would double-handle the rate.
}


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------

def apply(doc, method=None):
    """before_validate hook: populate rate fields per the doc's source choice.

    Source field placement differs by doctype:
      - PI / PE / Employee Advance: parent-level `custom_forex_rate_source`
        applies uniformly to every slot.
      - Journal Entry: per-row `custom_forex_rate_source` on each
        Journal Entry Account, read and stamped independently per row.
    Applied date is always at parent level.
    """
    adapter = ADAPTERS.get(doc.doctype)
    if not adapter:
        return

    as_of = doc.get("custom_forex_rate_applied_date") \
            or doc.get("posting_date") or nowdate()
    company = doc.get("company")
    if not company:
        return
    to_currency = frappe.get_cached_value("Company", company, "default_currency")
    if not to_currency:
        return

    # JE: per-row source. Each accounts[] row resolves independently.
    if doc.doctype == "Journal Entry":
        _apply_je_per_row(doc, adapter, to_currency, as_of)
        return

    # Everyone else: one parent-level source applies to all slots.
    source = _to_internal(doc.get("custom_forex_rate_source") or "Auto")

    # PEAS policy: at advance-request time the actual rate is unknown,
    # so a Spot or back-dated rate makes no sense. Force Ask Rate +
    # use-today regardless of what was saved on the doc. (PE and EC
    # keep full Spot/Ask/Manual + as-of-date flexibility.)
    if doc.doctype == "Employee Advance":
        source = "Ask Rate"
        as_of = doc.get("posting_date") or nowdate()

    if source in ("Inherited", "Manual"):
        return

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
        doc.custom_forex_rate_source = _to_display(resolved_source)

    # Stamp the date the rate was looked up so auditors can re-derive the
    # exact resolver decision later. Only set on docs that actually had a
    # rate resolved this pass — leaves single-currency docs untouched.
    if resolved_source and not doc.get("custom_forex_rate_applied_date"):
        doc.custom_forex_rate_applied_date = as_of


def _apply_je_per_row(doc, adapter, to_currency, as_of):
    """JE source lives on each Journal Entry Account row. Populate
    exchange_rate per row, stamp source per row, and also compute
    base-currency debit/credit so ERPNext's validate ('Both Debit and
    Credit values cannot be zero') sees consistent numbers."""
    slot = adapter["slots"][0]  # JE has one slot: the accounts child table
    table = slot["table"]

    for row in doc.get(table) or []:
        from_currency = row.get(slot["from_field"])
        if not from_currency or from_currency == to_currency:
            # Same-currency row: rate is 1, no lookup needed. Leave source
            # alone; if user picked Auto it stays Auto and is harmless.
            continue

        source = _to_internal(row.get("custom_forex_rate_source") or "Auto")

        if source == "Inherited":
            # Programmatic callers (EC settlement, revaluation) fill the
            # rate themselves; don't touch.
            continue

        if source == "Manual":
            _recompute_je_row_base(row, row.get(slot["rate_field"]))
            continue

        rate, actual_source, _ = resolve(from_currency, to_currency, as_of, source)
        if rate is not None:
            row.set(slot["rate_field"], rate)
            _recompute_je_row_base(row, rate)
        if source == "Auto" and actual_source:
            row.set("custom_forex_rate_source", _to_display(actual_source))


def _recompute_je_row_base(row, rate):
    """Set base-currency debit/credit from account-currency values, so
    the row is internally consistent when ERPNext's validate runs."""
    if not rate:
        return
    dr_ac = row.get("debit_in_account_currency") or 0
    cr_ac = row.get("credit_in_account_currency") or 0
    if dr_ac:
        row.set("debit", dr_ac * rate)
    if cr_ac:
        row.set("credit", cr_ac * rate)


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
    """Whitelisted wrapper for client-side calls.

    Accepts "Live Rate" as source (user-facing label) and returns "Live Rate"
    in the response. Internally delegates to resolve() which uses "Ask Rate".
    """
    rate, actual_source, rate_date = resolve(
        from_currency, to_currency, as_of_date, _to_internal(source)
    )
    return {
        "rate": rate,
        "source": _to_display(actual_source),
        "rate_date": str(rate_date) if rate_date else None,
    }


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
    # Spot is a negotiated bank rate for a specific transaction day — it
    # never carries forward (yesterday's Spot is meaningless for today's
    # transaction). Require exact date match.
    # Ask Rate / Central Bank Rate are reference rates — they carry forward
    # if today's hasn't synced yet, so use <= for those.
    if rate_type == "Spot":
        date_clause = "rate_date = %s"
    else:
        date_clause = "rate_date <= %s"
    rows = frappe.db.sql(f"""
        SELECT exchange_rate, rate_date
        FROM `tabForex Rate Log`
        WHERE from_currency = %s AND to_currency = %s
          AND rate_type = %s AND {date_clause}
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


