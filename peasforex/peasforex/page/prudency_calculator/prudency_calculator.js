// Copyright (c) 2026, ERP Champions and contributors
// For license information, please see license.txt

frappe.pages['prudency-calculator'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'PEAS Prudency Calculator',
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
            mode: 'proposal', // 'proposal' or 'expense'
            grant_currency: 'GBP',
            local_currency: 'UGX',
            as_of_month: null, // Will be set in setup_fields
            months: [],
            grand_average: null,
            has_sufficient_data: false,
            // Proposal mode state
            proposal_prudency_factor: 0.95,
            proposal_target_amount: 0,
            // Expense planning mode state
            expense_prudency_factor: 1.05,
            expense_grant_amount: 0
        };
        
        this.init();
    }
    
    init() {
        // Load HTML template
        this.wrapper.html(frappe.render_template('prudency_calculator'));
        
        // Setup fields
        this.setup_fields();
        
        // Setup tab switching
        this.setup_tabs();
        
        // Load initial data
        this.load_rates();
    }
    
    setup_tabs() {
        const me = this;
        
        this.wrapper.find('.tab-btn').on('click', function() {
            const mode = $(this).data('mode');
            me.switch_mode(mode);
        });
    }
    
    switch_mode(mode) {
        this.state.mode = mode;
        
        // Update tab buttons
        this.wrapper.find('.tab-btn').removeClass('active');
        this.wrapper.find(`.tab-btn[data-mode="${mode}"]`).addClass('active');
        
        // Show/hide content sections
        if (mode === 'proposal') {
            this.wrapper.find('.proposal-mode-content').show();
            this.wrapper.find('.expense-mode-content').hide();
            // Reset to default prudency factor
            this.state.proposal_prudency_factor = 0.95;
            this.proposal_prudency_factor_field.set_value(0.95);
            this.recalculate_proposal();
        } else {
            this.wrapper.find('.proposal-mode-content').hide();
            this.wrapper.find('.expense-mode-content').show();
            // Reset to default prudency factor
            this.state.expense_prudency_factor = 1.05;
            this.expense_prudency_factor_field.set_value(1.05);
            this.recalculate_expense();
        }
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
        
        // As of Month field (default to current month)
        const today = new Date();
        const currentMonth = today.toISOString().slice(0, 7) + '-01'; // Format: YYYY-MM-01
        
        this.as_of_month_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Date',
                fieldname: 'as_of_month',
                label: 'As of Month',
                default: currentMonth,
                change: function() {
                    me.state.as_of_month = this.get_value();
                }
            },
            parent: this.wrapper.find('.as-of-month-field'),
            render_input: true
        });
        this.as_of_month_field.set_value(currentMonth);
        this.state.as_of_month = currentMonth;
        
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
        
        // === PROPOSAL MODE FIELDS ===
        
        // Proposal Prudency Factor field
        this.proposal_prudency_factor_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Float',
                fieldname: 'proposal_prudency_factor',
                label: 'Prudency Factor',
                default: 0.95,
                precision: 2,
                change: function() {
                    me.state.proposal_prudency_factor = parseFloat(this.get_value()) || 0.95;
                    me.recalculate_proposal();
                }
            },
            parent: this.wrapper.find('.proposal-prudency-factor-field'),
            render_input: true
        });
        this.proposal_prudency_factor_field.set_value(0.95);
        
        // Proposal Target Amount field
        this.proposal_target_amount_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Float',
                fieldname: 'proposal_target_amount',
                label: 'Target Local Currency Amount',
                precision: 2,
                change: function() {
                    me.state.proposal_target_amount = parseFloat(this.get_value()) || 0;
                    me.recalculate_proposal();
                }
            },
            parent: this.wrapper.find('.proposal-target-amount-field'),
            render_input: true
        });
        this.proposal_target_amount_field.set_value(0);
        
        // === EXPENSE PLANNING MODE FIELDS ===
        
        // Expense Prudency Factor field
        this.expense_prudency_factor_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Float',
                fieldname: 'expense_prudency_factor',
                label: 'Prudency Factor',
                default: 1.05,
                precision: 2,
                change: function() {
                    me.state.expense_prudency_factor = parseFloat(this.get_value()) || 1.05;
                    me.recalculate_expense();
                }
            },
            parent: this.wrapper.find('.expense-prudency-factor-field'),
            render_input: true
        });
        this.expense_prudency_factor_field.set_value(1.05);
        
        // Expense Grant Amount field
        this.expense_grant_amount_field = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Float',
                fieldname: 'expense_grant_amount',
                label: 'Grant Amount',
                precision: 2,
                change: function() {
                    me.state.expense_grant_amount = parseFloat(this.get_value()) || 0;
                    me.recalculate_expense();
                }
            },
            parent: this.wrapper.find('.expense-grant-amount-field'),
            render_input: true
        });
        this.expense_grant_amount_field.set_value(0);
    }
    
    // Format number with commas and 2 decimal places
    formatNumber(num) {
        return num.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }
    
    // Update input field labels with currency indicators
    update_field_labels(grant_currency, local_currency) {
        // Update Proposal Mode: Target Local Currency Amount field
        this.proposal_target_amount_field.df.label = `Target Local Currency Amount (${local_currency})`;
        this.proposal_target_amount_field.set_label(`Target Local Currency Amount (${local_currency})`);
        
        // Update Expense Planning Mode: Grant Amount field
        this.expense_grant_amount_field.df.label = `Grant Amount (${grant_currency})`;
        this.expense_grant_amount_field.set_label(`Grant Amount (${grant_currency})`);
    }
    
    load_rates() {
        const me = this;
        const grant_currency = this.grant_currency_field.get_value();
        const local_currency = this.local_currency_field.get_value();
        const as_of_month = this.as_of_month_field.get_value();
        
        if (!grant_currency || !local_currency) {
            frappe.show_alert({
                message: __('Please select both currencies'),
                indicator: 'orange'
            });
            return;
        }
        
        if (!as_of_month) {
            frappe.show_alert({
                message: __('Please select a month'),
                indicator: 'orange'
            });
            return;
        }
        
        // Update pair label and currency labels
        this.wrapper.find('.pair-label').text(`${grant_currency} → ${local_currency}`);
        this.wrapper.find('.grant-currency-label').text(grant_currency);
        this.wrapper.find('.local-currency-label').text(local_currency);
        
        // Update input field labels with currency indicators
        this.update_field_labels(grant_currency, local_currency);
        
        frappe.call({
            method: 'peasforex.peasforex.page.prudency_calculator.prudency_calculator.get_monthly_averages',
            args: {
                grant_currency: grant_currency,
                local_currency: local_currency,
                as_of_date: as_of_month
            },
            freeze: true,
            freeze_message: __('Loading rates...'),
            callback: function(r) {
                if (r.message) {
                    me.update_state(r.message);
                    me.render_rates_table();
                    me.update_date_range_label(r.message);
                    me.update_ui_state();
                    me.recalculate();
                }
            }
        });
    }
    
    update_date_range_label(data) {
        const date_range_label = this.wrapper.find('.date-range-label');
        if (data.months && data.months.length > 0) {
            const start_month = data.months[data.months.length - 1].month;
            const end_month = data.months[0].month;
            date_range_label.text(`${start_month} - ${end_month}`);
        } else {
            date_range_label.text('');
        }
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
        const calc_sections = this.wrapper.find('.calculation-section');
        const result_sections = this.wrapper.find('.result-section');
        
        if (this.state.has_sufficient_data) {
            // Hide warning, enable calculations
            warning_div.addClass('hidden');
            rates_table.show();
            calc_sections.removeClass('disabled-state');
            result_sections.removeClass('disabled-state');
            
            // Enable input fields
            this.proposal_prudency_factor_field.$input.prop('disabled', false);
            this.proposal_target_amount_field.$input.prop('disabled', false);
            this.expense_prudency_factor_field.$input.prop('disabled', false);
            this.expense_grant_amount_field.$input.prop('disabled', false);
        } else {
            // Show warning, disable calculations
            warning_div.removeClass('hidden');
            warning_div.find('.warning-message').text(
                this.state.error || `Only ${this.state.months.length} months of data available. Need 6 months to calculate.`
            );
            
            // Still show table if we have some data
            if (this.state.months.length > 0) {
                rates_table.show();
            } else {
                rates_table.hide();
            }
            
            calc_sections.addClass('disabled-state');
            result_sections.addClass('disabled-state');
            
            // Disable input fields
            this.proposal_prudency_factor_field.$input.prop('disabled', true);
            this.proposal_target_amount_field.$input.prop('disabled', true);
            this.expense_prudency_factor_field.$input.prop('disabled', true);
            this.expense_grant_amount_field.$input.prop('disabled', true);
            
            // Clear results
            this.clear_results();
        }
    }
    
    clear_results() {
        // Proposal mode
        this.wrapper.find('.proposal-prudency-rate-value').text('-');
        this.wrapper.find('.proposal-prudency-rate-formula').text('');
        this.wrapper.find('.proposal-expected-value').text('-');
        this.wrapper.find('.proposal-expected-formula').text('');
        
        // Expense mode
        this.wrapper.find('.expense-prudency-rate-value').text('-');
        this.wrapper.find('.expense-prudency-rate-formula').text('');
        this.wrapper.find('.expense-expected-value').text('-');
        this.wrapper.find('.expense-expected-formula').text('');
    }
    
    recalculate() {
        // Recalculate based on current mode
        if (this.state.mode === 'proposal') {
            this.recalculate_proposal();
        } else {
            this.recalculate_expense();
        }
    }
    
    recalculate_proposal() {
        if (!this.state.has_sufficient_data) {
            return;
        }
        
        const grand_average = this.state.grand_average;
        const prudency_factor = this.state.proposal_prudency_factor;
        const target_amount = this.state.proposal_target_amount;
        
        // Calculate prudency rate
        const prudency_rate = grand_average * prudency_factor;
        
        // Update prudency rate display
        this.wrapper.find('.proposal-prudency-rate-value').text(prudency_rate.toFixed(2));
        this.wrapper.find('.proposal-prudency-rate-formula').text(
            `(${grand_average.toFixed(2)} × ${prudency_factor})`
        );
        
        // Calculate expected grant amount: Target Local / Prudency Rate
        if (target_amount > 0 && prudency_rate > 0) {
            const expected_grant = target_amount / prudency_rate;
            this.wrapper.find('.proposal-expected-value').text(this.formatNumber(expected_grant));
            this.wrapper.find('.proposal-expected-formula').text(
                `(${this.formatNumber(target_amount)} ÷ ${this.formatNumber(prudency_rate)})`
            );
        } else {
            this.wrapper.find('.proposal-expected-value').text('-');
            this.wrapper.find('.proposal-expected-formula').text('Enter target amount above');
        }
    }
    
    recalculate_expense() {
        if (!this.state.has_sufficient_data) {
            return;
        }
        
        const grand_average = this.state.grand_average;
        const prudency_factor = this.state.expense_prudency_factor;
        const grant_amount = this.state.expense_grant_amount;
        
        // Calculate prudency rate
        const prudency_rate = grand_average * prudency_factor;
        
        // Update prudency rate display
        this.wrapper.find('.expense-prudency-rate-value').text(prudency_rate.toFixed(2));
        this.wrapper.find('.expense-prudency-rate-formula').text(
            `(${grand_average.toFixed(2)} × ${prudency_factor})`
        );
        
        // Calculate expected local amount: Grant Amount × Prudency Rate
        if (grant_amount > 0 && prudency_rate > 0) {
            const expected_local = grant_amount * prudency_rate;
            this.wrapper.find('.expense-expected-value').text(this.formatNumber(expected_local));
            this.wrapper.find('.expense-expected-formula').text(
                `(${this.formatNumber(grant_amount)} × ${this.formatNumber(prudency_rate)})`
            );
        } else {
            this.wrapper.find('.expense-expected-value').text('-');
            this.wrapper.find('.expense-expected-formula').text('Enter grant amount above');
        }
    }
}
