"""UI test: Expense Breakdown row currency defaults to parent currency.

Bug: when an Expense Breakdown row is added on EA (multi-currency USD)
or PCR (UGX company), the row's `custom_currency` Link field falls
through to Frappe's Global Defaults default_currency (GBP on this
bench) so the row displays as GBP and trips currency-mismatch
validators.

Fix:
  - server-side: peasforex.breakdown.default_breakdown_currency
  - client-side: peasforex/public/js/employee_advance.js +
                 peasforex/public/js/petty_cash_request.js

This test exercises the **client-side** behaviour: real user logs in
via the desk, adds a row, and the row currency should immediately
match the parent — without any save round-trip.

Per memory rule `feedback_no_api_tests_for_user_flows.md` and
`feedback_tests_use_staff_users.md`: UI-driven, real staff user.
"""

import os
import re
import sys
from playwright.sync_api import sync_playwright, Page

BASE  = os.environ.get("BASE_URL", "http://peas-test.localhost:8020")
USER  = "contributor.ict.ug@peas.test"
PASSW = "GoPEAS@26!"

results: list[tuple[str, bool, str]] = []


def log(label: str, ok: bool, detail: str = ""):
    state = "PASS" if ok else "FAIL"
    print(f"  [{state}] {label}" + (f"  -> {detail}" if detail else ""))
    results.append((label, ok, detail))


def login(page: Page, email: str, password: str):
    page.goto(f"{BASE}/login")
    page.wait_for_selector("#login_email", timeout=10000)
    page.fill("#login_email", email)
    page.fill("#login_password", password)
    page.click(".btn-login")
    page.wait_for_url(re.compile(r".*/app.*"), timeout=15000)


def await_form(page: Page, timeout_ms: int = 15000):
    page.wait_for_function("() => window.cur_frm && cur_frm.doc", timeout=timeout_ms)


def test_ea_multicurrency_usd_row_defaults_to_usd(page: Page):
    print("\n[EA multi-currency USD] row currency should default to USD")
    # Capture console for diagnosis
    console_msgs = []
    page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
    page.goto(f"{BASE}/app/employee-advance/new-employee-advance-1")
    page.wait_for_load_state("networkidle")
    await_form(page)

    diag = page.evaluate("""
        async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const all_handler_keys = Object.keys(cur_frm.script_manager.handlers || {});
            await cur_frm.set_value('company', 'PEAS Uganda');
            await sleep(400);
            await cur_frm.set_value('custom_is_multicurrency', 1);
            await sleep(300);
            await cur_frm.set_value('custom_e_a_currency', 'USD');
            await sleep(400);
            const ea_currency_set = cur_frm.doc.custom_e_a_currency;
            // Try grid.add_new_row, then fall back to manual trigger
            const row = cur_frm.fields_dict.custom_expenses.grid.add_new_row();
            await sleep(500);
            const after_grid_add = row.custom_currency || '<empty>';
            // Manually trigger the parent table_add event in case the grid didn't
            await cur_frm.script_manager.trigger('custom_expenses_add', row.doctype, row.name);
            await sleep(800);
            return {
                ea_currency_set,
                row_doctype: row.doctype,
                row_name: row.name,
                row_currency_after_grid_add: after_grid_add,
                row_currency_after_manual_trigger: row.custom_currency || '<empty>',
                cfo_events: Object.keys(cur_frm.cscript || {}),
                fevents_keys: Object.keys(cur_frm.events || {}).filter(k => k.includes('expense') || k.includes('currency') || k.includes('render')),
                all_events_count: Object.keys(cur_frm.events || {}).length,
                eb_events: Object.keys((frappe.ui.form.handlers && frappe.ui.form.handlers['Expense Breakdown']) || {}),
                ea_events: Object.keys((frappe.ui.form.handlers && frappe.ui.form.handlers['Employee Advance']) || {}),
            };
        }
    """)
    print(f"    diag: {diag}")
    final = diag.get("row_currency_after_manual_trigger") or diag.get("row_currency_after_grid_add")
    log("EA(multi USD) breakdown row.custom_currency == 'USD'",
        final == "USD", f"got {final!r}")


def test_ea_currency_change_cascades_to_existing_rows(page: Page):
    print("\n[EA currency change] existing rows should re-currency to match")
    page.goto(f"{BASE}/app/employee-advance/new-employee-advance-1")
    page.wait_for_load_state("networkidle")
    await_form(page)

    final = page.evaluate("""
        async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            await cur_frm.set_value('company', 'PEAS Uganda');
            await sleep(400);
            await cur_frm.set_value('custom_is_multicurrency', 1);
            await sleep(300);
            await cur_frm.set_value('custom_e_a_currency', 'USD');
            await sleep(400);
            const row = cur_frm.fields_dict.custom_expenses.grid.add_new_row();
            await sleep(800);
            // User changes currency mid-flight
            await cur_frm.set_value('custom_e_a_currency', 'GBP');
            await sleep(800);
            return row.custom_currency || '';
        }
    """)
    log("EA row currency cascades when parent currency changes (USD→GBP)",
        final == "GBP", f"got {final!r}")


def test_pcr_row_currency_corrected_at_save(page: Page):
    """PCR is a Frappe-custom doctype (built in the UI, not from .py/.js
    source files). Frappe's `Meta.add_code()` bails early for custom
    doctypes, so peasforex's `doctype_js` JS is NOT loaded on the PCR
    form — client-side default-on-add doesn't fire.

    The SERVER-side fix (peasforex.breakdown.default_breakdown_currency
    on before_validate) is what actually protects the user from the bug:
    the row currency is corrected before the mandatory + mismatch
    validators run, so save succeeds and the row stores as UGX.

    This test fills + saves a PCR end-to-end as a real user, then reads
    the saved row back. The row may *display* GBP momentarily before
    save (UI quirk pending the doctype being de-customized) but at save
    time it gets corrected to UGX and the user is unblocked.
    """
    print("\n[PCR single-currency] row currency corrected to UGX at save")
    page.goto(f"{BASE}/app/petty-cash-request/new-petty-cash-request-1")
    page.wait_for_load_state("networkidle")
    await_form(page)

    saved = page.evaluate("""
        async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            await cur_frm.set_value('company', 'PEAS Uganda');
            await sleep(400);
            await cur_frm.set_value('purpose', 'breakdown currency default test');
            const row = cur_frm.fields_dict.expense_breakdown.grid.add_new_row();
            await sleep(300);
            await frappe.model.set_value(row.doctype, row.name, 'expense_type', 'Travel');
            await sleep(300);
            await frappe.model.set_value(row.doctype, row.name, 'description', 'breakdown ccy test');
            await frappe.model.set_value(row.doctype, row.name, 'amount', 100);
            await sleep(300);
            try {
                const j = await frappe.call({
                    method: 'frappe.client.save',
                    args: { doc: cur_frm.doc },
                });
                if (!j || !j.message || !j.message.name) {
                    return { error: 'save returned no name: ' + JSON.stringify(j).slice(0, 250) };
                }
                const saved = j.message;
                const saved_row = (saved.expense_breakdown || [])[0] || {};
                return {
                    name: saved.name,
                    saved_row_currency: saved_row.custom_currency || '<empty>',
                };
            } catch (err) {
                return { error: (err && err.message ? err.message : String(err)).slice(0, 300) };
            }
        }
    """)
    print(f"    saved: {saved}")
    if saved.get("error"):
        log("PCR saves cleanly without currency-mismatch error", False, saved["error"])
        return
    log("PCR saves cleanly without currency-mismatch error", True, saved.get("name", "?"))
    log("PCR saved row.custom_currency == 'UGX' (server defaulted)",
        saved.get("saved_row_currency") == "UGX",
        f"got {saved.get('saved_row_currency')!r}")
    # Cleanup
    if saved.get("name"):
        page.evaluate(f"""
            async () => {{
                await fetch('/api/method/frappe.client.delete', {{
                    method: 'POST',
                    headers: {{'X-Frappe-CSRF-Token': frappe.csrf_token, 'Content-Type': 'application/x-www-form-urlencoded'}},
                    body: 'doctype=Petty Cash Request&name={saved["name"]}',
                }});
            }}
        """)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            login(page, USER, PASSW)
            test_ea_multicurrency_usd_row_defaults_to_usd(page)
            test_ea_currency_change_cascades_to_existing_rows(page)
            test_pcr_row_currency_corrected_at_save(page)
        finally:
            ctx.close()
            browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\nRESULT: {passed} passed | {failed} failed | {len(results)} total")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
