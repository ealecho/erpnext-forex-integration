// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

// Live rate resolution on Journal Entry.
//
// Source choice lives per-row on Journal Entry Account (custom_forex_rate_source).
// Lookup date is parent-level (custom_forex_rate_applied_date or posting_date).
// Mirrors peasforex.rates._apply_je_per_row.

frappe.ui.form.on("Journal Entry", {
    posting_date: function (frm) {
        if (!frm.doc.custom_forex_rate_applied_date) resolve_je_all_rows(frm);
    },
    custom_forex_rate_applied_date: resolve_je_all_rows,
    company: function (frm) {
        frm.__peasforex_company = null;
        resolve_je_all_rows(frm);
    },
});

frappe.ui.form.on("Journal Entry Account", {
    account_currency: resolve_je_row,
    custom_forex_rate_source: resolve_je_row,
});

function resolve_je_all_rows(frm) {
    (frm.doc.accounts || []).forEach((row) => resolve_je_row(frm, row.doctype, row.name));
}

function resolve_je_row(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.account_currency) return;

    const source = row.custom_forex_rate_source || "Auto";
    if (source === "Manual" || source === "Inherited") return;

    const as_of = frm.doc.custom_forex_rate_applied_date || frm.doc.posting_date;
    if (!as_of) return;

    peasforex.resolver.with_company_currency(frm, (company_currency) => {
        if (row.account_currency === company_currency) {
            frappe.model.set_value(cdt, cdn, "exchange_rate", 1);
            return;
        }
        peasforex.resolver.fetch(row.account_currency, company_currency, as_of, source, (res) => {
            frappe.model.set_value(cdt, cdn, "exchange_rate", res.rate);
            if (source === "Auto" && res.source) {
                frappe.model.set_value(cdt, cdn, "custom_forex_rate_source", res.source);
            }
        });
    });
}
