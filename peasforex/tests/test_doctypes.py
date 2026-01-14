# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestForexSettings(FrappeTestCase):
    """Test cases for Forex Settings DocType"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Ensure clean state
        pass
    
    def test_forex_settings_is_single(self):
        """Test that Forex Settings is a Single DocType"""
        meta = frappe.get_meta("Forex Settings")
        self.assertTrue(meta.issingle)
    
    def test_forex_settings_required_fields(self):
        """Test required fields exist in Forex Settings"""
        meta = frappe.get_meta("Forex Settings")
        field_names = [f.fieldname for f in meta.fields]
        
        required_fields = [
            "enabled",
            "api_key",
            "create_bidirectional_rates",
            "auto_update_currency_exchange",
            "store_historical_data",
            "apply_to_all_companies",
            "currency_pairs"
        ]
        
        for field in required_fields:
            self.assertIn(field, field_names, f"Field {field} should exist")
    
    def test_currency_pair_fields(self):
        """Test Currency Pair child table has required fields"""
        meta = frappe.get_meta("Currency Pair")
        field_names = [f.fieldname for f in meta.fields]
        
        required_fields = [
            "from_currency",
            "to_currency",
            "enabled",
            "sync_spot_daily",
            "sync_closing_monthly",
            "sync_average_monthly",
            "sync_prudency_monthly"
        ]
        
        for field in required_fields:
            self.assertIn(field, field_names, f"Field {field} should exist")


class TestForexRateLog(FrappeTestCase):
    """Test cases for Forex Rate Log DocType"""
    
    def test_forex_rate_log_fields(self):
        """Test Forex Rate Log has required fields"""
        meta = frappe.get_meta("Forex Rate Log")
        field_names = [f.fieldname for f in meta.fields]
        
        required_fields = [
            "from_currency",
            "to_currency",
            "rate_date",
            "rate_type",
            "exchange_rate"
        ]
        
        for field in required_fields:
            self.assertIn(field, field_names, f"Field {field} should exist")
    
    def test_forex_rate_log_rate_types(self):
        """Test rate type options are correct"""
        meta = frappe.get_meta("Forex Rate Log")
        rate_type_field = next(f for f in meta.fields if f.fieldname == "rate_type")
        
        expected_options = [
            "Spot",
            "Closing",
            "Monthly Average",
            "Prudency (High)",
            "Prudency (Low)"
        ]
        
        options = rate_type_field.options.split("\n")
        for opt in expected_options:
            self.assertIn(opt, options, f"Rate type {opt} should be available")
    
    def test_create_forex_rate_log(self):
        """Test creating a Forex Rate Log entry"""
        # Create test currencies if they don't exist
        for currency in ["USD", "UGX"]:
            if not frappe.db.exists("Currency", currency):
                frappe.get_doc({
                    "doctype": "Currency",
                    "currency_name": currency,
                    "enabled": 1
                }).insert()
        
        doc = frappe.get_doc({
            "doctype": "Forex Rate Log",
            "from_currency": "USD",
            "to_currency": "UGX",
            "rate_date": "2026-01-14",
            "rate_type": "Spot",
            "exchange_rate": 3750.50
        })
        doc.insert()
        
        self.assertTrue(doc.name)
        self.assertEqual(doc.exchange_rate, 3750.50)
        
        # Cleanup
        doc.delete()
    
    def test_log_rate_static_method(self):
        """Test the static log_rate method"""
        from peasforex.peasforex.doctype.forex_rate_log.forex_rate_log import ForexRateLog
        
        # Create test currencies if they don't exist
        for currency in ["GBP", "EUR"]:
            if not frappe.db.exists("Currency", currency):
                frappe.get_doc({
                    "doctype": "Currency",
                    "currency_name": currency,
                    "enabled": 1
                }).insert()
        
        doc = ForexRateLog.log_rate(
            from_currency="GBP",
            to_currency="EUR",
            rate_date="2026-01-14",
            rate_type="Spot",
            exchange_rate=1.1650
        )
        
        self.assertTrue(doc.name)
        self.assertEqual(doc.from_currency, "GBP")
        self.assertEqual(doc.to_currency, "EUR")
        
        # Cleanup
        doc.delete()


class TestForexSyncLog(FrappeTestCase):
    """Test cases for Forex Sync Log DocType"""
    
    def test_forex_sync_log_fields(self):
        """Test Forex Sync Log has required fields"""
        meta = frappe.get_meta("Forex Sync Log")
        field_names = [f.fieldname for f in meta.fields]
        
        required_fields = [
            "sync_time",
            "sync_type",
            "currency_pair",
            "status",
            "exchange_rate",
            "error_message"
        ]
        
        for field in required_fields:
            self.assertIn(field, field_names, f"Field {field} should exist")
    
    def test_forex_sync_log_status_options(self):
        """Test status options are correct"""
        meta = frappe.get_meta("Forex Sync Log")
        status_field = next(f for f in meta.fields if f.fieldname == "status")
        
        expected_options = ["Success", "Error", "Skipped"]
        options = status_field.options.split("\n")
        
        for opt in expected_options:
            self.assertIn(opt, options, f"Status {opt} should be available")
    
    def test_create_sync_log(self):
        """Test creating a sync log entry"""
        from peasforex.peasforex.doctype.forex_sync_log.forex_sync_log import log_sync
        
        doc = log_sync(
            sync_type="Spot (Daily)",
            currency_pair="USD-UGX",
            status="Success",
            exchange_rate=3750.50
        )
        
        self.assertTrue(doc.name)
        self.assertEqual(doc.status, "Success")
        self.assertEqual(doc.currency_pair, "USD-UGX")
        
        # Cleanup
        doc.delete()


class TestApplicableCompany(FrappeTestCase):
    """Test cases for Applicable Company child table"""
    
    def test_applicable_company_is_child_table(self):
        """Test that Applicable Company is a child table"""
        meta = frappe.get_meta("Applicable Company")
        self.assertTrue(meta.istable)
    
    def test_applicable_company_has_company_field(self):
        """Test company field exists and links to Company"""
        meta = frappe.get_meta("Applicable Company")
        company_field = next((f for f in meta.fields if f.fieldname == "company"), None)
        
        self.assertIsNotNone(company_field)
        self.assertEqual(company_field.fieldtype, "Link")
        self.assertEqual(company_field.options, "Company")


if __name__ == "__main__":
    unittest.main()
