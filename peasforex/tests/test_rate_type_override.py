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


def test_manual_skips_forex_rate_log():
    with (
        patch.object(overrides, "_requested_rate_type", return_value="Manual"),
        patch.object(overrides, "_get_logged_rate") as logged,
        patch("erpnext.setup.utils.get_exchange_rate", return_value=3700.0),
        patch.object(overrides.frappe, "local", types.SimpleNamespace()),
    ):
        assert overrides.get_rate_as_at("2026-08-31", "USD", "UGX") == 3700.0
        logged.assert_not_called()
