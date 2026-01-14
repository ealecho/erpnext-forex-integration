# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def after_install():
    """
    Post-installation setup for Peasforex.
    Creates default currency pairs and initializes settings.
    """
    create_default_settings()
    frappe.db.commit()
    
    frappe.msgprint(
        _("Peasforex installed successfully! Please configure your API key in Forex Settings."),
        title=_("Installation Complete"),
        indicator="green"
    )


def before_uninstall():
    """
    Cleanup before uninstalling the app.
    """
    # Optionally clean up data
    pass


def create_default_settings():
    """
    Create default Forex Settings with predefined currency pairs.
    """
    # Check if settings already exist (for reinstall scenarios)
    if frappe.db.exists("Forex Settings", "Forex Settings"):
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
    
    # Ensure currencies exist
    ensure_currencies_exist()
    
    # Create the settings document
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
        settings.append("currency_pairs", {
            "from_currency": pair["from_currency"],
            "to_currency": pair["to_currency"],
            "enabled": pair["enabled"],
            "sync_spot_daily": 1,
            "sync_closing_monthly": 1,
            "sync_average_monthly": 1,
            "sync_prudency_monthly": 1
        })
    
    settings.insert(ignore_permissions=True)
    
    frappe.logger().info("Forex Settings created with default currency pairs")


def ensure_currencies_exist():
    """
    Ensure all required currencies exist in the system.
    """
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
        if not frappe.db.exists("Currency", currency["currency_name"]):
            frappe.logger().info(f"Creating currency: {currency['currency_name']}")
            doc = frappe.get_doc({
                "doctype": "Currency",
                "currency_name": currency["currency_name"],
                "enabled": 1,
                "symbol": currency["symbol"],
                "fraction": currency.get("fraction", ""),
                "fraction_units": currency.get("fraction_units", 100),
                "smallest_currency_fraction_value": currency.get("smallest_currency_fraction_value", 0.01)
            })
            doc.insert(ignore_permissions=True)
