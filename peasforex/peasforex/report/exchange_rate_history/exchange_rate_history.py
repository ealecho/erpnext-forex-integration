# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns(filters)
    data = get_data(filters)
    chart = get_chart(data, filters)
    
    return columns, data, None, chart


def get_columns(filters):
    columns = [
        {
            "fieldname": "rate_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 120
        },
        {
            "fieldname": "from_currency",
            "label": _("From Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "width": 100
        },
        {
            "fieldname": "to_currency",
            "label": _("To Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "width": 100
        },
        {
            "fieldname": "rate_type",
            "label": _("Rate Type"),
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "exchange_rate",
            "label": _("Exchange Rate"),
            "fieldtype": "Float",
            "precision": 6,
            "width": 140
        },
        {
            "fieldname": "high_rate",
            "label": _("High"),
            "fieldtype": "Float",
            "precision": 6,
            "width": 120
        },
        {
            "fieldname": "low_rate",
            "label": _("Low"),
            "fieldtype": "Float",
            "precision": 6,
            "width": 120
        },
        {
            "fieldname": "synced_at",
            "label": _("Synced At"),
            "fieldtype": "Datetime",
            "width": 160
        }
    ]
    
    return columns


def get_data(filters):
    conditions = []
    values = {}
    
    if filters.get("from_date"):
        conditions.append("rate_date >= %(from_date)s")
        values["from_date"] = filters.get("from_date")
    
    if filters.get("to_date"):
        conditions.append("rate_date <= %(to_date)s")
        values["to_date"] = filters.get("to_date")
    
    if filters.get("from_currency"):
        conditions.append("from_currency = %(from_currency)s")
        values["from_currency"] = filters.get("from_currency")
    
    if filters.get("to_currency"):
        conditions.append("to_currency = %(to_currency)s")
        values["to_currency"] = filters.get("to_currency")
    
    if filters.get("rate_type"):
        conditions.append("rate_type = %(rate_type)s")
        values["rate_type"] = filters.get("rate_type")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    data = frappe.db.sql(f"""
        SELECT 
            rate_date,
            from_currency,
            to_currency,
            rate_type,
            exchange_rate,
            high_rate,
            low_rate,
            synced_at
        FROM `tabForex Rate Log`
        WHERE {where_clause}
        ORDER BY rate_date DESC, from_currency, to_currency
    """, values, as_dict=True)
    
    return data


def get_chart(data, filters):
    if not data:
        return None
    
    # Group data for charting
    # If specific currencies are selected, show trend chart
    if filters.get("from_currency") and filters.get("to_currency"):
        # Filter for spot rates only for cleaner chart
        spot_data = [d for d in data if d.get("rate_type") == "Spot"]
        
        if not spot_data:
            spot_data = data
        
        # Reverse to show chronological order
        spot_data = sorted(spot_data, key=lambda x: x.get("rate_date"))
        
        labels = [str(d.get("rate_date")) for d in spot_data[-30:]]  # Last 30 data points
        values = [d.get("exchange_rate") for d in spot_data[-30:]]
        
        return {
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "name": f"{filters.get('from_currency')}/{filters.get('to_currency')}",
                        "values": values
                    }
                ]
            },
            "type": "line",
            "colors": ["#5e64ff"],
            "lineOptions": {
                "regionFill": 1
            }
        }
    
    return None
