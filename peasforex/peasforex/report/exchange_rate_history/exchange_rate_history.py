# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns(filters)
    data = get_data(filters)
    chart = get_chart(data, filters)
    report_summary = get_report_summary(data, filters)
    
    return columns, data, None, chart, report_summary


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
    """Generate chart data for the report"""
    if not data:
        return None
    
    # Group data by currency pair for multi-line chart
    pairs = {}
    for row in data:
        pair_key = f"{row.get('from_currency')} → {row.get('to_currency')}"
        if pair_key not in pairs:
            pairs[pair_key] = []
        pairs[pair_key].append(row)
    
    # If specific currencies are selected, show detailed trend chart
    if filters.get("from_currency") and filters.get("to_currency"):
        pair_key = f"{filters.get('from_currency')} → {filters.get('to_currency')}"
        pair_data = pairs.get(pair_key, data)
        
        # Filter for spot rates for cleaner chart, fallback to all if no spot
        spot_data = [d for d in pair_data if d.get("rate_type") == "Spot"]
        if not spot_data:
            spot_data = pair_data
        
        # Sort chronologically and limit to last 60 data points
        spot_data = sorted(spot_data, key=lambda x: x.get("rate_date"))[-60:]
        
        labels = [str(d.get("rate_date")) for d in spot_data]
        values = [float(d.get("exchange_rate") or 0) for d in spot_data]
        
        return {
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "name": pair_key,
                        "values": values
                    }
                ]
            },
            "type": "line",
            "height": 300,
            "colors": ["#5e64ff"],
            "lineOptions": {
                "regionFill": 1,
                "hideDots": 0
            },
            "axisOptions": {
                "xIsSeries": True
            }
        }
    
    # Multi-currency view - show all pairs
    if len(pairs) <= 8:  # Only show chart if not too many pairs
        # Get unique dates across all pairs
        all_dates = set()
        for pair_data in pairs.values():
            for row in pair_data:
                if row.get("rate_type") == "Spot":
                    all_dates.add(str(row.get("rate_date")))
        
        if not all_dates:
            # Fallback to all rate types
            for pair_data in pairs.values():
                for row in pair_data:
                    all_dates.add(str(row.get("rate_date")))
        
        labels = sorted(list(all_dates))[-30:]  # Last 30 dates
        
        datasets = []
        colors = ["#7cd6fd", "#5e64ff", "#743ee2", "#ff5858", "#ffa00a", "#28a745", "#17a2b8", "#6c757d"]
        
        for idx, (pair_key, pair_data) in enumerate(pairs.items()):
            # Build date -> rate mapping for this pair
            date_rate_map = {}
            for row in pair_data:
                if row.get("rate_type") == "Spot":
                    date_rate_map[str(row.get("rate_date"))] = float(row.get("exchange_rate") or 0)
            
            # If no spot rates, use any rate
            if not date_rate_map:
                for row in pair_data:
                    date_rate_map[str(row.get("rate_date"))] = float(row.get("exchange_rate") or 0)
            
            values = [date_rate_map.get(date, 0) for date in labels]
            
            datasets.append({
                "name": pair_key,
                "values": values,
                "chartType": "line"
            })
        
        if datasets:
            return {
                "data": {
                    "labels": labels,
                    "datasets": datasets
                },
                "type": "line",
                "height": 300,
                "colors": colors[:len(datasets)],
                "lineOptions": {
                    "regionFill": 0,
                    "hideDots": 0
                },
                "axisOptions": {
                    "xIsSeries": True
                }
            }
    
    return None


def get_report_summary(data, filters):
    """Generate summary cards for dashboard view"""
    if not data:
        return None
    
    summary = []
    
    # Total records
    summary.append({
        "value": len(data),
        "label": _("Total Records"),
        "datatype": "Int",
        "indicator": "blue"
    })
    
    # Unique currency pairs
    pairs = set()
    for row in data:
        pairs.add(f"{row.get('from_currency')}-{row.get('to_currency')}")
    
    summary.append({
        "value": len(pairs),
        "label": _("Currency Pairs"),
        "datatype": "Int",
        "indicator": "green"
    })
    
    # Date range
    dates = [row.get("rate_date") for row in data if row.get("rate_date")]
    if dates:
        min_date = min(dates)
        max_date = max(dates)
        days = (max_date - min_date).days + 1 if hasattr(max_date - min_date, 'days') else 1
        
        summary.append({
            "value": days,
            "label": _("Days Covered"),
            "datatype": "Int",
            "indicator": "orange"
        })
    
    # Latest sync
    synced_times = [row.get("synced_at") for row in data if row.get("synced_at")]
    if synced_times:
        latest_sync = max(synced_times)
        summary.append({
            "value": frappe.utils.pretty_date(latest_sync),
            "label": _("Last Synced"),
            "datatype": "Data",
            "indicator": "gray"
        })
    
    return summary
