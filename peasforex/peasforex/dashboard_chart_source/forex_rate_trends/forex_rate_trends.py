# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, add_days, nowdate


@frappe.whitelist()
def get_data(chart_name=None, chart=None, no_cache=None, filters=None,
             from_date=None, to_date=None, timespan=None, time_interval=None,
             heatmap_year=None):
    """
    Custom data source for Forex Rate Trends chart.
    Shows actual exchange rate values over time for each currency pair.
    """
    
    # Determine date range based on timespan
    if timespan == "Last Week":
        days = 7
    elif timespan == "Last Month":
        days = 30
    elif timespan == "Last Quarter":
        days = 90
    elif timespan == "Last Year":
        days = 365
    else:
        days = 30  # Default to last month
    
    start_date = add_days(nowdate(), -days)
    end_date = nowdate()
    
    # Override with explicit dates if provided
    if from_date:
        start_date = from_date
    if to_date:
        end_date = to_date
    
    # Get spot rates for all currency pairs, grouped by date and pair
    data = frappe.db.sql("""
        SELECT 
            rate_date,
            CONCAT(from_currency, ' → ', to_currency) as currency_pair,
            exchange_rate
        FROM `tabForex Rate Log`
        WHERE rate_type = 'Spot'
        AND rate_date >= %(start_date)s
        AND rate_date <= %(end_date)s
        ORDER BY rate_date ASC
    """, {
        "start_date": start_date,
        "end_date": end_date
    }, as_dict=1)
    
    if not data:
        return {
            "labels": [],
            "datasets": []
        }
    
    # Group by currency pair
    pairs = {}
    all_dates = set()
    
    for row in data:
        pair = row.currency_pair
        date = row.rate_date
        rate = float(row.exchange_rate or 0)
        
        if pair not in pairs:
            pairs[pair] = {}
        pairs[pair][date] = rate
        all_dates.add(date)
    
    # Sort dates and format for display
    sorted_dates = sorted(list(all_dates))
    labels = [format_short_date(d) for d in sorted_dates]
    
    # Build datasets for each currency pair
    datasets = []
    for pair, date_rates in pairs.items():
        values = [date_rates.get(date, 0) for date in sorted_dates]
        datasets.append({
            "name": pair,
            "values": values
        })
    
    return {
        "labels": labels,
        "datasets": datasets
    }


def format_short_date(date_obj):
    """Format date as 'Jan 14' style"""
    if not date_obj:
        return ""
    if isinstance(date_obj, str):
        date_obj = getdate(date_obj)
    return date_obj.strftime("%b %d")
