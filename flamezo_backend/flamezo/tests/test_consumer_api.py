# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for consumer-facing APIs added for the Discover / profile flows:

  logout_customer  (otp.py)
    - Missing token → error
    - Valid token → cache entry deleted, success=True
    - Already-deleted token → idempotent success

  list_restaurants  (restaurant.py)
    - Returns full card shape (logo, photos, primaryColor, tagline, city, …)
    - active_only=True filters inactive restaurants
    - city filter is case-insensitive
    - active_offers_count counts only is_active=1 coupons
    - isNew=True for onboarding_date within 90 days
    - isNew=False for onboarding_date older than 90 days
    - No RestaurantConfig → primaryColor defaults to #B7410E
"""

import unittest
import datetime

import frappe
from frappe.utils import add_days, today

from flamezo_backend.flamezo.tests.utils import (
    cleanup_restaurants_by_prefix,
    make_restaurant,
    make_restaurant_config,
)

_PREFIX = "TEST-CA"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_coupon(restaurant, is_active=1):
    """Insert a minimal Coupon for offer-count tests."""
    doc = frappe.get_doc({
        "doctype": "Coupon",
        "restaurant": restaurant,
        "code": frappe.generate_hash(length=8).upper(),
        "discount_type": "Percentage",
        "discount_value": 10,
        "is_active": is_active,
        "min_order_amount": 0,
        "valid_until": add_days(today(), 30),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _cleanup(res_names):
    for name in res_names:
        frappe.db.delete("Restaurant Gallery Item", {"restaurant": name})
        frappe.db.delete("Coupon", {"restaurant": name})
        frappe.db.delete("Restaurant Config", {"restaurant": name})
        frappe.db.delete("Restaurant", name)
    frappe.db.commit()


# ─── logout_customer ─────────────────────────────────────────────────────────

class TestLogoutCustomer(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")

    def _put_session(self, token, phone="9000000099", customer_id="CUST-LOG-TEST"):
        frappe.cache().set_value(
            f"customer_session:{token}",
            {"customer_id": customer_id, "phone": phone},
            expires_in_sec=3600,
        )

    def test_missing_token_returns_error(self):
        from flamezo_backend.flamezo.api.otp import logout_customer
        result = logout_customer(session_token=None)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "MISSING_TOKEN")

    def test_empty_string_token_returns_error(self):
        from flamezo_backend.flamezo.api.otp import logout_customer
        result = logout_customer(session_token="")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "MISSING_TOKEN")

    def test_valid_token_is_deleted(self):
        from flamezo_backend.flamezo.api.otp import logout_customer
        token = frappe.generate_hash(length=32)
        self._put_session(token)

        # Confirm it exists before logout
        self.assertIsNotNone(frappe.cache().get_value(f"customer_session:{token}"))

        result = logout_customer(session_token=token)
        self.assertTrue(result["success"])

        # Must be gone from cache now
        self.assertIsNone(frappe.cache().get_value(f"customer_session:{token}"))

    def test_idempotent_for_already_deleted_token(self):
        """Calling logout twice should not raise — second call is a no-op success."""
        from flamezo_backend.flamezo.api.otp import logout_customer
        token = frappe.generate_hash(length=32)
        self._put_session(token)

        logout_customer(session_token=token)
        result = logout_customer(session_token=token)
        self.assertTrue(result["success"])


# ─── list_restaurants ─────────────────────────────────────────────────────────

class TestListRestaurants(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-LR-")

        # Restaurant A — fully configured, active, new
        cls.res_a = f"{_PREFIX}-LR-ACTIVE-A"
        make_restaurant(
            cls.res_a,
            city="Surat",
            address="123 Main Street, Surat",
            latitude=21.17,
            longitude=72.83,
            onboarding_date=add_days(today(), -10),  # 10 days ago → isNew
        )
        make_restaurant_config(
            cls.res_a,
            primary_color="#FF5733",
            tagline="Best food in town",
            subtitle="North Indian Cuisine",
        )

        # Restaurant B — active, old, no config
        cls.res_b = f"{_PREFIX}-LR-ACTIVE-B"
        make_restaurant(
            cls.res_b,
            city="Mumbai",
            onboarding_date=add_days(today(), -120),  # 120 days ago → NOT new
        )
        # No RestaurantConfig for B → primaryColor should default to #B7410E

        # Restaurant C — inactive
        cls.res_c = f"{_PREFIX}-LR-INACTIVE"
        make_restaurant(cls.res_c, city="Surat")
        frappe.db.set_value("Restaurant", cls.res_c, "is_active", 0)
        frappe.db.commit()

        # Add one gallery photo to A
        frappe.get_doc({
            "doctype": "Restaurant Gallery Item",
            "restaurant": cls.res_a,
            "url": "https://example.com/photo1.jpg",
            "media_type": "image",
            "is_selected": 1,
            "sort_order": 1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        # Coupons for A: 2 active, 1 inactive
        _make_coupon(cls.res_a, is_active=1)
        _make_coupon(cls.res_a, is_active=1)
        _make_coupon(cls.res_a, is_active=0)

    @classmethod
    def tearDownClass(cls):
        _cleanup([cls.res_a, cls.res_b, cls.res_c])

    def _call(self, **kwargs):
        from flamezo_backend.flamezo.api.restaurant import list_restaurants
        result = list_restaurants(**kwargs)
        self.assertTrue(result["success"], msg=f"list_restaurants failed: {result}")
        return result["data"]["restaurants"]

    def _find(self, restaurants, res_id):
        for r in restaurants:
            if r["restaurant_id"] == res_id:
                return r
        return None

    # --- shape tests ---

    def test_returns_list(self):
        restaurants = self._call()
        self.assertIsInstance(restaurants, list)

    def test_required_fields_present(self):
        restaurants = self._call()
        required = {
            "restaurant_id", "restaurant_name", "is_active",
            "logo", "photos", "city", "address",
            "latitude", "longitude", "plan_type",
            "primaryColor", "tagline", "cuisine_type",
            "active_offers_count", "isNew",
        }
        for r in restaurants:
            missing = required - set(r.keys())
            self.assertEqual(missing, set(), msg=f"Missing fields in {r['restaurant_id']}: {missing}")

    # --- active_only filter ---

    def test_active_only_true_excludes_inactive(self):
        restaurants = self._call(active_only=True)
        ids = [r["restaurant_id"] for r in restaurants]
        self.assertNotIn(self.res_c, ids, "Inactive restaurant must not appear when active_only=True")

    def test_active_only_false_includes_inactive(self):
        restaurants = self._call(active_only=False)
        ids = [r["restaurant_id"] for r in restaurants]
        self.assertIn(self.res_c, ids, "Inactive restaurant must appear when active_only=False")

    # --- city filter ---

    def test_city_filter_case_insensitive(self):
        restaurants = self._call(city="surat")
        ids = [r["restaurant_id"] for r in restaurants]
        self.assertIn(self.res_a, ids)
        self.assertNotIn(self.res_b, ids)

    def test_city_filter_uppercase(self):
        restaurants = self._call(city="MUMBAI")
        ids = [r["restaurant_id"] for r in restaurants]
        self.assertIn(self.res_b, ids)
        self.assertNotIn(self.res_a, ids)

    # --- primaryColor ---

    def test_primary_color_from_config(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_a)
        self.assertIsNotNone(r)
        self.assertEqual(r["primaryColor"], "#FF5733")

    def test_primary_color_defaults_when_no_config(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_b)
        self.assertIsNotNone(r)
        self.assertEqual(r["primaryColor"], "#B7410E")

    # --- tagline / cuisine_type ---

    def test_tagline_from_config(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_a)
        self.assertEqual(r["tagline"], "Best food in town")

    def test_cuisine_type_from_subtitle(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_a)
        self.assertEqual(r["cuisine_type"], "North Indian Cuisine")

    # --- photos ---

    def test_photos_list_for_configured_restaurant(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_a)
        self.assertIsInstance(r["photos"], list)
        self.assertIn("https://example.com/photo1.jpg", r["photos"])

    def test_photos_empty_when_no_gallery(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_b)
        self.assertEqual(r["photos"], [])

    # --- active_offers_count ---

    def test_offers_count_only_active_coupons(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_a)
        self.assertEqual(r["active_offers_count"], 2, "Must count only is_active=1 coupons")

    def test_offers_count_zero_when_no_coupons(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_b)
        self.assertEqual(r["active_offers_count"], 0)

    # --- isNew ---

    def test_is_new_true_for_recent_onboarding(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_a)
        self.assertTrue(r["isNew"])

    def test_is_new_false_for_old_onboarding(self):
        restaurants = self._call()
        r = self._find(restaurants, self.res_b)
        self.assertFalse(r["isNew"])

    # --- limit ---

    def test_limit_respected(self):
        restaurants = self._call(active_only=False, limit=1)
        self.assertLessEqual(len(restaurants), 1)


if __name__ == "__main__":
    unittest.main()
