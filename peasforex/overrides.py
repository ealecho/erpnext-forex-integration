# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

"""Monkeypatch erpnext.accounts.report.utils.get_rate_as_at so financial
reports (Balance Sheet, P&L, Cash Flow) honour the "Rate Type" filter
injected by peasforex.js. Rates come from Forex Rate Log; anything not
found there (including "Manual") falls back to ERPNext's standard
Currency Exchange lookup."""

import json

import frappe
from frappe.utils import flt, getdate


def _requested_rate_type():
    # ponytail: reads the report filters off frappe.form_dict, so prepared
    # reports run in background workers fall back to the default lookup;
    # pass rate_type through currency_info if that ever matters.
    filters = frappe.form_dict.get("filters")
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except ValueError:
            return None
    if isinstance(filters, dict):
        return filters.get("rate_type")
    return None


def _get_logged_rate(rate_type, from_currency, to_currency, date):
    def latest(f, t):
        return frappe.db.get_value(
            "Forex Rate Log",
            {
                "rate_type": rate_type,
                "from_currency": f,
                "to_currency": t,
                "rate_date": ("<=", getdate(date)),
            },
            "exchange_rate",
            order_by="rate_date desc",
        )

    rate = latest(from_currency, to_currency)
    if rate:
        return flt(rate)
    inverse = latest(to_currency, from_currency)
    return 1 / flt(inverse) if inverse else None


def get_rate_as_at(date, from_currency, to_currency):
    from erpnext.setup.utils import get_exchange_rate

    rate_type = _requested_rate_type()
    cache = getattr(frappe.local, "peasforex_rate_cache", None)
    if cache is None:
        cache = frappe.local.peasforex_rate_cache = {}
    key = f"{from_currency}-{to_currency}@{date}|{rate_type}"
    if key not in cache:
        rate = None
        if rate_type and rate_type != "Manual":
            rate = _get_logged_rate(rate_type, from_currency, to_currency, date)
        cache[key] = rate or get_exchange_rate(from_currency, to_currency, date) or 1
    return cache[key]


def apply_patches():
    from erpnext.accounts.report import utils

    utils.get_rate_as_at = get_rate_as_at
