# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ForexSettings(Document):
    def validate(self):
        if self.enabled and not self.api_key:
            frappe.throw(_("API Key is required when integration is enabled"))
        
        if not self.currency_pairs:
            frappe.throw(_("At least one currency pair is required"))
        
        # Validate no duplicate pairs
        pairs = set()
        for row in self.currency_pairs:
            pair_key = f"{row.from_currency}-{row.to_currency}"
            if pair_key in pairs:
                frappe.throw(_("Duplicate currency pair found: {0}").format(pair_key))
            pairs.add(pair_key)
    
    @frappe.whitelist()
    def test_connection(self):
        """Test the Alpha Vantage API connection"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        try:
            client = AlphaVantageClient(api_key=self.get_password("api_key"))
            result = client.get_exchange_rate("USD", "EUR")
            
            if result.get("error"):
                return {
                    "status": "error",
                    "message": result.get("error")
                }
            
            return {
                "status": "success",
                "message": _("Connection successful!"),
                "sample_rate": result.get("exchange_rate"),
                "from_currency": "USD",
                "to_currency": "EUR"
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Forex API Test Connection Error")
            return {
                "status": "error",
                "message": str(e)
            }
    
    @frappe.whitelist()
    def sync_now(self):
        """Trigger immediate sync of daily spot rates"""
        if not self.enabled:
            frappe.throw(_("Please enable the integration first"))
        
        frappe.enqueue(
            "peasforex.tasks.sync_forex.sync_daily_spot_rates",
            queue="short",
            timeout=600,
            job_name="forex_sync_daily_manual"
        )
        
        return {
            "status": "queued",
            "message": _("Daily spot rate sync has been queued. Check Forex Sync Log for status.")
        }
    
    @frappe.whitelist()
    def sync_monthly_now(self):
        """Trigger immediate sync of monthly rates"""
        if not self.enabled:
            frappe.throw(_("Please enable the integration first"))
        
        frappe.enqueue(
            "peasforex.tasks.sync_forex.sync_monthly_rates",
            queue="long",
            timeout=1800,
            job_name="forex_sync_monthly_manual"
        )
        
        return {
            "status": "queued",
            "message": _("Monthly rate sync has been queued. Check Forex Sync Log for status.")
        }
    
    @frappe.whitelist()
    def backfill_historical(self, months=2):
        """Backfill historical data for the specified number of months"""
        if not self.enabled:
            frappe.throw(_("Please enable the integration first"))
        
        frappe.enqueue(
            "peasforex.tasks.sync_forex.backfill_historical_rates",
            queue="long",
            timeout=3600,
            months=int(months),
            job_name="forex_backfill_historical"
        )
        
        return {
            "status": "queued",
            "message": _("Historical data backfill for {0} months has been queued.").format(months)
        }
    
    def get_enabled_pairs(self):
        """Get list of enabled currency pairs"""
        return [
            {
                "from_currency": row.from_currency,
                "to_currency": row.to_currency,
                "sync_spot_daily": row.sync_spot_daily,
                "sync_closing_monthly": row.sync_closing_monthly,
                "sync_average_monthly": row.sync_average_monthly,
                "sync_prudency_monthly": row.sync_prudency_monthly
            }
            for row in self.currency_pairs
            if row.enabled
        ]
    
    def get_applicable_companies(self):
        """Get list of companies to apply rates to"""
        if self.apply_to_all_companies:
            return frappe.get_all("Company", pluck="name")
        else:
            return [row.company for row in self.applicable_companies]


def get_forex_settings():
    """Helper function to get Forex Settings singleton"""
    return frappe.get_single("Forex Settings")
