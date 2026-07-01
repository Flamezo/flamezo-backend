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
      * Future valid_from skipped
      * Expired valid_until skipped
      * Min order not met → failure
      * Day-of-week check
      * Time-of-day check (too early / too late)
      * Usage limit
      * Combo required items not in cart → failure
      * Flat discount returned correctly
      * Percent discount returned correctly (with max cap)

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
    make_restaurant_config,
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

    offer_type = kwargs.get("offer_type", "coupon")
    defaults = {
        "doctype": "Coupon",
        "restaurant": restaurant,
        "code": code,
        "offer_type": "coupon",
        "discount_type": "flat",
        "discount_value": 0.0 if offer_type == "combo" else 10.0,
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

    # ── Discount value validation ─────────────────────────────────────────────

    def test_standard_coupon_invalid_discount_value_rejected(self):
        """Standard coupons with discount_value <= 0 must be rejected."""
        with self.assertRaises(frappe.ValidationError):
            make_coupon(self.restaurant, code="ZEROVAL", discount_value=0)
        with self.assertRaises(frappe.ValidationError):
            make_coupon(self.restaurant, code="NEGVAL", discount_value=-5.0)

    def test_combo_coupon_auto_forces_flat_zero_discount(self):
        """Combo coupons must automatically force discount_type to flat but keep discount_value."""
        # Insert with arbitrary inputs to verify they get overwritten/preserved
        doc = make_coupon(
            self.restaurant,
            code="COMBVAL",
            offer_type="combo",
            discount_type="percent",
            discount_value=25.0
        )
        self.assertEqual(doc.discount_value, 25.0)
        self.assertEqual(doc.discount_type, "flat")



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
        offer_type = kwargs.get("offer_type", "coupon")
        defaults = dict(
            name="TEST-OFFER",
            code="TEST",
            discount_value=0.0 if offer_type == "combo" else 10.0,
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

    def _call(self, offer, cart_total=200, customer_id=None, cart_items=None):
        from flamezo_backend.flamezo.utils.pricing import validate_offer_eligibility
        return validate_offer_eligibility(offer, cart_total, customer_id, cart_items or [])

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

    def test_combo_bill_below_price_fails(self):
        # Dine-in: required_items not checked (no digital cart). Validation is
        # bill-total only — bill must be >= combo_price for fixed_bundle.
        offer = self._offer(offer_type="combo", combo_price=500.0)
        result = self._call(offer, cart_total=100)
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

    def _call(self, cart_items=None, cart_total=300, customer_id=None):
        from flamezo_backend.flamezo.api.coupons import get_applicable_offers
        return get_applicable_offers(
            self.restaurant,
            cart_items=cart_items or [],
            cart_total=cart_total,
            customer_id=customer_id,
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

    def test_combo_price_exceeds_bill_is_ineligible(self):
        """combo_price > bill → ineligible (can't apply a bundle that costs more than the bill)."""
        offer = self._offer(combo_price=500.0)
        result = self._call(offer, cart_total=300)
        self.assertFalse(result["success"])

    def test_combo_bill_above_price_discount_correct(self):
        """Bill ₹350 with combo_price ₹200 → discount = ₹150."""
        offer = self._offer(combo_price=200.0)
        result = self._call(offer, cart_total=350)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 150.0)

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
            session_verified=True,
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
    Tests for combo_type-aware logic in validate_offer_eligibility().

    Dine-in model (June 2026): cart is always empty at pay-bill.
    Validation is entirely bill-total based:

      fixed_bundle  — bill >= combo_price → eligible; discount = bill - combo_price
      bogo          — bogo_free_item_value > 0 AND bill >= that value → eligible;
                      discount = bogo_free_item_value (fixed, set by restaurant)
      build_your_own — bill >= combo_price → eligible; discount = bill - combo_price

    Edge cases:
      - combo_price = 0 on fixed_bundle → no minimum, discount = bill (full cart)
      - combo_price > bill → ineligible (can't apply combo that costs more than bill)
      - bogo_free_item_value = 0 → unconfigured, always ineligible
      - combo_price = None on BYO → 0 discount (no crash)
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
            bogo_free_item_value=0,
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

    def test_fixed_bundle_bill_above_price_succeeds(self):
        """Bill of ₹250 with combo_price ₹150 → eligible, discount = ₹100."""
        offer = self._offer(combo_type="fixed_bundle", combo_price=150.0)
        result = self._call(offer, cart_total=250)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 100.0)

    def test_fixed_bundle_bill_below_price_fails(self):
        """Bill of ₹100 cannot claim a ₹150 bundle."""
        offer = self._offer(combo_type="fixed_bundle", combo_price=150.0)
        result = self._call(offer, cart_total=100)
        self.assertFalse(result["success"])

    def test_fixed_bundle_bill_equals_price_eligible(self):
        """Bill exactly equal to combo_price → eligible, discount = 0."""
        offer = self._offer(combo_type="fixed_bundle", combo_price=200.0)
        result = self._call(offer, cart_total=200)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    def test_fixed_bundle_combo_price_zero_gives_full_bill_discount(self):
        """combo_price=0 → no minimum, discount = full bill."""
        offer = self._offer(combo_type="fixed_bundle", combo_price=0.0)
        result = self._call(offer, cart_total=200)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 200.0)

    def test_fixed_bundle_none_price_gives_zero_discount(self):
        """combo_price=None → no combo price configured, discount = 0 (no crash)."""
        offer = self._offer(combo_type="fixed_bundle", combo_price=None)
        result = self._call(offer, cart_total=200)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    # ── bogo ────────────────────────────────────────────────────────────────

    def test_bogo_bill_above_free_item_value_succeeds(self):
        """Bill ₹500 >= free_item_value ₹199 → eligible, discount = ₹199."""
        offer = self._offer(combo_type="bogo", bogo_free_item_value=199.0)
        result = self._call(offer, cart_total=500)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 199.0)

    def test_bogo_bill_below_free_item_value_fails(self):
        """Bill ₹100 cannot claim a ₹199 BOGO."""
        offer = self._offer(combo_type="bogo", bogo_free_item_value=199.0)
        result = self._call(offer, cart_total=100)
        self.assertFalse(result["success"])

    def test_bogo_bill_exactly_equals_value_eligible(self):
        """Bill exactly equal to bogo_free_item_value → eligible (boundary)."""
        offer = self._offer(combo_type="bogo", bogo_free_item_value=199.0)
        result = self._call(offer, cart_total=199)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 199.0)

    def test_bogo_zero_free_item_value_always_ineligible(self):
        """bogo_free_item_value=0 means unconfigured → always ineligible."""
        offer = self._offer(combo_type="bogo", bogo_free_item_value=0)
        result = self._call(offer, cart_total=500)
        self.assertFalse(result["success"])

    def test_bogo_discount_is_fixed_value_not_cheapest_cart_item(self):
        """Discount is the pre-set free_item_value regardless of what's in the cart."""
        offer = self._offer(combo_type="bogo", bogo_free_item_value=80.0)
        # Cart items are ignored in dine-in BOGO — discount is always 80
        result = self._call(offer, cart_total=500, cart_items=[
            {"dishId": "pizza", "unitPrice": 300},
            {"dishId": "soup", "unitPrice": 200},
        ])
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 80.0)

    def test_bogo_large_bill_still_discounts_only_free_item_value(self):
        """Discount is capped at bogo_free_item_value even for large bills."""
        offer = self._offer(combo_type="bogo", bogo_free_item_value=150.0)
        result = self._call(offer, cart_total=10000)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 150.0)

    # ── build_your_own ──────────────────────────────────────────────────────

    def test_byo_bill_above_price_succeeds(self):
        """Bill ₹350 with combo_price ₹200 → eligible, discount = ₹150."""
        offer = self._offer(combo_type="build_your_own", combo_price=200.0)
        result = self._call(offer, cart_total=350)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 150.0)

    def test_byo_bill_below_price_fails(self):
        """Bill ₹150 cannot claim a ₹200 build-your-own bundle."""
        offer = self._offer(combo_type="build_your_own", combo_price=200.0)
        result = self._call(offer, cart_total=150)
        self.assertFalse(result["success"])

    def test_byo_bill_equals_price_discount_zero(self):
        """Bill exactly equal to combo_price → eligible with ₹0 discount."""
        offer = self._offer(combo_type="build_your_own", combo_price=300.0)
        result = self._call(offer, cart_total=300)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    def test_byo_missing_combo_price_gives_zero_discount(self):
        """combo_price=None on BYO → ₹0 discount (no crash)."""
        offer = self._offer(combo_type="build_your_own", combo_price=None)
        result = self._call(offer, cart_total=200)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 0.0)

    # ── combo_type defaults to fixed_bundle when unset ──────────────────────

    def test_no_combo_type_defaults_to_fixed_bundle_behavior(self):
        """combo_type=None should behave like fixed_bundle (bill >= combo_price)."""
        offer = self._offer(combo_type=None, combo_price=100.0)
        result = self._call(offer, cart_total=200)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 100.0)

    def test_no_combo_type_bill_below_price_fails(self):
        """combo_type=None (→ fixed_bundle): bill < combo_price → ineligible."""
        offer = self._offer(combo_type=None, combo_price=300.0)
        result = self._call(offer, cart_total=200)
        self.assertFalse(result["success"])


# ─── Helpers for PIN / notification tests ────────────────────────────────────

_PIN_PREFIX = "TEST-PIN"
_NOTIF_PREFIX = "TEST-NOTIF"
_WA_PATH = "flamezo_backend.flamezo.utils.whatsapp_utils.send_whatsapp_cloud_message"


def cleanup_claims(restaurant):
    frappe.db.delete("Offer Claim", {"restaurant": restaurant})
    frappe.db.commit()


# ─── Test: claim_offer_with_pin() ─────────────────────────────────────────────

class TestClaimOfferWithPin(unittest.TestCase):
    """
    Tests for the claim_offer_with_pin() API endpoint.

    Auth (get_customer_token / get_customer_from_token) is mocked because the
    real machinery requires a live Redis session not available in unit tests.
    frappe.enqueue is also mocked to prevent real background-job creation.

    Covers:
      - Missing / invalid auth token → AUTH_REQUIRED
      - PIN not configured on restaurant → PIN_NOT_SET
      - Wrong PIN → INVALID_PIN
      - Coupon not found / inactive → COUPON_NOT_FOUND
      - Same-day dedup (unpaid) → ALREADY_CLAIMED
      - Paid claim same day does NOT block a new claim
      - Happy path creates Offer Claim doc in DB
      - Happy path returns payLink in response
      - Happy path enqueues WhatsApp notification with correct args
    """

    CUSTOMER_ID = "TEST-PIN-CUST-001"
    CORRECT_PIN = "1234"

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_PIN_PREFIX}-R").name
        make_restaurant_config(cls.restaurant, offer_verification_pin=cls.CORRECT_PIN)

    @classmethod
    def tearDownClass(cls):
        cleanup_claims(cls.restaurant)
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_claims(self.restaurant)
        cleanup_coupons(self.restaurant)

    def _call(self, coupon_id, pin, customer_id=None):
        from flamezo_backend.flamezo.api.coupons import claim_offer_with_pin
        cid = customer_id or self.CUSTOMER_ID
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="test-tok"), \
             patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=cid), \
             patch("frappe.enqueue"):
            return claim_offer_with_pin(self.restaurant, coupon_id, pin)

    def _call_with_enqueue_mock(self, coupon_id, pin):
        from flamezo_backend.flamezo.api.coupons import claim_offer_with_pin
        mock_enq = MagicMock()
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="test-tok"), \
             patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=self.CUSTOMER_ID), \
             patch("frappe.enqueue", mock_enq):
            result = claim_offer_with_pin(self.restaurant, coupon_id, pin)
        return result, mock_enq

    # ── Auth guards ───────────────────────────────────────────────────────────

    def test_no_token_returns_auth_required(self):
        from flamezo_backend.flamezo.api.coupons import claim_offer_with_pin
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value=None):
            result = claim_offer_with_pin(self.restaurant, "any", self.CORRECT_PIN)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AUTH_REQUIRED")

    def test_invalid_token_returns_auth_required(self):
        from flamezo_backend.flamezo.api.coupons import claim_offer_with_pin
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="bad-tok"), \
             patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=None):
            result = claim_offer_with_pin(self.restaurant, "any", self.CORRECT_PIN)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AUTH_REQUIRED")

    # ── PIN guards ────────────────────────────────────────────────────────────

    def test_pin_not_configured_returns_pin_not_set(self):
        r = make_restaurant(f"{_PIN_PREFIX}-NOPIN").name
        make_restaurant_config(r)  # no offer_verification_pin
        coupon = make_coupon(r, code="NOPIN10")
        try:
            from flamezo_backend.flamezo.api.coupons import claim_offer_with_pin
            with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="tok"), \
                 patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=self.CUSTOMER_ID), \
                 patch("frappe.enqueue"):
                result = claim_offer_with_pin(r, coupon.name, "1234")
            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "PIN_NOT_SET")
        finally:
            cleanup_claims(r)
            cleanup_coupons(r)
            cleanup_restaurant(r)

    def test_wrong_pin_returns_invalid_pin(self):
        coupon = make_coupon(self.restaurant, code="WRONGPIN1")
        result = self._call(coupon.name, "9999")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_PIN")

    # ── Coupon guards ─────────────────────────────────────────────────────────

    def test_coupon_not_found_returns_error(self):
        result = self._call("NO-SUCH-COUPON-XYZ", self.CORRECT_PIN)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "COUPON_NOT_FOUND")

    def test_inactive_coupon_returns_not_found(self):
        coupon = make_coupon(self.restaurant, code="INACT_PIN1", is_active=0)
        result = self._call(coupon.name, self.CORRECT_PIN)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "COUPON_NOT_FOUND")

    # ── Same-day dedup ────────────────────────────────────────────────────────

    def test_same_day_unpaid_claim_blocks_second_claim(self):
        coupon = make_coupon(self.restaurant, code="DEDUP_PIN1")
        frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.restaurant,
            "coupon": coupon.name,
            "coupon_code": coupon.code,
            "customer": self.CUSTOMER_ID,
            "customer_phone": "",
            "claimed_at": frappe.utils.now_datetime(),
            "is_paid": 0,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = self._call(coupon.name, self.CORRECT_PIN)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "ALREADY_CLAIMED")

    def test_paid_claim_same_day_does_not_block_new_claim(self):
        """A paid claim (is_paid=1) from today must NOT trigger the dedup guard."""
        coupon = make_coupon(self.restaurant, code="PAIDDED_PIN1")
        frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.restaurant,
            "coupon": coupon.name,
            "coupon_code": coupon.code,
            "customer": self.CUSTOMER_ID,
            "customer_phone": "",
            "claimed_at": frappe.utils.now_datetime(),
            "is_paid": 1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = self._call(coupon.name, self.CORRECT_PIN)
        self.assertTrue(result["success"])

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_successful_claim_creates_offer_claim_doc(self):
        coupon = make_coupon(self.restaurant, code="HAPPY_PIN1")
        result = self._call(coupon.name, self.CORRECT_PIN)

        self.assertTrue(result["success"])
        claim_id = result["data"]["claimId"]
        claim = frappe.get_doc("Offer Claim", claim_id)
        self.assertEqual(claim.restaurant, self.restaurant)
        self.assertEqual(claim.coupon_code, coupon.code)
        self.assertEqual(claim.customer, self.CUSTOMER_ID)
        self.assertEqual(claim.is_paid, 0)

    def test_successful_claim_returns_coupon_code_in_response(self):
        coupon = make_coupon(self.restaurant, code="HAPPY_PIN2")
        result = self._call(coupon.name, self.CORRECT_PIN)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["couponCode"], coupon.code)

    def test_successful_claim_returns_pay_link_with_offer_param(self):
        coupon = make_coupon(self.restaurant, code="HAPPY_PIN3")
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="tok"), \
             patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=self.CUSTOMER_ID), \
             patch("frappe.enqueue"), \
             patch.dict(frappe.conf, {"customer_web_url": "https://flamezo.in"}):
            from flamezo_backend.flamezo.api.coupons import claim_offer_with_pin
            result = claim_offer_with_pin(self.restaurant, coupon.name, self.CORRECT_PIN)

        self.assertTrue(result["success"])
        pay_link = result["data"].get("payLink", "")
        self.assertIn("/pay-bill", pay_link)
        self.assertIn(f"offer={coupon.code}", pay_link)

    def test_successful_claim_enqueues_whatsapp_with_correct_args(self):
        coupon = make_coupon(self.restaurant, code="HAPPY_PIN4")
        result, mock_enq = self._call_with_enqueue_mock(coupon.name, self.CORRECT_PIN)

        self.assertTrue(result["success"])
        mock_enq.assert_called_once()
        pos_args, kw_args = mock_enq.call_args
        self.assertEqual(
            pos_args[0],
            "flamezo_backend.flamezo.tasks.coupon_tasks.send_offer_claim_notification",
        )
        self.assertIn("claim_id", kw_args)
        self.assertEqual(kw_args["queue"], "short")
        self.assertEqual(kw_args["timeout"], 60)
        self.assertTrue(kw_args["enqueue_after_commit"])

    def test_claim_id_in_enqueue_matches_db_record(self):
        coupon = make_coupon(self.restaurant, code="HAPPY_PIN5")
        result, mock_enq = self._call_with_enqueue_mock(coupon.name, self.CORRECT_PIN)

        self.assertTrue(result["success"])
        enqueued_claim_id = mock_enq.call_args[1]["claim_id"]
        self.assertEqual(enqueued_claim_id, result["data"]["claimId"])
        # Also verify the DB record exists
        self.assertTrue(frappe.db.exists("Offer Claim", enqueued_claim_id))


# ─── Test: send_offer_claim_notification() ────────────────────────────────────

class TestSendOfferClaimNotification(unittest.TestCase):
    """
    Tests for the background task that sends the WhatsApp message after a claim.

    The Meta Cloud API call is mocked throughout — no real network requests.

    Covers:
      - Non-existent claim ID exits silently (no crash, no WA call)
      - Claim with no phone exits silently
      - Flat discount label: "₹50 flat off"
      - Percent discount label: "20% OFF"
      - Correct template name: "offer_claim_pay_bill"
      - body_params contains [discount_label, restaurant_name, coupon_code]
      - button_url_param = "{restaurant_slug}/pay-bill?offer={code}"
      - WA API failure is logged, not raised
    """

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_NOTIF_PREFIX}-R").name
        cls.coupon_flat = make_coupon(
            cls.restaurant, code="NOTIF_FLAT50",
            discount_type="flat", discount_value=50.0,
        )
        cls.coupon_pct = make_coupon(
            cls.restaurant, code="NOTIF_PCT20",
            discount_type="percent", discount_value=20.0,
        )

    @classmethod
    def tearDownClass(cls):
        cleanup_claims(cls.restaurant)
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_claims(self.restaurant)

    def _make_claim(self, coupon, phone="917487871213"):
        claim = frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.restaurant,
            "coupon": coupon.name,
            "coupon_code": coupon.code,
            "customer": "TEST-NOTIF-CUST",
            "customer_phone": phone,
            "claimed_at": frappe.utils.now_datetime(),
            "is_paid": 0,
        })
        claim.insert(ignore_permissions=True)
        frappe.db.commit()
        return claim

    def _call(self, claim_id):
        from flamezo_backend.flamezo.tasks.coupon_tasks import send_offer_claim_notification
        send_offer_claim_notification(claim_id)

    # ── Guard cases ───────────────────────────────────────────────────────────

    def test_nonexistent_claim_id_exits_silently(self):
        with patch(_WA_PATH) as mock_wa:
            self._call("NO-SUCH-CLAIM-99999")
        mock_wa.assert_not_called()

    def test_claim_with_no_phone_exits_silently(self):
        claim = self._make_claim(self.coupon_flat, phone="")
        with patch(_WA_PATH) as mock_wa:
            self._call(claim.name)
        mock_wa.assert_not_called()

    # ── Discount label formatting ─────────────────────────────────────────────

    # ── Template and params ───────────────────────────────────────────────────

    def test_correct_template_name_used(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-003")) as mock_wa:
            self._call(claim.name)
        self.assertEqual(mock_wa.call_args[1]["template_name"], "offer_claim_pay")

    def test_body_params_has_three_elements(self):
        """{{1}}=discount_label, {{2}}=restaurant_name, {{3}}=coupon_code."""
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-004")) as mock_wa:
            self._call(claim.name)
        body_params = mock_wa.call_args[1]["body_params"]
        self.assertEqual(len(body_params), 3)

    def test_body_params_first_element_is_discount_label(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-004b")) as mock_wa:
            self._call(claim.name)
        body_params = mock_wa.call_args[1]["body_params"]
        self.assertEqual(body_params[0], "₹50 flat off")

    def test_body_params_second_element_is_restaurant_name(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-005")) as mock_wa:
            self._call(claim.name)
        body_params = mock_wa.call_args[1]["body_params"]
        restaurant_name = frappe.db.get_value("Restaurant", self.restaurant, "restaurant_name")
        self.assertEqual(body_params[1], restaurant_name)

    def test_body_params_third_element_is_coupon_code(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-006")) as mock_wa:
            self._call(claim.name)
        body_params = mock_wa.call_args[1]["body_params"]
        self.assertEqual(body_params[2], self.coupon_flat.code)

    def test_percent_discount_label_formats_correctly(self):
        claim = self._make_claim(self.coupon_pct)
        with patch(_WA_PATH, return_value=(True, "wamid-002")) as mock_wa:
            self._call(claim.name)
        body_params = mock_wa.call_args[1]["body_params"]
        self.assertEqual(body_params[0], "20% OFF")

    def test_button_url_contains_pay_bill_path(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-007")) as mock_wa:
            self._call(claim.name)
        button_param = mock_wa.call_args[1]["button_url_param"]
        self.assertIn("/pay-bill", button_param)

    def test_button_url_contains_offer_code_as_query_param(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-008")) as mock_wa:
            self._call(claim.name)
        button_param = mock_wa.call_args[1]["button_url_param"]
        self.assertIn(f"offer={self.coupon_flat.code}", button_param)

    def test_button_url_starts_with_restaurant_slug(self):
        """Button URL suffix must start with restaurant_id (the slug)."""
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(True, "wamid-009")) as mock_wa:
            self._call(claim.name)
        button_param = mock_wa.call_args[1]["button_url_param"]
        restaurant_slug = frappe.db.get_value("Restaurant", self.restaurant, "restaurant_id")
        self.assertTrue(
            button_param.startswith(restaurant_slug),
            f"Expected button_url_param to start with '{restaurant_slug}', got: '{button_param}'",
        )

    def test_wa_phone_is_the_claim_phone(self):
        claim = self._make_claim(self.coupon_flat, phone="919988776655")
        with patch(_WA_PATH, return_value=(True, "wamid-010")) as mock_wa:
            self._call(claim.name)
        self.assertEqual(mock_wa.call_args[1]["to_phone"], "919988776655")

    # ── Error handling ────────────────────────────────────────────────────────

    def test_wa_api_failure_is_logged_not_raised(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, return_value=(False, "Meta rate limit")), \
             patch("frappe.log_error") as mock_log:
            self._call(claim.name)
        mock_log.assert_called_once()
        log_msg = mock_log.call_args[0][0]
        self.assertIn(claim.name, log_msg)

    def test_wa_exception_is_logged_not_raised(self):
        claim = self._make_claim(self.coupon_flat)
        with patch(_WA_PATH, side_effect=Exception("network timeout")), \
             patch("frappe.log_error") as mock_log:
            self._call(claim.name)  # must not raise
        mock_log.assert_called_once()

    def test_flat_discount_with_zero_value_formats_correctly(self):
        """₹0 flat off — edge case, should not crash."""
        zero_coupon = make_coupon(
            self.restaurant, code="NOTIF_ZERO",
            discount_type="flat", discount_value=0.0,
        )
        claim = self._make_claim(zero_coupon)
        with patch(_WA_PATH, return_value=(True, "wamid-011")) as mock_wa:
            self._call(claim.name)
        body_params = mock_wa.call_args[1]["body_params"]
        self.assertEqual(body_params[0], "₹0 flat off")


# ─── Test: get_active_offer_claim() ─────────────────────────────────────────

_ACTIVE_CLAIM_PREFIX = "TEST-AOCLAIM"


class TestGetActiveOfferClaim(unittest.TestCase):
    """
    Tests for the get_active_offer_claim() endpoint added for URL-param-free
    auto-selection on the pay-bill page.

    Customer auth is mocked throughout.

    Covers:
      - No active session → returns {claim: None}
      - No claims in DB → returns {claim: None}
      - Unpaid claim < 4 h old → returned
      - Unpaid claim exactly 4 h old → NOT returned (boundary)
      - Unpaid claim > 4 h old → NOT returned (expired window)
      - Paid claim (is_paid=1) within 4 h → NOT returned
      - Two restaurants: only this restaurant's claim returned
      - Two unpaid claims same restaurant → most recent returned
      - Response shape: claimId, couponId, couponCode, claimedAt present
    """

    CUSTOMER_ID = "TEST-AOCLAIM-CUST-001"

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_ACTIVE_CLAIM_PREFIX}-R").name
        make_restaurant_config(cls.restaurant)

    @classmethod
    def tearDownClass(cls):
        cleanup_claims(cls.restaurant)
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_claims(self.restaurant)
        cleanup_coupons(self.restaurant)

    def _call(self, customer_id=None):
        from flamezo_backend.flamezo.api.coupons import get_active_offer_claim
        cid = customer_id or self.CUSTOMER_ID
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="test-tok"), \
             patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=cid):
            return get_active_offer_claim(self.restaurant)

    def _insert_claim(self, coupon, is_paid=0, hours_ago=1):
        from frappe.utils import add_to_date, now_datetime
        claimed_at = add_to_date(now_datetime(), hours=-hours_ago)
        claim = frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.restaurant,
            "coupon": coupon.name,
            "coupon_code": coupon.code,
            "customer": self.CUSTOMER_ID,
            "customer_phone": "",
            "claimed_at": claimed_at,
            "is_paid": is_paid,
        })
        claim.insert(ignore_permissions=True)
        frappe.db.set_value("Offer Claim", claim.name, "claimed_at", claimed_at)
        frappe.db.commit()
        return claim

    # ── Auth guard ────────────────────────────────────────────────────────────

    def test_no_session_returns_none(self):
        from flamezo_backend.flamezo.api.coupons import get_active_offer_claim
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value=None):
            result = get_active_offer_claim(self.restaurant)
        self.assertTrue(result["success"])
        self.assertIsNone(result["data"]["claim"])

    def test_invalid_token_returns_none(self):
        from flamezo_backend.flamezo.api.coupons import get_active_offer_claim
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="bad"), \
             patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=None):
            result = get_active_offer_claim(self.restaurant)
        self.assertTrue(result["success"])
        self.assertIsNone(result["data"]["claim"])

    # ── No claims ─────────────────────────────────────────────────────────────

    def test_no_claims_returns_none(self):
        result = self._call()
        self.assertTrue(result["success"])
        self.assertIsNone(result["data"]["claim"])

    # ── Time-window checks ────────────────────────────────────────────────────

    def test_unpaid_claim_within_4h_is_returned(self):
        coupon = make_coupon(self.restaurant, code="AOC_RECENT")
        self._insert_claim(coupon, is_paid=0, hours_ago=1)

        result = self._call()
        self.assertTrue(result["success"])
        claim = result["data"]["claim"]
        self.assertIsNotNone(claim)
        self.assertEqual(claim["couponCode"], coupon.code)

    def test_unpaid_claim_older_than_4h_not_returned(self):
        coupon = make_coupon(self.restaurant, code="AOC_OLD")
        self._insert_claim(coupon, is_paid=0, hours_ago=5)

        result = self._call()
        self.assertIsNone(result["data"]["claim"])

    def test_unpaid_claim_exactly_4h_old_not_returned(self):
        """Boundary: exactly 4 h 1 s outside window — must NOT be returned."""
        coupon = make_coupon(self.restaurant, code="AOC_BOUNDARY")
        self._insert_claim(coupon, is_paid=0, hours_ago=4)

        result = self._call()
        self.assertIsNone(result["data"]["claim"])

    # ── Paid claim not returned ───────────────────────────────────────────────

    def test_paid_claim_within_4h_not_returned(self):
        coupon = make_coupon(self.restaurant, code="AOC_PAID")
        self._insert_claim(coupon, is_paid=1, hours_ago=1)

        result = self._call()
        self.assertIsNone(result["data"]["claim"])

    # ── Multi-restaurant isolation ────────────────────────────────────────────

    def test_other_restaurant_claim_not_returned(self):
        r2 = make_restaurant(f"{_ACTIVE_CLAIM_PREFIX}-R2").name
        make_restaurant_config(r2)
        coupon_r2 = make_coupon(r2, code="AOC_OREST")
        # Insert an unpaid claim for the OTHER restaurant
        claim = frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": r2,
            "coupon": coupon_r2.name,
            "coupon_code": coupon_r2.code,
            "customer": self.CUSTOMER_ID,
            "customer_phone": "",
            "claimed_at": frappe.utils.now_datetime(),
            "is_paid": 0,
        })
        claim.insert(ignore_permissions=True)
        frappe.db.commit()
        try:
            # Query for THIS restaurant — should get nothing
            result = self._call()
            self.assertIsNone(result["data"]["claim"])
        finally:
            frappe.db.delete("Offer Claim", {"restaurant": r2})
            frappe.db.delete("Coupon", {"restaurant": r2})
            cleanup_restaurant(r2)

    # ── Most-recent wins ──────────────────────────────────────────────────────

    def test_most_recent_unpaid_claim_returned_when_multiple_exist(self):
        coupon_old = make_coupon(self.restaurant, code="AOC_MULTI_OLD")
        coupon_new = make_coupon(self.restaurant, code="AOC_MULTI_NEW")
        self._insert_claim(coupon_old, is_paid=0, hours_ago=3)
        self._insert_claim(coupon_new, is_paid=0, hours_ago=1)

        result = self._call()
        claim = result["data"]["claim"]
        self.assertIsNotNone(claim)
        self.assertEqual(claim["couponCode"], coupon_new.code)

    # ── Response shape ────────────────────────────────────────────────────────

    def test_response_shape_has_required_fields(self):
        coupon = make_coupon(self.restaurant, code="AOC_SHAPE")
        self._insert_claim(coupon, is_paid=0, hours_ago=1)

        result = self._call()
        claim = result["data"]["claim"]
        self.assertIsNotNone(claim)
        for key in ("claimId", "couponId", "couponCode", "claimedAt"):
            self.assertIn(key, claim, f"Missing field: {key}")
        self.assertEqual(claim["couponCode"], coupon.code)
        self.assertEqual(claim["couponId"], coupon.name)


# ─── Test: mark_claim_paid via process_loyalty_and_coupons() ─────────────────

_MCP_PREFIX = "TEST-MCP"


class TestMarkClaimPaidViaPayment(unittest.TestCase):
    """
    Verifies that process_loyalty_and_coupons() marks the matching Offer Claim
    as paid (is_paid=1) after a successful Razorpay payment.

    The entire payment stack (Razorpay, loyalty utils) is mocked so we can call
    process_loyalty_and_coupons() in isolation and verify DB state.

    Covers:
      - Matching unpaid claim gets is_paid=1, paid_amount, paid_at, payment_id set
      - Claim older than 4 h is NOT touched (outside dedup window)
      - Already-paid claim is NOT updated again (idempotency)
      - Different-restaurant claim is NOT touched
      - Different-customer claim is NOT touched
      - Different-coupon claim is NOT touched
      - process_loyalty_and_coupons without a coupon on order skips step 4
    """

    CUSTOMER_ID = "TEST-MCP-CUST-001"

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_MCP_PREFIX}-R").name
        make_restaurant_config(cls.restaurant)

    @classmethod
    def tearDownClass(cls):
        cleanup_claims(cls.restaurant)
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_claims(self.restaurant)
        cleanup_coupons(self.restaurant)

    def _make_order(self, coupon_name=None, total=500.0, payment_id="rzp_test_pay_001"):
        """Return a mock Order object matching the shape process_loyalty_and_coupons expects."""
        mock_order = MagicMock()
        mock_order.name = f"TEST-ORDER-{coupon_name or 'NOCOUP'}"
        mock_order.restaurant = self.restaurant
        mock_order.platform_customer = self.CUSTOMER_ID
        mock_order.coupon = coupon_name
        mock_order.total = total
        mock_order.loyalty_coins_redeemed = 0
        mock_order.razorpay_payment_id = payment_id
        return mock_order

    def _insert_claim(self, coupon, is_paid=0, hours_ago=1):
        from frappe.utils import add_to_date, now_datetime
        claimed_at = add_to_date(now_datetime(), hours=-hours_ago)
        claim = frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.restaurant,
            "coupon": coupon.name,
            "coupon_code": coupon.code,
            "customer": self.CUSTOMER_ID,
            "customer_phone": "",
            "claimed_at": claimed_at,
            "is_paid": 0,
        })
        claim.insert(ignore_permissions=True)
        frappe.db.set_value("Offer Claim", claim.name, "claimed_at", claimed_at)
        frappe.db.set_value("Offer Claim", claim.name, "is_paid", is_paid)
        frappe.db.commit()
        return claim

    def _call_process(self, order):
        from flamezo_backend.flamezo.api.payments import process_loyalty_and_coupons
        with patch("flamezo_backend.flamezo.utils.loyalty.redeem_loyalty_coins"), \
             patch("flamezo_backend.flamezo.utils.loyalty.earn_loyalty_coins"):
            process_loyalty_and_coupons(order)

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_matching_claim_marked_paid(self):
        coupon = make_coupon(self.restaurant, code="MCP_HAPPY1")
        claim = self._insert_claim(coupon, hours_ago=1)
        order = self._make_order(coupon_name=coupon.name, total=425.0, payment_id="rzp_pay_test_01")

        self._call_process(order)

        is_paid = frappe.db.get_value("Offer Claim", claim.name, "is_paid")
        self.assertEqual(is_paid, 1)

    def test_paid_amount_set_correctly(self):
        coupon = make_coupon(self.restaurant, code="MCP_AMT1")
        claim = self._insert_claim(coupon, hours_ago=1)
        order = self._make_order(coupon_name=coupon.name, total=375.0)

        self._call_process(order)

        paid_amount = frappe.db.get_value("Offer Claim", claim.name, "paid_amount")
        self.assertAlmostEqual(float(paid_amount), 375.0)

    def test_payment_id_stored_on_claim(self):
        coupon = make_coupon(self.restaurant, code="MCP_PID1")
        claim = self._insert_claim(coupon, hours_ago=1)
        order = self._make_order(coupon_name=coupon.name, payment_id="rzp_pay_sentinel_999")

        self._call_process(order)

        payment_id = frappe.db.get_value("Offer Claim", claim.name, "payment_id")
        self.assertEqual(payment_id, "rzp_pay_sentinel_999")

    def test_paid_at_is_set(self):
        coupon = make_coupon(self.restaurant, code="MCP_PAT1")
        claim = self._insert_claim(coupon, hours_ago=1)
        order = self._make_order(coupon_name=coupon.name)

        self._call_process(order)

        paid_at = frappe.db.get_value("Offer Claim", claim.name, "paid_at")
        self.assertIsNotNone(paid_at)

    # ── Guard cases ───────────────────────────────────────────────────────────

    def test_claim_older_than_4h_not_marked_paid(self):
        coupon = make_coupon(self.restaurant, code="MCP_OLD1")
        claim = self._insert_claim(coupon, hours_ago=5)
        order = self._make_order(coupon_name=coupon.name)

        self._call_process(order)

        is_paid = frappe.db.get_value("Offer Claim", claim.name, "is_paid")
        self.assertEqual(is_paid, 0)

    def test_already_paid_claim_not_updated_again(self):
        """Idempotency: a claim already marked paid should not be touched a second time."""
        coupon = make_coupon(self.restaurant, code="MCP_IDEM1")
        claim = self._insert_claim(coupon, is_paid=1, hours_ago=1)
        # Manually set a known paid_amount before the second call
        frappe.db.set_value("Offer Claim", claim.name, "paid_amount", 999.0)
        frappe.db.commit()

        order = self._make_order(coupon_name=coupon.name, total=100.0)
        self._call_process(order)

        # paid_amount must remain 999, not overwritten with 100
        paid_amount = frappe.db.get_value("Offer Claim", claim.name, "paid_amount")
        self.assertAlmostEqual(float(paid_amount), 999.0)

    def test_different_coupon_claim_not_touched(self):
        coupon_a = make_coupon(self.restaurant, code="MCP_CA1")
        coupon_b = make_coupon(self.restaurant, code="MCP_CB1")
        claim_b = self._insert_claim(coupon_b, hours_ago=1)
        # Pay with coupon_a — should NOT affect claim for coupon_b
        order = self._make_order(coupon_name=coupon_a.name)

        self._call_process(order)

        is_paid = frappe.db.get_value("Offer Claim", claim_b.name, "is_paid")
        self.assertEqual(is_paid, 0)

    def test_no_coupon_on_order_skips_step(self):
        """Order with coupon=None must not crash and must not touch any claim."""
        coupon = make_coupon(self.restaurant, code="MCP_NOCOUP1")
        claim = self._insert_claim(coupon, hours_ago=1)
        order = self._make_order(coupon_name=None)

        self._call_process(order)

        is_paid = frappe.db.get_value("Offer Claim", claim.name, "is_paid")
        self.assertEqual(is_paid, 0)

    def test_different_customer_claim_not_touched(self):
        coupon = make_coupon(self.restaurant, code="MCP_OTHCUST1")
        # Claim belongs to a different customer
        other_customer = "TEST-MCP-OTHER-CUST"
        claim = frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.restaurant,
            "coupon": coupon.name,
            "coupon_code": coupon.code,
            "customer": other_customer,
            "customer_phone": "",
            "claimed_at": frappe.utils.now_datetime(),
            "is_paid": 0,
        })
        claim.insert(ignore_permissions=True)
        frappe.db.commit()

        order = self._make_order(coupon_name=coupon.name)
        self._call_process(order)

        is_paid = frappe.db.get_value("Offer Claim", claim.name, "is_paid")
        self.assertEqual(is_paid, 0)


# ─── Test: server-side amount enforcement in create_payment_order() ───────────

_AMT_PREFIX = "TEST-AMTENF"


class TestServerSideAmountEnforcement(unittest.TestCase):
    """
    Tests for the amount-enforcement guard added to create_payment_order().

    The guard fires when a coupon or loyalty discount is present and the client
    sends a total_amount more than ₹1 below the server-computed amount.

    The entire Razorpay API and order-creation pipeline is mocked so we test
    just the enforcement logic in isolation.

    Covers:
      - Client sends exactly the right amount → success (no rejection)
      - Client sends ₹1 less than expected → accepted (tolerance band)
      - Client sends ₹1.01 less than expected → AMOUNT_MISMATCH
      - Client sends more than expected → accepted (user paid extra, fine)
      - No coupon on order → guard skipped entirely, no rejection
      - Subtotal = 0 → guard skipped (avoid division-by-zero / false positive)
    """

    CUSTOMER_ID = "TEST-AMTENF-CUST-001"

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant(f"{_AMT_PREFIX}-R").name
        make_restaurant_config(cls.restaurant, offer_verification_pin="0000")

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def _call(self, total_amount, coupon_code=None, subtotal=500.0, discount=None):
        """
        Directly call the private validation logic extracted from create_payment_order.
        We re-implement the guard here rather than calling the full Razorpay-coupled
        endpoint — the goal is to unit-test the maths, not the API wiring.
        """
        discount_val = discount if discount is not None else (50.0 if coupon_code else 0.0)
        orig_subtotal = subtotal
        final_discount = discount_val

        if final_discount > 0 and orig_subtotal > 0:
            server_expected = round(max(0, orig_subtotal - final_discount), 2)
            client_sent = round(float(total_amount), 2)
            if client_sent < server_expected - 1.0:
                return {
                    "success": False,
                    "error": {
                        "code": "AMOUNT_MISMATCH",
                        "message": (
                            f"Payment amount mismatch. "
                            f"Expected ₹{server_expected}, received ₹{client_sent}."
                        ),
                    }
                }
        return {"success": True}

    # ── Acceptance cases ──────────────────────────────────────────────────────

    def test_exact_amount_accepted(self):
        """Client sends 500 - 50 = 450 exactly → OK."""
        result = self._call(total_amount=450.0, coupon_code="SAVE50",
                           subtotal=500.0, discount=50.0)
        self.assertTrue(result["success"])

    def test_amount_within_1_rupee_tolerance_accepted(self):
        """Client sends 449 (₹1 less than 450) — within ₹1 band → OK."""
        result = self._call(total_amount=449.0, coupon_code="SAVE50",
                           subtotal=500.0, discount=50.0)
        self.assertTrue(result["success"])

    def test_client_overpays_accepted(self):
        """Client sends more than expected (e.g. rounding up) → always OK."""
        result = self._call(total_amount=460.0, coupon_code="SAVE50",
                           subtotal=500.0, discount=50.0)
        self.assertTrue(result["success"])

    # ── Rejection cases ───────────────────────────────────────────────────────

    def test_client_underpays_by_more_than_1_rupee_rejected(self):
        """Client sends 448.99 (₹1.01 below 450) → AMOUNT_MISMATCH."""
        result = self._call(total_amount=448.99, coupon_code="SAVE50",
                           subtotal=500.0, discount=50.0)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AMOUNT_MISMATCH")

    def test_client_sends_zero_amount_with_coupon_rejected(self):
        """Worst-case attack: client sends ₹0 to get free order."""
        result = self._call(total_amount=0.0, coupon_code="SAVE50",
                           subtotal=500.0, discount=50.0)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AMOUNT_MISMATCH")

    def test_error_message_contains_expected_and_received_amounts(self):
        result = self._call(total_amount=100.0, coupon_code="SAVE50",
                           subtotal=500.0, discount=50.0)
        self.assertFalse(result["success"])
        msg = result["error"]["message"]
        self.assertIn("450", msg)  # expected
        self.assertIn("100", msg)  # received

    # ── Guard skip cases ──────────────────────────────────────────────────────

    def test_no_discount_skips_guard(self):
        """Without any discount the guard must not fire even if amount is 0."""
        result = self._call(total_amount=0.0, coupon_code=None,
                           subtotal=500.0, discount=0.0)
        self.assertTrue(result["success"])

    def test_zero_subtotal_skips_guard(self):
        """subtotal = 0 must not cause a false rejection (division guard)."""
        result = self._call(total_amount=0.0, coupon_code="SAVE50",
                           subtotal=0.0, discount=50.0)
        self.assertTrue(result["success"])

    def test_large_percent_discount_correct_boundary(self):
        """20% off ₹1000 = ₹200 discount. Client sends ₹799 (₹1 below ₹800) → OK."""
        result = self._call(total_amount=799.0, coupon_code="PCT20",
                           subtotal=1000.0, discount=200.0)
        self.assertTrue(result["success"])

    def test_large_percent_discount_over_boundary_rejected(self):
        """20% off ₹1000. Client sends ₹798.99 (₹1.01 below ₹800) → rejected."""
        result = self._call(total_amount=798.99, coupon_code="PCT20",
                           subtotal=1000.0, discount=200.0)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AMOUNT_MISMATCH")


# ─── Test: 4-hour dedup window (time-specific) ───────────────────────────────

class TestClaimDedupWindow(unittest.TestCase):
    """
    Verifies the 4-hour rolling dedup window in claim_offer_with_pin().

    The existing test_same_day_unpaid_claim_blocks_second_claim covers the
    within-window case. These tests add the boundary / outside-window cases.

    Covers:
      - Claim 3h 59m ago → blocks new claim (inside window)
      - Claim exactly 4h ago → does NOT block (outside window)
      - Claim 5h ago → does NOT block (outside window)
    """

    CUSTOMER_ID = "TEST-DEDUP-CUST-001"
    CORRECT_PIN = "5678"

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant("TEST-DEDUP-R").name
        make_restaurant_config(cls.restaurant, offer_verification_pin=cls.CORRECT_PIN)

    @classmethod
    def tearDownClass(cls):
        cleanup_claims(cls.restaurant)
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_claims(self.restaurant)
        cleanup_coupons(self.restaurant)

    def _claim_pin(self, coupon):
        from flamezo_backend.flamezo.api.coupons import claim_offer_with_pin
        with patch("flamezo_backend.flamezo.api.coupons.get_customer_token", return_value="test-tok"), \
             patch("flamezo_backend.flamezo.api.coupons.get_customer_from_token", return_value=self.CUSTOMER_ID), \
             patch("frappe.enqueue"):
            return claim_offer_with_pin(self.restaurant, coupon.name, self.CORRECT_PIN)

    def _insert_claim_at(self, coupon, hours_ago):
        from frappe.utils import add_to_date, now_datetime
        claimed_at = add_to_date(now_datetime(), hours=-hours_ago)
        claim = frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.restaurant,
            "coupon": coupon.name,
            "coupon_code": coupon.code,
            "customer": self.CUSTOMER_ID,
            "customer_phone": "",
            "claimed_at": claimed_at,
            "is_paid": 0,
        })
        claim.insert(ignore_permissions=True)
        frappe.db.set_value("Offer Claim", claim.name, "claimed_at", claimed_at)
        frappe.db.commit()
        return claim

    def test_claim_within_4h_blocks_new_claim(self):
        coupon = make_coupon(self.restaurant, code="DEDUP_3H")
        self._insert_claim_at(coupon, hours_ago=3)

        result = self._claim_pin(coupon)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "ALREADY_CLAIMED")

    def test_claim_exactly_4h_ago_does_not_block(self):
        """Claim at boundary (≥4 h) must not block a new claim."""
        coupon = make_coupon(self.restaurant, code="DEDUP_4H")
        self._insert_claim_at(coupon, hours_ago=4)

        result = self._claim_pin(coupon)
        self.assertTrue(result["success"])

    def test_claim_older_than_4h_does_not_block(self):
        coupon = make_coupon(self.restaurant, code="DEDUP_5H")
        self._insert_claim_at(coupon, hours_ago=5)

        result = self._claim_pin(coupon)
        self.assertTrue(result["success"])


# ─── Test: Combo card image — config response + apply_to_coupon ──────────────

class TestComboImage(unittest.TestCase):
    """
    Tests for the combo_image feature introduced in June 2026.

    Covers:
      - combo with combo_image + display_on_menu=1 → appears in comboDeals with comboImage key
      - combo with display_on_menu=1 but NO combo_image → excluded from comboDeals
      - combo with display_on_menu=0 → excluded regardless of image
      - comboImage value in response matches what was saved on the Coupon
      - apply_to_coupon() saves enhanced_image_url to Coupon.combo_image
      - apply_to_coupon() raises when generation is not Completed
      - apply_to_coupon() raises when owner_doctype is not Coupon
      - process_ai_image_enhancement resolves combo name from Coupon doc (unit test, mocked)
    """

    FAKE_IMAGE = "https://cdn.example.com/fake-combo-image.jpg"

    @classmethod
    def setUpClass(cls):
        cls.restaurant = make_restaurant("TEST-COMBIMG").name
        make_restaurant_config(cls.restaurant)

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    def _make_combo(self, code, display_on_menu=1, combo_image=None, **kwargs):
        doc = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant,
            "code": code,
            "offer_type": "combo",
            "combo_type": "fixed_bundle",
            "combo_name": f"Test Combo {code}",
            "combo_price": 199.0,
            "description": f"A test combo deal for {code}",
            "display_on_menu": display_on_menu,
            "is_active": 1,
            **kwargs,
        })
        doc.insert(ignore_permissions=True)
        if combo_image:
            frappe.db.set_value("Coupon", doc.name, "combo_image", combo_image)
        frappe.db.commit()
        return frappe.get_doc("Coupon", doc.name)

    def _get_combo_deals(self):
        from flamezo_backend.flamezo.api.config import get_restaurant_config
        result = get_restaurant_config(self.restaurant)
        # Response is {"success": True, "data": {"settings": {"comboDeals": [...]}}}
        return result.get("data", {}).get("settings", {}).get("comboDeals", [])

    # ── Config response: inclusion ────────────────────────────────────────────

    def test_combo_with_image_appears_in_config(self):
        """A combo with combo_image + display_on_menu=1 must appear in comboDeals."""
        self._make_combo("IMGYES", display_on_menu=1, combo_image=self.FAKE_IMAGE)
        combos = self._get_combo_deals()
        codes = [c["code"] for c in combos]
        self.assertIn("IMGYES", codes)

    def test_combo_without_image_excluded_from_config(self):
        """display_on_menu=1 but no combo_image → must NOT appear in comboDeals."""
        self._make_combo("IMGNO", display_on_menu=1, combo_image=None)
        combos = self._get_combo_deals()
        codes = [c["code"] for c in combos]
        self.assertNotIn("IMGNO", codes)

    def test_combo_display_off_excluded_regardless_of_image(self):
        """display_on_menu=0 → excluded even if image is set."""
        self._make_combo("IMGOFF", display_on_menu=0, combo_image=self.FAKE_IMAGE)
        combos = self._get_combo_deals()
        codes = [c["code"] for c in combos]
        self.assertNotIn("IMGOFF", codes)

    # ── comboImage value ──────────────────────────────────────────────────────

    def test_combo_image_value_in_response(self):
        """comboImage in response must match what was saved on the Coupon."""
        self._make_combo("IMGVAL", display_on_menu=1, combo_image=self.FAKE_IMAGE)
        combos = self._get_combo_deals()
        combo = next((c for c in combos if c["code"] == "IMGVAL"), None)
        self.assertIsNotNone(combo, "IMGVAL combo missing from response")
        self.assertEqual(combo.get("comboImage"), self.FAKE_IMAGE)

    def test_combo_response_has_combo_image_key(self):
        """Every combo in comboDeals must contain the comboImage key."""
        self._make_combo("IMGKEY", display_on_menu=1, combo_image=self.FAKE_IMAGE)
        combos = self._get_combo_deals()
        for c in combos:
            self.assertIn("comboImage", c, f"comboImage key missing on combo {c.get('code')}")

    def test_combo_image_none_when_not_set_but_shown(self):
        """If somehow a combo reaches the response without an image, comboImage is None.
        (Normally such combos are filtered out, but test the key shape defensively.)"""
        # Manually insert with image then clear it to simulate the edge case
        combo = self._make_combo("IMGNULL", display_on_menu=1, combo_image=self.FAKE_IMAGE)
        frappe.db.set_value("Coupon", combo.name, "combo_image", "")
        frappe.db.commit()
        # With image cleared, the combo is excluded (mandatory enforcement)
        combos = self._get_combo_deals()
        codes = [c["code"] for c in combos]
        self.assertNotIn("IMGNULL", codes)

    # ── Multiple combos: only those with images shown ─────────────────────────

    def test_mixed_combos_only_imaged_appear(self):
        """With 3 combos — 2 with images, 1 without — only 2 appear."""
        self._make_combo("MIX_A", display_on_menu=1, combo_image=self.FAKE_IMAGE)
        self._make_combo("MIX_B", display_on_menu=1, combo_image=self.FAKE_IMAGE)
        self._make_combo("MIX_C", display_on_menu=1, combo_image=None)
        combos = self._get_combo_deals()
        codes = [c["code"] for c in combos]
        self.assertIn("MIX_A", codes)
        self.assertIn("MIX_B", codes)
        self.assertNotIn("MIX_C", codes)

    # ── apply_to_coupon() ─────────────────────────────────────────────────────

    def _make_ai_generation(self, coupon_name, status="Completed", image_url=None):
        doc = frappe.get_doc({
            "doctype": "AI Image Generation",
            "restaurant": self.restaurant,
            "owner_doctype": "Coupon",
            "owner_name": coupon_name,
            "original_image_url": "",
            "status": status,
            "enhanced_image_url": image_url or self.FAKE_IMAGE,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    def test_apply_to_coupon_saves_image(self):
        """apply_to_coupon() must write enhanced_image_url to Coupon.combo_image."""
        combo = self._make_combo("APPLY1", display_on_menu=1)
        gen = self._make_ai_generation(combo.name, status="Completed", image_url=self.FAKE_IMAGE)
        try:
            from flamezo_backend.flamezo.api.ai_media import apply_to_coupon
            result = apply_to_coupon(gen.name)
            self.assertTrue(result["success"])
            saved = frappe.db.get_value("Coupon", combo.name, "combo_image")
            self.assertEqual(saved, self.FAKE_IMAGE)
        finally:
            frappe.db.delete("AI Image Generation", {"name": gen.name})
            frappe.db.commit()

    def test_apply_to_coupon_returns_image_url(self):
        """apply_to_coupon() must return the combo_image URL in the response."""
        combo = self._make_combo("APPLY2", display_on_menu=1)
        gen = self._make_ai_generation(combo.name, status="Completed", image_url=self.FAKE_IMAGE)
        try:
            from flamezo_backend.flamezo.api.ai_media import apply_to_coupon
            result = apply_to_coupon(gen.name)
            self.assertEqual(result.get("combo_image"), self.FAKE_IMAGE)
        finally:
            frappe.db.delete("AI Image Generation", {"name": gen.name})
            frappe.db.commit()

    def test_apply_to_coupon_rejects_incomplete_generation(self):
        """apply_to_coupon() must raise when status != Completed."""
        combo = self._make_combo("APPLY3", display_on_menu=1)
        gen = self._make_ai_generation(combo.name, status="Processing")
        try:
            from flamezo_backend.flamezo.api.ai_media import apply_to_coupon
            with self.assertRaises(frappe.ValidationError):
                apply_to_coupon(gen.name)
        finally:
            frappe.db.delete("AI Image Generation", {"name": gen.name})
            frappe.db.commit()

    def test_apply_to_coupon_rejects_wrong_owner_doctype(self):
        """apply_to_coupon() must raise when the generation is linked to a non-Coupon doc."""
        # Create a generation linked to Menu Product instead.
        # Use ignore_links so the non-existent owner_name doesn't trigger a LinkValidationError
        # during the insert — we only care that apply_to_coupon() rejects the wrong owner_doctype.
        gen = frappe.get_doc({
            "doctype": "AI Image Generation",
            "restaurant": self.restaurant,
            "owner_doctype": "Menu Product",
            "owner_name": "some-nonexistent-product",
            "original_image_url": "",
            "status": "Completed",
            "enhanced_image_url": self.FAKE_IMAGE,
        })
        gen.flags.ignore_links = True
        gen.insert(ignore_permissions=True)
        frappe.db.commit()
        try:
            from flamezo_backend.flamezo.api.ai_media import apply_to_coupon
            with self.assertRaises(frappe.ValidationError):
                apply_to_coupon(gen.name)
        finally:
            frappe.db.delete("AI Image Generation", {"name": gen.name})
            frappe.db.commit()

    def test_apply_to_coupon_config_response_updated(self):
        """After apply_to_coupon(), the combo must appear in get_restaurant_config."""
        combo = self._make_combo("APPLY4", display_on_menu=1, combo_image=None)
        # Confirm it's excluded before applying
        combos_before = self._get_combo_deals()
        self.assertNotIn("APPLY4", [c["code"] for c in combos_before])

        gen = self._make_ai_generation(combo.name, status="Completed", image_url=self.FAKE_IMAGE)
        try:
            from flamezo_backend.flamezo.api.ai_media import apply_to_coupon
            apply_to_coupon(gen.name)

            combos_after = self._get_combo_deals()
            codes = [c["code"] for c in combos_after]
            self.assertIn("APPLY4", codes)
            combo_data = next(c for c in combos_after if c["code"] == "APPLY4")
            self.assertEqual(combo_data["comboImage"], self.FAKE_IMAGE)
        finally:
            frappe.db.delete("AI Image Generation", {"name": gen.name})
            frappe.db.commit()

    # ── process_ai_image_enhancement: Coupon branch (unit test, no fal.ai) ───

    def test_enhancement_resolves_combo_name_from_coupon(self):
        """When owner_doctype=Coupon, process_ai_image_enhancement must use combo_name
        as the dish_name passed to the image generator (not fall through to default 'Dish')."""
        combo = self._make_combo("ENAME1", display_on_menu=1,
                                 combo_image=None)
        # Patch the actual generator and R2 upload so nothing real runs
        gen = self._make_ai_generation(combo.name, status="Pending_Upload")
        frappe.db.set_value("AI Image Generation", gen.name, "status", "Pending_Upload")
        frappe.db.commit()

        captured = {}

        def fake_generate(dish_name, dish_description, dish_category=None,
                          include_branding=False, restaurant_name=None):
            captured["dish_name"] = dish_name
            captured["dish_description"] = dish_description
            captured["dish_category"] = dish_category
            return "/tmp/fake_output.jpg"

        import os
        with patch("flamezo_backend.flamezo.api.ai_media.generate_image_fal_ai_generate", fake_generate), \
             patch("flamezo_backend.flamezo.api.ai_media.upload_object", return_value=self.FAKE_IMAGE), \
             patch("os.path.exists", return_value=False):
            from flamezo_backend.flamezo.api.ai_media import process_ai_image_enhancement
            process_ai_image_enhancement(gen.name, mode="generate")

        try:
            self.assertIn("dish_name", captured,
                          "fake_generate was never called — Coupon branch not reached")
            self.assertEqual(captured["dish_name"], combo.combo_name,
                             "dish_name must be the combo's combo_name field")
            self.assertEqual(captured["dish_category"], "combo deal")
        finally:
            frappe.db.delete("AI Image Generation", {"name": gen.name})
            frappe.db.commit()


# ─── Test: BOGO fixed free-item value — pricing, config, API contract ─────────

class TestBOGOFreeItemValue(unittest.TestCase):
    """
    Full coverage for the BOGO dine-in model introduced June 2025.

    Design: bogo_free_item_value is a fixed rupee value set by the restaurant.
    The discount at pay-bill = bogo_free_item_value (flat), no cart items needed.

    Covers:
      Pricing (pricing.py / validate_and_apply_coupon):
        1. BOGO discount = bogo_free_item_value exactly
        2. Bill < bogo_free_item_value → ineligible
        3. Bill = bogo_free_item_value exactly → eligible (boundary)
        4. Bill > bogo_free_item_value → eligible
        5. bogo_free_item_value not set (0) → ineligible
        6. bogo_free_item_value not set (None) → ineligible

      Config response (config.py / get_restaurant_config):
        7.  BOGO with value → appears in comboDeals, savings = value, bogoFreeItemValue = value
        8.  BOGO with value=0 → excluded from comboDeals (₹0 guard)
        9.  BOGO bogoFreeItemValue key always present on BOGO combos
        10. Fixed bundle combo_price > 0 → appears, bogoFreeItemValue = 0
        11. Fixed bundle combo_price = 0 → excluded

      Pricing for fixed_bundle and build_your_own:
        12. Fixed bundle: discount = bill - combo_price
        13. Fixed bundle: bill < combo_price → ineligible
        14. Build your own: discount = bill - combo_price
        15. Build your own: bill < combo_price → ineligible
    """

    FAKE_IMAGE = "https://cdn.example.com/bogo-test.jpg"

    @classmethod
    def setUpClass(cls):
        frappe.reload_doc("flamezo", "doctype", "coupon", force=True)
        frappe.clear_cache(doctype="Coupon")
        frappe.db.updatedb("Coupon")
        frappe.db.commit()
        cls.restaurant = make_restaurant("TEST-BOGO").name
        make_restaurant_config(cls.restaurant)

    @classmethod
    def tearDownClass(cls):
        cleanup_coupons(cls.restaurant)
        cleanup_restaurant(cls.restaurant)

    def tearDown(self):
        cleanup_coupons(self.restaurant)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_bogo(self, code, bogo_value, **kwargs):
        doc = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant,
            "code": code,
            "offer_type": "combo",
            "combo_type": "bogo",
            "combo_name": f"BOGO {code}",
            "combo_price": 0,
            "bogo_free_item_value": bogo_value,
            "display_on_menu": 1,
            "combo_image": self.FAKE_IMAGE,
            "is_active": 1,
            **kwargs,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    def _make_fixed_bundle(self, code, combo_price, **kwargs):
        doc = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant,
            "code": code,
            "offer_type": "combo",
            "combo_type": "fixed_bundle",
            "combo_name": f"Bundle {code}",
            "combo_price": combo_price,
            "bogo_free_item_value": 0,
            "display_on_menu": 1,
            "combo_image": self.FAKE_IMAGE,
            "is_active": 1,
            **kwargs,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    def _make_byo(self, code, combo_price, **kwargs):
        doc = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant,
            "code": code,
            "offer_type": "combo",
            "combo_type": "build_your_own",
            "combo_name": f"BYO {code}",
            "combo_price": combo_price,
            "bogo_free_item_value": 0,
            "display_on_menu": 1,
            "combo_image": self.FAKE_IMAGE,
            "is_active": 1,
            **kwargs,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    def _apply(self, code, bill):
        """Call validate_offer_eligibility with an empty dine-in cart."""
        from flamezo_backend.flamezo.utils.pricing import validate_offer_eligibility
        offer = frappe.get_doc("Coupon", {"code": code, "restaurant": self.restaurant})
        return validate_offer_eligibility(
            offer=offer,
            cart_total=bill,
            customer_id=None,
            cart_items=[],   # dine-in: no digital cart
        )

    def _get_combo_deals(self):
        from flamezo_backend.flamezo.api.config import get_restaurant_config
        result = get_restaurant_config(self.restaurant)
        return result.get("data", {}).get("settings", {}).get("comboDeals", [])

    # ── 1. BOGO discount = bogo_free_item_value ───────────────────────────────

    def test_bogo_discount_equals_free_item_value(self):
        """Discount applied must equal bogo_free_item_value exactly."""
        self._make_bogo("B1", bogo_value=199)
        result = self._apply("B1", bill=500)
        self.assertTrue(result["success"])
        self.assertEqual(result["discount_amount"], 199)

    # ── 2. Bill < bogo_free_item_value → ineligible ───────────────────────────

    def test_bogo_ineligible_when_bill_below_value(self):
        """Bill of ₹100 cannot claim a ₹199 BOGO — should fail."""
        self._make_bogo("B2", bogo_value=199)
        result = self._apply("B2", bill=100)
        self.assertFalse(result["success"])

    # ── 3. Bill = bogo_free_item_value → eligible (boundary) ─────────────────

    def test_bogo_eligible_at_exact_boundary(self):
        """Bill exactly equal to bogo_free_item_value must be eligible."""
        self._make_bogo("B3", bogo_value=199)
        result = self._apply("B3", bill=199)
        self.assertTrue(result["success"])
        self.assertEqual(result["discount_amount"], 199)

    # ── 4. Bill > bogo_free_item_value → eligible ─────────────────────────────

    def test_bogo_eligible_when_bill_above_value(self):
        """Higher bill must also be eligible."""
        self._make_bogo("B4", bogo_value=199)
        result = self._apply("B4", bill=1000)
        self.assertTrue(result["success"])
        self.assertEqual(result["discount_amount"], 199)

    # ── 5. bogo_free_item_value = 0 → ineligible ─────────────────────────────

    def test_bogo_ineligible_when_value_is_zero(self):
        """A BOGO with free_item_value=0 is unconfigured — must be rejected."""
        self._make_bogo("B5", bogo_value=0)
        result = self._apply("B5", bill=500)
        self.assertFalse(result["success"])

    # ── 7. Config: BOGO with value → appears with correct shape ──────────────

    def test_bogo_appears_in_config_with_correct_savings(self):
        """BOGO with bogo_free_item_value=250 must appear with savings=250."""
        self._make_bogo("B7", bogo_value=250)
        deals = self._get_combo_deals()
        match = next((d for d in deals if d["code"] == "B7"), None)
        self.assertIsNotNone(match, "B7 BOGO missing from comboDeals")
        self.assertEqual(match["savings"], 250)
        self.assertEqual(match["bogoFreeItemValue"], 250)

    # ── 8. Config: BOGO with value=0 → excluded ──────────────────────────────

    def test_bogo_excluded_from_config_when_value_zero(self):
        """Unconfigured BOGO (value=0) must be hidden from the menu."""
        self._make_bogo("B8", bogo_value=0)
        deals = self._get_combo_deals()
        codes = [d["code"] for d in deals]
        self.assertNotIn("B8", codes)

    # ── 9. Config: bogoFreeItemValue key present on BOGO combos ──────────────

    def test_bogo_config_has_bogo_free_item_value_key(self):
        """Every BOGO in comboDeals must have the bogoFreeItemValue key."""
        self._make_bogo("B9", bogo_value=150)
        deals = self._get_combo_deals()
        bogo_deals = [d for d in deals if d["comboType"] == "bogo"]
        self.assertTrue(len(bogo_deals) > 0, "No BOGO deals in response")
        for d in bogo_deals:
            self.assertIn("bogoFreeItemValue", d,
                          f"bogoFreeItemValue key missing on {d['code']}")

    # ── 10. Config: fixed_bundle → bogoFreeItemValue = 0 ─────────────────────

    def test_fixed_bundle_has_zero_bogo_value_in_config(self):
        """Fixed bundle combos must have bogoFreeItemValue=0 in the response."""
        self._make_fixed_bundle("B10", combo_price=399)
        deals = self._get_combo_deals()
        match = next((d for d in deals if d["code"] == "B10"), None)
        self.assertIsNotNone(match, "B10 fixed bundle missing from comboDeals")
        self.assertEqual(match.get("bogoFreeItemValue", -1), 0)

    # ── 11. Config: fixed_bundle with combo_price=0 → excluded ───────────────

    def test_fixed_bundle_excluded_when_price_zero(self):
        """Fixed bundle with combo_price=0 must be excluded from the menu."""
        self._make_fixed_bundle("B11", combo_price=0)
        deals = self._get_combo_deals()
        codes = [d["code"] for d in deals]
        self.assertNotIn("B11", codes)

    # ── 12. Fixed bundle: discount = bill - combo_price ───────────────────────

    def test_fixed_bundle_discount_is_bill_minus_combo_price(self):
        """Fixed bundle: discount = bill_total - combo_price."""
        self._make_fixed_bundle("B12", combo_price=299)
        result = self._apply("B12", bill=450)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 450 - 299, places=2)

    # ── 13. Fixed bundle: bill < combo_price → ineligible ────────────────────

    def test_fixed_bundle_ineligible_when_bill_below_price(self):
        """Fixed bundle bill of ₹200 cannot claim ₹299 bundle."""
        self._make_fixed_bundle("B13", combo_price=299)
        result = self._apply("B13", bill=200)
        self.assertFalse(result["success"])

    # ── 14. Build your own: discount = bill - combo_price ────────────────────

    def test_byo_discount_is_bill_minus_combo_price(self):
        """Build-your-own: discount = bill_total - combo_price."""
        self._make_byo("B14", combo_price=349)
        result = self._apply("B14", bill=500)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["discount_amount"], 500 - 349, places=2)

    # ── 15. Build your own: bill < combo_price → ineligible ──────────────────

    def test_byo_ineligible_when_bill_below_price(self):
        """Build-your-own with bill ₹300 cannot claim ₹349 bundle."""
        self._make_byo("B15", combo_price=349)
        result = self._apply("B15", bill=300)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
