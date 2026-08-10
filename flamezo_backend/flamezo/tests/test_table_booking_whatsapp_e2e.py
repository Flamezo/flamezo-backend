# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for utils/table_booking_whatsapp.py — the merchant lead alert.

Covers:
  build_table_booking_params:
    - formats customer/party/date/time+notes correctly
    - collapses multi-space/note text to a single line (WhatsApp param rule)

  dispatch_table_booking_whatsapp:
    - success path sets is_sent_to_whatsapp + whatsapp_send_status
    - idempotent — already-sent booking is skipped (no second send attempt)
    - no outlet WhatsApp number configured — recorded, no crash
    - no template configured — recorded, no crash
    - send failure retries up to MAX_ATTEMPTS then gives up
    - never raises — exceptions inside must never propagate (best-effort)
"""

import unittest
from unittest.mock import patch
from frappe.utils import add_days, today

import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-TBWA"
_PHONE = "9600000010"


def _make_rest(suffix="01", **kwargs):
    name = f"{_PREFIX}-R{suffix}"
    r = make_restaurant(name, outlet_type="dining", **kwargs)
    frappe.db.set_value("Restaurant", r.name, "is_active", 1)
    frappe.db.commit()
    return r


def _make_booking(restaurant, notes=""):
    doc = frappe.get_doc({
        "doctype": "Table Booking",
        "restaurant": restaurant,
        "customer_phone": _PHONE,
        "customer_name": "Test Guest",
        "date": add_days(today(), 2),
        "time_slot": "Tonight, around 8",
        "number_of_diners": 3,
        "notes": notes,
        "status": "pending",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _cleanup():
    frappe.db.sql("DELETE FROM `tabTable Booking` WHERE customer_phone=%s", _PHONE)
    frappe.db.sql("DELETE FROM `tabRestaurant` WHERE name LIKE %s", [f"{_PREFIX}%"])
    frappe.db.commit()


from flamezo_backend.flamezo.utils import table_booking_whatsapp as tbw


class TestBuildParams(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()

    def tearDown(self):
        _cleanup()

    def test_params_shape(self):
        b = _make_booking(self.rest.name)
        params = tbw.build_table_booking_params(b, self.rest.restaurant_name)
        self.assertEqual(len(params), 4)
        self.assertIn("Test Guest", params[0])
        self.assertIn(_PHONE, params[0])
        self.assertEqual(params[1], "3 guests")
        self.assertEqual(params[3], "Tonight, around 8")

    def test_notes_appended_to_time_param(self):
        b = _make_booking(self.rest.name, notes="Window seat if possible")
        params = tbw.build_table_booking_params(b, self.rest.restaurant_name)
        self.assertIn("Window seat if possible", params[3])
        self.assertIn("Tonight, around 8", params[3])

    def test_multiline_notes_collapsed_to_one_line(self):
        b = _make_booking(self.rest.name, notes="Line one\n\tLine two    with   spaces")
        params = tbw.build_table_booking_params(b, self.rest.restaurant_name)
        self.assertNotIn("\n", params[3])
        self.assertNotIn("\t", params[3])
        self.assertNotIn("    ", params[3])


class TestDispatch(unittest.TestCase):

    def setUp(self):
        _cleanup()
        # owner_phone is the fallback-chain's last tier (see
        # dispatch_table_booking_whatsapp) — order_whatsapp_number is a
        # Custom Field that frappe.get_doc(...).insert() doesn't reliably
        # set outside a real request context, so exercise the chain via a
        # plain base field instead; the chain logic itself is what's under
        # test, not which specific tier resolves.
        self.rest = _make_rest(owner_phone="9911111111")
        self.settings_patch = patch(
            "frappe.get_single",
            return_value=frappe._dict({"table_booking_whatsapp_template_name": "tbk_lead_alert"}),
        )

    def tearDown(self):
        _cleanup()

    def test_success_marks_sent(self):
        b = _make_booking(self.rest.name)
        with self.settings_patch, patch(
            "flamezo_backend.flamezo.utils.table_booking_whatsapp.send_whatsapp_cloud_message",
            return_value=(True, "wamid.123"),
        ) as mock_send:
            tbw.dispatch_table_booking_whatsapp(b.name)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[0], self.rest.owner_phone)
        sent, status = frappe.db.get_value(
            "Table Booking", b.name, ["is_sent_to_whatsapp", "whatsapp_send_status"]
        )
        self.assertEqual(sent, 1)
        self.assertIn("Sent", status)

    def test_idempotent_already_sent_skips(self):
        b = _make_booking(self.rest.name)
        frappe.db.set_value("Table Booking", b.name, "is_sent_to_whatsapp", 1)
        frappe.db.commit()
        with self.settings_patch, patch(
            "flamezo_backend.flamezo.utils.table_booking_whatsapp.send_whatsapp_cloud_message"
        ) as mock_send:
            tbw.dispatch_table_booking_whatsapp(b.name)
        mock_send.assert_not_called()

    def test_no_outlet_whatsapp_number_recorded_no_crash(self):
        rest_no_number = _make_rest("02")
        b = _make_booking(rest_no_number.name)
        with self.settings_patch, patch(
            "flamezo_backend.flamezo.utils.table_booking_whatsapp.send_whatsapp_cloud_message"
        ) as mock_send:
            tbw.dispatch_table_booking_whatsapp(b.name)
        mock_send.assert_not_called()
        status = frappe.db.get_value("Table Booking", b.name, "whatsapp_send_status")
        self.assertIn("No outlet WhatsApp number", status)

    def test_no_template_configured_recorded_no_crash(self):
        b = _make_booking(self.rest.name)
        with patch("frappe.get_single", return_value=frappe._dict({})), patch(
            "flamezo_backend.flamezo.utils.table_booking_whatsapp.send_whatsapp_cloud_message"
        ) as mock_send:
            tbw.dispatch_table_booking_whatsapp(b.name)
        mock_send.assert_not_called()
        status = frappe.db.get_value("Table Booking", b.name, "whatsapp_send_status")
        self.assertIn("No template configured", status)

    def test_failure_retries_via_enqueue(self):
        b = _make_booking(self.rest.name)
        with self.settings_patch, patch(
            "flamezo_backend.flamezo.utils.table_booking_whatsapp.send_whatsapp_cloud_message",
            return_value=(False, "Meta API error"),
        ), patch("frappe.enqueue") as mock_enqueue:
            tbw.dispatch_table_booking_whatsapp(b.name, attempt=1)
        mock_enqueue.assert_called_once()
        self.assertEqual(mock_enqueue.call_args.kwargs.get("attempt"), 2)

    def test_failure_gives_up_after_max_attempts(self):
        b = _make_booking(self.rest.name)
        with self.settings_patch, patch(
            "flamezo_backend.flamezo.utils.table_booking_whatsapp.send_whatsapp_cloud_message",
            return_value=(False, "Meta API error"),
        ), patch("frappe.enqueue") as mock_enqueue:
            tbw.dispatch_table_booking_whatsapp(b.name, attempt=tbw.MAX_ATTEMPTS)
        mock_enqueue.assert_not_called()
        status = frappe.db.get_value("Table Booking", b.name, "whatsapp_send_status")
        self.assertIn("FAILED", status)

    def test_exception_never_propagates(self):
        b = _make_booking(self.rest.name)
        with patch("frappe.get_single", side_effect=RuntimeError("boom")):
            try:
                tbw.dispatch_table_booking_whatsapp(b.name)
            except Exception as e:
                self.fail(f"dispatch_table_booking_whatsapp raised {e!r} — must be best-effort")

    def test_nonexistent_booking_never_propagates(self):
        try:
            tbw.dispatch_table_booking_whatsapp("TBK-DOES-NOT-EXIST")
        except Exception as e:
            self.fail(f"dispatch_table_booking_whatsapp raised {e!r} — must be best-effort")
