# Peasforex - Alpha Vantage Forex Integration for ERPNext

A Frappe/ERPNext app that integrates with Alpha Vantage to automatically sync foreign exchange rates into ERPNext's Currency Exchange system.

## Features

- **Automatic Daily Spot Rate Sync**: Fetches current exchange rates daily at 6:00 AM
- **Monthly Rate Calculations**: On the 1st of each month, calculates:
  - **Closing Rate**: Last trading day rate of the previous month
  - **Monthly Average**: Average of all daily closing rates
  - **Prudency Rates**: Highest and lowest rates for conservative accounting
- **Bidirectional Rates**: Automatically creates both forward and reverse exchange rates
- **Company-Specific Application**: Apply rates to all companies or select specific ones
- **Historical Data Storage**: Stores all rates in a log for reporting and analysis
- **Exchange Rate History Report**: Visual report with charts for trend analysis
- **Manual Sync & Backfill**: Manually trigger syncs or backfill historical data

## Pre-configured Currency Pairs

The app comes with these default currency pairs configured:

| From | To  | Suggested Company | Sync Types |
|------|-----|-------------------|------------|
| GBP  | UGX | PEAS Uganda       | Spot, Closing, Average, Prudency |
| GBP  | ZMW | PEAS Zambia       | Spot, Closing, Average, Prudency |
| GBP  | GHS | PEAS Ghana        | Spot, Closing, Average, Prudency |
| GBP  | USD | PEAS Global       | Spot, Closing, Average, Prudency |
| USD  | UGX | PEAS Uganda       | Spot, Closing, Average, Prudency |
| USD  | ZMW | PEAS Zambia       | Spot, Closing, Average, Prudency |
| DKK  | GBP | PEAS Global       | Spot, Closing, Average, Prudency |
| EUR  | GBP | PEAS Global       | Spot, Closing, Average, Prudency |

You can add or remove currency pairs and assign each to a specific company in the Forex Settings.

### Company-Specific Currency Pairs

Each currency pair can be assigned to a specific company using the **Target Company** field. This is useful when:

- Different subsidiaries operate in different currencies
- You want to associate GBP-UGX rates with your Uganda company
- You want to associate GBP-ZMW rates with your Zambia company

If no target company is specified, the rate will use the default company from Global Defaults.

## Installation

### Prerequisites

- ERPNext v13 or v14
- Alpha Vantage Premium API key (get one at https://www.alphavantage.co/support/#api-key)

### Install via Bench

```bash
# Get the app
bench get-app https://github.com/your-org/peasforex.git

# Install on your site
bench --site your-site.local install-app peasforex

# Run migrations
bench --site your-site.local migrate

# Restart bench
bench restart
```

## Configuration

1. Go to **Forex Settings** (search in Awesome Bar or navigate via Forex Integration workspace)

2. Enter your **Alpha Vantage API Key**

3. Configure options:
   - **Create Bidirectional Rates**: Creates both USD→EUR and EUR→USD rates
   - **Auto Update Currency Exchange**: Updates ERPNext's Currency Exchange doctype
   - **Store Historical Data**: Keeps a log of all fetched rates

4. Select **Applicable Companies** (or apply to all)

5. Review/modify **Currency Pairs** as needed

6. Check **Enabled** to activate the integration

7. Click **Test Connection** to verify API connectivity

8. Click **Backfill 2 Months** to populate historical data

## Scheduled Tasks

| Schedule | Task | Description |
|----------|------|-------------|
| Daily 6:00 AM | `sync_daily_spot_rates` | Fetches current spot rates for all pairs |
| Monthly 1st 7:00 AM | `sync_monthly_rates` | Calculates closing, average, and prudency rates |
| Daily (fallback) | `check_and_sync_daily` | Ensures daily sync runs if cron missed |

## API Call Estimates

### Daily Sync
- 8 pairs × 1 call = **8 API calls/day**

### Monthly Sync (1st of month)
- 8 pairs × 1 call (for previous month data) = **8 API calls/month**
- (Uses daily historical data to calculate closing, average, and prudency rates)

### Backfill (one-time)
- 8 pairs × 1 call = **8 API calls**

**Total monthly estimate**: ~250 API calls (well within premium limits)

## Rate Types Explained

| Rate Type | Description | Use Case |
|-----------|-------------|----------|
| **Spot** | Current market rate | Daily transactions |
| **Closing** | Last rate of month | Month-end valuations |
| **Monthly Average** | Average of daily closes | Average rate accounting |
| **Prudency (High)** | Highest rate in month | Conservative expense valuation |
| **Prudency (Low)** | Lowest rate in month | Conservative income valuation |

## DocTypes

### Forex Settings (Single)
Main configuration for the integration.

### Currency Pair (Child Table)
Defines currency pairs to sync with:
- From/To currency selection
- **Target Company**: Assign rates to a specific company
- Individual sync type toggles (Spot, Closing, Average, Prudency)

### Applicable Company (Child Table)
Lists companies to apply exchange rates to.

### Forex Rate Log
Historical storage of all fetched rates with OHLC data.

### Forex Sync Log
Audit log of all sync operations with status and error messages.

## Reports

### Exchange Rate History
Script report with:
- Date range filtering
- Currency pair filtering
- Rate type filtering
- Trend chart visualization

## Manual Operations

### Test Connection
Verifies API key and connectivity by fetching a sample rate.

### Sync Daily Rates
Immediately triggers a sync of spot rates for all enabled pairs.

### Sync Monthly Rates
Immediately triggers a sync of monthly rates (closing, average, prudency).

### Backfill Historical
Backfills X months of historical data (default: 2 months).

## Troubleshooting

### Common Issues

1. **API Rate Limit Exceeded**
   - Check Forex Sync Log for "rate_limited" errors
   - Wait for rate limit to reset (usually 1 minute)

2. **No Data for Currency Pair**
   - Verify the currency codes are correct
   - Some exotic pairs may not be available

3. **Sync Not Running**
   - Ensure Scheduler is enabled: `bench --site your-site enable-scheduler`
   - Check Error Log for exceptions

4. **Currency Not Found**
   - The app creates common currencies on install
   - For others, create the Currency doctype first

### Logs

- **Forex Sync Log**: Detailed sync operation history
- **Error Log**: System exceptions and API errors
- **Scheduler Log**: Background job execution status

## License

MIT License - See LICENSE file for details.

## Contributing

Pull requests are welcome! Please ensure:
- Code follows Frappe/ERPNext conventions
- Tests pass
- Documentation is updated

## Support

For issues and feature requests, please use the GitHub issue tracker.
