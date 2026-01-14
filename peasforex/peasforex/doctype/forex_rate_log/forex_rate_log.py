# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


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
        import json
        
        # Check if entry exists
        existing = frappe.db.exists("Forex Rate Log", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate_date": rate_date,
            "rate_type": rate_type
        })
        
        if existing:
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
            return doc
        else:
            # Create new
            doc = frappe.get_doc({
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
            })
            doc.insert(ignore_permissions=True)
            return doc
