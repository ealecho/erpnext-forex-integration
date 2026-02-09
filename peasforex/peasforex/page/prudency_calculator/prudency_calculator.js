// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

frappe.pages['prudency-calculator'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Prudency Calculator',
        single_column: true
    });
    
    // Initialize the calculator
    new PrudencyCalculator(page);
};

class PrudencyCalculator {
    constructor(page) {
        this.page = page;
        this.wrapper = $(page.body);
        
        // State
        this.state = {
            grant_currency: 'GBP',
            local_currency: 'UGX',
            months: [],
            grand_average: null,
            has_sufficient_data: false,
            prudency_factor: 0.95,
            target_amount: 0
        };
        
        this.init();
    }
    
    init() {
        // Load HTML template
        this.wrapper.html(frappe.render_template('prudency_calculator'));
        
        // Setup fields
        this.setup_fields();
        
        // Load initial data
        this.load_rates();
    }
    
    setup_fields() {
        const me = this;
        
        // Grant Currency field
        this.grant_currency_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Link',
                fieldname: 'grant_currency',
                label: 'Grant Currency',
                options: 'Currency',
                default: 'GBP',
                change: function() {
                    me.state.grant_currency = this.get_value();
                }
            },
            parent: this.wrapper.find('.grant-currency-field'),
            render_input: true
        });
        this.grant_currency_field.set_value('GBP');
        
        // Local Currency field
        this.local_currency_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Link',
                fieldname: 'local_currency',
                label: 'Local Currency',
                options: 'Currency',
                default: 'UGX',
                change: function() {
                    me.state.local_currency = this.get_value();
                }
            },
            parent: this.wrapper.find('.local-currency-field'),
            render_input: true
        });
        this.local_currency_field.set_value('UGX');
        
        // Load Rates button
        this.load_btn = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Button',
                fieldname: 'load_rates',
                label: 'Load Rates',
                click: function() {
                    me.load_rates();
                }
            },
            parent: this.wrapper.find('.load-rates-btn'),
            render_input: true
        });
        
        // Prudency Factor field
        this.prudency_factor_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Float',
                fieldname: 'prudency_factor',
                label: 'Prudency Factor',
                default: 0.95,
                precision: 2,
                change: function() {
                    me.state.prudency_factor = parseFloat(this.get_value()) || 0.95;
                    me.recalculate();
                }
            },
            parent: this.wrapper.find('.prudency-factor-field'),
            render_input: true
        });
        this.prudency_factor_field.set_value(0.95);
        
        // Target Amount field
        this.target_amount_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Float',
                fieldname: 'target_amount',
                label: 'Target Local Currency Amount',
                precision: 2,
                change: function() {
                    me.state.target_amount = parseFloat(this.get_value()) || 0;
                    me.recalculate();
                }
            },
            parent: this.wrapper.find('.target-amount-field'),
            render_input: true
        });
        this.target_amount_field.set_value(0);
    }
    
    load_rates() {
        const me = this;
        const grant_currency = this.grant_currency_field.get_value();
        const local_currency = this.local_currency_field.get_value();
        
        if (!grant_currency || !local_currency) {
            frappe.show_alert({
                message: __('Please select both currencies'),
                indicator: 'orange'
            });
            return;
        }
        
        // Update pair label
        this.wrapper.find('.pair-label').text(`${grant_currency} → ${local_currency}`);
        this.wrapper.find('.grant-currency-label').text(grant_currency);
        
        frappe.call({
            method: 'peasforex.peasforex.page.prudency_calculator.prudency_calculator.get_monthly_averages',
            args: {
                grant_currency: grant_currency,
                local_currency: local_currency
            },
            freeze: true,
            freeze_message: __('Loading rates...'),
            callback: function(r) {
                if (r.message) {
                    me.update_state(r.message);
                    me.render_rates_table();
                    me.update_ui_state();
                    me.recalculate();
                }
            }
        });
    }
    
    update_state(data) {
        this.state.months = data.months || [];
        this.state.grand_average = data.grand_average;
        this.state.has_sufficient_data = data.has_sufficient_data;
        this.state.error = data.error;
    }
    
    render_rates_table() {
        const tbody = this.wrapper.find('.rates-table-body');
        tbody.empty();
        
        if (this.state.months.length === 0) {
            tbody.append(`
                <tr>
                    <td colspan="2" class="text-center text-muted">No data available</td>
                </tr>
            `);
            return;
        }
        
        // Render rows
        this.state.months.forEach(row => {
            tbody.append(`
                <tr>
                    <td>${row.month}</td>
                    <td style="text-align: right;">${row.exchange_rate.toFixed(2)}</td>
                </tr>
            `);
        });
        
        // Update grand average
        if (this.state.grand_average) {
            this.wrapper.find('.grand-average-value').text(this.state.grand_average.toFixed(2));
        } else {
            this.wrapper.find('.grand-average-value').text('-');
        }
    }
    
    update_ui_state() {
        const warning_div = this.wrapper.find('.insufficient-data-warning');
        const rates_table = this.wrapper.find('.rates-table-container');
        const calc_section = this.wrapper.find('.calculation-section');
        const result_section = this.wrapper.find('.result-section');
        
        if (this.state.has_sufficient_data) {
            // Hide warning, enable calculations
            warning_div.hide();
            rates_table.show();
            calc_section.removeClass('disabled-state');
            result_section.removeClass('disabled-state');
            
            // Enable input fields
            this.prudency_factor_field.$input.prop('disabled', false);
            this.target_amount_field.$input.prop('disabled', false);
        } else {
            // Show warning, disable calculations
            warning_div.show();
            warning_div.find('.warning-message').text(
                this.state.error || `Only ${this.state.months.length} months of data available. Need 6 months to calculate.`
            );
            
            // Still show table if we have some data
            if (this.state.months.length > 0) {
                rates_table.show();
            } else {
                rates_table.hide();
            }
            
            calc_section.addClass('disabled-state');
            result_section.addClass('disabled-state');
            
            // Disable input fields
            this.prudency_factor_field.$input.prop('disabled', true);
            this.target_amount_field.$input.prop('disabled', true);
            
            // Clear results
            this.wrapper.find('.prudency-rate-value').text('-');
            this.wrapper.find('.prudency-rate-formula').text('');
            this.wrapper.find('.expected-grant-value').text('-');
            this.wrapper.find('.expected-grant-formula').text('');
        }
    }
    
    recalculate() {
        if (!this.state.has_sufficient_data) {
            return;
        }
        
        const grand_average = this.state.grand_average;
        const prudency_factor = this.state.prudency_factor;
        const target_amount = this.state.target_amount;
        
        // Calculate prudency rate
        const prudency_rate = grand_average * prudency_factor;
        
        // Update prudency rate display
        this.wrapper.find('.prudency-rate-value').text(prudency_rate.toFixed(2));
        this.wrapper.find('.prudency-rate-formula').text(
            `(${grand_average.toFixed(2)} × ${prudency_factor})`
        );
        
        // Calculate expected grant amount
        if (target_amount > 0 && prudency_rate > 0) {
            const expected_grant = target_amount / prudency_rate;
            this.wrapper.find('.expected-grant-value').text(expected_grant.toFixed(2));
            this.wrapper.find('.expected-grant-formula').text(
                `(${target_amount.toFixed(2)} ÷ ${prudency_rate.toFixed(2)})`
            );
        } else {
            this.wrapper.find('.expected-grant-value').text('-');
            this.wrapper.find('.expected-grant-formula').text('Enter target amount above');
        }
    }
}
