# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_data(chart_name=None, chart=None, no_cache=None, filters=None,
             from_date=None, to_date=None, timespan=None, time_interval=None,
             heatmap_year=None):
    """
    Custom data source for Forex Latest Rates chart.
    Shows the most recent exchange rate for each currency pair as a bar chart.
    """
    
    # Get the latest spot rate for each currency pair
    data = frappe.db.sql("""
        SELECT 
            CONCAT(from_currency, ' → ', to_currency) as currency_pair,
            exchange_rate,
            rate_date
        FROM `tabForex Rate Log` frl
        WHERE rate_type = 'Spot'
        AND rate_date = (
            SELECT MAX(rate_date) 
            FROM `tabForex Rate Log` frl2 
            WHERE frl2.from_currency = frl.from_currency 
            AND frl2.to_currency = frl.to_currency
            AND frl2.rate_type = 'Spot'
        )
        ORDER BY from_currency, to_currency
    """, as_dict=1)
    
    if not data:
        return {
            "labels": [],
            "datasets": []
        }
    
    labels = [row.currency_pair for row in data]
    values = [float(row.exchange_rate or 0) for row in data]
    
    return {
        "labels": labels,
        "datasets": [
            {
                "name": "Latest Rate",
                "values": values
            }
        ]
    }
