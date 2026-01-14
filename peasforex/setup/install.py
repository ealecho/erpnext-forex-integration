# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _

# Module-level logger
logger = frappe.logger("peasforex", allow_site=True, file_count=5)


def log_debug(message, data=None):
    """Log debug message with optional data"""
    if data:
        logger.debug(f"[Peasforex Install] {message}: {data}")
    else:
        logger.debug(f"[Peasforex Install] {message}")


def log_info(message, data=None):
    """Log info message with optional data"""
    if data:
        logger.info(f"[Peasforex Install] {message}: {data}")
    else:
        logger.info(f"[Peasforex Install] {message}")


def log_error(message, data=None):
    """Log error message with optional data"""
    if data:
        logger.error(f"[Peasforex Install] {message}: {data}")
    else:
        logger.error(f"[Peasforex Install] {message}")


def after_install():
    """
    Post-installation setup for Peasforex.
    Creates default currency pairs and initializes settings.
    """
    log_info("=" * 50)
    log_info("Starting Peasforex after_install")
    log_info("=" * 50)
    
    try:
        create_default_settings()
        frappe.db.commit()
        log_info("Installation completed successfully")
        
        frappe.msgprint(
            _("Peasforex installed successfully! Please configure your API key in Forex Settings."),
            title=_("Installation Complete"),
            indicator="green"
        )
    except Exception as e:
        log_error(f"Installation failed: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Peasforex: Installation Error")
        raise


def before_uninstall():
    """
    Cleanup before uninstalling the app.
    """
    log_info("Starting Peasforex before_uninstall")
    # Optionally clean up data
    log_info("Uninstall cleanup completed")


def create_default_settings():
    """
    Create default Forex Settings with predefined currency pairs.
    """
    log_info("Creating default settings")
    
    # Check if settings already exist (for reinstall scenarios)
    if frappe.db.exists("Forex Settings", "Forex Settings"):
        log_info("Forex Settings already exists, skipping creation")
        return
    
    # Default currency pairs as specified
    default_pairs = [
        {"from_currency": "GBP", "to_currency": "UGX", "enabled": 1},
        {"from_currency": "GBP", "to_currency": "ZMW", "enabled": 1},
        {"from_currency": "GBP", "to_currency": "GHS", "enabled": 1},
        {"from_currency": "GBP", "to_currency": "USD", "enabled": 1},
        {"from_currency": "USD", "to_currency": "UGX", "enabled": 1},
        {"from_currency": "USD", "to_currency": "ZMW", "enabled": 1},
        {"from_currency": "DKK", "to_currency": "GBP", "enabled": 1},
        {"from_currency": "EUR", "to_currency": "GBP", "enabled": 1},
    ]
    
    log_info(f"Default pairs to create: {len(default_pairs)}")
    
    # Ensure currencies exist
    ensure_currencies_exist()
    
    # Create the settings document
    log_debug("Creating Forex Settings document")
    settings = frappe.get_doc({
        "doctype": "Forex Settings",
        "enabled": 0,  # Disabled by default until API key is set
        "create_bidirectional_rates": 1,
        "auto_update_currency_exchange": 1,
        "store_historical_data": 1,
        "apply_to_all_companies": 1,
        "currency_pairs": []
    })
    
    # Add default pairs
    for pair in default_pairs:
        log_debug(f"Adding currency pair: {pair['from_currency']}-{pair['to_currency']}")
        settings.append("currency_pairs", {
            "from_currency": pair["from_currency"],
            "to_currency": pair["to_currency"],
            "enabled": pair["enabled"],
            "sync_spot_daily": 1,
            "sync_closing_monthly": 1,
            "sync_average_monthly": 1,
            "sync_prudency_monthly": 1
        })
    
    try:
        settings.insert(ignore_permissions=True)
        log_info(f"Forex Settings created with {len(default_pairs)} currency pairs")
    except Exception as e:
        log_error(f"Failed to create Forex Settings: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Peasforex: Settings Creation Error")
        raise


def ensure_currencies_exist():
    """
    Ensure all required currencies exist in the system.
    """
    log_info("Ensuring required currencies exist")
    
    required_currencies = [
        {"currency_name": "GBP", "symbol": "£", "fraction": "Pence", "fraction_units": 100, "smallest_currency_fraction_value": 0.01},
        {"currency_name": "USD", "symbol": "$", "fraction": "Cents", "fraction_units": 100, "smallest_currency_fraction_value": 0.01},
        {"currency_name": "EUR", "symbol": "€", "fraction": "Cents", "fraction_units": 100, "smallest_currency_fraction_value": 0.01},
        {"currency_name": "UGX", "symbol": "USh", "fraction": "Cents", "fraction_units": 100, "smallest_currency_fraction_value": 1},
        {"currency_name": "ZMW", "symbol": "ZK", "fraction": "Ngwee", "fraction_units": 100, "smallest_currency_fraction_value": 0.01},
        {"currency_name": "GHS", "symbol": "GH₵", "fraction": "Pesewas", "fraction_units": 100, "smallest_currency_fraction_value": 0.01},
        {"currency_name": "DKK", "symbol": "kr", "fraction": "Øre", "fraction_units": 100, "smallest_currency_fraction_value": 0.01},
    ]
    
    for currency in required_currencies:
        currency_name = currency["currency_name"]
        if not frappe.db.exists("Currency", currency_name):
            log_info(f"Creating currency: {currency_name}")
            try:
                doc = frappe.get_doc({
                    "doctype": "Currency",
                    "currency_name": currency_name,
                    "enabled": 1,
                    "symbol": currency["symbol"],
                    "fraction": currency.get("fraction", ""),
                    "fraction_units": currency.get("fraction_units", 100),
                    "smallest_currency_fraction_value": currency.get("smallest_currency_fraction_value", 0.01)
                })
                doc.insert(ignore_permissions=True)
                log_debug(f"Currency {currency_name} created successfully")
            except Exception as e:
                log_error(f"Failed to create currency {currency_name}: {str(e)}")
                # Don't raise - currency might already exist with different case or similar
        else:
            log_debug(f"Currency {currency_name} already exists")
    
    log_info("Currency check completed")
