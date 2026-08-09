// Default the row currency on PCR breakdown rows.
//
// PCR is single-currency by design (the company's default currency). Without
// this default, the row's `custom_currency` Link field falls through to
// Frappe's Global Defaults default_currency (GBP on this bench), so rows on
// a UGX PCR show as GBP and trip "currency mismatch" validators.
//
// Server-side `breakdown.default_breakdown_currency` is the source of truth
// at save time; this handler is for the form UX so users see the right
// currency the moment they add a row.

function pcr_default_row_currency(frm, cdt, cdn) {
    if (frm.doc.docstatus !== 0) return; // form_render fires on submitted docs too
    console.log("peasforex PCR: pcr_default_row_currency fired", cdt, cdn);
    let row = locals[cdt][cdn];
    peasforex.resolver.with_company_currency(frm, (cur) => {
        console.log("peasforex PCR: company_currency =", cur, "row currency =", row.custom_currency);
        if (cur && row.custom_currency !== cur) {
            frappe.model.set_value(cdt, cdn, "custom_currency", cur);
        }
    });
}

// Register on the CHILD doctype because grid.add_new_row triggers the
// `expense_breakdown_add` event keyed on the child doctype, not on PCR.
frappe.ui.form.on("Expense Breakdown", {
    expense_breakdown_add: function (frm, cdt, cdn) {
        if (frm.doctype !== "Petty Cash Request") return;
        pcr_default_row_currency(frm, cdt, cdn);
    },
    form_render: function (frm, cdt, cdn) {
        if (frm.doctype !== "Petty Cash Request") return;
        pcr_default_row_currency(frm, cdt, cdn);
    },
});
