# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, formatdate, get_last_day, add_months


@frappe.whitelist()
def get_monthly_averages(grant_currency, local_currency, as_of_date=None):
    """
    Fetch 6 Monthly Average rates for the currency pair ending on the specified month.

    Args:
        grant_currency: Source currency (e.g., 'GBP')
        local_currency: Target currency (e.g., 'UGX')
        as_of_date: End date for the 6-month range (defaults to today)

    Returns:
        dict: {
            "success": True/False,
            "months": [
                {"month": "Feb 2026", "rate_date": "2026-02-28", "exchange_rate": 4530.00},
                ...
            ],
            "grand_average": 4530.00,
            "has_sufficient_data": True/False,
            "months_available": 6,
            "error": "..." (if any)
        }
    """
    if not grant_currency or not local_currency:
        return {
            "success": False,
            "months": [],
            "grand_average": None,
            "has_sufficient_data": False,
            "months_available": 0,
            "error": _("Please select both Grant Currency and Local Currency"),
        }

    if grant_currency == local_currency:
        return {
            "success": False,
            "months": [],
            "grand_average": None,
            "has_sufficient_data": False,
            "months_available": 0,
            "error": _("Grant Currency and Local Currency must be different"),
        }

    # Determine end date — use the month BEFORE the selected month
    # so "As of Jan 2026" fetches Jul-Dec 2025 (6 prior months)
    if as_of_date:
        end_date = get_last_day(add_months(getdate(as_of_date), -1))
    else:
        end_date = get_last_day(add_months(getdate(), -1))

    # Fetch the 6 most recent Monthly Average rates up to the selected date
    monthly_averages = frappe.db.sql(
        """
        SELECT rate_date, exchange_rate
        FROM `tabForex Rate Log`
        WHERE from_currency = %(grant_currency)s
        AND to_currency = %(local_currency)s
        AND rate_type = 'Monthly Average'
        AND rate_date <= %(end_date)s
        ORDER BY rate_date DESC
        LIMIT 6
    """,
        {
            "grant_currency": grant_currency,
            "local_currency": local_currency,
            "end_date": end_date,
        },
        as_dict=True,
    )

    months_available = len(monthly_averages)
    has_sufficient_data = months_available >= 6

    # Format months for display
    formatted_months = []
    for row in monthly_averages:
        rate_date = row.rate_date
        # Format as "Feb 2026"
        month_str = formatdate(rate_date, "MMM YYYY")
        formatted_months.append(
            {
                "month": month_str,
                "rate_date": str(rate_date),
                "exchange_rate": float(row.exchange_rate),
            }
        )

    # Calculate grand average only if we have 6 months
    grand_average = None
    if has_sufficient_data:
        rates = [row.exchange_rate for row in monthly_averages]
        grand_average = sum(rates) / len(rates)

    # Build response
    if has_sufficient_data:
        return {
            "success": True,
            "months": formatted_months,
            "grand_average": grand_average,
            "has_sufficient_data": True,
            "months_available": months_available,
        }
    else:
        return {
            "success": False,
            "months": formatted_months,
            "grand_average": None,
            "has_sufficient_data": False,
            "months_available": months_available,
            "error": _(
                "Only {0} months of data available. Need 6 months to calculate."
            ).format(months_available),
        }


@frappe.whitelist()
def get_available_currencies():
    """
    Get list of currencies that have Monthly Average data in Forex Rate Log.

    Returns:
        dict: {
            "grant_currencies": ["GBP", "USD", ...],
            "local_currencies": ["UGX", "ZMW", "GHS", ...]
        }
    """
    # Get unique from_currencies (grant currencies)
    grant_currencies = frappe.db.sql(
        """
        SELECT DISTINCT from_currency
        FROM `tabForex Rate Log`
        WHERE rate_type = 'Monthly Average'
        ORDER BY from_currency
    """,
        as_dict=True,
    )

    # Get unique to_currencies (local currencies)
    local_currencies = frappe.db.sql(
        """
        SELECT DISTINCT to_currency
        FROM `tabForex Rate Log`
        WHERE rate_type = 'Monthly Average'
        ORDER BY to_currency
    """,
        as_dict=True,
    )

    return {
        "grant_currencies": [r.from_currency for r in grant_currencies],
        "local_currencies": [r.to_currency for r in local_currencies],
    }
