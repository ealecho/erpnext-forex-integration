app_name = "peasforex"
app_title = "Peasforex"
app_publisher = "ERP Champions"
app_description = "Alpha Vantage Forex Integration for ERPNext - Automatic currency exchange rate syncing"
app_email = "info@erpchampions.com"
app_license = "MIT"
app_version = "0.0.1"

# Required Apps
required_apps = ["frappe", "erpnext"]

# Include JS in Desk
app_include_js = "/assets/peasforex/js/peasforex.js"

# Include CSS in Desk
# app_include_css = "/assets/peasforex/css/peasforex.css"

# DocType JS
doctype_js = {
    "Currency Exchange": "peasforex/public/js/currency_exchange.js"
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
    "Employee Advance": {
        "before_validate": "peasforex.rates.apply"
    },
    "Payment Entry": {
        "before_validate": "peasforex.rates.apply"
    },
    "Journal Entry": {
        "before_validate": "peasforex.rates.apply"
    },
    # NOTE: "Accountability" hook is intentionally not registered - the
    # distribution_csf app that owns it isn't installed on every PEAS site.
    # Re-enable here (and restore custom_field fixture entries) when
    # distribution_csf is present. The rates.py ADAPTERS entry stays so
    # the resolver works once the hook is wired.
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
