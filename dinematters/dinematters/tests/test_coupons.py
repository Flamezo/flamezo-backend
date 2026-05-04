# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

"""
Tests for the Coupon doctype and coupon API layer.

Covers:
  - Coupon.validate()
      * JSON field fix: required_items="" → None (the original MariaDB constraint bug)
      * JSON field fix: valid_days_of_week="" → None
      * Code is uppercased and stripped on save
      * Duplicate code within same restaurant is rejected
      * Duplicate code across different restaurants is allowed

  - get_coupon_details() / validate_coupon()
      * Not found returns COUPON_NOT_FOUND
      * Inactive coupon returns COUPON_INACTIVE
      * Expired coupon (valid_until in past) returns COUPON_EXPIRED
      * Future coupon (valid_from tomorrow) returns COUPON_NOT_VALID_YET
      * Minimum order amount not met returns MIN_ORDER_NOT_MET
      * Usage limit exhausted returns COUPON_LIMIT_REACHED
      * Per-customer limit exhausted returns CUSTOMER_LIMIT_REACHED
      * Day-of-week restriction (invalid day) returns INVALID_DAY
      * Time-of-day restriction returns INVALID_TIME
      * Combo coupon with missing cart items returns COMBO_ITEMS_MISSING / COMBO_INCOMPLETE
      * Flat discount calculated correctly
      * Percent discount calculated correctly (with and without cap)
      * Combo price discount calculated correctly
      * Valid coupon returns success with correct discount_amount

  - validate_offer_eligibility() (pricing.py)
      * Delivery offer rejected for non-delivery order type
      * Future valid_from skipped
      * Expired valid_until skipped
      * Min order not met → failure
      * Day-of-week check
      * Time-of-day check (too early / too late)
      * Usage limit
      * Combo required items not in cart → failure
      * Flat discount returned correctly
      * Percent discount returned correctly (with max cap)
      * Delivery free-delivery discount equals delivery_fee
      * Delivery percent discount calculated on delivery_fee

Run with:
    bench run-tests --app dinematters --module dinematters.dinematters.tests.test_coupons
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

import frappe
from frappe.utils import today, add_days

from dinematters.dinematters.tests.utils import (
    make_restaurant,
    make_customer,
    cleanup_restaurant,
)

_PREFIX = "TEST-COUPON"


# ─── Coupon factory ──────────────────────────────────────────────────────────

def make_coupon(restaurant, code="SAVE10", **kwargs):
    """Insert a Coupon and return the doc. Caller is responsible for cleanup."""
    # Time fields are cleared by Coupon.validate() for new docs (Frappe auto-fills them with
    # nowtime()). Extract them from kwargs and write directly after insert so tests can set
    # explicit time restrictions without fighting the ORM default behaviour.
    time_fields = {f: kwargs.pop(f) for f in ("valid_time_start", "valid_time_end") if f in kwargs}

    defaults = {
        "doctype": "Coupon",
        "restaurant": restaurant,
        "code": code,
        "offer_type": "coupon",
        "discount_type": "flat",
        "discount_value": 10.0,
        "is_active": 1,
    }
    defaults.update(kwargs)
    doc = frappe.get_doc(defaults)
    doc.insert(ignore_permissions=True)

    if time_fields:
        frappe.db.set_value("Coupon", doc.name, time_fields)
        doc.update(time_fields)

    frappe.db.commit()
    return doc


def cleanup_coupons(restaurant):
    frappe.db.delete("Coupon Usage", {"restaurant": restaurant})
    frappe.db.delete("Coupon", {"restaurant": restaurant})
    frappe.db.commit()


# ─── Test: Coupon.validate() ─────────────────────────────────────────────────

class TestCouponValidate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PREFIX}-VAL").name

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    # ── JSON field constraint fix (the original bug) ──────────────────────────

    def test_required_items_empty_string_becomes_none(self):
        """required_items='' must be coerced to None so MariaDB JSON constraint passes."""
        doc = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant,
            "code": "COMBO1",
            "offer_type": "coupon",
            "discount_type": "flat",
            "discount_value": 5.0,
            "is_active": 1,
            "required_items": "",          # ← the trigger for the original bug
        })
        doc.insert(ignore_permissions=True)   # must NOT raise OperationalError
        frappe.db.commit()
        saved = frappe.db.get_value("Coupon", doc.name, "required_items")
        self.assertIsNone(saved, "required_items should be NULL in DB, not empty string")

    def test_valid_days_of_week_empty_string_becomes_none(self):
        """valid_days_of_week='' must also be coerced to None."""
        doc = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant,
            "code": "DAYS1",
            "offer_type": "coupon",
            "discount_type": "flat",
            "discount_value": 5.0,
            "is_active": 1,
            "valid_days_of_week": "",
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        saved = frappe.db.get_value("Coupon", doc.name, "valid_days_of_week")
        self.assertIsNone(saved)

    def test_valid_json_required_items_preserved(self):
        """A valid JSON string for required_items must survive save unchanged."""
        items_json = json.dumps(["dish-1", "dish-2"])
        doc = make_coupon(
            self.restaurant, code="COMBO2",
            offer_type="combo",
            required_items=items_json,
        )
        saved = frappe.db.get_value("Coupon", doc.name, "required_items")
        self.assertEqual(json.loads(saved), ["dish-1", "dish-2"])

    # ── Code normalisation ────────────────────────────────────────────────────

    def test_code_uppercased_on_save(self):
        doc = make_coupon(self.restaurant, code="save20")
        self.assertEqual(doc.code, "SAVE20")

    def test_code_stripped_on_save(self):
        doc = make_coupon(self.restaurant, code="  TRIM  ")
        self.assertEqual(doc.code, "TRIM")

    # ── Duplicate code validation ─────────────────────────────────────────────

    def test_duplicate_code_same_restaurant_rejected(self):
        make_coupon(self.restaurant, code="DUP10")
        with self.assertRaises(frappe.ValidationError):
            make_coupon(self.restaurant, code="DUP10")

    def test_duplicate_code_different_restaurant_allowed(self):
        r2 = make_restaurant(f"{_PREFIX}-VAL2").name
        try:
            make_coupon(self.restaurant, code="MULTI10")
            # Should NOT raise
            make_coupon(r2, code="MULTI10")
        finally:
            cleanup_coupons(r2)
            cleanup_restaurant(r2)


# ─── Test: get_coupon_details() ──────────────────────────────────────────────

class TestGetCouponDetails(unittest.TestCase):
    """
    Tests for the internal helper used by validate_coupon API.
    We patch time/date utilities where needed so tests are deterministic.
    """

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PREFIX}-DET").name
        cls.customer = make_customer(phone="9100000001", name="Coupon Test Customer")

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def _call(self, coupon_code, cart_total=200, customer_id=None, cart_items=None):
        from dinematters.dinematters.api.coupons import get_coupon_details
        return get_coupon_details(
            self.restaurant, coupon_code,
            cart_total=cart_total,
            customer_id=customer_id,
            cart_items=cart_items,
        )

    # ── Not found / inactive ─────────────────────────────────────────────────

    def test_not_found(self):
        result = self._call("NOSUCHCODE")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "COUPON_NOT_FOUND")

    def test_inactive_coupon(self):
        make_coupon(self.restaurant, code="INACT", is_active=0)
        result = self._call("INACT")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "COUPON_INACTIVE")

    # ── Date validity ─────────────────────────────────────────────────────────

    def test_expired_coupon(self):
        make_coupon(self.restaurant, code="EXP", valid_until=add_days(today(), -1))
        result = self._call("EXP")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "COUPON_EXPIRED")

    def test_not_valid_yet(self):
        make_coupon(self.restaurant, code="FUTURE", valid_from=add_days(today(), 1))
        result = self._call("FUTURE")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "COUPON_NOT_VALID_YET")

    def test_valid_until_today_is_accepted(self):
        make_coupon(self.restaurant, code="TODAY", valid_until=today(), discount_value=15.0)
        result = self._call("TODAY")
        self.assertTrue(result["success"])

    def test_valid_from_today_is_accepted(self):
        make_coupon(self.restaurant, code="FROMTDY", valid_from=today(), discount_value=12.0)
        result = self._call("FROMTDY")
        self.assertTrue(result["success"])

    # ── Min order ────────────────────────────────────────────────────────────

    def test_min_order_not_met(self):
        make_coupon(self.restaurant, code="MIN500", min_order_amount=500)
        result = self._call("MIN500", cart_total=100)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "MIN_ORDER_NOT_MET")

    def test_min_order_exactly_met(self):
        make_coupon(self.restaurant, code="MIN200", min_order_amount=200, discount_value=20.0)
        result = self._call("MIN200", cart_total=200)
        self.assertTrue(result["success"])

    # ── Usage limits ─────────────────────────────────────────────────────────

    def test_usage_limit_exhausted(self):
        make_coupon(self.restaurant, code="USED", max_uses=5, usage_count=5)
        result = self._call("USED")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "COUPON_LIMIT_REACHED")

    def test_usage_limit_not_yet_exhausted(self):
        make_coupon(self.restaurant, code="NOTUSED", max_uses=5, usage_count=4, discount_value=10.0)
        result = self._call("NOTUSED")
        self.assertTrue(result["success"])

    def test_customer_limit_exhausted(self):
        coupon_doc = make_coupon(self.restaurant, code="CUSTLIM", max_uses_per_user=2)
        customer_id = self.customer.name
        # Insert usage records via raw SQL to bypass mandatory field validation
        # (order and discount_amount are required by the doctype but irrelevant to the count check)
        for i in range(2):
            frappe.db.sql(
                """INSERT INTO `tabCoupon Usage`
                   (name, coupon, customer, restaurant, `order`, discount_amount, usage_date, docstatus, modified, creation, owner, modified_by)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW(), 0, NOW(), NOW(), 'Administrator', 'Administrator')""",
                (f"TEST-CU-{coupon_doc.name}-{i}", coupon_doc.name, customer_id, self.restaurant, f"TEST-ORDER-{i}", 10.0),
            )
        frappe.db.commit()

        result = self._call("CUSTLIM", customer_id=customer_id)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "CUSTOMER_LIMIT_REACHED")

    # ── Day-of-week restriction ───────────────────────────────────────────────

    def test_invalid_day_of_week(self):
        # Force current day to "monday", allow only "sunday"
        make_coupon(
            self.restaurant, code="SUNONLY",
            valid_days_of_week=json.dumps(["sunday"]),
        )
        with patch("dinematters.dinematters.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0, 0)  # Monday
            result = self._call("SUNONLY")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INVALID_DAY")

    def test_valid_day_of_week(self):
        make_coupon(
            self.restaurant, code="MONOK",
            valid_days_of_week=json.dumps(["monday"]),
            discount_value=8.0,
        )
        with patch("dinematters.dinematters.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0, 0)  # Monday
            result = self._call("MONOK")
        self.assertTrue(result["success"])

    # ── Time-of-day restriction ───────────────────────────────────────────────

    def test_too_early(self):
        make_coupon(self.restaurant, code="LUNCH", valid_time_start="12:00:00")
        with patch("dinematters.dinematters.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 10, 0, 0)  # 10 AM
            result = self._call("LUNCH")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INVALID_TIME")

    def test_too_late(self):
        make_coupon(self.restaurant, code="BRKFST", valid_time_end="10:00:00")
        with patch("dinematters.dinematters.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 11, 0, 0)  # 11 AM
            result = self._call("BRKFST")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INVALID_TIME")

    def test_within_time_window(self):
        make_coupon(
            self.restaurant, code="DINETIME",
            valid_time_start="18:00:00", valid_time_end="22:00:00",
            discount_value=30.0,
        )
        with patch("dinematters.dinematters.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 19, 30, 0)  # 7:30 PM
            result = self._call("DINETIME")
        self.assertTrue(result["success"])

    # ── Combo validation ──────────────────────────────────────────────────────

    def test_combo_no_cart_items_provided(self):
        make_coupon(
            self.restaurant, code="BUNDLE",
            offer_type="combo",
            required_items=json.dumps(["dish-A"]),
        )
        result = self._call("BUNDLE", cart_items=None)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "COMBO_ITEMS_MISSING")

    def test_combo_missing_required_item(self):
        make_coupon(
            self.restaurant, code="BUNDLE2",
            offer_type="combo",
            required_items=json.dumps(["dish-A", "dish-B"]),
        )
        result = self._call(
            "BUNDLE2",
            cart_items=[{"dishId": "dish-A"}],  # dish-B missing
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "COMBO_INCOMPLETE")

    def test_combo_all_required_items_present(self):
        make_coupon(
            self.restaurant, code="BUNDLE3",
            offer_type="combo",
            required_items=json.dumps(["dish-A", "dish-B"]),
            combo_price=150.0,
        )
        result = self._call(
            "BUNDLE3",
            cart_total=300,
            cart_items=[{"dishId": "dish-A"}, {"dishId": "dish-B"}],
        )
        self.assertTrue(result["success"])
        # discount = cart_total - combo_price = 300 - 150 = 150
        self.assertAlmostEqual(result["discount_amount"], 150.0)

    # ── Discount calculation ──────────────────────────────────────────────────

    def test_flat_discount(self):
        make_coupon(self.restaurant, code="FLAT50", discount_type="flat", discount_value=50.0)
        result = self._call("FLAT50", cart_total=300)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 50.0)

    def test_percent_discount(self):
        make_coupon(self.restaurant, code="PCT10", discount_type="percent", discount_value=10.0)
        result = self._call("PCT10", cart_total=200)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 20.0)  # 10% of 200

    def test_percent_discount_capped(self):
        make_coupon(
            self.restaurant, code="PCT20CAP",
            discount_type="percent", discount_value=20.0,
            max_discount_cap=30.0,
        )
        result = self._call("PCT20CAP", cart_total=500)
        self.assertTrue(result["success"])
        # 20% of 500 = 100, capped at 30
        self.assertAlmostEqual(result["discount_amount"], 30.0)

    def test_percent_discount_below_cap(self):
        make_coupon(
            self.restaurant, code="PCT20NOCAP",
            discount_type="percent", discount_value=20.0,
            max_discount_cap=100.0,
        )
        result = self._call("PCT20NOCAP", cart_total=200)
        self.assertTrue(result["success"])
        # 20% of 200 = 40, below cap of 100
        self.assertAlmostEqual(result["discount_amount"], 40.0)

    def test_combo_price_discount(self):
        make_coupon(
            self.restaurant, code="COMBOFIX",
            offer_type="combo",
            combo_price=100.0,
            required_items=None,
        )
        result = self._call("COMBOFIX", cart_total=250)
        self.assertTrue(result["success"])
        # discount = 250 - 100 = 150
        self.assertAlmostEqual(result["discount_amount"], 150.0)

    def test_result_contains_expected_fields(self):
        make_coupon(self.restaurant, code="FIELDS", discount_value=5.0)
        result = self._call("FIELDS")
        self.assertTrue(result["success"])
        for key in ("coupon_name", "coupon_code", "discount_amount", "type", "priority", "can_stack"):
            self.assertIn(key, result, f"Missing key: {key}")


# ─── Test: validate_offer_eligibility() ─────────────────────────────────────

class TestValidateOfferEligibility(unittest.TestCase):
    """Unit tests for pricing.validate_offer_eligibility() using mock offer dicts."""

    def _offer(self, **kwargs):
        """Build a minimal mock offer object (SimpleNamespace-style via MagicMock)."""
        defaults = dict(
            name="TEST-OFFER",
            code="TEST",
            discount_value=10.0,
            discount_type="flat",
            offer_type="coupon",
            category="",
            min_order_amount=0,
            max_uses=0,
            usage_count=0,
            max_uses_per_user=0,
            valid_from=None,
            valid_until=None,
            valid_days_of_week=None,
            valid_time_start=None,
            valid_time_end=None,
            max_discount_cap=None,
            required_items=None,
            combo_price=None,
            can_stack=0,
        )
        defaults.update(kwargs)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _call(self, offer, cart_total=200, customer_id=None, cart_items=None, delivery_type=None, delivery_fee=0):
        from dinematters.dinematters.utils.pricing import validate_offer_eligibility
        return validate_offer_eligibility(
            offer, cart_total, customer_id,
            cart_items or [], delivery_type, delivery_fee,
        )

    # ── Delivery offer guards ─────────────────────────────────────────────────

    def test_delivery_offer_rejected_for_dine_in(self):
        offer = self._offer(discount_type="delivery")
        result = self._call(offer, delivery_type="Dine-in")
        self.assertFalse(result["success"])

    def test_delivery_offer_accepted_for_delivery_order(self):
        offer = self._offer(discount_type="delivery", discount_value=40.0)
        result = self._call(offer, delivery_type="Delivery", delivery_fee=40.0)
        self.assertTrue(result["success"])

    # ── Date guards ───────────────────────────────────────────────────────────

    def test_future_valid_from_skipped(self):
        offer = self._offer(valid_from=add_days(today(), 1))
        result = self._call(offer)
        self.assertFalse(result["success"])

    def test_expired_valid_until_skipped(self):
        offer = self._offer(valid_until=add_days(today(), -1))
        result = self._call(offer)
        self.assertFalse(result["success"])

    # ── Min order ────────────────────────────────────────────────────────────

    def test_min_order_not_met(self):
        offer = self._offer(min_order_amount=500)
        result = self._call(offer, cart_total=100)
        self.assertFalse(result["success"])

    def test_min_order_met(self):
        offer = self._offer(min_order_amount=100)
        result = self._call(offer, cart_total=100)
        self.assertTrue(result["success"])

    # ── Day-of-week ───────────────────────────────────────────────────────────

    def test_wrong_day_of_week(self):
        offer = self._offer(valid_days_of_week=json.dumps(["sunday"]))
        with patch("dinematters.dinematters.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0)  # Monday
            result = self._call(offer)
        self.assertFalse(result["success"])

    def test_correct_day_of_week(self):
        offer = self._offer(valid_days_of_week=json.dumps(["monday"]))
        with patch("dinematters.dinematters.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0)  # Monday
            result = self._call(offer)
        self.assertTrue(result["success"])

    # ── Time-of-day ───────────────────────────────────────────────────────────

    def test_too_early(self):
        offer = self._offer(valid_time_start="14:00:00")
        with patch("dinematters.dinematters.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 10, 0)  # 10 AM
            result = self._call(offer)
        self.assertFalse(result["success"])

    def test_too_late(self):
        offer = self._offer(valid_time_end="10:00:00")
        with patch("dinematters.dinematters.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0)  # Noon
            result = self._call(offer)
        self.assertFalse(result["success"])

    def test_within_time_window(self):
        offer = self._offer(valid_time_start="10:00:00", valid_time_end="14:00:00")
        with patch("dinematters.dinematters.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0)  # Noon
            result = self._call(offer)
        self.assertTrue(result["success"])

    # ── Usage limits ─────────────────────────────────────────────────────────

    def test_usage_limit_exhausted(self):
        offer = self._offer(max_uses=10, usage_count=10)
        result = self._call(offer)
        self.assertFalse(result["success"])

    def test_usage_limit_not_exhausted(self):
        offer = self._offer(max_uses=10, usage_count=9)
        result = self._call(offer)
        self.assertTrue(result["success"])

    # ── Combo ─────────────────────────────────────────────────────────────────

    def test_combo_missing_required_item(self):
        offer = self._offer(offer_type="combo", required_items=json.dumps(["dish-X"]))
        cart_items = [{"dishId": "dish-Y"}]
        result = self._call(offer, cart_items=cart_items)
        self.assertFalse(result["success"])

    def test_combo_all_items_present(self):
        offer = self._offer(
            offer_type="combo",
            required_items=json.dumps(["dish-X", "dish-Y"]),
            combo_price=100.0,
        )
        cart_items = [{"dishId": "dish-X"}, {"dishId": "dish-Y"}]
        result = self._call(offer, cart_total=250, cart_items=cart_items)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 150.0)  # 250 - 100

    # ── Discount calculations ─────────────────────────────────────────────────

    def test_flat_discount(self):
        offer = self._offer(discount_type="flat", discount_value=25.0)
        result = self._call(offer, cart_total=200)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 25.0)

    def test_percent_discount(self):
        offer = self._offer(discount_type="percent", discount_value=10.0)
        result = self._call(offer, cart_total=300)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 30.0)

    def test_percent_discount_with_cap(self):
        offer = self._offer(discount_type="percent", discount_value=50.0, max_discount_cap=40.0)
        result = self._call(offer, cart_total=200)  # 50% of 200 = 100, capped at 40
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 40.0)

    def test_delivery_free_delivery_equals_fee(self):
        offer = self._offer(discount_type="delivery", category="delivery")
        result = self._call(offer, delivery_type="Delivery", delivery_fee=60.0)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 60.0)

    def test_delivery_percent_discount(self):
        offer = self._offer(
            discount_type="percent",
            discount_value=50.0,
            category="delivery",
        )
        result = self._call(offer, delivery_type="Delivery", delivery_fee=80.0)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 40.0)  # 50% of 80


if __name__ == "__main__":
    unittest.main()
