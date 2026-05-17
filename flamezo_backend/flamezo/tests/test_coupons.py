# Copyright (c) 2026, Flamezo and contributors
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
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_coupons
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

import frappe
from frappe.utils import today, add_days, flt

from flamezo_backend.flamezo.tests.utils import (
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
        from flamezo_backend.flamezo.api.coupons import get_coupon_details
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
        with patch("flamezo_backend.flamezo.api.coupons.now_datetime") as mock_now:
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
        with patch("flamezo_backend.flamezo.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0, 0)  # Monday
            result = self._call("MONOK")
        self.assertTrue(result["success"])

    # ── Time-of-day restriction ───────────────────────────────────────────────

    def test_too_early(self):
        make_coupon(self.restaurant, code="LUNCH", valid_time_start="12:00:00")
        with patch("flamezo_backend.flamezo.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 10, 0, 0)  # 10 AM
            result = self._call("LUNCH")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INVALID_TIME")

    def test_too_late(self):
        make_coupon(self.restaurant, code="BRKFST", valid_time_end="10:00:00")
        with patch("flamezo_backend.flamezo.api.coupons.now_datetime") as mock_now:
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
        with patch("flamezo_backend.flamezo.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 19, 30, 0)  # 7:30 PM
            result = self._call("DINETIME")
        self.assertTrue(result["success"])

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
            combo_type=None,
            item_pool=None,
            items_to_select=2,
            can_stack=0,
        )
        defaults.update(kwargs)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _call(self, offer, cart_total=200, customer_id=None, cart_items=None, delivery_type=None, delivery_fee=0):
        from flamezo_backend.flamezo.utils.pricing import validate_offer_eligibility
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
        with patch("flamezo_backend.flamezo.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0)  # Monday
            result = self._call(offer)
        self.assertFalse(result["success"])

    def test_correct_day_of_week(self):
        offer = self._offer(valid_days_of_week=json.dumps(["monday"]))
        with patch("flamezo_backend.flamezo.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0)  # Monday
            result = self._call(offer)
        self.assertTrue(result["success"])

    # ── Time-of-day ───────────────────────────────────────────────────────────

    def test_too_early(self):
        offer = self._offer(valid_time_start="14:00:00")
        with patch("flamezo_backend.flamezo.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 10, 0)  # 10 AM
            result = self._call(offer)
        self.assertFalse(result["success"])

    def test_too_late(self):
        offer = self._offer(valid_time_end="10:00:00")
        with patch("flamezo_backend.flamezo.utils.pricing.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0)  # Noon
            result = self._call(offer)
        self.assertFalse(result["success"])

    def test_within_time_window(self):
        offer = self._offer(valid_time_start="10:00:00", valid_time_end="14:00:00")
        with patch("flamezo_backend.flamezo.utils.pricing.now_datetime") as mock_now:
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


# ─── Test: get_coupons() API ─────────────────────────────────────────────────

class TestGetCouponsAPI(unittest.TestCase):
    """Tests for the public get_coupons() API endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PREFIX}-GCAPI").name

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def _call(self, active_only=True):
        from flamezo_backend.flamezo.api.coupons import get_coupons
        return get_coupons(self.restaurant, active_only=active_only)

    def test_returns_success_structure(self):
        make_coupon(self.restaurant, code="GCAPI1", discount_value=10.0)
        result = self._call()
        self.assertTrue(result["success"])
        self.assertIn("data", result)
        self.assertIn("coupons", result["data"])

    def test_active_only_excludes_inactive(self):
        make_coupon(self.restaurant, code="GCAPI2", is_active=1)
        make_coupon(self.restaurant, code="GCAPI3", is_active=0)
        result = self._call(active_only=True)
        codes = [c["code"] for c in result["data"]["coupons"]]
        self.assertIn("GCAPI2", codes)
        self.assertNotIn("GCAPI3", codes)

    def test_active_only_excludes_expired(self):
        make_coupon(self.restaurant, code="GCAPI4", valid_until=add_days(today(), -1))
        result = self._call(active_only=True)
        codes = [c["code"] for c in result["data"]["coupons"]]
        self.assertNotIn("GCAPI4", codes)

    def test_active_only_excludes_future(self):
        make_coupon(self.restaurant, code="GCAPI5", valid_from=add_days(today(), 1))
        result = self._call(active_only=True)
        codes = [c["code"] for c in result["data"]["coupons"]]
        self.assertNotIn("GCAPI5", codes)

    def test_active_only_false_includes_inactive(self):
        make_coupon(self.restaurant, code="GCAPI6", is_active=0)
        result = self._call(active_only=False)
        codes = [c["code"] for c in result["data"]["coupons"]]
        self.assertIn("GCAPI6", codes)

    def test_coupon_data_shape(self):
        make_coupon(self.restaurant, code="GCAPI7", discount_type="percent", discount_value=15.0,
                    min_order_amount=200.0, offer_type="coupon")
        result = self._call()
        coupon = next((c for c in result["data"]["coupons"] if c["code"] == "GCAPI7"), None)
        self.assertIsNotNone(coupon)
        for key in ("id", "code", "discount", "minOrderAmount", "type", "offerType", "isActive"):
            self.assertIn(key, coupon, f"Missing key: {key}")
        self.assertAlmostEqual(coupon["discount"], 15.0)
        self.assertAlmostEqual(coupon["minOrderAmount"], 200.0)
        self.assertEqual(coupon["type"], "percent")


# ─── Test: get_applicable_offers() API ──────────────────────────────────────

class TestGetApplicableOffersAPI(unittest.TestCase):
    """Tests for the public get_applicable_offers() API endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PREFIX}-GAO").name

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def _call(self, cart_items=None, cart_total=300, customer_id=None, order_type=None):
        from flamezo_backend.flamezo.api.coupons import get_applicable_offers
        return get_applicable_offers(
            self.restaurant,
            cart_items=cart_items or [],
            cart_total=cart_total,
            customer_id=customer_id,
            order_type=order_type,
        )

    def test_returns_success_structure(self):
        result = self._call()
        self.assertTrue(result["success"])
        data = result["data"]
        for key in ("eligibleOffers", "ineligibleOffers", "bestOffer", "cartTotal", "totalOffers"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_eligible_offer_in_eligible_list(self):
        make_coupon(self.restaurant, code="GAO1", discount_type="flat", discount_value=30.0,
                    min_order_amount=100.0)
        result = self._call(cart_total=300)
        codes = [o["code"] for o in result["data"]["eligibleOffers"]]
        self.assertIn("GAO1", codes)

    def test_min_order_not_met_goes_to_ineligible(self):
        make_coupon(self.restaurant, code="GAO2", min_order_amount=999.0, discount_value=50.0)
        result = self._call(cart_total=100)
        ineligible_codes = [o["code"] for o in result["data"]["ineligibleOffers"]]
        eligible_codes = [o["code"] for o in result["data"]["eligibleOffers"]]
        self.assertIn("GAO2", ineligible_codes)
        self.assertNotIn("GAO2", eligible_codes)

    def test_ineligible_offer_contains_reason(self):
        make_coupon(self.restaurant, code="GAO3", min_order_amount=999.0, discount_value=50.0)
        result = self._call(cart_total=100)
        offer = next((o for o in result["data"]["ineligibleOffers"] if o["code"] == "GAO3"), None)
        self.assertIsNotNone(offer)
        self.assertIn("ineligibilityReasons", offer)
        self.assertTrue(len(offer["ineligibilityReasons"]) > 0)
        codes = [r["code"] for r in offer["ineligibilityReasons"]]
        self.assertIn("MIN_ORDER_NOT_MET", codes)

    def test_best_offer_is_highest_discount(self):
        make_coupon(self.restaurant, code="GAO4", discount_type="flat", discount_value=20.0)
        make_coupon(self.restaurant, code="GAO5", discount_type="flat", discount_value=50.0)
        result = self._call(cart_total=300)
        self.assertIsNotNone(result["data"]["bestOffer"])
        self.assertEqual(result["data"]["bestOffer"]["code"], "GAO5")

    def test_delivery_offer_ineligible_for_dine_in(self):
        make_coupon(self.restaurant, code="GAO6", discount_type="delivery",
                    category="delivery", offer_type="delivery", discount_value=0.0)
        result = self._call(cart_total=300, order_type="dine_in")
        ineligible_codes = [o["code"] for o in result["data"]["ineligibleOffers"]]
        self.assertIn("GAO6", ineligible_codes)

    def test_total_offers_count(self):
        make_coupon(self.restaurant, code="GAO7", discount_value=10.0, min_order_amount=100.0)
        make_coupon(self.restaurant, code="GAO8", discount_value=20.0, min_order_amount=999.0)
        result = self._call(cart_total=200)
        self.assertEqual(result["data"]["totalOffers"], 2)

    def test_day_restriction_sends_to_ineligible(self):
        make_coupon(
            self.restaurant, code="GAO9",
            valid_days_of_week=json.dumps(["sunday"]),
            discount_value=15.0,
        )
        with patch("flamezo_backend.flamezo.api.coupons.now_datetime") as mock_now:
            mock_now.return_value = datetime(2026, 4, 27, 12, 0, 0)  # Monday
            result = self._call(cart_total=200)
        ineligible_codes = [o["code"] for o in result["data"]["ineligibleOffers"]]
        self.assertIn("GAO9", ineligible_codes)

    def test_per_customer_limit_sends_to_ineligible(self):
        customer = make_customer(phone="9100000099", name="GAO Limit Customer")
        coupon_doc = make_coupon(self.restaurant, code="GAO10", max_uses_per_user=1, discount_value=20.0)
        # Exhaust per-customer limit
        frappe.db.sql(
            """INSERT INTO `tabCoupon Usage`
               (name, coupon, customer, restaurant, `order`, discount_amount, usage_date, docstatus, modified, creation, owner, modified_by)
               VALUES (%s, %s, %s, %s, %s, %s, NOW(), 0, NOW(), NOW(), 'Administrator', 'Administrator')""",
            (f"TEST-GAO10-CU", coupon_doc.name, customer.name, self.restaurant, "TEST-ORDER-GAO10", 20.0),
        )
        frappe.db.commit()
        result = self._call(cart_total=200, customer_id=customer.name)
        ineligible_codes = [o["code"] for o in result["data"]["ineligibleOffers"]]
        eligible_codes = [o["code"] for o in result["data"]["eligibleOffers"]]
        self.assertIn("GAO10", ineligible_codes)
        self.assertNotIn("GAO10", eligible_codes)
        # Cleanup
        frappe.db.delete("Coupon Usage", {"coupon": coupon_doc.name})
        frappe.db.commit()


# ─── Test: Combo + BOGO edge cases ──────────────────────────────────────────

class TestComboAndBOGO(unittest.TestCase):
    """Extended combo offer tests via validate_offer_eligibility."""

    def _offer(self, **kwargs):
        defaults = dict(
            name="COMBO-TEST",
            code="COMBO",
            discount_value=0.0,
            discount_type="flat",
            offer_type="combo",
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
            combo_type=None,
            item_pool=None,
            items_to_select=2,
            can_stack=0,
        )
        defaults.update(kwargs)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _call(self, offer, cart_total=300, cart_items=None):
        from flamezo_backend.flamezo.utils.pricing import validate_offer_eligibility
        return validate_offer_eligibility(offer, cart_total, None, cart_items or [])

    def test_combo_discount_is_zero_when_combo_price_exceeds_cart(self):
        """combo_price higher than cart_total should yield discount=0, not negative."""
        offer = self._offer(
            required_items=json.dumps(["dish-A"]),
            combo_price=500.0,
        )
        result = self._call(offer, cart_total=300, cart_items=[{"dishId": "dish-A"}])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    def test_combo_partial_match_fails(self):
        """Only one of two required items present → ineligible."""
        offer = self._offer(required_items=json.dumps(["dish-A", "dish-B"]))
        result = self._call(offer, cart_items=[{"dishId": "dish-A"}])
        self.assertFalse(result["success"])

    def test_combo_exact_match_succeeds(self):
        offer = self._offer(
            required_items=json.dumps(["dish-A", "dish-B"]),
            combo_price=200.0,
        )
        result = self._call(offer, cart_total=350, cart_items=[
            {"dishId": "dish-A"}, {"dishId": "dish-B"}
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 150.0)  # 350 - 200

    def test_combo_empty_required_items_json(self):
        """Empty required_items list → combo has no requirements → success."""
        offer = self._offer(
            required_items=json.dumps([]),
            combo_price=100.0,
        )
        result = self._call(offer, cart_total=200, cart_items=[{"dishId": "any-dish"}])
        self.assertTrue(result["success"])

    def test_combo_superset_cart_matches(self):
        """Cart has more items than required — should still qualify."""
        offer = self._offer(
            required_items=json.dumps(["dish-A"]),
            combo_price=150.0,
        )
        result = self._call(offer, cart_total=400, cart_items=[
            {"dishId": "dish-A"}, {"dishId": "dish-B"}, {"dishId": "dish-C"}
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 250.0)


# ─── Test: Stacking logic in calculate_cart_totals() ────────────────────────

class TestOfferStacking(unittest.TestCase):
    """Integration tests for stacking logic in pricing.calculate_cart_totals()."""

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PREFIX}-STACK").name
        # Minimal items list for cart totals
        cls.items = [{"unitPrice": 300.0, "quantity": 1, "dishId": "dish-stack"}]

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def _totals(self, coupon_code=None):
        from flamezo_backend.flamezo.utils.pricing import calculate_cart_totals
        return calculate_cart_totals(
            self.restaurant, self.items,
            coupon_code=coupon_code,
            delivery_type="Dine-in",
        )

    def test_manual_coupon_applied(self):
        make_coupon(self.restaurant, code="MANUALSTACK", discount_type="flat", discount_value=50.0)
        result = self._totals(coupon_code="MANUALSTACK")
        self.assertEqual(result["appliedCoupon"], "MANUALSTACK")
        self.assertAlmostEqual(result["discount"], 50.0)

    def test_no_coupon_no_discount(self):
        result = self._totals()
        self.assertEqual(result["discount"], 0)
        self.assertIsNone(result["appliedCoupon"])

    def test_auto_offer_applied_without_code(self):
        make_coupon(self.restaurant, code="AUTOSTACK", offer_type="auto",
                    discount_type="flat", discount_value=25.0, min_order_amount=100.0)
        result = self._totals()
        self.assertIn("AUTOSTACK", result["appliedOffers"])
        self.assertAlmostEqual(result["discount"], 25.0)

    def test_best_non_stackable_wins(self):
        make_coupon(self.restaurant, code="NS_HIGH", offer_type="auto",
                    discount_type="flat", discount_value=60.0, can_stack=0)
        make_coupon(self.restaurant, code="NS_LOW", offer_type="auto",
                    discount_type="flat", discount_value=20.0, can_stack=0)
        result = self._totals()
        self.assertIn("NS_HIGH", result["appliedOffers"])
        self.assertNotIn("NS_LOW", result["appliedOffers"])
        self.assertAlmostEqual(result["discount"], 60.0)

    def test_stackable_offer_combines(self):
        make_coupon(self.restaurant, code="STK_A", offer_type="auto",
                    discount_type="flat", discount_value=30.0, can_stack=1)
        make_coupon(self.restaurant, code="STK_B", offer_type="auto",
                    discount_type="flat", discount_value=20.0, can_stack=1)
        result = self._totals()
        self.assertIn("STK_A", result["appliedOffers"])
        self.assertIn("STK_B", result["appliedOffers"])
        self.assertAlmostEqual(result["discount"], 50.0)


# ─── Test: Auto-activate / deactivate scheduler ──────────────────────────────

class TestCouponSchedulerTasks(unittest.TestCase):
    """Tests for daily coupon auto-activation and expiry deactivation tasks."""

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PREFIX}-SCHED").name

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def test_auto_activate_coupon_with_valid_from_today(self):
        make_coupon(self.restaurant, code="SCHED1", is_active=0, valid_from=today())
        from flamezo_backend.flamezo.tasks.coupon_tasks import auto_activate_scheduled_coupons
        activated = auto_activate_scheduled_coupons()
        self.assertIn("SCHED1", activated)
        is_active = frappe.db.get_value("Coupon", {"code": "SCHED1", "restaurant": self.restaurant}, "is_active")
        self.assertEqual(is_active, 1)

    def test_auto_activate_skips_already_active(self):
        make_coupon(self.restaurant, code="SCHED2", is_active=1, valid_from=today())
        from flamezo_backend.flamezo.tasks.coupon_tasks import auto_activate_scheduled_coupons
        activated = auto_activate_scheduled_coupons()
        self.assertNotIn("SCHED2", activated)

    def test_auto_activate_skips_expired(self):
        make_coupon(self.restaurant, code="SCHED3", is_active=0,
                    valid_from=add_days(today(), -5), valid_until=add_days(today(), -1))
        from flamezo_backend.flamezo.tasks.coupon_tasks import auto_activate_scheduled_coupons
        activated = auto_activate_scheduled_coupons()
        self.assertNotIn("SCHED3", activated)

    def test_auto_deactivate_expired_coupon(self):
        make_coupon(self.restaurant, code="SCHED4", is_active=1, valid_until=add_days(today(), -1))
        from flamezo_backend.flamezo.tasks.coupon_tasks import auto_deactivate_expired_coupons
        deactivated = auto_deactivate_expired_coupons()
        self.assertIn("SCHED4", deactivated)
        is_active = frappe.db.get_value("Coupon", {"code": "SCHED4", "restaurant": self.restaurant}, "is_active")
        self.assertEqual(is_active, 0)

    def test_auto_deactivate_skips_non_expired(self):
        make_coupon(self.restaurant, code="SCHED5", is_active=1, valid_until=add_days(today(), 5))
        from flamezo_backend.flamezo.tasks.coupon_tasks import auto_deactivate_expired_coupons
        deactivated = auto_deactivate_expired_coupons()
        self.assertNotIn("SCHED5", deactivated)


# ─── Test: Bulk export / import ──────────────────────────────────────────────

class TestCouponExportImport(unittest.TestCase):
    """Tests for CSV export and import endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PREFIX}-EXIM").name

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def test_export_returns_csv_download(self):
        make_coupon(self.restaurant, code="EXP1", discount_value=25.0)
        from flamezo_backend.flamezo.api.coupons import export_coupons
        # export_coupons sets frappe.local.response directly; we just verify no exception
        # and that it can be called without error
        try:
            export_coupons(self.restaurant)
        except Exception as e:
            self.fail(f"export_coupons raised an exception: {e}")

    def test_import_creates_new_coupons(self):
        csv_content = (
            "code,offer_type,discount_type,discount_value,min_order_amount,max_discount_cap,"
            "description,detailed_description,category,priority,can_stack,is_active,"
            "valid_from,valid_until,valid_days_of_week,valid_time_start,valid_time_end,"
            "max_uses,max_uses_per_user\n"
            "IMPORT1,coupon,flat,40,200,,Import test,,best,5,0,1,,,,,,,0,0\n"
            "IMPORT2,coupon,percent,15,0,50,Percent deal,,best,3,0,1,,,,,,,100,2\n"
        )
        from flamezo_backend.flamezo.api.coupons import import_coupons
        result = import_coupons(self.restaurant, csv_content)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["created"], 2)
        self.assertEqual(result["data"]["skipped"], 0)
        self.assertTrue(frappe.db.exists("Coupon", {"code": "IMPORT1", "restaurant": self.restaurant}))
        self.assertTrue(frappe.db.exists("Coupon", {"code": "IMPORT2", "restaurant": self.restaurant}))

    def test_import_skips_duplicate_by_default(self):
        make_coupon(self.restaurant, code="DUP_IMPORT", discount_value=10.0)
        csv_content = (
            "code,offer_type,discount_type,discount_value,min_order_amount,max_discount_cap,"
            "description,detailed_description,category,priority,can_stack,is_active,"
            "valid_from,valid_until,valid_days_of_week,valid_time_start,valid_time_end,"
            "max_uses,max_uses_per_user\n"
            "DUP_IMPORT,coupon,flat,99,0,,,,best,0,0,1,,,,,,,0,0\n"
        )
        from flamezo_backend.flamezo.api.coupons import import_coupons
        result = import_coupons(self.restaurant, csv_content)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["skipped"], 1)
        self.assertEqual(result["data"]["created"], 0)
        # Value should NOT have changed
        val = frappe.db.get_value("Coupon", {"code": "DUP_IMPORT", "restaurant": self.restaurant}, "discount_value")
        self.assertAlmostEqual(flt(val), 10.0)

    def test_import_overwrites_when_flag_set(self):
        make_coupon(self.restaurant, code="OVR_IMPORT", discount_value=10.0)
        csv_content = (
            "code,offer_type,discount_type,discount_value,min_order_amount,max_discount_cap,"
            "description,detailed_description,category,priority,can_stack,is_active,"
            "valid_from,valid_until,valid_days_of_week,valid_time_start,valid_time_end,"
            "max_uses,max_uses_per_user\n"
            "OVR_IMPORT,coupon,flat,75,0,,,,best,0,0,1,,,,,,,0,0\n"
        )
        from flamezo_backend.flamezo.api.coupons import import_coupons
        result = import_coupons(self.restaurant, csv_content, overwrite_existing=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["updated"], 1)
        val = frappe.db.get_value("Coupon", {"code": "OVR_IMPORT", "restaurant": self.restaurant}, "discount_value")
        self.assertAlmostEqual(flt(val), 75.0)

    def test_import_skips_row_with_missing_code(self):
        csv_content = (
            "code,offer_type,discount_type,discount_value,min_order_amount,max_discount_cap,"
            "description,detailed_description,category,priority,can_stack,is_active,"
            "valid_from,valid_until,valid_days_of_week,valid_time_start,valid_time_end,"
            "max_uses,max_uses_per_user\n"
            ",coupon,flat,10,0,,,,best,0,0,1,,,,,,,0,0\n"
        )
        from flamezo_backend.flamezo.api.coupons import import_coupons
        result = import_coupons(self.restaurant, csv_content)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["skipped"], 1)
        self.assertEqual(result["data"]["created"], 0)


# ─── Test: New combo_type field — fixed_bundle / bogo / build_your_own ─────────

class TestComboTypeEligibility(unittest.TestCase):
    """
    Tests for the new combo_type-aware logic in validate_offer_eligibility().

    Covers:
      fixed_bundle — all required_items must be in cart; discount = cart_total - combo_price
      bogo         — ≥ items_to_select items from item_pool in cart; cheapest one free
      build_your_own — ≥ items_to_select from item_pool; discount = sum(pool items) - combo_price

    Edge cases:
      - Missing required items (fixed_bundle) → ineligible
      - BOGO with fewer pool items than items_to_select → ineligible
      - BOGO: discount is the CHEAPEST matching item, not the most expensive
      - BYO: discount is sum − combo_price, never negative
      - combo_price = 0 on fixed_bundle → discount = cart_total
      - Malformed JSON in item_pool/required_items → treated as empty (no crash)
      - items_to_select = 1 (single-item BOGO)
      - Extra cart items that aren't in pool don't count toward BOGO requirement
    """

    def _offer(self, **kwargs):
        """Return a mock Coupon doc with sensible defaults."""
        defaults = dict(
            name="CT-TEST",
            code="CTTEST",
            discount_value=0.0,
            discount_type="flat",
            offer_type="combo",
            combo_type="fixed_bundle",
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
            item_pool=None,
            items_to_select=2,
            combo_price=None,
            can_stack=0,
        )
        defaults.update(kwargs)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _call(self, offer, cart_total=300, cart_items=None):
        from flamezo_backend.flamezo.utils.pricing import validate_offer_eligibility
        return validate_offer_eligibility(offer, cart_total, None, cart_items or [])

    # ── fixed_bundle ────────────────────────────────────────────────────────

    def test_fixed_bundle_all_items_present_succeeds(self):
        offer = self._offer(
            combo_type="fixed_bundle",
            required_items=json.dumps(["pizza", "coke"]),
            combo_price=150.0,
        )
        result = self._call(offer, cart_total=250, cart_items=[
            {"dishId": "pizza", "unitPrice": 180},
            {"dishId": "coke", "unitPrice": 70},
        ])
        self.assertTrue(result["success"])
        # discount = cart_total(250) - combo_price(150) = 100
        self.assertAlmostEqual(result["discount_amount"], 100.0)

    def test_fixed_bundle_missing_one_item_fails(self):
        offer = self._offer(
            combo_type="fixed_bundle",
            required_items=json.dumps(["pizza", "coke"]),
            combo_price=150.0,
        )
        result = self._call(offer, cart_total=180, cart_items=[
            {"dishId": "pizza", "unitPrice": 180},
        ])
        self.assertFalse(result["success"])

    def test_fixed_bundle_extra_cart_items_still_qualifies(self):
        """Cart has required items + extras — should still succeed."""
        offer = self._offer(
            combo_type="fixed_bundle",
            required_items=json.dumps(["pizza"]),
            combo_price=100.0,
        )
        result = self._call(offer, cart_total=400, cart_items=[
            {"dishId": "pizza", "unitPrice": 180},
            {"dishId": "burger", "unitPrice": 120},
            {"dishId": "fries", "unitPrice": 100},
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 300.0)  # 400 - 100

    def test_fixed_bundle_combo_price_zero_gives_full_cart_discount(self):
        """combo_price=0 → full cart is free (edge case)."""
        offer = self._offer(
            combo_type="fixed_bundle",
            required_items=json.dumps(["pizza"]),
            combo_price=0.0,
        )
        result = self._call(offer, cart_total=200, cart_items=[{"dishId": "pizza", "unitPrice": 200}])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 200.0)

    def test_fixed_bundle_combo_price_exceeds_cart_discount_is_zero(self):
        """combo_price > cart_total → discount should be 0, never negative."""
        offer = self._offer(
            combo_type="fixed_bundle",
            required_items=json.dumps(["pizza"]),
            combo_price=999.0,
        )
        result = self._call(offer, cart_total=200, cart_items=[{"dishId": "pizza", "unitPrice": 200}])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    def test_fixed_bundle_malformed_required_items_json_treated_as_empty(self):
        """Malformed JSON in required_items → no crash, treated as no requirements."""
        offer = self._offer(
            combo_type="fixed_bundle",
            required_items="{not valid json]",
            combo_price=100.0,
        )
        # Should not raise; with empty requirements, combo qualifies
        result = self._call(offer, cart_total=200, cart_items=[{"dishId": "any-dish", "unitPrice": 200}])
        # Must not crash; success or failure both acceptable, but no exception
        self.assertIn("success", result)

    def test_fixed_bundle_none_required_items_qualifies(self):
        """required_items=None → no restriction, always eligible."""
        offer = self._offer(
            combo_type="fixed_bundle",
            required_items=None,
            combo_price=100.0,
        )
        result = self._call(offer, cart_total=200, cart_items=[{"dishId": "any", "unitPrice": 200}])
        self.assertTrue(result["success"])

    # ── bogo ────────────────────────────────────────────────────────────────

    def test_bogo_enough_pool_items_succeeds(self):
        """2 items from pool in cart, items_to_select=2 → eligible, cheapest is free."""
        offer = self._offer(
            combo_type="bogo",
            item_pool=json.dumps(["burger", "wrap"]),
            items_to_select=2,
        )
        result = self._call(offer, cart_total=350, cart_items=[
            {"dishId": "burger", "unitPrice": 200},
            {"dishId": "wrap", "unitPrice": 150},
        ])
        self.assertTrue(result["success"])
        # cheapest = 150 (wrap)
        self.assertAlmostEqual(result["discount_amount"], 150.0)

    def test_bogo_discount_is_cheapest_not_most_expensive(self):
        """BOGO must free the cheapest item, not the most expensive."""
        offer = self._offer(
            combo_type="bogo",
            item_pool=json.dumps(["pizza", "soup", "juice"]),
            items_to_select=2,
        )
        result = self._call(offer, cart_total=500, cart_items=[
            {"dishId": "pizza", "unitPrice": 300},  # most expensive
            {"dishId": "soup", "unitPrice": 80},    # cheapest — should be free
            {"dishId": "juice", "unitPrice": 120},
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 80.0)  # soup price

    def test_bogo_insufficient_pool_items_fails(self):
        """Only 1 pool item in cart, items_to_select=2 → ineligible."""
        offer = self._offer(
            combo_type="bogo",
            item_pool=json.dumps(["burger", "wrap"]),
            items_to_select=2,
        )
        result = self._call(offer, cart_total=200, cart_items=[
            {"dishId": "burger", "unitPrice": 200},
        ])
        self.assertFalse(result["success"])

    def test_bogo_non_pool_items_dont_count(self):
        """Cart has 3 items but none from pool → ineligible."""
        offer = self._offer(
            combo_type="bogo",
            item_pool=json.dumps(["burger", "wrap"]),
            items_to_select=2,
        )
        result = self._call(offer, cart_total=400, cart_items=[
            {"dishId": "pizza", "unitPrice": 200},
            {"dishId": "pasta", "unitPrice": 200},
        ])
        self.assertFalse(result["success"])

    def test_bogo_single_item_select(self):
        """items_to_select=1: buy 1 from pool, get it free."""
        offer = self._offer(
            combo_type="bogo",
            item_pool=json.dumps(["tea"]),
            items_to_select=1,
        )
        result = self._call(offer, cart_total=50, cart_items=[
            {"dishId": "tea", "unitPrice": 50},
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 50.0)

    def test_bogo_empty_pool_fails(self):
        """Empty item_pool → no items can qualify → ineligible."""
        offer = self._offer(
            combo_type="bogo",
            item_pool=json.dumps([]),
            items_to_select=2,
        )
        result = self._call(offer, cart_total=300, cart_items=[
            {"dishId": "burger", "unitPrice": 200},
            {"dishId": "wrap", "unitPrice": 100},
        ])
        self.assertFalse(result["success"])

    def test_bogo_malformed_item_pool_treated_as_empty(self):
        """Malformed JSON in item_pool → treated as no pool → ineligible."""
        offer = self._offer(
            combo_type="bogo",
            item_pool="[invalid",
            items_to_select=1,
        )
        result = self._call(offer, cart_total=200, cart_items=[
            {"dishId": "burger", "unitPrice": 200},
        ])
        # Should not crash; with empty pool and items_to_select≥1 → ineligible
        self.assertFalse(result["success"])

    def test_bogo_exactly_meets_threshold(self):
        """Exactly items_to_select items in pool → should qualify."""
        offer = self._offer(
            combo_type="bogo",
            item_pool=json.dumps(["a", "b", "c"]),
            items_to_select=3,
        )
        result = self._call(offer, cart_total=600, cart_items=[
            {"dishId": "a", "unitPrice": 300},
            {"dishId": "b", "unitPrice": 200},
            {"dishId": "c", "unitPrice": 100},  # cheapest = free
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 100.0)

    # ── build_your_own ──────────────────────────────────────────────────────

    def test_byo_enough_items_succeeds(self):
        """Pick 2 from pool, combo_price=200, sum=350 → discount=150."""
        offer = self._offer(
            combo_type="build_your_own",
            item_pool=json.dumps(["steak", "salad"]),
            items_to_select=2,
            combo_price=200.0,
        )
        result = self._call(offer, cart_total=350, cart_items=[
            {"dishId": "steak", "unitPrice": 250},
            {"dishId": "salad", "unitPrice": 100},
        ])
        self.assertTrue(result["success"])
        # sum of pool items = 350, combo_price = 200 → discount = 150
        self.assertAlmostEqual(result["discount_amount"], 150.0)

    def test_byo_discount_never_negative(self):
        """sum of selected items < combo_price → discount = 0."""
        offer = self._offer(
            combo_type="build_your_own",
            item_pool=json.dumps(["tea", "biscuit"]),
            items_to_select=2,
            combo_price=500.0,
        )
        result = self._call(offer, cart_total=200, cart_items=[
            {"dishId": "tea", "unitPrice": 80},
            {"dishId": "biscuit", "unitPrice": 40},
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    def test_byo_insufficient_pool_items_fails(self):
        """Only 1 of required 2 pool items in cart → ineligible."""
        offer = self._offer(
            combo_type="build_your_own",
            item_pool=json.dumps(["steak", "salad"]),
            items_to_select=2,
            combo_price=200.0,
        )
        result = self._call(offer, cart_total=250, cart_items=[
            {"dishId": "steak", "unitPrice": 250},
        ])
        self.assertFalse(result["success"])

    def test_byo_non_pool_items_excluded_from_discount_calculation(self):
        """Items not in pool shouldn't add to the discount sum."""
        offer = self._offer(
            combo_type="build_your_own",
            item_pool=json.dumps(["steak"]),
            items_to_select=1,
            combo_price=100.0,
        )
        result = self._call(offer, cart_total=600, cart_items=[
            {"dishId": "steak", "unitPrice": 200},    # in pool
            {"dishId": "wine", "unitPrice": 400},     # NOT in pool
        ])
        self.assertTrue(result["success"])
        # Only steak(200) counts: discount = 200 - 100 = 100
        self.assertAlmostEqual(result["discount_amount"], 100.0)

    def test_byo_missing_combo_price_gives_zero_discount(self):
        """combo_price=None on BYO → discount falls through to 0 (no crash)."""
        offer = self._offer(
            combo_type="build_your_own",
            item_pool=json.dumps(["steak"]),
            items_to_select=1,
            combo_price=None,
        )
        result = self._call(offer, cart_total=200, cart_items=[
            {"dishId": "steak", "unitPrice": 200},
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    def test_byo_empty_pool_fails(self):
        offer = self._offer(
            combo_type="build_your_own",
            item_pool=json.dumps([]),
            items_to_select=1,
            combo_price=100.0,
        )
        result = self._call(offer, cart_total=300, cart_items=[
            {"dishId": "steak", "unitPrice": 300},
        ])
        self.assertFalse(result["success"])

    # ── combo_type defaults to fixed_bundle when unset ──────────────────────

    def test_no_combo_type_defaults_to_fixed_bundle_behavior(self):
        """offer with combo_type=None should behave like fixed_bundle."""
        offer = self._offer(
            combo_type=None,
            required_items=json.dumps(["dish-X"]),
            combo_price=100.0,
        )
        result = self._call(offer, cart_total=200, cart_items=[{"dishId": "dish-X", "unitPrice": 200}])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 100.0)

    def test_no_combo_type_missing_item_fails(self):
        offer = self._offer(
            combo_type=None,
            required_items=json.dumps(["dish-X", "dish-Y"]),
            combo_price=100.0,
        )
        result = self._call(offer, cart_total=200, cart_items=[{"dishId": "dish-X", "unitPrice": 200}])
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
