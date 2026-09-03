# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

"""Applied-rates strip for financial reports: for each account currency in
the company's chart, the exact rate (per the selected Rate Type) used to
express values in the presentation currency."""

import json

import frappe
from frappe.utils import flt, getdate, today


def _logged_rate_with_date(rate_type, from_currency, to_currency, date):
    """Like peasforex.overrides._get_logged_rate but also returns the
    rate_date actually matched, so the UI can show the real 'as at' date."""

    def latest(f, t):
        return frappe.db.get_value(
            "Forex Rate Log",
            {
                "rate_type": rate_type,
                "from_currency": f,
                "to_currency": t,
                "rate_date": ("<=", getdate(date)),
            },
            ["exchange_rate", "rate_date"],
            order_by="rate_date desc",
            as_dict=True,
        )

    row = latest(from_currency, to_currency)
    if row and row.exchange_rate:
        return flt(row.exchange_rate), row.rate_date
    row = latest(to_currency, from_currency)
    if row and row.exchange_rate:
        return 1 / flt(row.exchange_rate), row.rate_date
    return None, None


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
        rate, rate_date, source = None, None, rate_type
        if rate_type != "Manual":
            rate, rate_date = _logged_rate_with_date(rate_type, ccy, pres, date)
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
            "rate_date": str(rate_date) if rate_date else None,
            "source": source,
            "used_for_conversion": ccy == base,
        })

    return {"date": str(date), "rate_type": rate_type, "rates": rates}
