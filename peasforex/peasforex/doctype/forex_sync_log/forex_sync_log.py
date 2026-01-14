# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json

# Module-level logger
logger = frappe.logger("peasforex", allow_site=True, file_count=5)


def log_debug(message, data=None):
    """Log debug message with optional data"""
    if data:
        logger.debug(f"[Peasforex SyncLog] {message}: {data}")
    else:
        logger.debug(f"[Peasforex SyncLog] {message}")


def log_error(message, data=None):
    """Log error message with optional data"""
    if data:
        logger.error(f"[Peasforex SyncLog] {message}: {data}")
    else:
        logger.error(f"[Peasforex SyncLog] {message}")


class ForexSyncLog(Document):
    pass


def log_sync(sync_type, currency_pair, status, exchange_rate=None, error_message=None, api_response=None):
    """Create a sync log entry"""
    log_debug(f"Creating sync log: type={sync_type}, pair={currency_pair}, status={status}")
    
    try:
        doc_data = {
            "doctype": "Forex Sync Log",
            "sync_time": frappe.utils.now(),
            "sync_type": sync_type,
            "currency_pair": currency_pair,
            "status": status,
            "exchange_rate": exchange_rate,
            "error_message": error_message,
            "api_response": json.dumps(api_response) if isinstance(api_response, dict) else api_response
        }
        
        log_debug(f"Sync log data: {doc_data}")
        
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        log_debug(f"Sync log created: {doc.name}")
        return doc
    except Exception as e:
        log_error(f"Failed to create sync log: {str(e)}")
        frappe.log_error(
            f"Failed to create sync log\n"
            f"Type: {sync_type}, Pair: {currency_pair}, Status: {status}\n"
            f"Error: {str(e)}\n\n"
            f"{frappe.get_traceback()}",
            "Forex Sync Log Error"
        )
        return None
