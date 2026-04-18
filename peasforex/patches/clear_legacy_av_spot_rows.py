"""Relabel legacy Forex Rate Log rows mis-labelled as Spot from Alpha Vantage.

Uses direct SQL for performance — frappe.rename_doc is too heavy for bulk
operations on large FRL tables (lock timeout on production).
"""

import frappe


def execute():
    # Count stale rows
    count = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabForex Rate Log` WHERE rate_type='Spot' AND source='Alpha Vantage'"
    )[0][0]
    if not count:
        return

    # Step 1: Delete Spot rows where an Ask Rate row already exists for same pair/date
    frappe.db.sql("""
        DELETE s FROM `tabForex Rate Log` s
        INNER JOIN `tabForex Rate Log` a
            ON a.from_currency = s.from_currency
            AND a.to_currency = s.to_currency
            AND a.rate_date = s.rate_date
            AND a.rate_type = 'Ask Rate'
        WHERE s.rate_type = 'Spot' AND s.source = 'Alpha Vantage'
    """)
    frappe.db.commit()

    # Step 2: Rename remaining Spot→Ask Rate via SQL UPDATE (name + rate_type)
    frappe.db.sql("""
        UPDATE `tabForex Rate Log`
        SET rate_type = 'Ask Rate',
            name = CONCAT(from_currency, '-', to_currency, '-', rate_date, '-Ask Rate')
        WHERE rate_type = 'Spot' AND source = 'Alpha Vantage'
    """)
    frappe.db.commit()

    remaining = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabForex Rate Log` WHERE rate_type='Spot' AND source='Alpha Vantage'"
    )[0][0]
    frappe.logger().info(
        f"peasforex: clear_legacy_av_spot_rows — processed {count} rows, {remaining} remaining"
    )
