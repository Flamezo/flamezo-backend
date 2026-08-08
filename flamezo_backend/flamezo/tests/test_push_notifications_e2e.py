# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for push_notifications.py — specifically:

1. A real, confirmed bug fix: `save_customer_subscription` /
   `remove_customer_subscription` used to query a `normalized_phone` column
   that doesn't exist on Customer (only `phone` does) — every call with a
   `customer_phone` silently failed to find the customer and never stored a
   token. Confirmed via `frappe.db.has_column` and zero real rows in
   `push_fcm_tokens` before this fix. Regression-tested here.

2. The new mobile registration endpoints (`register_mobile_push_token` /
   `unregister_mobile_push_token`) — session-gated, unlike the web-facing
   pair above.

3. `push_to_customer` — the best-effort fan-out sender used by
   `create_notification`. `_send_fcm_message` is mocked throughout (no real
   network calls / no dependency on the FCM service account actually
   working) so these tests verify the *storage and token-pruning* logic,
   not real delivery.
"""

import json
import unittest
from unittest.mock import patch

import frappe

from flamezo_backend.flamezo.api import push_notifications as push_api
from flamezo_backend.flamezo.tests.utils import make_customer

_PHONE_A = "9600000001"
_PHONE_B = "9600000002"


def _verified_session():
    return patch("flamezo_backend.flamezo.api.push_notifications.has_active_customer_session", return_value=True)


def _cleanup():
    for phone in (_PHONE_A, _PHONE_B):
        existing = frappe.db.get_value("Customer", {"phone": phone}, "name")
        if existing:
            frappe.delete_doc("Customer", existing, force=True, ignore_permissions=True)
    frappe.db.commit()


class TestSaveCustomerSubscriptionPhoneBugFix(unittest.TestCase):
    """Regression test for the `normalized_phone` bug — a raw string
    literal, not `_require_session`-gated, so no mocking needed here."""

    def setUp(self):
        _cleanup()
        self.customer = make_customer(phone=_PHONE_A, name="Push Test Customer")

    def tearDown(self):
        _cleanup()

    def test_save_finds_customer_by_phone(self):
        result = push_api.save_customer_subscription("test-restaurant", "fake-token-123", customer_phone=_PHONE_A)
        self.assertTrue(result["success"])
        stored = frappe.db.get_value("Customer", self.customer.name, "push_fcm_tokens")
        tokens = json.loads(stored or "[]")
        self.assertIn("fake-token-123", tokens)

    def test_remove_finds_customer_by_phone(self):
        push_api.save_customer_subscription("test-restaurant", "fake-token-123", customer_phone=_PHONE_A)
        result = push_api.remove_customer_subscription("fake-token-123", customer_phone=_PHONE_A)
        self.assertTrue(result["success"])
        stored = frappe.db.get_value("Customer", self.customer.name, "push_fcm_tokens")
        tokens = json.loads(stored or "[]")
        self.assertNotIn("fake-token-123", tokens)

    def test_max_five_tokens_kept(self):
        for i in range(7):
            push_api.save_customer_subscription("test-restaurant", f"token-{i}", customer_phone=_PHONE_A)
        stored = frappe.db.get_value("Customer", self.customer.name, "push_fcm_tokens")
        tokens = json.loads(stored or "[]")
        self.assertEqual(len(tokens), 5)
        self.assertEqual(tokens, [f"token-{i}" for i in range(2, 7)])


class TestRegisterMobilePushToken(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.customer = make_customer(phone=_PHONE_A, name="Mobile Push Customer")

    def tearDown(self):
        _cleanup()

    def test_registers_token(self):
        with _verified_session():
            result = push_api.register_mobile_push_token(_PHONE_A, "mobile-token-1")["data"]
        self.assertTrue(result["ok"])
        tokens = json.loads(frappe.db.get_value("Customer", self.customer.name, "push_fcm_tokens") or "[]")
        self.assertIn("mobile-token-1", tokens)

    def test_duplicate_token_not_added_twice(self):
        with _verified_session():
            push_api.register_mobile_push_token(_PHONE_A, "mobile-token-1")
            push_api.register_mobile_push_token(_PHONE_A, "mobile-token-1")
        tokens = json.loads(frappe.db.get_value("Customer", self.customer.name, "push_fcm_tokens") or "[]")
        self.assertEqual(tokens.count("mobile-token-1"), 1)

    def test_unregistered_session_rejected(self):
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            push_api.register_mobile_push_token(_PHONE_A, "mobile-token-1")

    def test_missing_token_throws(self):
        with _verified_session(), self.assertRaises(Exception):
            push_api.register_mobile_push_token(_PHONE_A, None)

    def test_nonexistent_customer_throws(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            push_api.register_mobile_push_token("9600099999", "mobile-token-1")

    def test_unregister_removes_token(self):
        with _verified_session():
            push_api.register_mobile_push_token(_PHONE_A, "mobile-token-1")
            result = push_api.unregister_mobile_push_token(_PHONE_A, "mobile-token-1")["data"]
        self.assertTrue(result["ok"])
        tokens = json.loads(frappe.db.get_value("Customer", self.customer.name, "push_fcm_tokens") or "[]")
        self.assertNotIn("mobile-token-1", tokens)

    def test_unregister_without_session_rejected(self):
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            push_api.unregister_mobile_push_token(_PHONE_A, "mobile-token-1")


class TestPushToCustomer(unittest.TestCase):
    """`_send_fcm_message` is mocked — these tests are about the
    lookup/fan-out/pruning logic, not real FCM delivery."""

    def setUp(self):
        _cleanup()
        self.customer = make_customer(phone=_PHONE_A, name="Push Fanout Customer")
        with _verified_session():
            push_api.register_mobile_push_token(_PHONE_A, "token-1")
            push_api.register_mobile_push_token(_PHONE_A, "token-2")

    def tearDown(self):
        _cleanup()

    def test_sends_to_every_registered_token(self):
        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message", return_value=True) as mock_send:
            push_api.push_to_customer(_PHONE_A, "Title", "Body")
        self.assertEqual(mock_send.call_count, 2)
        sent_tokens = {call.args[0] for call in mock_send.call_args_list}
        self.assertEqual(sent_tokens, {"token-1", "token-2"})

    def test_unregistered_token_pruned(self):
        def fake_send(token, *args, **kwargs):
            return "unregistered" if token == "token-1" else True

        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message", side_effect=fake_send):
            push_api.push_to_customer(_PHONE_A, "Title", "Body")

        tokens = json.loads(frappe.db.get_value("Customer", self.customer.name, "push_fcm_tokens") or "[]")
        self.assertNotIn("token-1", tokens)
        self.assertIn("token-2", tokens)

    def test_no_customer_does_not_throw(self):
        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message") as mock_send:
            push_api.push_to_customer("9600099999", "Title", "Body")
        mock_send.assert_not_called()

    def test_no_tokens_does_not_throw(self):
        with _verified_session():
            push_api.unregister_mobile_push_token(_PHONE_A, "token-1")
            push_api.unregister_mobile_push_token(_PHONE_A, "token-2")
        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message") as mock_send:
            push_api.push_to_customer(_PHONE_A, "Title", "Body")
        mock_send.assert_not_called()

    def test_send_exception_never_propagates(self):
        # A real network/credential failure (e.g. today's corrupted service
        # account key) must never surface as an exception to the caller —
        # push is always best-effort.
        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message", side_effect=RuntimeError("boom")):
            try:
                push_api.push_to_customer(_PHONE_A, "Title", "Body")
            except Exception as e:
                self.fail(f"push_to_customer raised {e!r} — must be best-effort")


class TestCreateNotificationPushIntegration(unittest.TestCase):
    """`create_notification` (notifications_consumer.py) now also calls
    `push_notifications.push_to_customer` — verified here without touching
    the real FCM network."""

    def setUp(self):
        _cleanup()
        self.customer = make_customer(phone=_PHONE_A, name="Notif Push Customer")
        frappe.db.sql("DELETE FROM `tabFlamezo Notification` WHERE customer_phone=%s", _PHONE_A)
        frappe.db.commit()

    def tearDown(self):
        frappe.db.sql("DELETE FROM `tabFlamezo Notification` WHERE customer_phone=%s", _PHONE_A)
        frappe.db.commit()
        _cleanup()

    def test_create_notification_triggers_push(self):
        from flamezo_backend.flamezo.api.notifications_consumer import create_notification

        with patch("flamezo_backend.flamezo.api.push_notifications.push_to_customer") as mock_push:
            name = create_notification(_PHONE_A, "Test Title", "Test Body", notification_type="general")
        self.assertIsNotNone(name)
        mock_push.assert_called_once()
        call_args = mock_push.call_args
        self.assertEqual(call_args[0][0], _PHONE_A)
        self.assertEqual(call_args[0][1], "Test Title")

    def test_push_failure_does_not_block_notification_creation(self):
        from flamezo_backend.flamezo.api.notifications_consumer import create_notification

        with patch("flamezo_backend.flamezo.api.push_notifications.push_to_customer", side_effect=RuntimeError("fcm down")):
            name = create_notification(_PHONE_A, "Test Title", "Test Body", notification_type="general")
        self.assertIsNotNone(name)
        self.assertTrue(frappe.db.exists("Flamezo Notification", name))
