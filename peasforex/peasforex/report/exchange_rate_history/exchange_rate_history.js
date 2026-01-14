// Copyright (c) 2024, ERP Champions and contributors
// For license information, please see license.txt

frappe.query_reports["Exchange Rate History"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "reqd": 0
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 0
        },
        {
            "fieldname": "from_currency",
            "label": __("From Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "reqd": 0
        },
        {
            "fieldname": "to_currency",
            "label": __("To Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "reqd": 0
        },
        {
            "fieldname": "rate_type",
            "label": __("Rate Type"),
            "fieldtype": "Select",
            "options": "\nSpot\nClosing\nMonthly Average\nPrudency (High)\nPrudency (Low)",
            "reqd": 0
        }
    ]
};
