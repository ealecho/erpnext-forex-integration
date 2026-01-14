// Copyright (c) 2024, ERP Champions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Forex Settings", {
    refresh: function(frm) {
        // Add custom buttons
        if (frm.doc.enabled && frm.doc.api_key) {
            frm.add_custom_button(__("Test Connection"), function() {
                frm.trigger("test_connection");
            });
            
            frm.add_custom_button(__("Sync Daily Rates"), function() {
                frm.trigger("sync_now");
            }, __("Sync Actions"));
            
            frm.add_custom_button(__("Sync Monthly Rates"), function() {
                frm.trigger("sync_monthly_now");
            }, __("Sync Actions"));
            
            frm.add_custom_button(__("Backfill 2 Months"), function() {
                frm.trigger("backfill_historical");
            }, __("Sync Actions"));
        }
        
        // Add default currency pairs button
        frm.add_custom_button(__("Add Default Pairs"), function() {
            frm.trigger("add_default_pairs");
        }, __("Setup"));
        
        // Render sync status
        frm.trigger("render_sync_status");
    },
    
    test_connection: function(frm) {
        frappe.call({
            method: "test_connection",
            doc: frm.doc,
            freeze: true,
            freeze_message: __("Testing connection..."),
            callback: function(r) {
                if (r.message) {
                    if (r.message.status === "success") {
                        frappe.msgprint({
                            title: __("Success"),
                            indicator: "green",
                            message: __("Connection successful! Sample rate: {0} {1} = {2} {3}", 
                                [1, r.message.from_currency, r.message.sample_rate, r.message.to_currency])
                        });
                    } else {
                        frappe.msgprint({
                            title: __("Error"),
                            indicator: "red",
                            message: r.message.message
                        });
                    }
                }
            }
        });
    },
    
    sync_now: function(frm) {
        frappe.confirm(
            __("This will sync daily spot rates for all enabled currency pairs. Continue?"),
            function() {
                frappe.call({
                    method: "sync_now",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("Queuing sync..."),
                    callback: function(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: r.message.message,
                                indicator: r.message.status === "queued" ? "green" : "red"
                            });
                        }
                    }
                });
            }
        );
    },
    
    sync_monthly_now: function(frm) {
        frappe.confirm(
            __("This will sync monthly rates (Closing, Average, Prudency) for the previous month. Continue?"),
            function() {
                frappe.call({
                    method: "sync_monthly_now",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("Queuing monthly sync..."),
                    callback: function(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: r.message.message,
                                indicator: r.message.status === "queued" ? "green" : "red"
                            });
                        }
                    }
                });
            }
        );
    },
    
    backfill_historical: function(frm) {
        frappe.prompt([
            {
                label: __("Number of Months"),
                fieldname: "months",
                fieldtype: "Int",
                default: 2,
                description: __("Number of months to backfill historical data")
            }
        ], function(values) {
            frappe.call({
                method: "backfill_historical",
                doc: frm.doc,
                args: {
                    months: values.months
                },
                freeze: true,
                freeze_message: __("Queuing backfill..."),
                callback: function(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: r.message.status === "queued" ? "green" : "red"
                        });
                    }
                }
            });
        }, __("Backfill Historical Data"), __("Start Backfill"));
    },
    
    add_default_pairs: function(frm) {
        // Default currency pairs as specified
        const default_pairs = [
            { from_currency: "GBP", to_currency: "UGX" },
            { from_currency: "GBP", to_currency: "ZMW" },
            { from_currency: "GBP", to_currency: "GHS" },
            { from_currency: "GBP", to_currency: "USD" },
            { from_currency: "USD", to_currency: "UGX" },
            { from_currency: "USD", to_currency: "ZMW" },
            { from_currency: "DKK", to_currency: "GBP" },
            { from_currency: "EUR", to_currency: "GBP" }
        ];
        
        // Get existing pairs
        const existing_pairs = new Set();
        (frm.doc.currency_pairs || []).forEach(row => {
            existing_pairs.add(`${row.from_currency}-${row.to_currency}`);
        });
        
        // Add missing pairs
        let added = 0;
        default_pairs.forEach(pair => {
            const pair_key = `${pair.from_currency}-${pair.to_currency}`;
            if (!existing_pairs.has(pair_key)) {
                let row = frm.add_child("currency_pairs");
                row.from_currency = pair.from_currency;
                row.to_currency = pair.to_currency;
                row.enabled = 1;
                row.sync_spot_daily = 1;
                row.sync_closing_monthly = 1;
                row.sync_average_monthly = 1;
                row.sync_prudency_monthly = 1;
                added++;
            }
        });
        
        if (added > 0) {
            frm.refresh_field("currency_pairs");
            frappe.show_alert({
                message: __("Added {0} default currency pairs", [added]),
                indicator: "green"
            });
        } else {
            frappe.show_alert({
                message: __("All default currency pairs already exist"),
                indicator: "blue"
            });
        }
    },
    
    render_sync_status: function(frm) {
        // Fetch recent sync logs
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Forex Sync Log",
                filters: {},
                fields: ["name", "sync_time", "sync_type", "currency_pair", "status", "exchange_rate", "error_message"],
                order_by: "sync_time desc",
                limit_page_length: 10
            },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    let html = `
                        <div class="recent-syncs">
                            <h6>Recent Sync Activity</h6>
                            <table class="table table-bordered table-sm">
                                <thead>
                                    <tr>
                                        <th>Time</th>
                                        <th>Type</th>
                                        <th>Pair</th>
                                        <th>Status</th>
                                        <th>Rate</th>
                                    </tr>
                                </thead>
                                <tbody>
                    `;
                    
                    r.message.forEach(log => {
                        const status_class = log.status === "Success" ? "text-success" : "text-danger";
                        html += `
                            <tr>
                                <td>${frappe.datetime.prettyDate(log.sync_time)}</td>
                                <td>${log.sync_type || "-"}</td>
                                <td>${log.currency_pair || "-"}</td>
                                <td class="${status_class}">${log.status}</td>
                                <td>${log.exchange_rate ? log.exchange_rate.toFixed(6) : "-"}</td>
                            </tr>
                        `;
                    });
                    
                    html += `
                                </tbody>
                            </table>
                            <a href="/app/forex-sync-log" class="btn btn-xs btn-default">View All Logs</a>
                        </div>
                    `;
                    
                    frm.fields_dict.sync_status_html.$wrapper.html(html);
                } else {
                    frm.fields_dict.sync_status_html.$wrapper.html(`
                        <div class="text-muted">
                            No sync activity yet. Use the sync buttons above to start syncing rates.
                        </div>
                    `);
                }
            }
        });
    }
});
