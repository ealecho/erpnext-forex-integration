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
    
    // Helper function to format date as "Jan 14" style
    formatShortDate: function(dateStr) {
        if (!dateStr) return '';
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        // Handle both YYYY-MM-DD string and date objects
        let date;
        if (typeof dateStr === 'string') {
            const parts = dateStr.split('-');
            if (parts.length === 3) {
                const month = months[parseInt(parts[1]) - 1];
                const day = parseInt(parts[2]);
                return `${month} ${day}`;
            }
            date = new Date(dateStr);
        } else {
            date = dateStr;
        }
        if (date instanceof Date && !isNaN(date)) {
            return `${months[date.getMonth()]} ${date.getDate()}`;
        }
        return dateStr;
    },
    
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
        
        const self = frappe.query_reports["Exchange Rate History"];
        
        // Group data by currency pair
        let datasets = {};
        let date_list = [];
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
        
        // Sort dates and keep original for data lookup
        date_list = Array.from(label_set).sort();
        
        // Format labels for display (short format like "Jan 14")
        let labels = date_list.map(d => self.formatShortDate(d));
        
        // Build chart datasets
        let chart_datasets = [];
        let colors = [
            "#7cd6fd", "#5e64ff", "#743ee2", "#ff5858", 
            "#ffa00a", "#feef72", "#28a745", "#17a2b8"
        ];
        let color_idx = 0;
        
        for (let pair in datasets) {
            let values = date_list.map(date => datasets[pair][date] || 0);
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
                formatTooltipX: (d, i) => {
                    // Show full date in tooltip
                    if (date_list && date_list[i]) {
                        return frappe.datetime.str_to_user(date_list[i]);
                    }
                    return d;
                },
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
