# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def before_save(doc, method):
    """
    Hook called before saving a Currency Exchange record.
    Can be used to validate or modify the exchange rate.
    """
    # Validate exchange rate is positive
    if doc.exchange_rate and doc.exchange_rate <= 0:
        frappe.throw(_("Exchange rate must be greater than 0"))


@frappe.whitelist()
def fetch_rate(from_currency, to_currency):
    """
    Fetch current exchange rate from Alpha Vantage.
    Called from Currency Exchange form.
    
    Args:
        from_currency: Source currency code
        to_currency: Target currency code
        
    Returns:
        dict: {exchange_rate: float} or {error: str}
    """
    from peasforex.api.alpha_vantage import AlphaVantageClient
    
    # Check if integration is enabled
    settings = frappe.get_single("Forex Settings")
    if not settings.enabled or not settings.api_key:
        return {
            "error": _("Forex integration is not configured. Please set up Forex Settings first.")
        }
    
    try:
        client = AlphaVantageClient()
        result = client.get_exchange_rate(from_currency, to_currency)
        
        if result.get("error"):
            return {"error": result.get("error")}
        
        return {
            "exchange_rate": result.get("exchange_rate"),
            "from_currency": from_currency,
            "to_currency": to_currency,
            "last_refreshed": result.get("last_refreshed")
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Fetch Exchange Rate Error")
        return {"error": str(e)}


@frappe.whitelist()
def get_latest_rate(from_currency, to_currency, rate_type="Spot"):
    """
    Get the latest exchange rate from Forex Rate Log.
    
    Args:
        from_currency: Source currency code
        to_currency: Target currency code
        rate_type: Type of rate (Spot, Closing, Monthly Average, Prudency)
        
    Returns:
        dict: Rate information or None
    """
    rate = frappe.db.get_value(
        "Forex Rate Log",
        filters={
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate_type": rate_type
        },
        fieldname=["exchange_rate", "rate_date", "synced_at"],
        order_by="rate_date desc",
        as_dict=True
    )
    
    return rate
