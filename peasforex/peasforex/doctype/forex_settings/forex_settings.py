# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Module-level logger
logger = frappe.logger("peasforex", allow_site=True, file_count=5)


def log_debug(message, data=None):
    """Log debug message with optional data"""
    if data:
        logger.debug(f"[Peasforex Settings] {message}: {data}")
    else:
        logger.debug(f"[Peasforex Settings] {message}")


def log_info(message, data=None):
    """Log info message with optional data"""
    if data:
        logger.info(f"[Peasforex Settings] {message}: {data}")
    else:
        logger.info(f"[Peasforex Settings] {message}")


def log_error(message, data=None):
    """Log error message with optional data"""
    if data:
        logger.error(f"[Peasforex Settings] {message}: {data}")
    else:
        logger.error(f"[Peasforex Settings] {message}")


class ForexSettings(Document):
    def validate(self):
        log_debug("Validating Forex Settings")
        
        if self.enabled and not self.api_key:
            log_error("Validation failed: API Key required when enabled")
            frappe.throw(_("API Key is required when integration is enabled"))
        
        if not self.currency_pairs:
            log_error("Validation failed: No currency pairs")
            frappe.throw(_("At least one currency pair is required"))
        
        # Validate no duplicate pairs
        pairs = set()
        for row in self.currency_pairs:
            pair_key = f"{row.from_currency}-{row.to_currency}"
            if pair_key in pairs:
                log_error(f"Validation failed: Duplicate pair {pair_key}")
                frappe.throw(_("Duplicate currency pair found: {0}").format(pair_key))
            pairs.add(pair_key)
        
        log_debug(f"Validation passed: {len(pairs)} currency pairs")
    
    @frappe.whitelist()
    def test_connection(self):
        """Test the Alpha Vantage API connection"""
        log_info("Testing API connection")
        
        try:
            from peasforex.api.alpha_vantage import AlphaVantageClient
            
            api_key = self.get_password("api_key")
            if not api_key:
                log_error("Test connection failed: No API key")
                return {
                    "status": "error",
                    "message": _("API key is not configured")
                }
            
            log_debug("Initializing AlphaVantageClient for test")
            client = AlphaVantageClient(api_key=api_key)
            
            log_debug("Fetching test rate: USD -> EUR")
            result = client.get_exchange_rate("USD", "EUR")
            
            if result.get("error"):
                log_error(f"Test connection failed: {result.get('error')}")
                return {
                    "status": "error",
                    "message": result.get("error")
                }
            
            sample_rate = result.get("exchange_rate")
            log_info(f"Test connection successful: USD->EUR = {sample_rate}")
            
            return {
                "status": "success",
                "message": _("Connection successful!"),
                "sample_rate": sample_rate,
                "from_currency": "USD",
                "to_currency": "EUR"
            }
        except Exception as e:
            log_error(f"Test connection exception: {str(e)}")
            frappe.log_error(frappe.get_traceback(), "Forex API Test Connection Error")
            return {
                "status": "error",
                "message": str(e)
            }
    
    @frappe.whitelist()
    def sync_now(self):
        """Trigger immediate sync of daily spot rates"""
        log_info("Manual sync triggered: sync_now")
        
        if not self.enabled:
            log_error("Sync failed: Integration not enabled")
            frappe.throw(_("Please enable the integration first"))
        
        log_debug("Enqueueing sync_daily_spot_rates")
        frappe.enqueue(
            "peasforex.tasks.sync_forex.sync_daily_spot_rates",
            queue="short",
            timeout=600,
            job_name="forex_sync_daily_manual"
        )
        
        log_info("Daily sync job queued")
        return {
            "status": "queued",
            "message": _("Daily spot rate sync has been queued. Check Forex Sync Log for status.")
        }
    
    @frappe.whitelist()
    def sync_monthly_now(self):
        """Trigger immediate sync of monthly rates"""
        log_info("Manual sync triggered: sync_monthly_now")
        
        if not self.enabled:
            log_error("Sync failed: Integration not enabled")
            frappe.throw(_("Please enable the integration first"))
        
        log_debug("Enqueueing sync_monthly_rates")
        frappe.enqueue(
            "peasforex.tasks.sync_forex.sync_monthly_rates",
            queue="long",
            timeout=1800,
            job_name="forex_sync_monthly_manual"
        )
        
        log_info("Monthly sync job queued")
        return {
            "status": "queued",
            "message": _("Monthly rate sync has been queued. Check Forex Sync Log for status.")
        }
    
    @frappe.whitelist()
    def backfill_historical(self, months=2):
        """Backfill historical data for the specified number of months"""
        log_info(f"Manual sync triggered: backfill_historical for {months} months")
        
        if not self.enabled:
            log_error("Backfill failed: Integration not enabled")
            frappe.throw(_("Please enable the integration first"))
        
        log_debug(f"Enqueueing backfill_historical_rates with months={months}")
        frappe.enqueue(
            "peasforex.tasks.sync_forex.backfill_historical_rates",
            queue="long",
            timeout=3600,
            months=int(months),
            job_name="forex_backfill_historical"
        )
        
        log_info(f"Backfill job queued for {months} months")
        return {
            "status": "queued",
            "message": _("Historical data backfill for {0} months has been queued.").format(months)
        }
    
    def get_enabled_pairs(self):
        """Get list of enabled currency pairs"""
        log_debug("Getting enabled currency pairs")
        
        pairs = [
            {
                "from_currency": row.from_currency,
                "to_currency": row.to_currency,
                "sync_spot_daily": row.sync_spot_daily,
                "sync_closing_monthly": row.sync_closing_monthly,
                "sync_average_monthly": row.sync_average_monthly,
                "sync_prudency_monthly": row.sync_prudency_monthly,
                "target_company": getattr(row, "target_company", None)  # Company-specific rate
            }
            for row in self.currency_pairs
            if row.enabled
        ]
        
        log_debug(f"Found {len(pairs)} enabled pairs")
        return pairs
    
    def get_applicable_companies(self):
        """Get list of companies to apply rates to"""
        log_debug("Getting applicable companies")
        
        if self.apply_to_all_companies:
            companies = frappe.get_all("Company", pluck="name")
            log_debug(f"Apply to all companies: {companies}")
            return companies
        else:
            companies = [row.company for row in self.applicable_companies]
            log_debug(f"Apply to specific companies: {companies}")
            return companies


def get_forex_settings():
    """Helper function to get Forex Settings singleton"""
    log_debug("Getting Forex Settings singleton")
    return frappe.get_single("Forex Settings")
