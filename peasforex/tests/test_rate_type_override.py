# Copyright (c) 2026, ERP Champions and contributors
# For license information, please see license.txt

import json
import types
from unittest.mock import patch

from peasforex import overrides


def test_requested_rate_type_parses_form_dict():
    with patch.object(overrides.frappe, "form_dict", {"filters": json.dumps({"rate_type": "Closing"})}):
        assert overrides._requested_rate_type() == "Closing"
    with patch.object(overrides.frappe, "form_dict", {"filters": "not json"}):
        assert overrides._requested_rate_type() is None
    with patch.object(overrides.frappe, "form_dict", {}):
        assert overrides._requested_rate_type() is None


def test_logged_rate_uses_inverse_pair():
    # direct pair missing, inverse UGX->USD = 0.00027 -> USD->UGX ~ 3703.7
    def fake_get_value(doctype, filters, fieldname, order_by=None):
        if filters["from_currency"] == "UGX":
            return 0.00027
        return None

    with patch.object(overrides.frappe.db, "get_value", side_effect=fake_get_value):
        rate = overrides._get_logged_rate("Closing", "USD", "UGX", "2026-08-31")
    assert round(rate, 1) == 3703.7


def test_err_rows_without_closing_rate_are_dropped():
    rows = [
        {"account": "A", "account_currency": "EUR", "new_exchange_rate": 0, "zero_balance": 0},
        {"account": "B", "account_currency": "USD", "new_exchange_rate": 3700.0, "zero_balance": 0},
        {"account": "C", "account_currency": "USD", "new_exchange_rate": 0, "zero_balance": 1},
    ]
    with (
        patch.object(overrides, "_orig_get_accounts_data", return_value=rows),
        patch.object(overrides.frappe, "msgprint") as msgprint,
    ):
        doc = types.SimpleNamespace(posting_date="2026-04-01")
        kept = overrides.err_get_accounts_data(doc)
    assert [r["account"] for r in kept] == ["B", "C"]  # zero-rate live row dropped, write-off row kept
    msgprint.assert_called_once()
    assert "EUR" in msgprint.call_args[0][0]


def test_manual_skips_forex_rate_log():
    with (
        patch.object(overrides, "_requested_rate_type", return_value="Manual"),
        patch.object(overrides, "_get_logged_rate") as logged,
        patch("erpnext.setup.utils.get_exchange_rate", return_value=3700.0),
        patch.object(overrides.frappe, "local", types.SimpleNamespace()),
    ):
        assert overrides.get_rate_as_at("2026-08-31", "USD", "UGX") == 3700.0
        logged.assert_not_called()
