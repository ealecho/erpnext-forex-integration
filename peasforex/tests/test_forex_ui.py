"""
Forex Ask Rate - Playwright UI Tests
Run locally against peas-dev.localhost:8020

Usage:
    pip install playwright && playwright install chromium
    python3 peasforex/tests/test_forex_ui.py
"""
import re
import sys
import json
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://peas-dev.localhost:8020")
USER = "Administrator"
PASSW = "admin"

# Set to today's date when running
import datetime
TODAY = datetime.date.today().strftime("%Y-%m-%d")

results = []


def log(label, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    msg = f"  [{mark}]  {label}"
    if detail:
        msg += f"  ->  {detail}"
    print(msg)
    results.append((label, ok, detail))


def api_get(page, doctype, filters, fields, limit=50):
    """Call Frappe REST API via browser fetch (uses existing session auth)."""
    filters_str = json.dumps(filters)
    fields_str = json.dumps(fields)
    result = page.evaluate(f"""
        async () => {{
            const r = await fetch(
                '/api/resource/{doctype}' +
                '?filters=' + encodeURIComponent('{filters_str}') +
                '&fields=' + encodeURIComponent('{fields_str}') +
                '&limit_page_length={limit}'
            );
            return await r.json();
        }}
    """)
    return result


def login(page):
    page.goto(f"{BASE}/login")
    page.wait_for_selector("#login_email", timeout=10000)
    page.fill("#login_email", USER)
    page.fill("#login_password", PASSW)
    page.click(".btn-login")
    page.wait_for_url(re.compile(r".*/app.*"), timeout=15000)


def test_forex_rate_log(page):
    print(f"\n[1] Forex Rate Log -- Ask Rate records for {TODAY}")

    data = api_get(page, "Forex Rate Log",
        [["rate_date", "=", TODAY], ["rate_type", "=", "Ask Rate"]],
        ["name", "from_currency", "to_currency", "exchange_rate"])
    records = data.get("data", [])

    log("Ask Rate records exist for today", len(records) > 0, f"{len(records)} records")
    log("Count = 18 (9 pairs x 2 directions)", len(records) == 18, f"got {len(records)}")

    spot = api_get(page, "Forex Rate Log",
        [["rate_date", "=", TODAY], ["rate_type", "=", "Spot"]],
        ["name"]).get("data", [])
    log("No new Spot records today", len(spot) == 0, f"{len(spot)} found")

    fwd = [r for r in records if r["from_currency"] == "GBP" and r["to_currency"] == "UGX"]
    rev = [r for r in records if r["from_currency"] == "UGX" and r["to_currency"] == "GBP"]

    log("GBP->UGX forward exists", len(fwd) == 1,
        f"rate={fwd[0]['exchange_rate']:.4f}" if fwd else "missing")
    log("UGX->GBP reverse exists", len(rev) == 1,
        f"rate={rev[0]['exchange_rate']:.8f}" if rev else "missing")

    if fwd and rev:
        product = fwd[0]["exchange_rate"] * rev[0]["exchange_rate"]
        log("Forward x reverse = 1.0 (inverse integrity)", abs(product - 1.0) < 0.01,
            f"{product:.6f}")


def test_currency_exchange(page):
    print("\n[2] Currency Exchange -- bidirectional Ask Rate records")

    fwd = api_get(page, "Currency Exchange",
        [["date", "=", TODAY], ["from_currency", "=", "GBP"], ["to_currency", "=", "UGX"]],
        ["name", "exchange_rate"]).get("data", [])
    rev = api_get(page, "Currency Exchange",
        [["date", "=", TODAY], ["from_currency", "=", "UGX"], ["to_currency", "=", "GBP"]],
        ["name", "exchange_rate"]).get("data", [])

    log("CE GBP->UGX exists",
        len(fwd) > 0, f"rate={fwd[0]['exchange_rate']:.4f}" if fwd else "missing")
    log("CE UGX->GBP exists",
        len(rev) > 0, f"rate={rev[0]['exchange_rate']:.8f}" if rev else "missing")

    frl = api_get(page, "Forex Rate Log",
        [["rate_date", "=", TODAY], ["from_currency", "=", "GBP"],
         ["to_currency", "=", "UGX"], ["rate_type", "=", "Ask Rate"]],
        ["exchange_rate"]).get("data", [])

    if fwd and frl:
        match = abs(fwd[0]["exchange_rate"] - frl[0]["exchange_rate"]) < 0.001
        log("CE rate = FRL Ask Rate exactly", match,
            f"CE={fwd[0]['exchange_rate']:.4f}  FRL={frl[0]['exchange_rate']:.4f}")


def test_purchase_invoice_rate(page):
    print("\n[3] Purchase Invoice -- conversion rate auto-populates")

    page.goto(f"{BASE}/app/purchase-invoice/new-purchase-invoice-1")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("() => window.cur_frm && cur_frm.doc", timeout=15000)

    # Drive the form via its JS API: hidden fields and an async
    # get_exchange_rate callback make DOM-level interaction brittle.
    # Pin company to a non-GBP one so GBP triggers a real lookup.
    rate_val = page.evaluate("""
        async () => {
            await cur_frm.set_value('company', 'PEAS Uganda');
            await cur_frm.set_value('currency', 'GBP');
            for (let i = 0; i < 40; i++) {
                const r = cur_frm.doc.conversion_rate;
                if (r && r !== 1) return String(r);
                await new Promise(res => setTimeout(res, 250));
            }
            return String(cur_frm.doc.conversion_rate ?? '');
        }
    """)
    log("Conversion rate field populated", rate_val not in ("", "0", "1"),
        f"value={rate_val}")

    ce = api_get(page, "Currency Exchange",
        [["date", "=", TODAY], ["from_currency", "=", "GBP"], ["to_currency", "=", "UGX"]],
        ["exchange_rate"]).get("data", [])

    if ce and rate_val and rate_val not in ("", "0", "1"):
        form_rate = float(rate_val)
        ce_rate = ce[0]["exchange_rate"]
        match = abs(form_rate - ce_rate) / ce_rate < 0.05
        log("Form rate matches CE Ask Rate (within 5%)", match,
            f"form={form_rate:.4f}  CE={ce_rate:.4f}")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        print("=" * 55)
        print("FOREX ASK RATE -- PLAYWRIGHT TEST SUITE")
        print(f"Site: {BASE}  |  Date: {TODAY}")
        print("=" * 55)

        try:
            login(page)
            log("Login", True, f"as {USER}")
        except Exception as e:
            log("Login", False, str(e)[:80])
            browser.close()
            sys.exit(1)

        for test_fn in [
            test_forex_rate_log,
            test_currency_exchange,
            test_purchase_invoice_rate,
        ]:
            try:
                test_fn(page)
            except Exception as e:
                log(test_fn.__name__, False, str(e)[:100])

        browser.close()

    print("\n" + "=" * 55)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"RESULT: {passed} passed | {failed} failed | {len(results)} total")
    print("=" * 55)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run()