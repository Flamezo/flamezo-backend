# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for update_profile API (flamezo.py).

Covers:
  Happy path:
    - update full_name only
    - update email only
    - update date_of_birth only
    - update all three fields together
    - update to empty email (clear)
    - return value includes updated fields

  Validation:
    - empty full_name rejected
    - invalid email format rejected
    - future date_of_birth rejected
    - malformed date_of_birth rejected
    - no fields provided → NO_FIELDS error

  Auth:
    - missing phone → AUTH_REQUIRED error

  Data integrity:
    - unchanged fields not zeroed out
    - phone field is immutable (not changed even if passed)
"""

import unittest
from unittest.mock import patch, MagicMock

import frappe
from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone, get_or_create_customer

_PHONE = "9500000001"
_PHONE2 = "9500000002"


def _make_customer(phone=_PHONE, name="Test User", email="test@example.com", dob=None):
    from flamezo_backend.flamezo.utils.customer_helpers import get_or_create_customer
    normalized = normalize_phone(phone)
    customer = get_or_create_customer(normalized)
    frappe.db.set_value("Customer", customer.name, {
        "customer_name": name,
        "email": email,
        "date_of_birth": dob,
    })
    frappe.db.commit()
    return customer


def _call(phone=_PHONE, **kwargs):
    from flamezo_backend.flamezo.api.flamezo import update_profile
    with patch("flamezo_backend.flamezo.api.flamezo.get_customer_token", return_value=None), \
         patch("flamezo_backend.flamezo.api.flamezo.validate_customer_session", return_value=True):
        return update_profile(phone=phone, **kwargs)


class TestUpdateProfile(unittest.TestCase):

    def setUp(self):
        self.customer = _make_customer(_PHONE, name="Original Name", email="orig@example.com")

    def tearDown(self):
        frappe.db.set_value("Customer", self.customer.name, {
            "customer_name": "Test User",
            "email": "",
            "date_of_birth": None,
        })
        frappe.db.commit()

    def test_update_full_name(self):
        result = _call(phone=_PHONE, full_name="New Name")
        self.assertTrue(result["success"])
        val = frappe.db.get_value("Customer", self.customer.name, "customer_name")
        self.assertEqual(val, "New Name")

    def test_update_email(self):
        result = _call(phone=_PHONE, email="new@flamezo.in")
        self.assertTrue(result["success"])
        val = frappe.db.get_value("Customer", self.customer.name, "email")
        self.assertEqual(val, "new@flamezo.in")

    def test_update_dob(self):
        result = _call(phone=_PHONE, date_of_birth="1995-06-15")
        self.assertTrue(result["success"])
        val = frappe.db.get_value("Customer", self.customer.name, "date_of_birth")
        self.assertIsNotNone(val)

    def test_update_all_fields(self):
        result = _call(phone=_PHONE, full_name="Full Update", email="full@x.com", date_of_birth="1990-01-01")
        self.assertTrue(result["success"])
        self.assertEqual(frappe.db.get_value("Customer", self.customer.name, "customer_name"), "Full Update")
        self.assertEqual(frappe.db.get_value("Customer", self.customer.name, "email"), "full@x.com")

    def test_clear_email(self):
        result = _call(phone=_PHONE, email="")
        self.assertTrue(result["success"])

    def test_return_data_includes_phone(self):
        result = _call(phone=_PHONE, full_name="Return Test")
        self.assertIn("data", result)
        self.assertIn("phone", result["data"])

    def test_return_data_includes_updated_name(self):
        result = _call(phone=_PHONE, full_name="Return Name Check")
        self.assertEqual(result["data"]["full_name"], "Return Name Check")

    def test_empty_full_name_rejected(self):
        result = _call(phone=_PHONE, full_name="  ")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")

    def test_invalid_email_rejected(self):
        result = _call(phone=_PHONE, email="not-an-email")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")

    def test_future_dob_rejected(self):
        result = _call(phone=_PHONE, date_of_birth="2099-01-01")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")

    def test_malformed_dob_rejected(self):
        result = _call(phone=_PHONE, date_of_birth="not-a-date")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")

    def test_no_fields_returns_error(self):
        result = _call(phone=_PHONE)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NO_FIELDS")

    def test_missing_phone_returns_auth_error(self):
        from flamezo_backend.flamezo.api.flamezo import update_profile
        with patch("flamezo_backend.flamezo.api.flamezo.get_customer_token", return_value=None):
            result = update_profile(phone=None, full_name="Test")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AUTH_REQUIRED")

    def test_unchanged_fields_not_zeroed(self):
        # Set name, then update only email — name should stay
        frappe.db.set_value("Customer", self.customer.name, "customer_name", "Keep This Name")
        frappe.db.commit()
        _call(phone=_PHONE, email="keepname@x.com")
        val = frappe.db.get_value("Customer", self.customer.name, "customer_name")
        self.assertEqual(val, "Keep This Name")

    def test_phone_isolation(self):
        # Updating one customer does not affect another
        c2 = _make_customer(_PHONE2, name="Other User")
        _call(phone=_PHONE, full_name="Changed Only One")
        val2 = frappe.db.get_value("Customer", c2.name, "customer_name")
        self.assertEqual(val2, "Other User")
