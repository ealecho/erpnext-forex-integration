// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

// Live rate resolution on Payment Entry.
//
// Two slots (mirrors peasforex.rates.ADAPTERS["Payment Entry"]):
//   paid_from_account_currency -> source_exchange_rate
//   paid_to_account_currency   -> target_exchange_rate
// Both resolve from the same source choice + applied date.

frappe.ui.form.on("Payment Entry", {
    custom_forex_rate_source: resolve_pe_rates,
    custom_forex_rate_applied_date: resolve_pe_rates,
    posting_date: function (frm) {
        if (!frm.doc.custom_forex_rate_applied_date) resolve_pe_rates(frm);
    },
    paid_from_account_currency: resolve_pe_rates,
    paid_to_account_currency: resolve_pe_rates,
    company: function (frm) {
        frm.__peasforex_company = null;
        resolve_pe_rates(frm);
    },
});

function resolve_pe_rates(frm) {
    if (frm.doc.docstatus !== 0) return; // never dirty a submitted doc
    const source = frm.doc.custom_forex_rate_source || "Auto";
    if (source === "Manual" || source === "Inherited") return;

    const as_of = frm.doc.custom_forex_rate_applied_date || frm.doc.posting_date;
    if (!as_of) return;

    peasforex.resolver.with_company_currency(frm, (company_currency) => {
        const slots = [
            { from: frm.doc.paid_from_account_currency, rate_field: "source_exchange_rate" },
            { from: frm.doc.paid_to_account_currency,   rate_field: "target_exchange_rate" },
        ];
        let stamped = false;
        slots.forEach((slot) => {
            if (!slot.from || slot.from === company_currency) return;
            peasforex.resolver.fetch(slot.from, company_currency, as_of, source, (res) => {
                frm.set_value(slot.rate_field, res.rate);
                if (source === "Auto" && res.source && !stamped) {
                    stamped = true;
                    frm.set_value("custom_forex_rate_source", res.source);
                }
                if (!frm.doc.custom_forex_rate_applied_date) {
                    frm.set_value("custom_forex_rate_applied_date", as_of);
                }
            });
        });
    });
}
