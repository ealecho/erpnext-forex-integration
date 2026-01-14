# Copyright (c) 2024, ERP Champions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now, today, getdate, add_months, get_first_day, get_last_day
from datetime import datetime, timedelta

# Module-level logger
logger = frappe.logger("peasforex", allow_site=True, file_count=5)


def log_debug(message, data=None):
    """Log debug message with optional data"""
    if data:
        logger.debug(f"[Peasforex] {message}: {data}")
    else:
        logger.debug(f"[Peasforex] {message}")


def log_info(message, data=None):
    """Log info message with optional data"""
    if data:
        logger.info(f"[Peasforex] {message}: {data}")
    else:
        logger.info(f"[Peasforex] {message}")


def log_error(message, data=None):
    """Log error message with optional data"""
    if data:
        logger.error(f"[Peasforex] {message}: {data}")
    else:
        logger.error(f"[Peasforex] {message}")


def get_settings():
    """Get Forex Settings singleton"""
    log_debug("Fetching Forex Settings")
    try:
        settings = frappe.get_single("Forex Settings")
        log_debug("Forex Settings loaded", {
            "enabled": settings.enabled,
            "has_api_key": bool(settings.api_key),
            "create_bidirectional": settings.create_bidirectional_rates,
            "auto_update": settings.auto_update_currency_exchange,
            "store_historical": settings.store_historical_data,
            "apply_to_all": settings.apply_to_all_companies
        })
        return settings
    except Exception as e:
        log_error(f"Failed to load Forex Settings: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Peasforex: Failed to load settings")
        raise


def is_enabled():
    """Check if forex integration is enabled"""
    settings = get_settings()
    enabled = settings.enabled and settings.api_key
    log_debug(f"Integration enabled check: {enabled}")
    return enabled


def log_sync(sync_type, currency_pair, status, exchange_rate=None, error_message=None, api_response=None):
    """Create a sync log entry"""
    log_debug(f"Creating sync log: {sync_type} | {currency_pair} | {status}")
    try:
        from peasforex.peasforex.doctype.forex_sync_log.forex_sync_log import log_sync as _log_sync
        return _log_sync(sync_type, currency_pair, status, exchange_rate, error_message, api_response)
    except Exception as e:
        log_error(f"Failed to create sync log: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Peasforex: Sync log creation failed")
        return None


def get_default_company():
    """Get the default company for Currency Exchange records"""
    log_debug("Getting default company")
    
    # Try to get from Global Defaults
    default_company = frappe.db.get_single_value("Global Defaults", "default_company")
    if default_company:
        log_debug(f"Default company from Global Defaults: {default_company}")
        return default_company
    
    # Fallback: get first company
    companies = frappe.get_all("Company", limit=1, pluck="name")
    if companies:
        log_debug(f"Using first company: {companies[0]}")
        return companies[0]
    
    log_error("No company found in the system")
    return None


def update_currency_exchange(from_currency, to_currency, rate, date, for_buying=1, for_selling=1, company=None):
    """
    Create or update ERPNext Currency Exchange record.
    
    Args:
        from_currency: Source currency
        to_currency: Target currency
        rate: Exchange rate
        date: Rate date
        for_buying: Apply to buying transactions
        for_selling: Apply to selling transactions
        company: Target company (optional, uses default if not specified)
    """
    log_info(f"Updating Currency Exchange: {from_currency} -> {to_currency} @ {rate} on {date} (company: {company or 'default'})")
    
    try:
        # Check if Currency Exchange requires company field
        meta = frappe.get_meta("Currency Exchange")
        has_company_field = meta.has_field("company")
        company_is_mandatory = False
        
        if has_company_field:
            company_field = meta.get_field("company")
            company_is_mandatory = company_field.reqd if company_field else False
            log_debug(f"Currency Exchange has company field: {has_company_field}, mandatory: {company_is_mandatory}")
        
        # Build filter for existing check
        filters = {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "date": date
        }
        
        # Check if entry exists
        existing = frappe.db.get_value("Currency Exchange", filters, "name")
        log_debug(f"Existing Currency Exchange record: {existing}")
        
        if existing:
            log_debug(f"Updating existing record: {existing}")
            frappe.db.set_value("Currency Exchange", existing, "exchange_rate", rate)
            frappe.db.set_value("Currency Exchange", existing, "for_buying", for_buying)
            frappe.db.set_value("Currency Exchange", existing, "for_selling", for_selling)
            log_info(f"Updated Currency Exchange {existing} with rate {rate}")
        else:
            log_debug("Creating new Currency Exchange record")
            doc_data = {
                "doctype": "Currency Exchange",
                "date": date,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "exchange_rate": rate,
                "for_buying": for_buying,
                "for_selling": for_selling
            }
            
            # Add company if required
            if has_company_field and company_is_mandatory:
                # Use provided company, or fall back to default
                target_company = company or get_default_company()
                if target_company:
                    doc_data["company"] = target_company
                    log_debug(f"Adding company to Currency Exchange: {target_company}")
                else:
                    log_error("Company is mandatory but no company found")
                    frappe.log_error(
                        "Currency Exchange requires company but no company found in system",
                        "Peasforex: Company Required"
                    )
                    return
            elif has_company_field and company:
                # Field exists but not mandatory - still use if provided
                doc_data["company"] = company
                log_debug(f"Adding optional company to Currency Exchange: {company}")
            
            log_debug(f"Creating Currency Exchange with data: {doc_data}")
            doc = frappe.get_doc(doc_data)
            doc.insert(ignore_permissions=True)
            log_info(f"Created Currency Exchange {doc.name} with rate {rate}")
        
        frappe.db.commit()
        
    except Exception as e:
        log_error(f"Failed to update Currency Exchange: {str(e)}")
        frappe.log_error(
            f"Failed to create/update Currency Exchange\n"
            f"From: {from_currency}, To: {to_currency}, Rate: {rate}, Date: {date}\n"
            f"Error: {str(e)}\n\n"
            f"{frappe.get_traceback()}",
            "Peasforex: Currency Exchange Error"
        )
        raise


def create_bidirectional_rate(from_currency, to_currency, rate, date, company=None):
    """Create both forward and reverse exchange rates"""
    log_info(f"Creating bidirectional rate: {from_currency} <-> {to_currency} @ {rate} (company: {company or 'default'})")
    
    settings = get_settings()
    
    # Forward rate
    log_debug(f"Creating forward rate: {from_currency} -> {to_currency}")
    update_currency_exchange(from_currency, to_currency, rate, date, company=company)
    
    # Reverse rate if bidirectional is enabled
    if settings.create_bidirectional_rates and rate > 0:
        reverse_rate = 1 / rate
        log_debug(f"Creating reverse rate: {to_currency} -> {from_currency} @ {reverse_rate}")
        update_currency_exchange(to_currency, from_currency, reverse_rate, date, company=company)


def store_rate_log(from_currency, to_currency, rate_date, rate_type, exchange_rate,
                   open_rate=None, high_rate=None, low_rate=None, close_rate=None,
                   api_response=None):
    """Store rate in Forex Rate Log for historical tracking"""
    log_debug(f"Storing rate log: {from_currency}-{to_currency} | {rate_type} | {exchange_rate}")
    
    try:
        from peasforex.peasforex.doctype.forex_rate_log.forex_rate_log import ForexRateLog
        doc = ForexRateLog.log_rate(
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
        log_debug(f"Rate log stored: {doc.name if doc else 'None'}")
        return doc
    except Exception as e:
        log_error(f"Failed to store rate log: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Peasforex: Rate log storage failed")
        return None


def check_and_sync_daily():
    """
    Fallback daily task to ensure sync happens.
    Called by scheduler as a backup to cron job.
    """
    log_info("Running check_and_sync_daily")
    
    if not is_enabled():
        log_debug("Integration not enabled, skipping")
        return
    
    settings = get_settings()
    
    # Check if we've synced today
    if settings.last_daily_sync:
        last_sync_date = getdate(settings.last_daily_sync)
        today_date = getdate(today())
        log_debug(f"Last sync date: {last_sync_date}, Today: {today_date}")
        
        if last_sync_date == today_date:
            log_debug("Already synced today, skipping")
            return
    
    # Run sync
    log_info("Running daily sync from fallback task")
    sync_daily_spot_rates()


def sync_daily_spot_rates():
    """
    Sync daily spot rates for all enabled currency pairs.
    
    This is the main daily sync task that fetches current
    exchange rates and updates ERPNext Currency Exchange.
    """
    log_info("=" * 50)
    log_info("Starting sync_daily_spot_rates")
    log_info("=" * 50)
    
    if not is_enabled():
        log_error("Forex integration is not enabled")
        frappe.log_error("Forex integration is not enabled", "Forex Sync Skipped")
        return
    
    try:
        from peasforex.api.alpha_vantage import AlphaVantageClient
    except Exception as e:
        log_error(f"Failed to import AlphaVantageClient: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Peasforex: Import Error")
        return
    
    settings = get_settings()
    enabled_pairs = settings.get_enabled_pairs()
    
    log_info(f"Found {len(enabled_pairs)} enabled currency pairs")
    
    if not enabled_pairs:
        log_error("No enabled currency pairs configured")
        frappe.log_error("No enabled currency pairs configured", "Forex Sync Error")
        return
    
    try:
        client = AlphaVantageClient()
        log_debug("AlphaVantageClient initialized")
    except Exception as e:
        log_error(f"Failed to initialize AlphaVantageClient: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Peasforex: API Client Error")
        return
    
    current_date = today()
    success_count = 0
    error_count = 0
    
    for idx, pair in enumerate(enabled_pairs):
        if not pair.get("sync_spot_daily"):
            log_debug(f"Pair {pair} has sync_spot_daily disabled, skipping")
            continue
        
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        target_company = pair.get("target_company")  # Company-specific rate
        pair_str = f"{from_currency}-{to_currency}"
        
        log_info(f"[{idx+1}/{len(enabled_pairs)}] Processing {pair_str}" + (f" for {target_company}" if target_company else ""))
        
        try:
            # Fetch current rate
            log_debug(f"Fetching exchange rate for {pair_str}")
            result = client.get_exchange_rate(from_currency, to_currency)
            
            if result.get("error"):
                log_error(f"API error for {pair_str}: {result.get('error')}")
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
            log_debug(f"Received rate for {pair_str}: {rate}")
            
            if not rate or rate <= 0:
                log_error(f"Invalid rate received for {pair_str}: {rate}")
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
                log_debug(f"Auto-updating Currency Exchange for {pair_str}")
                try:
                    create_bidirectional_rate(from_currency, to_currency, rate, current_date, company=target_company)
                except Exception as e:
                    log_error(f"Failed to create Currency Exchange for {pair_str}: {str(e)}")
                    # Continue with logging even if Currency Exchange fails
            
            # Store in rate log
            if settings.store_historical_data:
                log_debug(f"Storing historical data for {pair_str}")
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
            log_info(f"Successfully synced {pair_str} @ {rate}")
            
        except Exception as e:
            log_error(f"Exception syncing {pair_str}: {str(e)}")
            frappe.log_error(frappe.get_traceback(), f"Forex Sync Error: {pair_str}")
            log_sync(
                sync_type="Spot (Daily)",
                currency_pair=pair_str,
                status="Error",
                error_message=str(e)
            )
            error_count += 1
    
    # Update last sync time
    log_debug("Updating last_daily_sync timestamp")
    frappe.db.set_value("Forex Settings", "Forex Settings", "last_daily_sync", now())
    frappe.db.commit()
    
    log_info("=" * 50)
    log_info(f"Forex daily sync completed: {success_count} success, {error_count} errors")
    log_info("=" * 50)


def sync_monthly_rates():
    """
    Sync monthly rates (Closing, Average, Prudency) for all enabled currency pairs.
    
    This is run on the 1st of each month to get rates for the previous month.
    """
    log_info("=" * 50)
    log_info("Starting sync_monthly_rates")
    log_info("=" * 50)
    
    if not is_enabled():
        log_error("Forex integration is not enabled")
        frappe.log_error("Forex integration is not enabled", "Forex Sync Skipped")
        return
    
    try:
        from peasforex.api.alpha_vantage import AlphaVantageClient
    except Exception as e:
        log_error(f"Failed to import AlphaVantageClient: {str(e)}")
        return
    
    settings = get_settings()
    enabled_pairs = settings.get_enabled_pairs()
    
    log_info(f"Found {len(enabled_pairs)} enabled currency pairs")
    
    if not enabled_pairs:
        log_error("No enabled currency pairs")
        return
    
    try:
        client = AlphaVantageClient()
    except Exception as e:
        log_error(f"Failed to initialize AlphaVantageClient: {str(e)}")
        return
    
    # Get previous month dates
    today_date = getdate(today())
    first_of_this_month = get_first_day(today_date)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = get_first_day(last_of_prev_month)
    
    log_info(f"Syncing rates for previous month: {first_of_prev_month} to {last_of_prev_month}")
    
    success_count = 0
    error_count = 0
    
    for idx, pair in enumerate(enabled_pairs):
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        target_company = pair.get("target_company")  # Company-specific rate
        pair_str = f"{from_currency}-{to_currency}"
        
        log_info(f"[{idx+1}/{len(enabled_pairs)}] Processing {pair_str}" + (f" for {target_company}" if target_company else ""))
        
        try:
            # Get previous month rates
            log_debug(f"Fetching previous month rates for {pair_str}")
            result = client.get_previous_month_rates(from_currency, to_currency)
            
            if result.get("error"):
                log_error(f"API error for {pair_str}: {result.get('error')}")
                log_sync(
                    sync_type="Closing (Monthly)",
                    currency_pair=pair_str,
                    status="Error",
                    error_message=result.get("error")
                )
                error_count += 1
                continue
            
            month_end_date = result.get("month_end_date")
            log_debug(f"Month end date: {month_end_date}")
            
            # Sync Closing Rate
            if pair.get("sync_closing_monthly") and result.get("closing_rate"):
                closing_rate = result.get("closing_rate")
                log_debug(f"Closing rate: {closing_rate}")
                
                if settings.auto_update_currency_exchange:
                    try:
                        create_bidirectional_rate(from_currency, to_currency, closing_rate, month_end_date, company=target_company)
                    except Exception as e:
                        log_error(f"Failed to create closing rate: {str(e)}")
                
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
                log_debug(f"Average rate: {avg_rate}")
                
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
                    log_debug(f"Prudency high rate: {high_rate}")
                    
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
                    log_debug(f"Prudency low rate: {low_rate}")
                    
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
            log_info(f"Successfully synced monthly rates for {pair_str}")
            
        except Exception as e:
            log_error(f"Exception syncing {pair_str}: {str(e)}")
            frappe.log_error(frappe.get_traceback(), f"Forex Monthly Sync Error: {pair_str}")
            log_sync(
                sync_type="Closing (Monthly)",
                currency_pair=pair_str,
                status="Error",
                error_message=str(e)
            )
            error_count += 1
    
    # Update last monthly sync time
    log_debug("Updating last_monthly_sync timestamp")
    frappe.db.set_value("Forex Settings", "Forex Settings", "last_monthly_sync", now())
    frappe.db.commit()
    
    log_info("=" * 50)
    log_info(f"Forex monthly sync completed: {success_count} success, {error_count} errors")
    log_info("=" * 50)


def backfill_historical_rates(months=2):
    """
    Backfill historical exchange rate data for the specified number of months.
    
    Args:
        months: Number of months to backfill (default: 2)
    """
    log_info("=" * 50)
    log_info(f"Starting backfill_historical_rates for {months} months")
    log_info("=" * 50)
    
    if not is_enabled():
        log_error("Forex integration is not enabled")
        frappe.log_error("Forex integration is not enabled", "Forex Backfill Skipped")
        return
    
    try:
        from peasforex.api.alpha_vantage import AlphaVantageClient
    except Exception as e:
        log_error(f"Failed to import AlphaVantageClient: {str(e)}")
        return
    
    settings = get_settings()
    enabled_pairs = settings.get_enabled_pairs()
    
    log_info(f"Found {len(enabled_pairs)} enabled currency pairs")
    
    if not enabled_pairs:
        log_error("No enabled currency pairs")
        return
    
    try:
        client = AlphaVantageClient()
    except Exception as e:
        log_error(f"Failed to initialize AlphaVantageClient: {str(e)}")
        return
    
    # Calculate date range
    today_date = getdate(today())
    start_date = get_first_day(add_months(today_date, -months))
    
    log_info(f"Backfilling from {start_date} to {today_date}")
    
    success_count = 0
    error_count = 0
    
    for idx, pair in enumerate(enabled_pairs):
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        target_company = pair.get("target_company")  # Company-specific rate
        pair_str = f"{from_currency}-{to_currency}"
        
        log_info(f"[{idx+1}/{len(enabled_pairs)}] Processing {pair_str}" + (f" for {target_company}" if target_company else ""))
        
        try:
            # Get daily data (full to ensure we have enough history)
            log_debug(f"Fetching daily data for {pair_str}")
            result = client.get_fx_daily(from_currency, to_currency, outputsize="full")
            
            if result.get("error"):
                log_error(f"API error for {pair_str}: {result.get('error')}")
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
                log_error(f"No time series data for {pair_str}")
                log_sync(
                    sync_type="Backfill",
                    currency_pair=pair_str,
                    status="Error",
                    error_message="No time series data returned"
                )
                error_count += 1
                continue
            
            log_debug(f"Received {len(time_series)} data points for {pair_str}")
            
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
                        try:
                            create_bidirectional_rate(from_currency, to_currency, close_rate, date_str, company=target_company)
                        except Exception as e:
                            log_error(f"Failed to create rate for {date_str}: {str(e)}")
                    
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
                    log_error(f"Error processing {date_str}: {str(e)}")
                    frappe.log_error(f"Error processing {date_str}: {str(e)}", "Forex Backfill Error")
                    continue
            
            log_sync(
                sync_type="Backfill",
                currency_pair=pair_str,
                status="Success",
                error_message=f"Processed {days_processed} days"
            )
            success_count += 1
            log_info(f"Backfilled {days_processed} days for {pair_str}")
            
            frappe.db.commit()
            
        except Exception as e:
            log_error(f"Exception backfilling {pair_str}: {str(e)}")
            frappe.log_error(frappe.get_traceback(), f"Forex Backfill Error: {pair_str}")
            log_sync(
                sync_type="Backfill",
                currency_pair=pair_str,
                status="Error",
                error_message=str(e)
            )
            error_count += 1
    
    # Also backfill monthly rates for each past month
    log_info("Backfilling monthly rates...")
    for i in range(1, months + 1):
        month_date = add_months(today_date, -i)
        log_debug(f"Backfilling month: {month_date}")
        backfill_month_rates(month_date, client, enabled_pairs, settings)
    
    log_info("=" * 50)
    log_info(f"Forex backfill completed: {success_count} pairs success, {error_count} errors")
    log_info("=" * 50)


def backfill_month_rates(month_date, client, enabled_pairs, settings):
    """
    Backfill monthly rates (closing, average, prudency) for a specific month.
    """
    from datetime import datetime
    
    first_of_month = get_first_day(month_date)
    last_of_month = get_last_day(month_date)
    
    log_debug(f"Backfilling month rates for {first_of_month} to {last_of_month}")
    
    for pair in enabled_pairs:
        from_currency = pair["from_currency"]
        to_currency = pair["to_currency"]
        pair_str = f"{from_currency}-{to_currency}"
        
        try:
            # Get daily data
            result = client.get_fx_daily(from_currency, to_currency, outputsize="full")
            
            if result.get("error"):
                log_error(f"API error for {pair_str}: {result.get('error')}")
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
                log_debug(f"No month rates found for {pair_str}")
                continue
            
            month_end_str = str(last_of_month)
            log_debug(f"Processing {len(month_rates)} rates for {pair_str}, closing: {closing_rate}")
            
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
                log_debug(f"Average rate for {pair_str}: {avg_rate}")
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
                log_debug(f"Prudency high for {pair_str}: {max(highs)}")
                store_rate_log(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate_date=month_end_str,
                    rate_type="Prudency (High)",
                    exchange_rate=max(highs)
                )
            
            if lows and settings.store_historical_data:
                log_debug(f"Prudency low for {pair_str}: {min(lows)}")
                store_rate_log(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate_date=month_end_str,
                    rate_type="Prudency (Low)",
                    exchange_rate=min(lows)
                )
            
            frappe.db.commit()
            
        except Exception as e:
            log_error(f"Exception backfilling month rates for {pair_str}: {str(e)}")
            frappe.log_error(frappe.get_traceback(), f"Forex Month Backfill Error: {pair_str}")
            continue
