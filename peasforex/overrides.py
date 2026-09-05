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


def _report_filters():
    # ponytail: reads the report filters off frappe.form_dict, so prepared
    # reports run in background workers fall back to the default lookup;
    # pass rate_type through currency_info if that ever matters.
    filters = frappe.form_dict.get("filters")
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except ValueError:
            return {}
    return filters if isinstance(filters, dict) else {}


def _requested_rate_type():
    return _report_filters().get("rate_type")


def parse_manual_rates(raw):
    """The manual_rates filter: {"UGX": 0.000196, ...} - each value meaning
    1 <currency> = <value> <presentation currency>."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _manual_rate(from_currency, to_currency, filters):
    manual = parse_manual_rates(filters.get("manual_rates"))
    if not manual:
        return None
    pres = filters.get("presentation_currency")

    def r(ccy):
        return 1.0 if ccy == pres else (flt(manual.get(ccy)) or None)

    r_from, r_to = r(from_currency), r(to_currency)
    # 1 from = r_from pres and 1 to = r_to pres  =>  1 from = r_from/r_to to
    return r_from / r_to if r_from and r_to else None


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
        if rate_type == "Manual":
            rate = _manual_rate(from_currency, to_currency, _report_filters())
        elif rate_type:
            rate = _get_logged_rate(rate_type, from_currency, to_currency, date)
        cache[key] = rate or get_exchange_rate(from_currency, to_currency, date) or 1
    return cache[key]


_orig_cfs_execute = None

STANDALONE_FIELD = "peasforex_parent_standalone"


def cfs_execute(filters=None):
    """Wrap the Consolidated Financial Statement:
    - relabel the parent column '<Parent> ++' when it holds the group sum
      (Accumulated Values in Group Company checked), 'PEAS UK' when it holds
      only the parent's own books;
    - when accumulated, add a 'PEAS UK' column (and chart bar): the parent's
      standalone figures on the same conversion basis (presentation currency,
      selected Rate Type) as every other column, so the sum is traceable."""
    result = list(_orig_cfs_execute(filters))
    company = filters.get("company") if filters else None
    pres = filters.get("presentation_currency") if filters else None
    accumulated = bool(filters.get("accumulated_in_group_company")) if filters else False
    columns = result[0] if result else None
    chart = result[3] if len(result) > 3 else None

    def relabel(text, new_name):
        return new_name + text[len(company):] if isinstance(text, str) and text.startswith(company) else text

    if company and columns:
        new_name = f"{company} ++" if accumulated else "PEAS UK"
        for c in columns:
            if c.get("fieldname") == company:
                c["label"] = relabel(c.get("label"), new_name)
        if isinstance(chart, dict) and chart.get("data"):
            chart["data"]["labels"] = [relabel(l, new_name) for l in chart["data"].get("labels") or []]

    if company and pres and accumulated and len(result) >= 2 and result[1]:
        data = result[1]

        # ponytail: full second execution; cache if consolidated reports feel slow.
        # Same presentation currency and Rate Type (rate_type flows via
        # frappe.form_dict), but WITHOUT group accumulation: the parent's
        # standalone figures on the same conversion basis as every other column.
        standalone_filters = frappe._dict(filters)
        standalone_filters.accumulated_in_group_company = 0
        standalone_result = list(_orig_cfs_execute(standalone_filters))
        standalone_data = standalone_result[1] or []
        standalone_by_account = {row.get("account"): row.get(company) for row in standalone_data if row}

        label = f"PEAS UK ({pres})"
        idx = next((i for i, c in enumerate(columns) if c.get("fieldname") == company), len(columns) - 1)
        columns.insert(idx + 1, {
            "fieldname": STANDALONE_FIELD,
            "label": label,
            "fieldtype": "Currency",
            "options": "currency",
        })
        for row in data:
            if row and row.get("account") in standalone_by_account:
                row[STANDALONE_FIELD] = standalone_by_account[row.get("account")]

        # PEAS UK bar in the chart, right after the consolidated bar
        s_chart = standalone_result[3] if len(standalone_result) > 3 else None
        if isinstance(chart, dict) and chart.get("data") and isinstance(s_chart, dict) and s_chart.get("data"):
            s_labels = s_chart["data"].get("labels") or []
            s_idx = next(
                (i for i, l in enumerate(s_labels) if isinstance(l, str) and l.startswith(company)), None
            )
            if s_idx is not None:
                m_labels = chart["data"].get("labels") or []
                m_idx = next(
                    (i for i, l in enumerate(m_labels) if isinstance(l, str) and l.startswith(f"{company} ++")), -1
                )
                m_labels.insert(m_idx + 1, label)
                s_sets = {d.get("name"): d for d in s_chart["data"].get("datasets") or []}
                for d in chart["data"].get("datasets") or []:
                    s_vals = (s_sets.get(d.get("name")) or {}).get("values") or []
                    d.setdefault("values", []).insert(
                        m_idx + 1, s_vals[s_idx] if s_idx < len(s_vals) else 0
                    )

    # widen currency columns (after relabeling) so header labels aren't truncated
    if columns:
        for c in columns:
            if c.get("fieldtype") == "Currency":
                c["width"] = max(c.get("width") or 150, 40 + 8 * len(c.get("label") or ""))
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
    # collect matched rate dates so get_accounts_data can tell the user
    # which month-end actually priced this revaluation
    dates = getattr(frappe.local, "peasforex_err_rate_dates", None)
    if dates is None:
        dates = frappe.local.peasforex_err_rate_dates = set()
    dates.add(str(rate_date))
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
    balance), tell the user which currencies were skipped, and state which
    Closing rate date(s) priced the entries."""
    frappe.local.peasforex_err_rate_dates = set()
    accounts = _orig_get_accounts_data(self)
    dates = frappe.local.peasforex_err_rate_dates
    if dates:
        frappe.msgprint(
            _("Priced at Closing rate(s) of {0} (posting date {1}).").format(
                ", ".join(frappe.utils.formatdate(d) for d in sorted(dates)),
                frappe.utils.formatdate(self.posting_date),
            ),
            indicator="blue",
            alert=True,
        )
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
