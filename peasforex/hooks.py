app_name = "peasforex"
app_title = "Peasforex"
app_publisher = "ERP Champions"
app_description = "Alpha Vantage Forex Integration for ERPNext - Automatic currency exchange rate syncing"
app_email = "info@erpchampions.com"
app_license = "MIT"
app_version = "0.0.1"

# Required Apps
required_apps = ["frappe", "erpnext"]

# Include JS in Desk - a .bundle.js entry gets a content-hashed filename
# per bench build, so browsers pick up new code without cache-clearing
app_include_js = "peasforex.bundle.js"

# Include CSS in Desk
# app_include_css = "/assets/peasforex/css/peasforex.css"

# DocType JS
doctype_js = {
    "Currency Exchange": "peasforex/public/js/currency_exchange.js",
    # Live forex rate resolution - populates the native rate field client-side
    # so users aren't blocked by the mandatory check while picking a source.
    "Employee Advance": "peasforex/public/js/employee_advance.js",
    "Petty Cash Request": "peasforex/public/js/petty_cash_request.js",
    "Payment Entry": "peasforex/public/js/payment_entry.js",
    "Journal Entry": "peasforex/public/js/journal_entry.js",
}

# Fixtures - export these doctypes with the app
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [["module", "=", "Peasforex"]]
    }
]

# Scheduled Tasks
scheduler_events = {
    # Daily sync at 6:00 AM server time
    "cron": {
        "0 6 * * *": [
            "peasforex.tasks.sync_forex.sync_daily_spot_rates"
        ],
        # Monthly sync on the 1st at 7:00 AM
        "0 7 1 * *": [
            "peasforex.tasks.sync_forex.sync_monthly_rates"
        ]
    },
    # Fallback daily task
    "daily": [
        "peasforex.tasks.sync_forex.check_and_sync_daily"
    ]
}

# Document Events
doc_events = {
    "Currency Exchange": {
        "before_save": "peasforex.api.currency_exchange.before_save"
    },
    # Forex rate resolution on transaction doctypes. Each hook populates the
    # native rate field(s) based on custom_forex_rate_source + applied_date.
    # See peasforex/rates.py for resolution semantics (Auto: Spot→Ask).
    "Purchase Invoice": {
        "before_validate": "peasforex.rates.apply"
    },
    "Sales Invoice": {
        "before_validate": "peasforex.rates.apply"
    },
    "Employee Advance": {
        "before_validate": [
            "peasforex.breakdown.default_breakdown_currency",
            "peasforex.rates.apply",
            # After rates.apply: rows inherit the resolved advance rate.
            "peasforex.breakdown.stamp_breakdown_rates",
        ]
    },
    "Petty Cash Request": {
        "before_validate": "peasforex.breakdown.default_breakdown_currency"
    },
    "Payment Entry": {
        "before_validate": "peasforex.rates.apply"
    },
    "Journal Entry": {
        "before_validate": "peasforex.rates.apply"
    },
    # Expense Claim (displayed as "Accountability" in the PEAS UI when
    # custom_claim_type = "Advance Accountability") is handled entirely
    # by peas_hr's "Expense Claim Scripts V3" client script: per-row
    # currency inheritance from parent.custom_currency, and per-row rate
    # lookup via peasforex.rates.resolve_whitelisted. No server hook here.
}

# Jinja Environment
# jinja = {
#     "methods": [],
#     "filters": []
# }

# Installation hooks
after_install = "peasforex.setup.install.after_install"
before_uninstall = "peasforex.setup.install.before_uninstall"

# Desk Notifications
# notification_config = "peasforex.notifications.get_notification_config"

# Permissions evaluated in scripted ways
# permission_query_conditions = {}
# has_permission = {}

# Override whitelisted methods
# override_whitelisted_methods = {}

# Override DocType class
# override_doctype_class = {}

# Exempt linked doctypes from being cancelled on cancel of main doctype
# auto_cancel_exempted_doctypes = []
