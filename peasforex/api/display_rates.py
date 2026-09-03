# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

"""Applied-rates strip for financial reports: for each account currency in
the company's chart, the exact rate (per the selected Rate Type) used to
express values in the presentation currency."""

import json

import frappe
from frappe.utils import flt, today

from peasforex.overrides import _get_logged_rate


@frappe.whitelist()
def get_display_rates(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")
    company = filters.get("company")
    pres = filters.get("presentation_currency")
    if not (company and pres):
        return {}

    base = frappe.get_cached_value("Company", company, "default_currency")
    date = filters.get("to_date") or filters.get("period_end_date")
    if not date and filters.get("to_fiscal_year"):
        date = frappe.db.get_value("Fiscal Year", filters["to_fiscal_year"], "year_end_date")
    date = date or today()
    rate_type = filters.get("rate_type") or "Closing"

    account_ccys = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "disabled": 0},
        pluck="account_currency",
        distinct=True,
    )
    # company currency first (it's the one conversion actually runs through)
    ccys = [c for c in dict.fromkeys([base, *filter(None, account_ccys)]) if c != pres]

    rates = []
    for ccy in ccys:
        rate, source = None, rate_type
        if rate_type != "Manual":
            rate = _get_logged_rate(rate_type, ccy, pres, date)
        if rate is None:
            try:
                from erpnext.setup.utils import get_exchange_rate

                rate = get_exchange_rate(ccy, pres, date)
                source = "Manual" if rate_type == "Manual" else "Default (Currency Exchange)"
            except Exception:
                rate = None
        rates.append({
            "from_currency": ccy,
            "to_currency": pres,
            "rate": flt(rate) or None,
            "source": source,
            "used_for_conversion": ccy == base,
        })

    return {"date": str(date), "rate_type": rate_type, "rates": rates}
