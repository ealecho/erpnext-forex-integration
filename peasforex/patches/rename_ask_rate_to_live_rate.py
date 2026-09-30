"""Rename the "Ask Rate" rate type to "Live Rate" (PEAS UAT, Sept 2026).

Stored values only. Record names (e.g. GBP-UGX-2026-08-31-Ask Rate) are left
as-is, same as clear_legacy_av_spot_rows: every lookup filters on fields, not
on name, so old-named rows are still found and never duplicated.
"""

import frappe


def execute():
    for doctype, field, old, new in (
        ("Forex Rate Log", "rate_type", "Ask Rate", "Live Rate"),
        ("Forex Sync Log", "sync_type", "Ask Rate (Daily)", "Live Rate (Daily)"),
        ("FS Rate Demo", "bs_rate_type", "Ask Rate", "Live Rate"),
    ):
        frappe.db.set_value(doctype, {field: old}, field, new, update_modified=False)
