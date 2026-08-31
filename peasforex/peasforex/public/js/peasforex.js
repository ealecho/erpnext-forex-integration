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

// Inject a "Rate Type" filter into the financial statement reports.
// Report configs are assigned to frappe.query_reports[name] when the report
// script loads, so trap the assignment and append our filter then.
(function() {
    const REPORTS = ["Balance Sheet", "Profit and Loss Statement", "Cash Flow"];
    const RATE_TYPE_FILTER = {
        fieldname: "rate_type",
        label: __("Rate Type"),
        fieldtype: "Select",
        options: [
            { value: "Closing", label: __("Closing Rate") },
            { value: "Monthly Average", label: __("Average Rate") },
            { value: "Manual", label: __("Manual Rate") },
            { value: "Spot", label: __("Ask Rate (Spot)") },
        ],
        default: "Closing",
    };

    frappe.provide("frappe.query_reports");

    REPORTS.forEach(function(name) {
        let config;
        Object.defineProperty(frappe.query_reports, name, {
            configurable: true,
            enumerable: true,
            get() {
                return config;
            },
            set(value) {
                config = value;
                const filters = config && config.filters;
                // filters array is shared across the three reports, so guard
                if (filters && !filters.some((f) => f.fieldname === "rate_type")) {
                    const idx = filters.findIndex((f) => f.fieldname === "periodicity");
                    filters.splice(idx >= 0 ? idx + 1 : filters.length, 0, RATE_TYPE_FILTER);
                }
            },
        });
    });
})();

// Add shortcut to navbar (optional)
$(document).ready(function() {
    // Add any global initialization here
});
