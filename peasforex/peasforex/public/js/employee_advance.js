// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

// Live rate resolution on Employee Advance.
//
// PEAS policy (mirrors peasforex.rates.apply): at advance-request time the
// actual rate is unknown, so the server forces Ask Rate + posting_date
// regardless of what the user picked. We do the same here so the rate that
// shows in the form is the rate that will save.

frappe.ui.form.on("Employee Advance", {
    custom_is_multicurrency: function (frm) {
        if (frm.doc.custom_is_multicurrency) resolve_advance_rate(frm);
        cascade_breakdown_currency(frm);
    },
    custom_e_a_currency: function (frm) {
        resolve_advance_rate(frm);
        cascade_breakdown_currency(frm);
    },
    posting_date: resolve_advance_rate,
    company: function (frm) {
        frm.__peasforex_company = null;
        resolve_advance_rate(frm);
        cascade_breakdown_currency(frm);
    },
    custom_forex_rate_source: resolve_advance_rate,
    custom_forex_rate_applied_date: resolve_advance_rate,
});

// Row-add + form_render handlers live on the CHILD doctype 'Expense
// Breakdown' because grid.add_new_row triggers the event keyed on child
// doctype (`frappe.ui.form.handlers['Expense Breakdown']['custom_expenses_add']`),
// not the parent. The `frm.doctype` guard scopes the handler to EA-parented
// Expense Breakdown rows so it doesn't double-fire on PCR forms (which
// have their own handler in petty_cash_request.js).
frappe.ui.form.on("Expense Breakdown", {
    custom_expenses_add: function (frm, cdt, cdn) {
        if (frm.doctype !== "Employee Advance") return;
        default_breakdown_row_currency(frm, cdt, cdn);
    },
    form_render: function (frm, cdt, cdn) {
        if (frm.doctype !== "Employee Advance") return;
        default_breakdown_row_currency(frm, cdt, cdn);
    },
});

function resolve_advance_rate(frm) {
    if (!frm.doc.custom_is_multicurrency) return;
    if (!frm.doc.custom_e_a_currency || !frm.doc.posting_date) return;

    peasforex.resolver.with_company_currency(frm, (company_currency) => {
        peasforex.resolver.fetch(
            frm.doc.custom_e_a_currency,
            company_currency,
            frm.doc.posting_date,
            "Ask Rate",
            (res) => {
                frm.set_value("custom_advance_exchange_rate", res.rate);
                frm.set_value("custom_forex_rate_source", "Ask Rate");
                frm.set_value("custom_forex_rate_applied_date", frm.doc.posting_date);
            }
        );
    });
}

function ea_parent_currency(frm, cb) {
    // Multi-currency advance: row currency = the advance currency the user
    // picked. Single-currency: row currency = company default currency.
    if (frm.doc.custom_is_multicurrency && frm.doc.custom_e_a_currency) {
        cb(frm.doc.custom_e_a_currency);
        return;
    }
    peasforex.resolver.with_company_currency(frm, cb);
}

function default_breakdown_row_currency(frm, cdt, cdn) {
    console.log("peasforex EA: default_breakdown_row_currency fired", cdt, cdn);
    let row = locals[cdt][cdn];
    ea_parent_currency(frm, (cur) => {
        console.log("peasforex EA: parent currency =", cur, "row currency =", row.custom_currency);
        if (cur && row.custom_currency !== cur) {
            frappe.model.set_value(cdt, cdn, "custom_currency", cur);
        }
    });
}

function cascade_breakdown_currency(frm) {
    // Parent currency changed (multicurrency toggle, currency picker, or
    // company change). Refresh every breakdown row to match the new parent
    // currency, otherwise the user is left staring at stale GBP rows.
    if (!(frm.doc.custom_expenses || []).length) return;
    ea_parent_currency(frm, (cur) => {
        if (!cur) return;
        (frm.doc.custom_expenses || []).forEach((row) => {
            if (row.custom_currency !== cur) {
                frappe.model.set_value(row.doctype, row.name, "custom_currency", cur);
            }
        });
    });
}
