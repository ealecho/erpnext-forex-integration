"""Relabel legacy Forex Rate Log rows mis-labelled as Spot from Alpha Vantage.

By PEAS terminology Spot = manually-entered negotiated bank rate (see
CLAUDE.md). A previous sync code path mis-labelled Alpha Vantage rates
as Spot. An earlier patch renamed the first batch of ~2470 rows; this
handles the ~2228-row straggler batch from the Feb–Mar 2026 window.

Rename approach (not delete): these are the ONLY per-day rate data for
those dates on some sites. Deleting them would destroy historical
signal needed for retrospective rate lookups. Renaming preserves the
data — the rows just get the right rate_type label.

Collision handling: names are deterministic {from}-{to}-{date}-{type},
so if an Ask Rate row with the target name already exists (because
the corrected sync wrote one later for the same day), we delete the
Spot-labelled duplicate — no signal loss since Ask Rate coverage
already exists for that date.

Idempotent: only renames rows where rate_type=Spot AND source=Alpha Vantage.
Manual Spot entries (the legitimate ones) are untouched.
"""

import frappe


def execute():
    stale = frappe.db.sql(
        """
        SELECT name, from_currency, to_currency, rate_date
          FROM `tabForex Rate Log`
         WHERE rate_type = 'Spot' AND source = 'Alpha Vantage'
        """,
        as_dict=True,
    )
    if not stale:
        return

    renamed = 0
    deleted_dups = 0
    for row in stale:
        target_name = (
            f"{row.from_currency}-{row.to_currency}-{row.rate_date}-Ask Rate"
        )
        if frappe.db.exists("Forex Rate Log", target_name):
            # An Ask Rate row already covers this pair/date. The mis-labelled
            # Spot row is redundant — drop it, keep the correctly-labelled one.
            frappe.db.delete("Forex Rate Log", {"name": row.name})
            deleted_dups += 1
        else:
            frappe.rename_doc(
                "Forex Rate Log", row.name, target_name,
                force=True, merge=False, show_alert=False,
            )
            frappe.db.set_value("Forex Rate Log", target_name, "rate_type", "Ask Rate")
            renamed += 1

    frappe.db.commit()
    frappe.logger().info(
        f"peasforex: clear_legacy_av_spot_rows relabelled {renamed} rows "
        f"Spot→Ask Rate, dropped {deleted_dups} duplicates"
    )
