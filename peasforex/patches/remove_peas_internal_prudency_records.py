# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe


def execute():
    """
    Remove all Forex Rate Log entries with rate_type 'PEAS Internal Prudency'.

    This rate type is no longer used. The Prudency Calculator page computes
    prudency rates on the fly from Monthly Average data.
    """
    rate_log_count = frappe.db.count(
        "Forex Rate Log",
        filters={"rate_type": "PEAS Internal Prudency"},
    )

    if rate_log_count:
        frappe.db.delete(
            "Forex Rate Log",
            filters={"rate_type": "PEAS Internal Prudency"},
        )
        frappe.db.commit()
        print(
            f"Deleted {rate_log_count} Forex Rate Log entries with PEAS Internal Prudency rate type."
        )
    else:
        print("No PEAS Internal Prudency records found to delete.")
