# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import requests
import time
import json
import frappe
from frappe import _

# Module-level logger
logger = frappe.logger("peasforex", allow_site=True, file_count=5)


def log_debug(message, data=None):
    """Log debug message with optional data"""
    if data:
        logger.debug(f"[Peasforex API] {message}: {data}")
    else:
        logger.debug(f"[Peasforex API] {message}")


def log_info(message, data=None):
    """Log info message with optional data"""
    if data:
        logger.info(f"[Peasforex API] {message}: {data}")
    else:
        logger.info(f"[Peasforex API] {message}")


def log_error(message, data=None):
    """Log error message with optional data"""
    if data:
        logger.error(f"[Peasforex API] {message}: {data}")
    else:
        logger.error(f"[Peasforex API] {message}")


def log_warning(message, data=None):
    """Log warning message with optional data"""
    if data:
        logger.warning(f"[Peasforex API] {message}: {data}")
    else:
        logger.warning(f"[Peasforex API] {message}")


class RateLimiter:
    """Simple rate limiter for API calls"""

    def __init__(self, calls_per_minute=75):
        """
        Initialize rate limiter.
        Alpha Vantage premium allows up to 75 calls/minute (depending on plan).
        """
        self.delay = 60.0 / calls_per_minute
        self.last_call = 0
        log_debug(
            f"RateLimiter initialized with {calls_per_minute} calls/min, delay: {self.delay}s"
        )

    def wait(self):
        """Wait if necessary to respect rate limit"""
        elapsed = time.time() - self.last_call
        if elapsed < self.delay:
            wait_time = self.delay - elapsed
            log_debug(f"Rate limiting: waiting {wait_time:.2f}s")
            time.sleep(wait_time)
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
        log_info("Initializing AlphaVantageClient")

        if api_key:
            self.api_key = api_key
            log_debug("Using provided API key")
        else:
            log_debug("Fetching API key from Forex Settings")
            try:
                settings = frappe.get_single("Forex Settings")
                self.api_key = settings.get_password("api_key")
                log_debug("API key loaded from settings")
            except Exception as e:
                log_error(f"Failed to load Forex Settings: {str(e)}")
                frappe.log_error(
                    frappe.get_traceback(), "Peasforex: Settings Load Error"
                )
                raise

        if not self.api_key:
            log_error("No API key configured")
            raise ValueError(_("Alpha Vantage API key is not configured"))

        self.rate_limiter = RateLimiter(calls_per_minute=75)  # Premium tier
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ERPNext-Peasforex/1.0"})
        log_info("AlphaVantageClient initialized successfully")

    def _make_request(self, params):
        """
        Make an API request with rate limiting and error handling.

        Args:
            params: Dictionary of query parameters

        Returns:
            dict: API response data
        """
        params["apikey"] = self.api_key

        # Log request (without API key)
        safe_params = {k: v for k, v in params.items() if k != "apikey"}
        log_debug(f"Making API request", safe_params)

        # Apply rate limiting
        self.rate_limiter.wait()

        try:
            log_debug(f"Sending GET request to {self.BASE_URL}")
            response = self.session.get(
                self.BASE_URL, params=params, timeout=self.DEFAULT_TIMEOUT
            )

            log_debug(f"Response status code: {response.status_code}")
            response.raise_for_status()

            data = response.json()

            # Log raw response keys for debugging
            log_debug(f"Response keys: {list(data.keys())}")

            # Check for API error messages
            if "Error Message" in data:
                log_error(f"API Error: {data['Error Message']}")
                return {"error": data["Error Message"], "raw": data}

            if "Note" in data:
                # Rate limit exceeded
                log_error(f"Rate limited: {data['Note']}")
                return {"error": data["Note"], "rate_limited": True, "raw": data}

            if "Information" in data:
                # Usually means API key issues
                log_error(f"API Information: {data['Information']}")
                return {"error": data["Information"], "raw": data}

            log_debug("API request successful")
            return data

        except requests.exceptions.Timeout:
            log_error("API request timed out")
            frappe.log_error("Alpha Vantage API timeout", "Forex API Error")
            return {"error": _("API request timed out")}
        except requests.exceptions.RequestException as e:
            log_error(f"Request exception: {str(e)}")
            frappe.log_error(f"Alpha Vantage API error: {str(e)}", "Forex API Error")
            return {"error": str(e)}
        except ValueError as e:
            log_error(f"JSON parsing error: {str(e)}")
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
        log_info(f"Getting exchange rate: {from_currency} -> {to_currency}")

        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_currency,
            "to_currency": to_currency,
        }

        data = self._make_request(params)

        if "error" in data:
            return data

        try:
            rate_data = data.get("Realtime Currency Exchange Rate", {})

            if not rate_data:
                log_error(
                    f"No rate data in response for {from_currency}->{to_currency}"
                )
                log_debug(f"Raw response: {json.dumps(data, indent=2)[:500]}")
                return {"error": "No exchange rate data in response", "raw": data}

            exchange_rate = float(rate_data.get("5. Exchange Rate", 0))
            bid_price = float(rate_data.get("8. Bid Price", 0))
            ask_price = float(rate_data.get("9. Ask Price", 0))

            log_info(f"Exchange rate {from_currency}->{to_currency}: {exchange_rate}")

            return {
                "exchange_rate": exchange_rate,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "from_currency": rate_data.get("1. From_Currency Code"),
                "to_currency": rate_data.get("3. To_Currency Code"),
                "last_refreshed": rate_data.get("6. Last Refreshed"),
                "raw": data,
            }
        except (KeyError, TypeError, ValueError) as e:
            log_error(f"Failed to parse exchange rate: {str(e)}")
            return {"error": f"Failed to parse exchange rate: {str(e)}", "raw": data}

    def get_fx_daily(
        self, from_currency, to_currency, outputsize="compact", try_reverse=True
    ):
        """
        Get daily forex time series data.

        This uses the FX_DAILY endpoint which returns OHLC data.
        If no data is returned, will try the reverse pair and calculate inverse rates.

        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            outputsize: 'compact' (last 100 days) or 'full' (20+ years)
            try_reverse: If True, try reverse pair if direct pair fails

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
                'raw': dict,
                'is_inverse': bool  # True if rates were calculated from reverse pair
            }
        """
        log_info(
            f"Getting FX daily: {from_currency} -> {to_currency} (outputsize: {outputsize})"
        )

        params = {
            "function": "FX_DAILY",
            "from_symbol": from_currency,
            "to_symbol": to_currency,
            "outputsize": outputsize,
        }

        data = self._make_request(params)

        if "error" in data:
            return data

        try:
            meta_data = data.get("Meta Data", {})
            time_series_raw = data.get("Time Series FX (Daily)", {})

            if not time_series_raw:
                log_warning(f"No time series data for {from_currency}->{to_currency}")
                log_debug(f"Raw response keys: {list(data.keys())}")

                # Try reverse pair if enabled
                if try_reverse:
                    log_info(f"Trying reverse pair: {to_currency} -> {from_currency}")
                    reverse_result = self.get_fx_daily(
                        to_currency,
                        from_currency,
                        outputsize=outputsize,
                        try_reverse=False,  # Prevent infinite recursion
                    )

                    if "error" not in reverse_result and reverse_result.get(
                        "time_series"
                    ):
                        log_info(f"Reverse pair successful, calculating inverse rates")
                        return self._invert_time_series(
                            reverse_result, from_currency, to_currency
                        )
                    else:
                        log_error(
                            f"Reverse pair also failed for {to_currency}->{from_currency}"
                        )

                return {
                    "error": "No time series data in response",
                    "raw": data,
                    "no_data": True,
                }

            time_series = {}
            for date_str, values in time_series_raw.items():
                time_series[date_str] = {
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                }

            log_info(f"Received {len(time_series)} daily data points")

            return {
                "time_series": time_series,
                "meta_data": meta_data,
                "raw": data,
                "is_inverse": False,
            }
        except (KeyError, TypeError, ValueError) as e:
            log_error(f"Failed to parse daily data: {str(e)}")
            return {"error": f"Failed to parse daily data: {str(e)}", "raw": data}

    def _invert_time_series(self, result, original_from, original_to):
        """
        Invert time series data (calculate 1/rate for each data point).

        When converting from reverse pair, we need to:
        - Invert all rates (1/rate)
        - Swap high and low (1/high becomes low, 1/low becomes high)

        Args:
            result: Original result dict with time_series
            original_from: The original from_currency requested
            original_to: The original to_currency requested

        Returns:
            dict: Result with inverted rates
        """
        time_series = result.get("time_series", {})
        inverted_series = {}

        for date_str, values in time_series.items():
            # Invert all values, swap high/low
            open_rate = values.get("open", 0)
            high_rate = values.get("high", 0)
            low_rate = values.get("low", 0)
            close_rate = values.get("close", 0)

            inverted_series[date_str] = {
                "open": 1.0 / open_rate if open_rate else 0,
                "high": 1.0 / low_rate
                if low_rate
                else 0,  # Inverted: 1/low becomes high
                "low": 1.0 / high_rate
                if high_rate
                else 0,  # Inverted: 1/high becomes low
                "close": 1.0 / close_rate if close_rate else 0,
            }

        log_info(
            f"Inverted {len(inverted_series)} data points for {original_from}->{original_to}"
        )

        return {
            "time_series": inverted_series,
            "meta_data": {
                "note": f"Calculated from inverse pair {original_to}/{original_from}",
                "original_meta": result.get("meta_data", {}),
            },
            "raw": result.get("raw", {}),
            "is_inverse": True,
        }

    def get_fx_daily_with_fallback(
        self, from_currency, to_currency, outputsize="compact"
    ):
        """
        Get daily forex data with multiple fallback strategies.

        Order of attempts:
        1. Direct FX_DAILY call
        2. Reverse pair with inverse calculation
        3. Current spot rate (for today only)

        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            outputsize: 'compact' or 'full'

        Returns:
            dict: Result with time_series or error
        """
        pair_str = f"{from_currency}->{to_currency}"
        log_info(f"Getting FX daily with fallback: {pair_str}")

        # Try direct and reverse pair
        result = self.get_fx_daily(
            from_currency, to_currency, outputsize, try_reverse=True
        )

        if "error" not in result:
            return result

        # If both failed, try spot rate as last resort
        if result.get("no_data"):
            log_warning(f"No historical data for {pair_str}, trying spot rate fallback")
            spot_result = self.get_exchange_rate(from_currency, to_currency)

            if "error" not in spot_result and spot_result.get("exchange_rate"):
                from datetime import datetime

                today = datetime.now().strftime("%Y-%m-%d")
                rate = spot_result["exchange_rate"]

                log_info(f"Using spot rate fallback for {pair_str}: {rate}")

                return {
                    "time_series": {
                        today: {"open": rate, "high": rate, "low": rate, "close": rate}
                    },
                    "meta_data": {
                        "note": "Spot rate fallback - only today's rate available",
                        "fallback": True,
                    },
                    "raw": spot_result.get("raw", {}),
                    "is_inverse": False,
                    "is_spot_fallback": True,
                }

        return result

    def get_fx_monthly(self, from_currency, to_currency, try_reverse=True):
        """
        Get monthly forex time series data.

        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            try_reverse: If True, try reverse pair if direct pair fails

        Returns:
            dict: Similar to get_fx_daily but with monthly data
        """
        log_info(f"Getting FX monthly: {from_currency} -> {to_currency}")

        params = {
            "function": "FX_MONTHLY",
            "from_symbol": from_currency,
            "to_symbol": to_currency,
        }

        data = self._make_request(params)

        if "error" in data:
            return data

        try:
            meta_data = data.get("Meta Data", {})
            time_series_raw = data.get("Time Series FX (Monthly)", {})

            if not time_series_raw:
                log_warning(
                    f"No monthly time series data for {from_currency}->{to_currency}"
                )

                # Try reverse pair
                if try_reverse:
                    log_info(
                        f"Trying reverse monthly pair: {to_currency} -> {from_currency}"
                    )
                    reverse_result = self.get_fx_monthly(
                        to_currency, from_currency, try_reverse=False
                    )

                    if "error" not in reverse_result and reverse_result.get(
                        "time_series"
                    ):
                        log_info(
                            f"Reverse monthly pair successful, calculating inverse"
                        )
                        return self._invert_time_series(
                            reverse_result, from_currency, to_currency
                        )

                return {
                    "error": "No time series data in response",
                    "raw": data,
                    "no_data": True,
                }

            time_series = {}
            for date_str, values in time_series_raw.items():
                time_series[date_str] = {
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                }

            log_info(f"Received {len(time_series)} monthly data points")

            return {
                "time_series": time_series,
                "meta_data": meta_data,
                "raw": data,
                "is_inverse": False,
            }
        except (KeyError, TypeError, ValueError) as e:
            log_error(f"Failed to parse monthly data: {str(e)}")
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

        log_info(f"Getting previous month rates: {from_currency} -> {to_currency}")

        # Get previous month date range
        today = datetime.now()
        first_of_this_month = today.replace(day=1)
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        first_of_prev_month = last_of_prev_month.replace(day=1)

        log_debug(
            f"Previous month: {first_of_prev_month.strftime('%Y-%m-%d')} to {last_of_prev_month.strftime('%Y-%m-%d')}"
        )

        # Get daily data with fallback (compact should cover last 100 days which is enough)
        daily_data = self.get_fx_daily_with_fallback(
            from_currency, to_currency, outputsize="compact"
        )

        if "error" in daily_data:
            return daily_data

        time_series = daily_data.get("time_series", {})

        if not time_series:
            log_error("No time series data available")
            return {"error": "No time series data available"}

        # Check if this is spot rate fallback (only today's rate)
        if daily_data.get("is_spot_fallback"):
            log_warning(
                f"Only spot rate available for {from_currency}->{to_currency}, using as estimate"
            )
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str in time_series:
                rate = time_series[today_str]["close"]
                return {
                    "closing_rate": rate,
                    "average_rate": rate,
                    "high_rate": rate,
                    "low_rate": rate,
                    "month": last_of_prev_month.strftime("%Y-%m"),
                    "month_end_date": last_of_prev_month.strftime("%Y-%m-%d"),
                    "data_points": 1,
                    "is_estimate": True,
                    "note": "Using current spot rate as estimate - historical data unavailable",
                }

        # Filter for previous month
        prev_month_rates = []
        closing_rate = None

        for date_str, values in sorted(time_series.items(), reverse=True):
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")

                # Check if in previous month
                if (
                    date.year == last_of_prev_month.year
                    and date.month == last_of_prev_month.month
                ):
                    prev_month_rates.append(
                        {
                            "date": date_str,
                            "close": values["close"],
                            "high": values["high"],
                            "low": values["low"],
                        }
                    )

                    # The first one we encounter (most recent) is the closing rate
                    if closing_rate is None:
                        closing_rate = values["close"]
            except ValueError:
                continue

        if not prev_month_rates:
            log_error(
                f"No data available for previous month ({last_of_prev_month.strftime('%Y-%m')})"
            )
            return {
                "error": f"No data available for previous month ({last_of_prev_month.strftime('%Y-%m')})"
            }

        # Calculate averages and extremes
        closes = [r["close"] for r in prev_month_rates]
        highs = [r["high"] for r in prev_month_rates]
        lows = [r["low"] for r in prev_month_rates]

        avg_rate = sum(closes) / len(closes)
        high_rate = max(highs)
        low_rate = min(lows)

        log_info(
            f"Previous month rates calculated: closing={closing_rate}, avg={avg_rate:.6f}, high={high_rate}, low={low_rate}, data_points={len(prev_month_rates)}"
        )

        result = {
            "closing_rate": closing_rate,
            "average_rate": avg_rate,
            "high_rate": high_rate,  # Prudency for expenses
            "low_rate": low_rate,  # Prudency for income
            "month": last_of_prev_month.strftime("%Y-%m"),
            "month_end_date": last_of_prev_month.strftime("%Y-%m-%d"),
            "data_points": len(prev_month_rates),
            "raw_data": prev_month_rates,
        }

        # Add note if inverse rates were used
        if daily_data.get("is_inverse"):
            result["note"] = (
                f"Rates calculated from inverse pair {to_currency}/{from_currency}"
            )
            result["is_inverse"] = True

        return result
