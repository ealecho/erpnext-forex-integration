// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

frappe.query_reports["Exchange Rate History"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            "reqd": 0
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 0
        },
        {
            "fieldname": "from_currency",
            "label": __("From Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "reqd": 0
        },
        {
            "fieldname": "to_currency",
            "label": __("To Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "reqd": 0
        },
        {
            "fieldname": "rate_type",
            "label": __("Rate Type"),
            "fieldtype": "Select",
            "options": "\nSpot\nClosing\nMonthly Average\nPrudency (High)\nPrudency (Low)",
            "reqd": 0
        }
    ],
    
    // Default to Dashboard view
    "initial_depth": 1,
    
    onload: function(report) {
        // Set default view to Chart/Dashboard
        report.page.add_inner_button(__("Refresh"), function() {
            report.refresh();
        });
    },
    
    // Chart configuration for dashboard view
    get_chart_data: function(columns, result) {
        if (!result || result.length === 0) {
            return null;
        }
        
        // Group data by currency pair
        let datasets = {};
        let labels = [];
        let label_set = new Set();
        
        result.forEach(row => {
            let pair = row.from_currency + " → " + row.to_currency;
            let date = row.rate_date;
            
            if (!datasets[pair]) {
                datasets[pair] = {};
            }
            datasets[pair][date] = row.exchange_rate;
            label_set.add(date);
        });
        
        // Sort labels (dates)
        labels = Array.from(label_set).sort();
        
        // Build chart datasets
        let chart_datasets = [];
        let colors = [
            "#7cd6fd", "#5e64ff", "#743ee2", "#ff5858", 
            "#ffa00a", "#feef72", "#28a745", "#17a2b8"
        ];
        let color_idx = 0;
        
        for (let pair in datasets) {
            let values = labels.map(date => datasets[pair][date] || 0);
            chart_datasets.push({
                name: pair,
                values: values,
                chartType: "line"
            });
            color_idx++;
        }
        
        return {
            data: {
                labels: labels,
                datasets: chart_datasets
            },
            type: "line",
            height: 300,
            colors: colors.slice(0, chart_datasets.length),
            axisOptions: {
                xIsSeries: true
            },
            lineOptions: {
                regionFill: 1,
                hideDots: 0
            },
            tooltipOptions: {
                formatTooltipX: d => frappe.datetime.str_to_user(d),
                formatTooltipY: d => d ? d.toFixed(6) : "0"
            }
        };
    },
    
    // Formatter for better display
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        if (column.fieldname === "exchange_rate" && data) {
            // Format rate with 6 decimal places
            let rate = parseFloat(data.exchange_rate);
            if (!isNaN(rate)) {
                value = `<span style="font-weight: bold;">${rate.toFixed(6)}</span>`;
            }
        }
        
        if (column.fieldname === "rate_type" && data) {
            // Color code rate types
            let colors = {
                "Spot": "#28a745",
                "Closing": "#007bff",
                "Monthly Average": "#6c757d",
                "Prudency (High)": "#dc3545",
                "Prudency (Low)": "#ffc107"
            };
            let color = colors[data.rate_type] || "#333";
            value = `<span style="color: ${color}; font-weight: 500;">${data.rate_type}</span>`;
        }
        
        return value;
    }
};
