// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

// Global namespace for Peasforex
frappe.provide("peasforex");

window.peasforex = {
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
    const REPORTS = [
        "Balance Sheet",
        "Profit and Loss Statement",
        "Cash Flow",
        "Consolidated Financial Statement",
    ];
    const RATE_TYPE_FILTER = {
        fieldname: "rate_type",
        label: __("Rate Type"),
        fieldtype: "Select",
        options: [
            { value: "Closing", label: __("Closing Rate") },
            { value: "Monthly Average", label: __("Average Rate") },
            { value: "Manual", label: __("Manual Rate") },
            { value: "Ask Rate", label: __("Ask Rate (Spot)") },
        ],
        default: "Closing",
    };
    // holds user-entered rates for Rate Type = Manual, as JSON
    // {"UGX": 0.000196, ...} meaning 1 UGX = 0.000196 <presentation currency>
    const MANUAL_RATES_FILTER = {
        fieldname: "manual_rates",
        label: __("Manual Rates"),
        fieldtype: "Data",
        hidden: 1,
    };

    frappe.provide("frappe.query_reports");

    function format_rate(rate) {
        if (rate == null) return __("n/a");
        return rate >= 1 ? format_number(rate, null, 2) : rate.toFixed(6);
    }

    // quote in whichever direction reads >= 1: "1 GBP = 5,128.21 UGX"
    // rather than the technically-equal "1 UGX = 0.000195 GBP"
    function rate_direction(row) {
        if (row.rate && row.rate < 1) {
            return { from: row.to_currency, to: row.from_currency, rate: 1 / row.rate, flipped: true };
        }
        return { from: row.from_currency, to: row.to_currency, rate: row.rate, flipped: false };
    }

    // "Applied Rates" strip between the filter form and the summary cards:
    // one pill per account currency showing the exact rate used to express
    // it in the presentation currency, per the selected Rate Type.
    function render_applied_rates() {
        const report = frappe.query_report;
        if (!report || !report.page) return;
        const $form = report.page.main.find(".page-form");
        let $box = report.page.main.find(".peasforex-applied-rates");
        const values = report.get_filter_values();
        if (!values.presentation_currency) {
            $box.remove();
            return;
        }
        // create the container synchronously so two overlapping render
        // passes can't each insert one (the strip showed up twice otherwise)
        if (!$box.length) {
            $box = $(
                '<div class="peasforex-applied-rates" style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:var(--padding-sm) var(--padding-md);border-bottom:1px solid var(--border-color);"></div>'
            ).insertAfter($form);
        } else if ($box.length > 1) {
            $box.slice(1).remove();
            $box = $box.first();
        }
        frappe.call({
            method: "peasforex.api.display_rates.get_display_rates",
            args: { filters: values, report_name: report.report_name },
        }).then((r) => {
            const msg = r.message || {};
            if (!(msg.rates || []).length) {
                $box.remove();
                return;
            }
            const label = `${__("Applied Rates")} · ${__(msg.rate_type)} · ${__("for period ending {0}", [frappe.datetime.str_to_user(msg.date)])}`;
            $box.empty().append(
                `<span style="font-weight:600;font-size:var(--text-md,13px);">${label}:</span>`
            );
            msg.rates.forEach((row) => {
                let title = __("Source: {0}", [row.source]);
                if (row.rate_date) {
                    title += ` · ${__("rate dated {0}", [frappe.datetime.str_to_user(row.rate_date)])}`;
                }
                const dir = rate_direction(row);
                const pill = $('<span class="indicator-pill blue" style="font-weight:600;"></span>')
                    .text(`1 ${dir.from} = ${format_rate(dir.rate)} ${dir.to}`)
                    .attr("title", title);
                $box.append(pill);
            });
            if (values.rate_type === "Manual") {
                const btn = $(
                    `<button class="btn btn-xs btn-default">${__("Set Rates")}</button>`
                ).on("click", () => prompt_manual_rates(report, msg.rates));
                $box.append(btn);
            }
        });
    }

    function prompt_manual_rates(report, rates) {
        // entry direction matches the strip; flipped values are inverted
        // back to "1 <account ccy> = x <presentation ccy>" on Apply
        const flipped = {};
        const fields = rates.map((row) => {
            const dir = rate_direction(row);
            flipped[row.from_currency] = dir.flipped;
            return {
                fieldtype: "Float",
                fieldname: row.from_currency,
                label: __("1 {0} in {1}", [dir.from, dir.to]),
                default: dir.rate,
                // system float precision (3) rounds small rates to 0.000 on
                // display AND on parse - 6 matches the Applied Rates strip
                precision: 6,
            };
        });
        frappe.prompt(fields, (entered) => {
            const clean = {};
            Object.entries(entered).forEach(([ccy, rate]) => {
                if (rate) clean[ccy] = flipped[ccy] ? 1 / rate : rate;
            });
            const filter = report.get_filter("manual_rates");
            if (filter) {
                filter.value = JSON.stringify(clean);
                try {
                    filter.set_input && filter.set_input(filter.value);
                } catch (e) {
                    // hidden control may have no input element
                }
            }
            report.refresh();
        }, __("Manual Applied Rates"), __("Apply"));
    }

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
                    // right before the Currency filter, so the pair sits
                    // together in every report (CFS has no periodicity)
                    const idx = filters.findIndex((f) => f.fieldname === "presentation_currency");
                    filters.splice(idx >= 0 ? idx : filters.length, 0, RATE_TYPE_FILTER);
                }
                if (filters && !filters.some((f) => f.fieldname === "manual_rates")) {
                    filters.push(MANUAL_RATES_FILTER);
                }
                // picking a company defaults the presentation currency to
                // that company's currency, which activates rate retrieval
                const company = filters && filters.find((f) => f.fieldname === "company");
                if (company && !company.__peasforex_currency_hook) {
                    company.__peasforex_currency_hook = true;
                    const orig_change = company.on_change;
                    company.on_change = function (report) {
                        if (orig_change) orig_change.call(this, report);
                        const comp = report.get_filter_value("company");
                        if (comp && !report.get_filter_value("presentation_currency")) {
                            frappe.db.get_value("Company", comp, "default_currency").then((r) => {
                                const ccy = r.message && r.message.default_currency;
                                if (ccy) report.set_filter_value("presentation_currency", ccy);
                            });
                        }
                        // df.on_change suppresses the default auto-refresh
                        if (!orig_change) report.refresh();
                    };
                }
                if (config) {
                    const orig = config.after_datatable_render;
                    config.after_datatable_render = function(datatable) {
                        render_applied_rates();
                        if (orig) orig.call(this, datatable);
                    };
                }
            },
        });
    });
})();

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
