# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json

# Module-level logger
logger = frappe.logger("peasforex", allow_site=True, file_count=5)


def log_debug(message, data=None):
    """Log debug message with optional data"""
    if data:
        logger.debug(f"[Peasforex RateLog] {message}: {data}")
    else:
        logger.debug(f"[Peasforex RateLog] {message}")


def log_error(message, data=None):
    """Log error message with optional data"""
    if data:
        logger.error(f"[Peasforex RateLog] {message}: {data}")
    else:
        logger.error(f"[Peasforex RateLog] {message}")


class ForexRateLog(Document):
    def before_insert(self):
        # Set synced_at if not set
        if not self.synced_at:
            self.synced_at = frappe.utils.now()
    
    @staticmethod
    def log_rate(from_currency, to_currency, rate_date, rate_type, exchange_rate,
                 open_rate=None, high_rate=None, low_rate=None, close_rate=None,
                 api_response=None):
        """Create or update a forex rate log entry"""
        log_debug(f"Logging rate: {from_currency}->{to_currency} | {rate_type} | {exchange_rate} on {rate_date}")
        
        try:
            # Check if entry exists
            existing = frappe.db.exists("Forex Rate Log", {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate_date": rate_date,
                "rate_type": rate_type
            })
            
            if existing:
                log_debug(f"Updating existing rate log: {existing}")
                # Update existing
                doc = frappe.get_doc("Forex Rate Log", existing)
                doc.exchange_rate = exchange_rate
                doc.open_rate = open_rate
                doc.high_rate = high_rate
                doc.low_rate = low_rate
                doc.close_rate = close_rate
                doc.synced_at = frappe.utils.now()
                if api_response:
                    doc.api_response = json.dumps(api_response) if isinstance(api_response, dict) else api_response
                doc.save(ignore_permissions=True)
                log_debug(f"Rate log updated: {doc.name}")
                return doc
            else:
                log_debug("Creating new rate log entry")
                # Create new
                doc_data = {
                    "doctype": "Forex Rate Log",
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "rate_date": rate_date,
                    "rate_type": rate_type,
                    "exchange_rate": exchange_rate,
                    "open_rate": open_rate,
                    "high_rate": high_rate,
                    "low_rate": low_rate,
                    "close_rate": close_rate,
                    "source": "Alpha Vantage",
                    "synced_at": frappe.utils.now(),
                    "api_response": json.dumps(api_response) if isinstance(api_response, dict) else api_response
                }
                
                log_debug(f"Rate log data: {doc_data}")
                
                doc = frappe.get_doc(doc_data)
                doc.insert(ignore_permissions=True)
                log_debug(f"Rate log created: {doc.name}")
                return doc
                
        except Exception as e:
            log_error(f"Failed to log rate: {str(e)}")
            frappe.log_error(
                f"Failed to log forex rate\n"
                f"From: {from_currency}, To: {to_currency}, Date: {rate_date}\n"
                f"Type: {rate_type}, Rate: {exchange_rate}\n"
                f"Error: {str(e)}\n\n"
                f"{frappe.get_traceback()}",
                "Forex Rate Log Error"
            )
            return None
