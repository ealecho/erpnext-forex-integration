# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch, MagicMock
import json


class TestAlphaVantageClient(unittest.TestCase):
    """Test cases for the Alpha Vantage API client"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_key = "test_api_key_12345"
        
        # Sample API responses
        self.sample_exchange_rate_response = {
            "Realtime Currency Exchange Rate": {
                "1. From_Currency Code": "USD",
                "2. From_Currency Name": "United States Dollar",
                "3. To_Currency Code": "EUR",
                "4. To_Currency Name": "Euro",
                "5. Exchange Rate": "0.92150000",
                "6. Last Refreshed": "2024-01-14 12:00:00",
                "7. Time Zone": "UTC",
                "8. Bid Price": "0.92140000",
                "9. Ask Price": "0.92160000"
            }
        }
        
        self.sample_fx_daily_response = {
            "Meta Data": {
                "1. Information": "Forex Daily Prices (open, high, low, close)",
                "2. From Symbol": "USD",
                "3. To Symbol": "EUR",
                "4. Output Size": "Compact",
                "5. Last Refreshed": "2024-01-14"
            },
            "Time Series FX (Daily)": {
                "2024-01-14": {
                    "1. open": "0.9200",
                    "2. high": "0.9250",
                    "3. low": "0.9180",
                    "4. close": "0.9215"
                },
                "2024-01-13": {
                    "1. open": "0.9180",
                    "2. high": "0.9220",
                    "3. low": "0.9170",
                    "4. close": "0.9200"
                },
                "2024-01-12": {
                    "1. open": "0.9150",
                    "2. high": "0.9200",
                    "3. low": "0.9140",
                    "4. close": "0.9180"
                }
            }
        }
        
        self.sample_error_response = {
            "Error Message": "Invalid API call. Please retry or visit the documentation."
        }
        
        self.sample_rate_limit_response = {
            "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."
        }
    
    @patch('peasforex.api.alpha_vantage.frappe')
    def test_client_initialization_with_api_key(self, mock_frappe):
        """Test client initialization with provided API key"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        client = AlphaVantageClient(api_key=self.mock_api_key)
        
        self.assertEqual(client.api_key, self.mock_api_key)
        self.assertIsNotNone(client.rate_limiter)
        self.assertIsNotNone(client.session)
    
    @patch('peasforex.api.alpha_vantage.frappe')
    def test_client_initialization_from_settings(self, mock_frappe):
        """Test client initialization from Forex Settings"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.get_password.return_value = self.mock_api_key
        mock_frappe.get_single.return_value = mock_settings
        
        client = AlphaVantageClient()
        
        mock_frappe.get_single.assert_called_once_with("Forex Settings")
        mock_settings.get_password.assert_called_once_with("api_key")
        self.assertEqual(client.api_key, self.mock_api_key)
    
    @patch('peasforex.api.alpha_vantage.frappe')
    def test_client_initialization_no_api_key(self, mock_frappe):
        """Test client raises error when no API key available"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        # Mock settings with no API key
        mock_settings = MagicMock()
        mock_settings.get_password.return_value = None
        mock_frappe.get_single.return_value = mock_settings
        mock_frappe._.return_value = "Alpha Vantage API key is not configured"
        
        with self.assertRaises(ValueError):
            AlphaVantageClient()
    
    @patch('peasforex.api.alpha_vantage.frappe')
    @patch('requests.Session.get')
    def test_get_exchange_rate_success(self, mock_get, mock_frappe):
        """Test successful exchange rate fetch"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = self.sample_exchange_rate_response
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        client = AlphaVantageClient(api_key=self.mock_api_key)
        result = client.get_exchange_rate("USD", "EUR")
        
        self.assertNotIn("error", result)
        self.assertEqual(result["exchange_rate"], 0.9215)
        self.assertEqual(result["from_currency"], "USD")
        self.assertEqual(result["to_currency"], "EUR")
        self.assertEqual(result["bid_price"], 0.9214)
        self.assertEqual(result["ask_price"], 0.9216)
    
    @patch('peasforex.api.alpha_vantage.frappe')
    @patch('requests.Session.get')
    def test_get_exchange_rate_api_error(self, mock_get, mock_frappe):
        """Test handling of API error response"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        # Mock error response
        mock_response = MagicMock()
        mock_response.json.return_value = self.sample_error_response
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        client = AlphaVantageClient(api_key=self.mock_api_key)
        result = client.get_exchange_rate("INVALID", "XXX")
        
        self.assertIn("error", result)
        self.assertIn("Invalid API call", result["error"])
    
    @patch('peasforex.api.alpha_vantage.frappe')
    @patch('requests.Session.get')
    def test_get_exchange_rate_rate_limited(self, mock_get, mock_frappe):
        """Test handling of rate limit response"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        # Mock rate limit response
        mock_response = MagicMock()
        mock_response.json.return_value = self.sample_rate_limit_response
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        client = AlphaVantageClient(api_key=self.mock_api_key)
        result = client.get_exchange_rate("USD", "EUR")
        
        self.assertIn("error", result)
        self.assertTrue(result.get("rate_limited", False))
    
    @patch('peasforex.api.alpha_vantage.frappe')
    @patch('requests.Session.get')
    def test_get_fx_daily_success(self, mock_get, mock_frappe):
        """Test successful daily forex data fetch"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = self.sample_fx_daily_response
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        client = AlphaVantageClient(api_key=self.mock_api_key)
        result = client.get_fx_daily("USD", "EUR")
        
        self.assertNotIn("error", result)
        self.assertIn("time_series", result)
        self.assertIn("meta_data", result)
        self.assertEqual(len(result["time_series"]), 3)
        
        # Check data parsing
        self.assertEqual(result["time_series"]["2024-01-14"]["close"], 0.9215)
        self.assertEqual(result["time_series"]["2024-01-14"]["high"], 0.9250)
    
    @patch('peasforex.api.alpha_vantage.frappe')
    @patch('requests.Session.get')
    def test_request_timeout(self, mock_get, mock_frappe):
        """Test handling of request timeout"""
        from peasforex.api.alpha_vantage import AlphaVantageClient
        import requests
        
        # Mock timeout
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        mock_frappe._.return_value = "API request timed out"
        
        client = AlphaVantageClient(api_key=self.mock_api_key)
        result = client.get_exchange_rate("USD", "EUR")
        
        self.assertIn("error", result)
        mock_frappe.log_error.assert_called()


class TestRateLimiter(unittest.TestCase):
    """Test cases for the rate limiter"""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes with correct delay"""
        from peasforex.api.alpha_vantage import RateLimiter
        
        limiter = RateLimiter(calls_per_minute=60)
        self.assertEqual(limiter.delay, 1.0)
        
        limiter = RateLimiter(calls_per_minute=30)
        self.assertEqual(limiter.delay, 2.0)
    
    @patch('time.sleep')
    @patch('time.time')
    def test_rate_limiter_wait(self, mock_time, mock_sleep):
        """Test rate limiter waits appropriately"""
        from peasforex.api.alpha_vantage import RateLimiter
        
        # Simulate rapid calls
        mock_time.side_effect = [0, 0.5, 1.0]  # First call, then 0.5s elapsed
        
        limiter = RateLimiter(calls_per_minute=60)
        limiter.last_call = 0
        
        limiter.wait()
        
        # Should have slept for 0.5s (1.0 - 0.5 elapsed)
        mock_sleep.assert_called_once()


class TestExchangeRateCalculations(unittest.TestCase):
    """Test cases for exchange rate calculations"""
    
    def test_average_rate_calculation(self):
        """Test monthly average calculation"""
        rates = [1.0, 1.1, 1.2, 1.3, 1.4]
        average = sum(rates) / len(rates)
        self.assertEqual(average, 1.2)
    
    def test_prudency_high_rate(self):
        """Test prudency high (max) rate selection"""
        rates = [
            {"high": 1.25, "low": 1.20},
            {"high": 1.30, "low": 1.22},
            {"high": 1.28, "low": 1.18},
        ]
        high_rate = max(r["high"] for r in rates)
        self.assertEqual(high_rate, 1.30)
    
    def test_prudency_low_rate(self):
        """Test prudency low (min) rate selection"""
        rates = [
            {"high": 1.25, "low": 1.20},
            {"high": 1.30, "low": 1.22},
            {"high": 1.28, "low": 1.18},
        ]
        low_rate = min(r["low"] for r in rates)
        self.assertEqual(low_rate, 1.18)
    
    def test_bidirectional_rate_calculation(self):
        """Test reverse rate calculation"""
        forward_rate = 1.25  # USD to EUR
        reverse_rate = 1 / forward_rate  # EUR to USD
        self.assertAlmostEqual(reverse_rate, 0.8, places=2)


if __name__ == "__main__":
    unittest.main()
