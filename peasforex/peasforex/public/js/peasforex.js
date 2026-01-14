// Copyright (c) 2024, ERP Champions and contributors
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
