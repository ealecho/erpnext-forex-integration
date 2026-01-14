# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe
import json


# Currency group definitions
AFRICAN_CURRENCIES = ['UGX', 'ZMW', 'GHS']
MAJOR_CURRENCIES = ['USD', 'EUR', 'GBP', 'DKK']


@frappe.whitelist()
def get_data(chart_name=None, chart=None, no_cache=None, filters=None,
             from_date=None, to_date=None, timespan=None, time_interval=None,
             heatmap_year=None):
    """
    Custom data source for Forex Latest Rates chart.
    Shows the most recent exchange rate for each currency pair as a bar chart.
    Supports filtering by currency group (African or Major).
    """
    
    # Parse filters if string
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (json.JSONDecodeError, TypeError):
            filters = {}
    
    filters = filters or {}
    
    # Get currency group filter (default to African for better Y-axis scaling)
    currency_group = filters.get('currency_group', 'African')
    
    # Build WHERE clause based on currency group
    where_clause = build_currency_filter(currency_group)
    
    # Get the latest spot rate for each currency pair
    query = """
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
        {where_clause}
        ORDER BY from_currency, to_currency
    """.format(where_clause=where_clause)
    
    data = frappe.db.sql(query, as_dict=1)
    
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


def build_currency_filter(currency_group):
    """
    Build SQL WHERE clause based on currency group selection.
    
    African: Pairs where to_currency is UGX, ZMW, or GHS
    Major: Pairs where both from and to are major currencies (USD, EUR, GBP, DKK)
    """
    if currency_group == 'African':
        # African currencies as the target (to_currency)
        currencies = "', '".join(AFRICAN_CURRENCIES)
        return f"AND to_currency IN ('{currencies}')"
    elif currency_group == 'Major':
        # Both currencies should be major currencies
        currencies = "', '".join(MAJOR_CURRENCIES)
        return f"AND from_currency IN ('{currencies}') AND to_currency IN ('{currencies}')"
    else:
        # Default: return all (no additional filter)
        return ""
