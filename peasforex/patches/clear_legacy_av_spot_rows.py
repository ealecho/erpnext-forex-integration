"""Relabel legacy Forex Rate Log rows mis-labelled as Spot from Alpha Vantage.

Simple UPDATE only — no renames, no JOINs, no locks on other rows.
"""

import frappe


def execute():
    count = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabForex Rate Log` WHERE rate_type='Spot' AND source='Alpha Vantage'"
    )[0][0]
    if not count:
        return

    # Just change rate_type. Don't rename the `name` field (causes lock timeouts).
    frappe.db.sql("""
        UPDATE `tabForex Rate Log`
        SET rate_type = 'Ask Rate'
        WHERE rate_type = 'Spot' AND source = 'Alpha Vantage'
    """)
    frappe.db.commit()
    frappe.logger().info(f"peasforex: relabelled {count} Spot→Ask Rate rows")
