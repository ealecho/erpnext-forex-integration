// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

// Extend Currency Exchange form to show source info
frappe.ui.form.on("Currency Exchange", {
    refresh: function(frm) {
        // Add button to fetch rate from Alpha Vantage
        if (!frm.is_new()) {
            return;
        }
        
        frm.add_custom_button(__("Fetch from Alpha Vantage"), function() {
            if (!frm.doc.from_currency || !frm.doc.to_currency) {
                frappe.msgprint(__("Please select From Currency and To Currency first"));
                return;
            }
            
            frappe.call({
                method: "peasforex.api.currency_exchange.fetch_rate",
                args: {
                    from_currency: frm.doc.from_currency,
                    to_currency: frm.doc.to_currency
                },
                freeze: true,
                freeze_message: __("Fetching exchange rate..."),
                callback: function(r) {
                    if (r.message) {
                        if (r.message.error) {
                            frappe.msgprint({
                                title: __("Error"),
                                indicator: "red",
                                message: r.message.error
                            });
                        } else {
                            frm.set_value("exchange_rate", r.message.exchange_rate);
                            frappe.show_alert({
                                message: __("Rate fetched: {0}", [r.message.exchange_rate.toFixed(6)]),
                                indicator: "green"
                            });
                        }
                    }
                }
            });
        });
    }
});
