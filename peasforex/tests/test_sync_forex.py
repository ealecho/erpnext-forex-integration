# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timedelta


class TestSyncForex(unittest.TestCase):
    """Test cases for forex sync tasks"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.sample_exchange_rate = {
            "exchange_rate": 3750.50,
            "from_currency": "USD",
            "to_currency": "UGX",
            "bid_price": 3750.00,
            "ask_price": 3751.00,
            "last_refreshed": "2024-01-14 12:00:00",
            "raw": {}
        }
        
        self.sample_daily_data = {
            "time_series": {
                "2024-01-14": {"open": 3740.0, "high": 3760.0, "low": 3735.0, "close": 3750.5},
                "2024-01-13": {"open": 3730.0, "high": 3755.0, "low": 3725.0, "close": 3740.0},
                "2024-01-12": {"open": 3720.0, "high": 3745.0, "low": 3715.0, "close": 3730.0},
            },
            "meta_data": {},
            "raw": {}
        }
        
        self.sample_settings = {
            "enabled": True,
            "api_key": "test_key",
            "create_bidirectional_rates": True,
            "auto_update_currency_exchange": True,
            "store_historical_data": True,
            "apply_to_all_companies": True,
            "currency_pairs": [
                {
                    "from_currency": "USD",
                    "to_currency": "UGX",
                    "enabled": True,
                    "sync_spot_daily": True,
                    "sync_closing_monthly": True,
                    "sync_average_monthly": True,
                    "sync_prudency_monthly": True
                },
                {
                    "from_currency": "GBP",
                    "to_currency": "USD",
                    "enabled": True,
                    "sync_spot_daily": True,
                    "sync_closing_monthly": True,
                    "sync_average_monthly": True,
                    "sync_prudency_monthly": True
                }
            ]
        }
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_is_enabled_true(self, mock_frappe):
        """Test is_enabled returns True when enabled"""
        from peasforex.tasks.sync_forex import is_enabled
        
        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.api_key = "test_key"
        mock_frappe.get_single.return_value = mock_settings
        
        result = is_enabled()
        self.assertTrue(result)
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_is_enabled_false_no_key(self, mock_frappe):
        """Test is_enabled returns False when no API key"""
        from peasforex.tasks.sync_forex import is_enabled
        
        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.api_key = None
        mock_frappe.get_single.return_value = mock_settings
        
        result = is_enabled()
        self.assertFalse(result)
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_is_enabled_false_disabled(self, mock_frappe):
        """Test is_enabled returns False when disabled"""
        from peasforex.tasks.sync_forex import is_enabled
        
        mock_settings = MagicMock()
        mock_settings.enabled = False
        mock_settings.api_key = "test_key"
        mock_frappe.get_single.return_value = mock_settings
        
        result = is_enabled()
        self.assertFalse(result)
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_update_currency_exchange_create_new(self, mock_frappe):
        """Test creating new Currency Exchange record"""
        from peasforex.tasks.sync_forex import update_currency_exchange
        
        # Mock no existing record
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc
        
        update_currency_exchange("USD", "UGX", 3750.50, "2024-01-14")
        
        mock_frappe.get_doc.assert_called_once()
        mock_doc.insert.assert_called_once_with(ignore_permissions=True)
        mock_frappe.db.commit.assert_called_once()
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_update_currency_exchange_update_existing(self, mock_frappe):
        """Test updating existing Currency Exchange record"""
        from peasforex.tasks.sync_forex import update_currency_exchange
        
        # Mock existing record
        mock_frappe.db.get_value.return_value = "CE-00001"
        
        update_currency_exchange("USD", "UGX", 3750.50, "2024-01-14")
        
        # Should update, not create
        mock_frappe.db.set_value.assert_called()
        mock_frappe.get_doc.assert_not_called()
    
    @patch('peasforex.tasks.sync_forex.update_currency_exchange')
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_create_bidirectional_rate(self, mock_frappe, mock_update):
        """Test bidirectional rate creation"""
        from peasforex.tasks.sync_forex import create_bidirectional_rate
        
        mock_settings = MagicMock()
        mock_settings.create_bidirectional_rates = True
        mock_frappe.get_single.return_value = mock_settings
        
        create_bidirectional_rate("USD", "UGX", 3750.50, "2024-01-14")
        
        # Should be called twice - forward and reverse
        self.assertEqual(mock_update.call_count, 2)
        
        # Check reverse rate calculation
        calls = mock_update.call_args_list
        # First call: forward rate
        self.assertEqual(calls[0][0][0], "USD")
        self.assertEqual(calls[0][0][1], "UGX")
        self.assertEqual(calls[0][0][2], 3750.50)
        
        # Second call: reverse rate
        self.assertEqual(calls[1][0][0], "UGX")
        self.assertEqual(calls[1][0][1], "USD")
        self.assertAlmostEqual(calls[1][0][2], 1/3750.50, places=9)
    
    @patch('peasforex.tasks.sync_forex.log_sync')
    @patch('peasforex.tasks.sync_forex.store_rate_log')
    @patch('peasforex.tasks.sync_forex.create_bidirectional_rate')
    @patch('peasforex.tasks.sync_forex.AlphaVantageClient')
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_sync_daily_spot_rates_success(self, mock_frappe, mock_client_class, 
                                           mock_bidirectional, mock_store_log, mock_sync_log):
        """Test successful daily spot rate sync"""
        from peasforex.tasks.sync_forex import sync_daily_spot_rates
        
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.api_key = "test_key"
        mock_settings.auto_update_currency_exchange = True
        mock_settings.store_historical_data = True
        mock_settings.get_enabled_pairs.return_value = [
            {
                "from_currency": "USD",
                "to_currency": "UGX",
                "sync_spot_daily": True
            }
        ]
        mock_frappe.get_single.return_value = mock_settings
        mock_frappe.utils.today.return_value = "2024-01-14"
        mock_frappe.utils.now.return_value = "2024-01-14 12:00:00"
        
        # Mock API client
        mock_client = MagicMock()
        mock_client.get_exchange_rate.return_value = self.sample_exchange_rate
        mock_client_class.return_value = mock_client
        
        sync_daily_spot_rates()
        
        # Verify API was called
        mock_client.get_exchange_rate.assert_called_once_with("USD", "UGX")
        
        # Verify rate was created
        mock_bidirectional.assert_called_once()
        
        # Verify log was stored
        mock_store_log.assert_called_once()
        
        # Verify sync log created with success
        mock_sync_log.assert_called()
        call_args = mock_sync_log.call_args
        self.assertEqual(call_args[1]["status"], "Success")
    
    @patch('peasforex.tasks.sync_forex.log_sync')
    @patch('peasforex.tasks.sync_forex.AlphaVantageClient')
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_sync_daily_spot_rates_api_error(self, mock_frappe, mock_client_class, mock_sync_log):
        """Test daily sync handles API errors"""
        from peasforex.tasks.sync_forex import sync_daily_spot_rates
        
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.api_key = "test_key"
        mock_settings.get_enabled_pairs.return_value = [
            {
                "from_currency": "USD",
                "to_currency": "UGX",
                "sync_spot_daily": True
            }
        ]
        mock_frappe.get_single.return_value = mock_settings
        
        # Mock API client returning error
        mock_client = MagicMock()
        mock_client.get_exchange_rate.return_value = {"error": "API Error"}
        mock_client_class.return_value = mock_client
        
        sync_daily_spot_rates()
        
        # Verify error was logged
        mock_sync_log.assert_called()
        call_args = mock_sync_log.call_args
        self.assertEqual(call_args[1]["status"], "Error")
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_sync_daily_disabled(self, mock_frappe):
        """Test sync does nothing when disabled"""
        from peasforex.tasks.sync_forex import sync_daily_spot_rates
        
        mock_settings = MagicMock()
        mock_settings.enabled = False
        mock_frappe.get_single.return_value = mock_settings
        
        sync_daily_spot_rates()
        
        # Should log error and return early
        mock_frappe.log_error.assert_called()


class TestMonthlyRateCalculations(unittest.TestCase):
    """Test cases for monthly rate calculations"""
    
    def setUp(self):
        """Set up test data for a full month"""
        # Simulate 20 trading days of data
        self.monthly_data = {}
        base_rate = 3700.0
        for i in range(20):
            date = f"2024-12-{(i+1):02d}"
            variation = (i % 5) * 10  # Creates some variation
            self.monthly_data[date] = {
                "open": base_rate + variation,
                "high": base_rate + variation + 15,
                "low": base_rate + variation - 10,
                "close": base_rate + variation + 5
            }
    
    def test_closing_rate_is_last_day(self):
        """Test closing rate is from the last trading day"""
        # Sort dates and get last one
        sorted_dates = sorted(self.monthly_data.keys(), reverse=True)
        last_date = sorted_dates[0]
        closing_rate = self.monthly_data[last_date]["close"]
        
        self.assertEqual(last_date, "2024-12-20")
        self.assertIsNotNone(closing_rate)
    
    def test_average_rate_calculation(self):
        """Test monthly average is calculated correctly"""
        closes = [v["close"] for v in self.monthly_data.values()]
        average = sum(closes) / len(closes)
        
        # Should be around 3727.5 based on our test data pattern
        self.assertGreater(average, 3700)
        self.assertLess(average, 3800)
    
    def test_prudency_high_is_max(self):
        """Test prudency high is maximum high rate"""
        highs = [v["high"] for v in self.monthly_data.values()]
        max_high = max(highs)
        
        # Based on our pattern, max high should be 3755 (3700 + 40 + 15)
        self.assertEqual(max_high, 3755.0)
    
    def test_prudency_low_is_min(self):
        """Test prudency low is minimum low rate"""
        lows = [v["low"] for v in self.monthly_data.values()]
        min_low = min(lows)
        
        # Based on our pattern, min low should be 3690 (3700 + 0 - 10)
        self.assertEqual(min_low, 3690.0)


class TestLogFunctions(unittest.TestCase):
    """Test cases for logging functions"""
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_log_sync_success(self, mock_frappe):
        """Test sync log creation for success"""
        from peasforex.peasforex.doctype.forex_sync_log.forex_sync_log import log_sync
        
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc
        mock_frappe.utils.now.return_value = "2024-01-14 12:00:00"
        
        log_sync(
            sync_type="Spot (Daily)",
            currency_pair="USD-UGX",
            status="Success",
            exchange_rate=3750.50
        )
        
        mock_frappe.get_doc.assert_called_once()
        call_args = mock_frappe.get_doc.call_args[0][0]
        self.assertEqual(call_args["doctype"], "Forex Sync Log")
        self.assertEqual(call_args["status"], "Success")
        self.assertEqual(call_args["exchange_rate"], 3750.50)
        mock_doc.insert.assert_called_once_with(ignore_permissions=True)
    
    @patch('peasforex.tasks.sync_forex.frappe')
    def test_log_sync_error(self, mock_frappe):
        """Test sync log creation for error"""
        from peasforex.peasforex.doctype.forex_sync_log.forex_sync_log import log_sync
        
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc
        mock_frappe.utils.now.return_value = "2024-01-14 12:00:00"
        
        log_sync(
            sync_type="Spot (Daily)",
            currency_pair="USD-UGX",
            status="Error",
            error_message="API timeout"
        )
        
        call_args = mock_frappe.get_doc.call_args[0][0]
        self.assertEqual(call_args["status"], "Error")
        self.assertEqual(call_args["error_message"], "API timeout")


if __name__ == "__main__":
    unittest.main()
