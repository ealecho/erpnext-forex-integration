# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import requests
import time
import frappe
from frappe import _


class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, calls_per_minute=75):
        """
        Initialize rate limiter.
        Alpha Vantage premium allows up to 75 calls/minute (depending on plan).
        Being conservative with 60 calls/minute by default.
        """
        self.delay = 60.0 / calls_per_minute
        self.last_call = 0
    
    def wait(self):
        """Wait if necessary to respect rate limit"""
        elapsed = time.time() - self.last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_call = time.time()


class AlphaVantageClient:
    """
    Alpha Vantage API Client for Forex data
    
    Documentation: https://www.alphavantage.co/documentation/
    """
    
    BASE_URL = "https://www.alphavantage.co/query"
    DEFAULT_TIMEOUT = 30
    
    def __init__(self, api_key=None):
        """
        Initialize the Alpha Vantage client.
        
        Args:
            api_key: Alpha Vantage API key. If not provided, will fetch from settings.
        """
        if api_key:
            self.api_key = api_key
        else:
            settings = frappe.get_single("Forex Settings")
            self.api_key = settings.get_password("api_key")
        
        if not self.api_key:
            raise ValueError(_("Alpha Vantage API key is not configured"))
        
        self.rate_limiter = RateLimiter(calls_per_minute=60)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ERPNext-Peasforex/1.0"
        })
    
    def _make_request(self, params):
        """
        Make an API request with rate limiting and error handling.
        
        Args:
            params: Dictionary of query parameters
            
        Returns:
            dict: API response data
        """
        params["apikey"] = self.api_key
        
        # Apply rate limiting
        self.rate_limiter.wait()
        
        try:
            response = self.session.get(
                self.BASE_URL,
                params=params,
                timeout=self.DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API error messages
            if "Error Message" in data:
                return {"error": data["Error Message"], "raw": data}
            
            if "Note" in data:
                # Rate limit exceeded
                return {"error": data["Note"], "rate_limited": True, "raw": data}
            
            if "Information" in data:
                # Usually means API key issues
                return {"error": data["Information"], "raw": data}
            
            return data
            
        except requests.exceptions.Timeout:
            frappe.log_error("Alpha Vantage API timeout", "Forex API Error")
            return {"error": _("API request timed out")}
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Alpha Vantage API error: {str(e)}", "Forex API Error")
            return {"error": str(e)}
        except ValueError as e:
            frappe.log_error(f"Invalid JSON response: {str(e)}", "Forex API Error")
            return {"error": _("Invalid API response")}
    
    def get_exchange_rate(self, from_currency, to_currency):
        """
        Get realtime exchange rate for a currency pair.
        
        This uses the CURRENCY_EXCHANGE_RATE endpoint which returns
        the current spot rate.
        
        Args:
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'EUR')
            
        Returns:
            dict: {
                'exchange_rate': float,
                'bid_price': float,
                'ask_price': float,
                'from_currency': str,
                'to_currency': str,
                'last_refreshed': str,
                'raw': dict  # Original API response
            }
        """
        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_currency,
            "to_currency": to_currency
        }
        
        data = self._make_request(params)
        
        if "error" in data:
            return data
        
        try:
            rate_data = data.get("Realtime Currency Exchange Rate", {})
            
            return {
                "exchange_rate": float(rate_data.get("5. Exchange Rate", 0)),
                "bid_price": float(rate_data.get("8. Bid Price", 0)),
                "ask_price": float(rate_data.get("9. Ask Price", 0)),
                "from_currency": rate_data.get("1. From_Currency Code"),
                "to_currency": rate_data.get("3. To_Currency Code"),
                "last_refreshed": rate_data.get("6. Last Refreshed"),
                "raw": data
            }
        except (KeyError, TypeError, ValueError) as e:
            return {"error": f"Failed to parse exchange rate: {str(e)}", "raw": data}
    
    def get_fx_daily(self, from_currency, to_currency, outputsize="compact"):
        """
        Get daily forex time series data.
        
        This uses the FX_DAILY endpoint which returns OHLC data.
        
        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            outputsize: 'compact' (last 100 days) or 'full' (20+ years)
            
        Returns:
            dict: {
                'time_series': {
                    'YYYY-MM-DD': {
                        'open': float,
                        'high': float,
                        'low': float,
                        'close': float
                    },
                    ...
                },
                'meta_data': dict,
                'raw': dict
            }
        """
        params = {
            "function": "FX_DAILY",
            "from_symbol": from_currency,
            "to_symbol": to_currency,
            "outputsize": outputsize
        }
        
        data = self._make_request(params)
        
        if "error" in data:
            return data
        
        try:
            meta_data = data.get("Meta Data", {})
            time_series_raw = data.get("Time Series FX (Daily)", {})
            
            time_series = {}
            for date_str, values in time_series_raw.items():
                time_series[date_str] = {
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0))
                }
            
            return {
                "time_series": time_series,
                "meta_data": meta_data,
                "raw": data
            }
        except (KeyError, TypeError, ValueError) as e:
            return {"error": f"Failed to parse daily data: {str(e)}", "raw": data}
    
    def get_fx_monthly(self, from_currency, to_currency):
        """
        Get monthly forex time series data.
        
        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            
        Returns:
            dict: Similar to get_fx_daily but with monthly data
        """
        params = {
            "function": "FX_MONTHLY",
            "from_symbol": from_currency,
            "to_symbol": to_currency
        }
        
        data = self._make_request(params)
        
        if "error" in data:
            return data
        
        try:
            meta_data = data.get("Meta Data", {})
            time_series_raw = data.get("Time Series FX (Monthly)", {})
            
            time_series = {}
            for date_str, values in time_series_raw.items():
                time_series[date_str] = {
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0))
                }
            
            return {
                "time_series": time_series,
                "meta_data": meta_data,
                "raw": data
            }
        except (KeyError, TypeError, ValueError) as e:
            return {"error": f"Failed to parse monthly data: {str(e)}", "raw": data}
    
    def get_previous_month_rates(self, from_currency, to_currency):
        """
        Get various rate calculations for the previous month.
        
        Returns closing rate, monthly average, and prudency rates.
        
        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            
        Returns:
            dict: {
                'closing_rate': float (last day of previous month),
                'average_rate': float (average of all daily closes),
                'high_rate': float (highest rate - prudency for expenses),
                'low_rate': float (lowest rate - prudency for income),
                'month': str (YYYY-MM format),
                'data_points': int (number of trading days used)
            }
        """
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        
        # Get previous month date range
        today = datetime.now()
        first_of_this_month = today.replace(day=1)
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        first_of_prev_month = last_of_prev_month.replace(day=1)
        
        # Get daily data (compact should cover last 100 days which is enough)
        daily_data = self.get_fx_daily(from_currency, to_currency, outputsize="compact")
        
        if "error" in daily_data:
            return daily_data
        
        time_series = daily_data.get("time_series", {})
        
        if not time_series:
            return {"error": "No time series data available"}
        
        # Filter for previous month
        prev_month_rates = []
        closing_rate = None
        
        for date_str, values in sorted(time_series.items(), reverse=True):
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
                
                # Check if in previous month
                if date.year == last_of_prev_month.year and date.month == last_of_prev_month.month:
                    prev_month_rates.append({
                        "date": date_str,
                        "close": values["close"],
                        "high": values["high"],
                        "low": values["low"]
                    })
                    
                    # The first one we encounter (most recent) is the closing rate
                    if closing_rate is None:
                        closing_rate = values["close"]
            except ValueError:
                continue
        
        if not prev_month_rates:
            return {"error": f"No data available for previous month ({last_of_prev_month.strftime('%Y-%m')})"}
        
        # Calculate averages and extremes
        closes = [r["close"] for r in prev_month_rates]
        highs = [r["high"] for r in prev_month_rates]
        lows = [r["low"] for r in prev_month_rates]
        
        return {
            "closing_rate": closing_rate,
            "average_rate": sum(closes) / len(closes),
            "high_rate": max(highs),  # Prudency for expenses
            "low_rate": min(lows),    # Prudency for income
            "month": last_of_prev_month.strftime("%Y-%m"),
            "month_end_date": last_of_prev_month.strftime("%Y-%m-%d"),
            "data_points": len(prev_month_rates),
            "raw_data": prev_month_rates
        }
