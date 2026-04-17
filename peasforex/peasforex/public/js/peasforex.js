// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

// Global namespace for Peasforex
frappe.provide("peasforex");

peasforex = {
    // Get current exchange rate
    get_exchange_rate: function(from_currency, to_currency, callback) {
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Currency Exchange",
                filters: {
                    from_currency: from_currency,
                    to_currency: to_currency
                },
                fields: ["exchange_rate", "date"],
                order_by: "date desc",
                limit_page_length: 1
            },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    callback(r.message[0].exchange_rate);
                } else {
                    callback(null);
                }
            }
        });
    },
    
    // Format exchange rate with proper precision
    format_rate: function(rate, precision) {
        precision = precision || 6;
        return rate ? rate.toFixed(precision) : "-";
    },
    
    // Open Forex Settings
    open_settings: function() {
        frappe.set_route("Form", "Forex Settings");
    },
    
    // Check if forex integration is enabled
    is_enabled: function(callback) {
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Forex Settings",
                fieldname: "enabled"
            },
            callback: function(r) {
                callback(r.message ? r.message.enabled : false);
            }
        });
    }
};

// Add shortcut to navbar (optional)
$(document).ready(function() {
    // Add any global initialization here
});


// ---------------------------------------------------------------------------
// Client-side rate resolver
//
// Why: server-side `before_validate` (peasforex.rates.apply) only runs on
// Save, but the native rate field is mandatory - users get stuck picking a
// source without a rate. The handlers in public/js/forex_resolver/* call
// the existing whitelisted resolver as soon as the user changes the source
// dropdown or the lookup date, so the document is save-ready immediately.
// ---------------------------------------------------------------------------

frappe.provide("peasforex.resolver");

peasforex.resolver.fetch = function (from_currency, to_currency, as_of_date, source, on_resolved) {
    if (!from_currency || !to_currency || !as_of_date) return;
    if (from_currency === to_currency) {
        on_resolved({ rate: 1, source: source || "Auto" });
        return;
    }
    frappe.call({
        method: "peasforex.rates.resolve_whitelisted",
        args: {
            from_currency: from_currency,
            to_currency: to_currency,
            as_of_date: as_of_date,
            source: source || "Auto",
        },
        callback: function (r) {
            if (r.message && r.message.rate) {
                on_resolved(r.message);
            }
        },
    });
};

peasforex.resolver.with_company_currency = function (frm, cb) {
    if (!frm.doc.company) return;
    if (frm.__peasforex_company === frm.doc.company && frm.__peasforex_company_currency) {
        cb(frm.__peasforex_company_currency);
        return;
    }
    frappe.db.get_value("Company", frm.doc.company, "default_currency").then((r) => {
        const ccy = r.message && r.message.default_currency;
        if (!ccy) return;
        frm.__peasforex_company = frm.doc.company;
        frm.__peasforex_company_currency = ccy;
        cb(ccy);
    });
};
