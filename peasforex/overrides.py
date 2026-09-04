# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

"""Monkeypatch erpnext.accounts.report.utils.get_rate_as_at so financial
reports (Balance Sheet, P&L, Cash Flow) honour the "Rate Type" filter
injected by peasforex.js. Rates come from Forex Rate Log; anything not
found there (including "Manual") falls back to ERPNext's standard
Currency Exchange lookup."""

import json

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_last_day, getdate, today


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


_orig_cfs_execute = None

UNCONVERTED_FIELD = "peasforex_unconverted"


def cfs_execute(filters=None):
    """Wrap the Consolidated Financial Statement to add an extra column:
    the parent company's figures in its own base currency, untouched by
    presentation-currency conversion."""
    result = list(_orig_cfs_execute(filters))
    company = filters.get("company") if filters else None
    pres = filters.get("presentation_currency") if filters else None

    # widen currency columns so header labels aren't truncated
    if result and result[0]:
        for c in result[0]:
            if c.get("fieldtype") == "Currency":
                c["width"] = max(c.get("width") or 150, 40 + 8 * len(c.get("label") or ""))

    if not (company and pres) or len(result) < 2 or not result[1]:
        return tuple(result)

    base = frappe.get_cached_value("Company", company, "default_currency")
    columns, data = result[0], result[1]

    # ponytail: full second execution; cache if consolidated reports feel slow.
    # No presentation currency and no group accumulation: the column must
    # always show the parent's OWN books in its own currency - never a sum,
    # never converted - regardless of the report's checkboxes.
    raw_filters = frappe._dict(filters)
    raw_filters.presentation_currency = None
    raw_filters.accumulated_in_group_company = 0
    raw_data = list(_orig_cfs_execute(raw_filters))[1] or []
    raw_by_account = {row.get("account"): row.get(company) for row in raw_data if row}

    label = f"{company} ({base}, Unconverted)"
    idx = next((i for i, c in enumerate(columns) if c.get("fieldname") == company), len(columns) - 1)
    columns.insert(idx + 1, {
        "fieldname": UNCONVERTED_FIELD,
        "label": label,
        "fieldtype": "Currency",
        "width": 40 + 8 * len(label),
        "apply_currency_formatter": 1,
        "company_name": company,
    })
    for row in data:
        if row and row.get("account") in raw_by_account:
            row[UNCONVERTED_FIELD] = raw_by_account[row.get("account")]
    return tuple(result)


_orig_get_accounts_data = None


def err_closing_rate(from_currency, to_currency, transaction_date=None, *_args, **_kwargs):
    """Rate source for Exchange Rate Revaluation: the latest Closing rate on
    or before the posting date (so a revaluation posted 1 April prices at
    31 March - closings only exist at month-ends). Returns 0 when no Closing
    rate exists; the get_accounts_data wrapper drops and reports such rows
    rather than letting a 0 rate post the whole balance as a fake loss."""
    from peasforex.api.display_rates import _logged_rate_with_date

    as_of = transaction_date or today()
    rate, rate_date = _logged_rate_with_date("Closing", from_currency, to_currency, as_of)
    if not rate:
        return 0
    expected = get_last_day(add_months(getdate(as_of), -1))
    if getdate(rate_date) < expected:
        frappe.msgprint(
            _("Closing rate for {0} to {1} is dated {2} - older than expected ({3}). Check the monthly rate sync.").format(
                from_currency, to_currency, rate_date, expected
            ),
            indicator="orange",
            alert=True,
        )
    return rate


@frappe.whitelist()
def err_get_accounts_data(self):
    """Drop rows the Closing lookup could not price (new rate 0 on a live
    balance) and tell the user which currencies were skipped."""
    accounts = _orig_get_accounts_data(self)
    kept, skipped = [], set()
    for row in accounts or []:
        if not flt(row.get("new_exchange_rate")) and not row.get("zero_balance"):
            skipped.add(row.get("account_currency"))
        else:
            kept.append(row)
    if skipped:
        frappe.msgprint(
            _("Skipped accounts in {0}: no Closing rate on or before {1}. Log the rate in Forex Rate Log, or add the row manually with a rate.").format(
                ", ".join(sorted(skipped)), self.posting_date
            ),
            indicator="orange",
        )
    return kept


def apply_patches():
    global _orig_cfs_execute, _orig_get_accounts_data

    from erpnext.accounts.report import utils

    utils.get_rate_as_at = get_rate_as_at

    from erpnext.accounts.report.consolidated_financial_statement import (
        consolidated_financial_statement as cfs,
    )

    if not getattr(cfs.execute, "_peasforex_patched", False):
        _orig_cfs_execute = cfs.execute
        cfs_execute._peasforex_patched = True
        cfs.execute = cfs_execute

    from erpnext.accounts.doctype.exchange_rate_revaluation import (
        exchange_rate_revaluation as err,
    )

    # both get_accounts_data (grid fetch) and get_account_details (manual row)
    # resolve get_exchange_rate from this module's globals
    err.get_exchange_rate = err_closing_rate

    if not getattr(err.ExchangeRateRevaluation.get_accounts_data, "_peasforex_patched", False):
        _orig_get_accounts_data = err.ExchangeRateRevaluation.get_accounts_data
        err_get_accounts_data._peasforex_patched = True
        err.ExchangeRateRevaluation.get_accounts_data = err_get_accounts_data
