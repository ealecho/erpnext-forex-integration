# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now, today, getdate, add_months, get_first_day, get_last_day
from datetime import datetime, timedelta


def get_settings():
    """Get Forex Settings singleton"""
    return frappe.get_single("Forex Settings")


def is_enabled():
    """Check if forex integration is enabled"""
    settings = get_settings()
    return settings.enabled and settings.api_key


def log_sync(sync_type, currency_pair, status, exchange_rate=None, error_message=None, api_response=None):
    """Create a sync log entry"""
    from peasforex.peasforex.doctype.forex_sync_log.forex_sync_log import log_sync as _log_sync
    return _log_sync(sync_type, currency_pair, status, exchange_rate, error_message, api_response)


def update_currency_exchange(from_currency, to_currency, rate, date, for_buying=1, for_selling=1):
    """
    Create or update ERPNext Currency Exchange record.
    
    Args:
        from_currency: Source currency
        to_currency: Target currency
        rate: Exchange rate
        date: Rate date
        for_buying: Apply to buying transactions
        for_selling: Apply to selling transactions
    """
    # Check if entry exists
    existing = frappe.db.get_value("Currency Exchange", {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "date": date
    }, "name")
    
    if existing:
        frappe.db.set_value("Currency Exchange", existing, "exchange_rate", rate)
        frappe.db.set_value("Currency Exchange", existing, "for_buying", for_buying)
        frappe.db.set_value("Currency Exchange", existing, "for_selling", for_selling)
    else:
        doc = frappe.get_doc({
            "doctype": "Currency Exchange",
            "date": date,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "exchange_rate": rate,
            "for_buying": for_buying,
            "for_selling": for_selling
        })
        doc.insert(ignore_permissions=True)
    
    frappe.db.commit()


def create_bidirectional_rate(from_currency, to_currency, rate, date):
    """Create both forward and reverse exchange rates"""
    settings = get_settings()
    
    # Forward rate
    update_currency_exchange(from_currency, to_currency, rate, date)
    
    # Reverse rate if bidirectional is enabled
    if settings.create_bidirectional_rates and rate > 0:
        reverse_rate = 1 / rate
        update_currency_exchange(to_currency, from_currency, reverse_rate, date)


def store_rate_log(from_currency, to_currency, rate_date, rate_type, exchange_rate,
                   open_rate=None, high_rate=None, low_rate=None, close_rate=None,
                   api_response=None):
    """Store rate in Forex Rate Log for historical tracking"""
    from peasforex.peasforex.doctype.forex_rate_log.forex_rate_log import ForexRateLog
    return ForexRateLog.log_rate(
        from_currency=from_currency,
        to_currency=to_currency,
        rate_date=rate_date,
        rate_type=rate_type,
        exchange_rate=exchange_rate,
        open_rate=open_rate,
        high_rate=high_rate,
        low_rate=low_rate,
        close_rate=close_rate,
        api_response=api_response
    )


def check_and_sync_daily():
    """
    Fallback daily task to ensure sync happens.
    Called by scheduler as a backup to cron job.
    """
    if not is_enabled():
        return
    
    settings = get_settings()
    
    # Check if we've synced today
    if settings.last_daily_sync:
        last_sync_date = getdate(settings.last_daily_sync)
        if last_sync_date == getdate(today()):
            # Already synced today
            return
    
    # Run sync
    sync_daily_spot_rates()


def sync_daily_spot_rates():
    """
    Sync daily spot rates for all enabled currency pairs.
    
    This is the main daily sync task that fetches current
    exchange rates and updates ERPNext Currency Exchange.
    """
    if not is_enabled():
        frappe.log_error("Forex integration is not enabled", "Forex Sync Skipped")
        return
    
    from peasforex.api.alpha_vantage import AlphaVantageClient
    
    settings = get_settings()
    enabled_pairs = settings.get_enabled_pairs()
    
    if not enabled_pairs:
        frappe.log_error("No enabled currency pairs configured", "Forex Sync Error")
        return
    
    client = AlphaVantageClient()
    current_date = today()
    success_count = 0
    error_count = 0
    
    for pair in enabled_pairs:
        if not pair.get("sync_spot_daily"):
            continue
        
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        pair_str = f"{from_currency}-{to_currency}"
        
        try:
            # Fetch current rate
            result = client.get_exchange_rate(from_currency, to_currency)
            
            if result.get("error"):
                log_sync(
                    sync_type="Spot (Daily)",
                    currency_pair=pair_str,
                    status="Error",
                    error_message=result.get("error"),
                    api_response=result.get("raw")
                )
                error_count += 1
                continue
            
            rate = result.get("exchange_rate")
            
            if not rate or rate <= 0:
                log_sync(
                    sync_type="Spot (Daily)",
                    currency_pair=pair_str,
                    status="Error",
                    error_message="Invalid exchange rate received",
                    api_response=result.get("raw")
                )
                error_count += 1
                continue
            
            # Update Currency Exchange
            if settings.auto_update_currency_exchange:
                create_bidirectional_rate(from_currency, to_currency, rate, current_date)
            
            # Store in rate log
            if settings.store_historical_data:
                store_rate_log(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate_date=current_date,
                    rate_type="Spot",
                    exchange_rate=rate,
                    api_response=result.get("raw")
                )
            
            # Log success
            log_sync(
                sync_type="Spot (Daily)",
                currency_pair=pair_str,
                status="Success",
                exchange_rate=rate,
                api_response=result.get("raw")
            )
            success_count += 1
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Forex Sync Error: {pair_str}")
            log_sync(
                sync_type="Spot (Daily)",
                currency_pair=pair_str,
                status="Error",
                error_message=str(e)
            )
            error_count += 1
    
    # Update last sync time
    frappe.db.set_value("Forex Settings", "Forex Settings", "last_daily_sync", now())
    frappe.db.commit()
    
    frappe.logger().info(f"Forex daily sync completed: {success_count} success, {error_count} errors")


def sync_monthly_rates():
    """
    Sync monthly rates (Closing, Average, Prudency) for all enabled currency pairs.
    
    This is run on the 1st of each month to get rates for the previous month.
    """
    if not is_enabled():
        frappe.log_error("Forex integration is not enabled", "Forex Sync Skipped")
        return
    
    from peasforex.api.alpha_vantage import AlphaVantageClient
    
    settings = get_settings()
    enabled_pairs = settings.get_enabled_pairs()
    
    if not enabled_pairs:
        return
    
    client = AlphaVantageClient()
    
    # Get previous month dates
    today_date = getdate(today())
    first_of_this_month = get_first_day(today_date)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = get_first_day(last_of_prev_month)
    
    success_count = 0
    error_count = 0
    
    for pair in enabled_pairs:
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        pair_str = f"{from_currency}-{to_currency}"
        
        try:
            # Get previous month rates
            result = client.get_previous_month_rates(from_currency, to_currency)
            
            if result.get("error"):
                log_sync(
                    sync_type="Closing (Monthly)",
                    currency_pair=pair_str,
                    status="Error",
                    error_message=result.get("error")
                )
                error_count += 1
                continue
            
            month_end_date = result.get("month_end_date")
            
            # Sync Closing Rate
            if pair.get("sync_closing_monthly") and result.get("closing_rate"):
                closing_rate = result.get("closing_rate")
                
                if settings.auto_update_currency_exchange:
                    # For closing, we create a record dated at month end
                    create_bidirectional_rate(from_currency, to_currency, closing_rate, month_end_date)
                
                if settings.store_historical_data:
                    store_rate_log(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        rate_date=month_end_date,
                        rate_type="Closing",
                        exchange_rate=closing_rate
                    )
                
                log_sync(
                    sync_type="Closing (Monthly)",
                    currency_pair=pair_str,
                    status="Success",
                    exchange_rate=closing_rate
                )
            
            # Sync Monthly Average
            if pair.get("sync_average_monthly") and result.get("average_rate"):
                avg_rate = result.get("average_rate")
                
                if settings.store_historical_data:
                    store_rate_log(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        rate_date=month_end_date,
                        rate_type="Monthly Average",
                        exchange_rate=avg_rate
                    )
                
                log_sync(
                    sync_type="Monthly Average",
                    currency_pair=pair_str,
                    status="Success",
                    exchange_rate=avg_rate
                )
            
            # Sync Prudency Rates (High and Low)
            if pair.get("sync_prudency_monthly"):
                # Prudency High (for expenses - worst case is higher rate)
                if result.get("high_rate"):
                    high_rate = result.get("high_rate")
                    
                    if settings.store_historical_data:
                        store_rate_log(
                            from_currency=from_currency,
                            to_currency=to_currency,
                            rate_date=month_end_date,
                            rate_type="Prudency (High)",
                            exchange_rate=high_rate
                        )
                    
                    log_sync(
                        sync_type="Prudency",
                        currency_pair=f"{pair_str} (High)",
                        status="Success",
                        exchange_rate=high_rate
                    )
                
                # Prudency Low (for income - worst case is lower rate)
                if result.get("low_rate"):
                    low_rate = result.get("low_rate")
                    
                    if settings.store_historical_data:
                        store_rate_log(
                            from_currency=from_currency,
                            to_currency=to_currency,
                            rate_date=month_end_date,
                            rate_type="Prudency (Low)",
                            exchange_rate=low_rate
                        )
                    
                    log_sync(
                        sync_type="Prudency",
                        currency_pair=f"{pair_str} (Low)",
                        status="Success",
                        exchange_rate=low_rate
                    )
            
            success_count += 1
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Forex Monthly Sync Error: {pair_str}")
            log_sync(
                sync_type="Closing (Monthly)",
                currency_pair=pair_str,
                status="Error",
                error_message=str(e)
            )
            error_count += 1
    
    # Update last monthly sync time
    frappe.db.set_value("Forex Settings", "Forex Settings", "last_monthly_sync", now())
    frappe.db.commit()
    
    frappe.logger().info(f"Forex monthly sync completed: {success_count} success, {error_count} errors")


def backfill_historical_rates(months=2):
    """
    Backfill historical exchange rate data for the specified number of months.
    
    Args:
        months: Number of months to backfill (default: 2)
    """
    if not is_enabled():
        frappe.log_error("Forex integration is not enabled", "Forex Backfill Skipped")
        return
    
    from peasforex.api.alpha_vantage import AlphaVantageClient
    
    settings = get_settings()
    enabled_pairs = settings.get_enabled_pairs()
    
    if not enabled_pairs:
        return
    
    client = AlphaVantageClient()
    
    # Calculate date range
    today_date = getdate(today())
    start_date = get_first_day(add_months(today_date, -months))
    
    success_count = 0
    error_count = 0
    
    for pair in enabled_pairs:
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        pair_str = f"{from_currency}-{to_currency}"
        
        try:
            # Get daily data (full to ensure we have enough history)
            result = client.get_fx_daily(from_currency, to_currency, outputsize="full")
            
            if result.get("error"):
                log_sync(
                    sync_type="Backfill",
                    currency_pair=pair_str,
                    status="Error",
                    error_message=result.get("error")
                )
                error_count += 1
                continue
            
            time_series = result.get("time_series", {})
            
            if not time_series:
                log_sync(
                    sync_type="Backfill",
                    currency_pair=pair_str,
                    status="Error",
                    error_message="No time series data returned"
                )
                error_count += 1
                continue
            
            # Process each day in the backfill range
            days_processed = 0
            for date_str, values in time_series.items():
                try:
                    rate_date = getdate(date_str)
                    
                    # Skip if before start date
                    if rate_date < start_date:
                        continue
                    
                    # Skip if in the future
                    if rate_date > today_date:
                        continue
                    
                    close_rate = values.get("close", 0)
                    
                    if close_rate <= 0:
                        continue
                    
                    # Update Currency Exchange
                    if settings.auto_update_currency_exchange:
                        create_bidirectional_rate(from_currency, to_currency, close_rate, date_str)
                    
                    # Store in rate log
                    if settings.store_historical_data:
                        store_rate_log(
                            from_currency=from_currency,
                            to_currency=to_currency,
                            rate_date=date_str,
                            rate_type="Spot",
                            exchange_rate=close_rate,
                            open_rate=values.get("open"),
                            high_rate=values.get("high"),
                            low_rate=values.get("low"),
                            close_rate=values.get("close")
                        )
                    
                    days_processed += 1
                    
                except Exception as e:
                    frappe.log_error(f"Error processing {date_str}: {str(e)}", "Forex Backfill Error")
                    continue
            
            log_sync(
                sync_type="Backfill",
                currency_pair=pair_str,
                status="Success",
                error_message=f"Processed {days_processed} days"
            )
            success_count += 1
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Forex Backfill Error: {pair_str}")
            log_sync(
                sync_type="Backfill",
                currency_pair=pair_str,
                status="Error",
                error_message=str(e)
            )
            error_count += 1
    
    # Also backfill monthly rates for each past month
    for i in range(1, months + 1):
        month_date = add_months(today_date, -i)
        backfill_month_rates(month_date, client, enabled_pairs, settings)
    
    frappe.logger().info(f"Forex backfill completed: {success_count} pairs success, {error_count} errors")


def backfill_month_rates(month_date, client, enabled_pairs, settings):
    """
    Backfill monthly rates (closing, average, prudency) for a specific month.
    """
    from datetime import datetime
    
    first_of_month = get_first_day(month_date)
    last_of_month = get_last_day(month_date)
    
    for pair in enabled_pairs:
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        pair_str = f"{from_currency}-{to_currency}"
        
        try:
            # Get daily data
            result = client.get_fx_daily(from_currency, to_currency, outputsize="full")
            
            if result.get("error"):
                continue
            
            time_series = result.get("time_series", {})
            
            # Filter for the target month
            month_rates = []
            closing_rate = None
            
            for date_str, values in sorted(time_series.items(), reverse=True):
                try:
                    rate_date = getdate(date_str)
                    
                    if rate_date >= first_of_month and rate_date <= last_of_month:
                        month_rates.append({
                            "date": date_str,
                            "close": values.get("close", 0),
                            "high": values.get("high", 0),
                            "low": values.get("low", 0)
                        })
                        
                        if closing_rate is None:
                            closing_rate = values.get("close", 0)
                except:
                    continue
            
            if not month_rates:
                continue
            
            month_end_str = str(last_of_month)
            
            # Store closing rate
            if closing_rate and closing_rate > 0 and settings.store_historical_data:
                store_rate_log(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate_date=month_end_str,
                    rate_type="Closing",
                    exchange_rate=closing_rate
                )
            
            # Calculate and store average
            closes = [r["close"] for r in month_rates if r["close"] > 0]
            if closes:
                avg_rate = sum(closes) / len(closes)
                if settings.store_historical_data:
                    store_rate_log(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        rate_date=month_end_str,
                        rate_type="Monthly Average",
                        exchange_rate=avg_rate
                    )
            
            # Calculate and store prudency rates
            highs = [r["high"] for r in month_rates if r["high"] > 0]
            lows = [r["low"] for r in month_rates if r["low"] > 0]
            
            if highs and settings.store_historical_data:
                store_rate_log(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate_date=month_end_str,
                    rate_type="Prudency (High)",
                    exchange_rate=max(highs)
                )
            
            if lows and settings.store_historical_data:
                store_rate_log(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate_date=month_end_str,
                    rate_type="Prudency (Low)",
                    exchange_rate=min(lows)
                )
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Forex Month Backfill Error: {pair_str}")
            continue
