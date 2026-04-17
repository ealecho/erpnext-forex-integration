"""Default the per-row currency on Expense Breakdown children.

Expense Breakdown is the child doctype used by Employee Advance
(`custom_expenses` table) and Petty Cash Request (`expense_breakdown`
table). Without this hook, an empty `custom_currency` Link field on a
row falls through to Frappe's Global Defaults `default_currency` (GBP
on PEAS Global's base), so UGX/USD rows display + persist as GBP. That
trips the "Breakdown total in <X> does not match Advance Amount in <Y>"
validator on EA / PCR.

Fix: at parent before_validate time, walk the breakdown table and set
`custom_currency` to the parent's transaction currency:
  - EA  + multi-currency : doc.custom_e_a_currency
  - EA  + single-currency: company default_currency
  - PCR (never multi)    : company default_currency

Not in scope here: Expense Claim (labelled "Accountability" in the
PEAS UI). That uses a different child doctype (`Expense Claim Detail`)
with its own currency field (`custom_original_currency`), and peas_hr's
"Expense Claim Scripts V3" client script already handles row-currency
inheritance there.
"""

import frappe
from frappe.utils import flt


# parent doctype -> (table fieldname,
#                    optional multi-currency-currency field,
#                    optional multi-currency toggle field)
# When both optional fields are set and the toggle is on, use the
# multi-currency field as the row currency. Otherwise fall back to
# company default_currency.
_BREAKDOWN_TABLES = {
    "Employee Advance":   ("custom_expenses",    "custom_e_a_currency", "custom_is_multicurrency"),
    "Petty Cash Request": ("expense_breakdown",  None,                  None),
}


def default_breakdown_currency(doc, method=None):
    spec = _BREAKDOWN_TABLES.get(doc.doctype)
    if not spec:
        return
    table_field, currency_field, multi_field = spec
    rows = doc.get(table_field) or []
    if not rows:
        return

    parent_currency = _resolve_parent_currency(doc, currency_field, multi_field)
    if not parent_currency:
        return

    company_currency = _company_currency(doc.get("company"))
    for row in rows:
        # Always force the row currency to match the parent transaction
        # currency. Don't try to be clever about "only if empty" — Frappe's
        # Currency Link field auto-fills the system default (GBP on this
        # bench), so an "empty" check leaves stale GBP rows in place. PEAS
        # convention is parent-currency-locks-row, mirroring the V3 EC
        # script's behaviour on Expense Claim Detail.
        row.custom_currency = parent_currency
        # Same-currency rows have no resolver pass to fill exchange_rate;
        # set 1 explicitly so child-table currency math has a sane default.
        if not flt(row.get("custom_exchange_rate")) \
                and company_currency and parent_currency == company_currency:
            row.custom_exchange_rate = 1


def _resolve_parent_currency(doc, currency_field, multi_field):
    if currency_field and multi_field and doc.get(multi_field) and doc.get(currency_field):
        return doc.get(currency_field)
    return _company_currency(doc.get("company"))


def _company_currency(company):
    if not company:
        return None
    return frappe.get_cached_value("Company", company, "default_currency")
