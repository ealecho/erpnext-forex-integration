# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe


def execute():
    """
    Remove all Forex Rate Log entries with rate_type 'Prudency (High)' or 'Prudency (Low)'
    and all Forex Sync Log entries with sync_type 'Prudency'.

    These rate types are no longer used. PEAS Internal Prudency (6-month rolling
    average x factor) replaces them.
    """
    # Delete Forex Rate Log entries
    rate_log_count = frappe.db.count(
        "Forex Rate Log",
        filters={"rate_type": ["in", ["Prudency (High)", "Prudency (Low)"]]},
    )

    if rate_log_count:
        frappe.db.delete(
            "Forex Rate Log",
            filters={"rate_type": ["in", ["Prudency (High)", "Prudency (Low)"]]},
        )
        frappe.db.commit()
        print(
            f"Deleted {rate_log_count} Forex Rate Log entries with Prudency (High)/(Low) rate types."
        )

    # Delete Forex Sync Log entries
    sync_log_count = frappe.db.count(
        "Forex Sync Log",
        filters={"sync_type": "Prudency"},
    )

    if sync_log_count:
        frappe.db.delete(
            "Forex Sync Log",
            filters={"sync_type": "Prudency"},
        )
        frappe.db.commit()
        print(
            f"Deleted {sync_log_count} Forex Sync Log entries with Prudency sync type."
        )

    if not rate_log_count and not sync_log_count:
        print("No Prudency (High)/(Low) records found to delete.")
