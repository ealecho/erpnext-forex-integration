# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

"""Dev-only: bulk-seed GL Entries so financial reports can be perf-tested
at production volume (the 10k+ record UAT scenario).

Rows are raw inserts with voucher_no SEED-* and no real voucher behind
them - drill-down links from reports will 404. That's fine: this is a
perf fixture, not books. Every voucher is a balanced debit/credit pair
spread across the current fiscal year, so Balance Sheet / P&L / CFS with
a presentation currency + Rate Type exercise the per-date rate lookups
exactly like production.

    bench --site peas-dev.localhost execute \
        peasforex.tasks.seed_perf_data.seed --kwargs "{'count': 10000}"
    bench --site peas-dev.localhost execute peasforex.tasks.seed_perf_data.clear
"""

import frappe
from frappe.utils import add_days, flt, getdate, now, nowdate


def _guard():
    if not (frappe.conf.developer_mode or "dev" in frappe.local.site):
        frappe.throw("seed_perf_data is a dev-only tool; refusing to run on this site")


def seed(count=10000, company=None):
    """Insert `count` GL Entry rows (count/2 balanced vouchers)."""
    _guard()
    from erpnext.accounts.utils import get_fiscal_year

    company = (
        company
        or frappe.defaults.get_global_default("company")
        or frappe.db.get_value("Company", {}, "name")
    )
    if not company:
        frappe.throw("No Company found; pass one via --kwargs \"{'company': '...'}\"")
    currency = frappe.db.get_value("Company", company, "default_currency")
    fy_name, fy_start, fy_end = get_fiscal_year(nowdate(), company=company)
    fy_start, span = getdate(fy_start), (getdate(min(str(nowdate()), str(fy_end))) - getdate(fy_start)).days + 1

    pnl = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "root_type": ("in", ["Expense", "Income"])},
        fields=["name", "root_type"],
        limit_page_length=40,
    )
    bank = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 0, "account_type": ("in", ["Bank", "Cash"])},
        pluck="name",
        limit_page_length=1,
    )
    if not pnl or not bank:
        frappe.throw(f"Company {company} needs at least one leaf P&L account and one Bank/Cash account")
    bank = bank[0]

    start = frappe.db.count("GL Entry", {"voucher_no": ("like", "SEED-%")})
    fields = [
        "name", "creation", "modified", "owner", "modified_by", "docstatus",
        "posting_date", "account", "account_currency", "debit", "credit",
        "debit_in_account_currency", "credit_in_account_currency", "against",
        "voucher_type", "voucher_no", "company", "fiscal_year", "is_opening",
        "is_cancelled", "remarks",
    ]
    ts = now()
    values = []
    for v in range(count // 2):
        i = start + v
        date = str(add_days(fy_start, i % span))
        acc = pnl[i % len(pnl)]
        amount = flt(50 + (i * 37) % 5000)
        voucher = f"SEED-{i:07d}"
        # Expense: debit P&L / credit bank. Income: debit bank / credit P&L.
        expense = acc.root_type == "Expense"
        for name_sfx, account, against, debit, credit in (
            ("A", acc.name if expense else bank, bank if expense else acc.name,
             amount, 0),
            ("B", bank if expense else acc.name, acc.name if expense else bank,
             0, amount),
        ):
            values.append((
                f"SEEDGL{i:07d}{name_sfx}", ts, ts, "Administrator", "Administrator", 1,
                date, account, currency, debit, credit,
                debit, credit, against,
                "Journal Entry", voucher, company, fy_name, "No",
                0, "peasforex perf seed",
            ))

    frappe.db.bulk_insert("GL Entry", fields=fields, values=values, chunk_size=5000)
    frappe.db.commit()
    print(f"Seeded {len(values)} GL Entries ({count // 2} vouchers) for {company}, {fy_start} +{span}d")


def clear():
    """Delete every seeded row."""
    _guard()
    n = frappe.db.count("GL Entry", {"voucher_no": ("like", "SEED-%")})
    frappe.db.delete("GL Entry", {"voucher_no": ("like", "SEED-%")})
    frappe.db.commit()
    print(f"Deleted {n} seeded GL Entries")
