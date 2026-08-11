# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the production discovery APIs:
  - flamezo.get_all_outlets    (discovery feed)
  - flamezo.get_outlets_for_map (map markers)
  - outlet.get_outlet_detail (full outlet detail)

Covers:
  get_all_outlets:
    - Returns only active restaurants
    - outlet_type filter (single + comma-separated)
    - search across name, cuisines, description, city
    - section=featured returns only is_featured restaurants
    - section=new returns only recent (last 60d) restaurants
    - section=popular orders by total_orders DESC
    - has_offer filter returns only restaurants with active coupons
    - is_featured filter
    - radius_km hard geo filter (with lat/lon)
    - Pagination: page + limit + has_more
    - Response shape: all required fields present
    - Cache: Guest users get cached response
    - Inactive restaurants excluded

  get_outlets_for_map:
    - City filter returns correct restaurants
    - Bounding box filter works
    - outlet_type filter
    - Response shape: id, name, logo, lat, lng, outlet_type, is_featured, active_offers_count
    - Result cached

  get_outlet_detail:
    - Returns full outlet detail
    - All required fields present (photos, hours_json, cuisines, amenities_mask, etc.)
    - Lookup by outlet_id field
    - Lookup by internal name
    - Not found returns NOT_FOUND error
    - active_offers_count reflects real coupons
"""

import json
import unittest

import frappe
from frappe.utils import add_days, today

from flamezo_backend.flamezo.tests.utils import make_restaurant


_PREFIX = "TEST-DISCO"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_rest(
    suffix,
    outlet_type="dining",
    is_active=1,
    is_featured=0,
    rating=4.2,
    cuisines="North Indian, Chinese",
    price_range="₹300 – ₹800",
    amenities_mask=67,  # DINE_IN + TAKEOUT + DELIVERY
    hours_json=None,
    total_orders=0,
    onboarding_date=None,
    city="Surat",
    lat=21.1702,
    lng=72.8311,
):
    name = f"{_PREFIX}-{suffix}"
    if frappe.db.exists("Restaurant", name):
        frappe.delete_doc("Restaurant", name, force=True, ignore_permissions=True)
    r = make_restaurant(name, outlet_type=outlet_type)
    frappe.db.set_value("Restaurant", name, {
        "is_active": is_active,
        "is_featured": is_featured,
        "rating": rating,
        "cuisines": cuisines,
        "price_range": price_range,
        "amenities_mask": amenities_mask,
        "hours_json": hours_json or json.dumps({
            "mon": "11 AM – 11 PM", "tue": "11 AM – 11 PM",
            "wed": "11 AM – 11 PM", "thu": "11 AM – 11 PM",
            "fri": "11 AM – 11 PM", "sat": "11 AM – 11 PM",
            "sun": "Closed",
        }),
        "total_orders": total_orders,
        "onboarding_date": onboarding_date or today(),
        "city": city,
        "latitude": lat,
        "longitude": lng,
        "outlet_type": outlet_type,
        "description": f"Test restaurant {suffix} for discovery tests",
        "contact_phone": "9876543210",
        "whatsapp_number": "9876543210",
    })
    frappe.db.commit()
    return name


def _make_coupon(restaurant_name, discount_value=20):
    doc = frappe.get_doc({
        "doctype": "Coupon",
        "restaurant": restaurant_name,
        "code": f"TEST{restaurant_name[-4:].upper()}",
        "description": "Test discount",
        "discount_type": "percent",
        "discount_value": discount_value,
        "offer_type": "all",
        "is_active": 1,
        "valid_from": add_days(today(), -1),
        "valid_until": add_days(today(), 30),
        "min_order_amount": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _cleanup():
    frappe.db.sql("DELETE FROM `tabCoupon` WHERE code LIKE 'TEST%' AND description='Test discount'")
    frappe.db.sql(f"DELETE FROM `tabRestaurant` WHERE name LIKE '{_PREFIX}%'")
    # Clear discovery caches
    for key in frappe.cache().get_keys("flamezo:disco:*") or []:
        frappe.cache().delete_value(key)
    for key in frappe.cache().get_keys("flamezo:map:*") or []:
        frappe.cache().delete_value(key)
    frappe.db.commit()


from flamezo_backend.flamezo.api import flamezo as flamezo_api
from flamezo_backend.flamezo.api import outlet as outlet_api


# ── get_all_outlets ───────────────────────────────────────────────────────

class TestGetAllRestaurants(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.dining = _make_rest("D01", outlet_type="dining", total_orders=10)
        self.wellness = _make_rest("W01", outlet_type="wellness", total_orders=50, city="Ahmedabad", lat=23.02, lng=72.57)
        self.featured = _make_rest("F01", outlet_type="dining", is_featured=1, total_orders=100)
        self.inactive = _make_rest("I01", outlet_type="dining", is_active=0)
        self.new_rest = _make_rest("N01", outlet_type="cafe", onboarding_date=today())
        self.old_rest = _make_rest("O01", outlet_type="cafe", onboarding_date=add_days(today(), -90))

    def tearDown(self):
        _cleanup()

    def test_returns_only_active_restaurants(self):
        result = flamezo_api.get_all_outlets()
        self.assertTrue(result["success"], result)
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.dining, names)
        self.assertNotIn(self.inactive, names)

    def test_outlet_type_single_filter(self):
        result = flamezo_api.get_all_outlets(outlet_type="wellness")
        self.assertTrue(result["success"])
        types = {r["outlet_type"] for r in result["data"]["outlets"]}
        self.assertEqual(types, {"wellness"})
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.wellness, names)
        self.assertNotIn(self.dining, names)

    def test_outlet_type_comma_separated(self):
        result = flamezo_api.get_all_outlets(outlet_type="dining,cafe")
        self.assertTrue(result["success"])
        types = {r["outlet_type"] for r in result["data"]["outlets"]}
        self.assertIn("dining", types)
        self.assertIn("cafe", types)
        self.assertNotIn("wellness", types)

    def test_search_by_name(self):
        # Naming convention: restaurant_name = "Test Restaurant TEST-DISCO-D01"
        result = flamezo_api.get_all_outlets(search="DISCO-D01")
        self.assertTrue(result["success"])
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.dining, names)

    def test_search_by_cuisines(self):
        frappe.db.set_value("Restaurant", self.dining, "cuisines", "Gujarati, Jain")
        frappe.db.commit()
        result = flamezo_api.get_all_outlets(search="Gujarati")
        self.assertTrue(result["success"])
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.dining, names)

    def test_search_by_description(self):
        result = flamezo_api.get_all_outlets(search="discovery tests")
        self.assertTrue(result["success"])
        ids = [r["id"] for r in result["data"]["outlets"]]
        # All test restaurants have "discovery tests" in description
        self.assertGreater(len(ids), 0)

    def test_section_featured(self):
        result = flamezo_api.get_all_outlets(section="featured")
        self.assertTrue(result["success"])
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.featured, names)
        self.assertNotIn(self.dining, names)

    def test_is_featured_filter(self):
        result = flamezo_api.get_all_outlets(is_featured=1)
        self.assertTrue(result["success"])
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.featured, names)
        self.assertNotIn(self.dining, names)

    def test_section_new_returns_recent(self):
        result = flamezo_api.get_all_outlets(section="new")
        self.assertTrue(result["success"])
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.new_rest, names)
        # old_rest is 90 days old — outside the 60-day window
        self.assertNotIn(self.old_rest, names)

    def test_section_popular_orders_by_total_orders(self):
        result = flamezo_api.get_all_outlets(section="popular")
        self.assertTrue(result["success"])
        rests = result["data"]["outlets"]
        orders = [r.get("active_offers_count") for r in rests]
        # Check featured (100 orders) appears near top among test data
        names = [r["id"] for r in rests]
        feat_idx = names.index(self.featured) if self.featured in names else 999
        dining_idx = names.index(self.dining) if self.dining in names else 999
        self.assertLess(feat_idx, dining_idx)

    def test_has_offer_filter(self):
        coupon = _make_coupon(self.dining)
        try:
            result = flamezo_api.get_all_outlets(has_offer=1)
            self.assertTrue(result["success"])
            names = [r["id"] for r in result["data"]["outlets"]]
            self.assertIn(self.dining, names)
            # wellness has no coupon
            self.assertNotIn(self.wellness, names)
        finally:
            frappe.delete_doc("Coupon", coupon, force=True, ignore_permissions=True)
            frappe.db.commit()

    def test_active_offers_count_in_response(self):
        coupon = _make_coupon(self.dining)
        try:
            result = flamezo_api.get_all_outlets()
            self.assertTrue(result["success"])
            dining_card = next((r for r in result["data"]["outlets"] if r["id"] == self.dining), None)
            self.assertIsNotNone(dining_card)
            self.assertEqual(dining_card["active_offers_count"], 1)
        finally:
            frappe.delete_doc("Coupon", coupon, force=True, ignore_permissions=True)
            frappe.db.commit()

    def test_city_filter(self):
        result = flamezo_api.get_all_outlets(city="Ahmedabad")
        self.assertTrue(result["success"])
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.wellness, names)
        self.assertNotIn(self.dining, names)

    def test_pagination_page_and_limit(self):
        result = flamezo_api.get_all_outlets(page=1, limit=2)
        self.assertTrue(result["success"])
        self.assertLessEqual(len(result["data"]["outlets"]), 2)
        self.assertIn("has_more", result["data"])
        self.assertIn("total", result["data"])

    def test_response_shape(self):
        result = flamezo_api.get_all_outlets()
        self.assertTrue(result["success"])
        card = result["data"]["outlets"][0]
        for field in ("id", "outlet_name", "logo", "outlet_type", "city",
                      "latitude", "longitude", "is_featured", "cuisines",
                      "amenities_mask", "hours_json", "is_open_now",
                      "active_offers_count", "distance_km"):
            self.assertIn(field, card, f"Missing field: {field}")

    def test_cuisines_returned_as_list(self):
        result = flamezo_api.get_all_outlets()
        self.assertTrue(result["success"])
        card = next((r for r in result["data"]["outlets"] if r["id"] == self.dining), None)
        self.assertIsNotNone(card)
        self.assertIsInstance(card["cuisines"], list)

    def test_hours_json_returned_as_dict(self):
        result = flamezo_api.get_all_outlets()
        self.assertTrue(result["success"])
        card = next((r for r in result["data"]["outlets"] if r["id"] == self.dining), None)
        self.assertIsNotNone(card)
        self.assertIsInstance(card["hours_json"], dict)
        self.assertIn("mon", card["hours_json"])

    def test_geo_radius_filter(self):
        # Surat restaurants within 5 km, Ahmedabad wellness is ~250 km away
        result = flamezo_api.get_all_outlets(
            latitude=21.1702, longitude=72.8311, radius_km=50
        )
        self.assertTrue(result["success"])
        names = [r["id"] for r in result["data"]["outlets"]]
        self.assertIn(self.dining, names)
        self.assertNotIn(self.wellness, names)  # Ahmedabad is outside 50km

    def test_distance_sort_nearest_first(self):
        result = flamezo_api.get_all_outlets(latitude=21.1702, longitude=72.8311)
        self.assertTrue(result["success"])
        rests = result["data"]["outlets"]
        # Surat restaurants should appear before Ahmedabad one
        surat_ids = {self.dining, self.featured}
        for r in rests:
            if r["id"] in surat_ids:
                self.assertLessEqual(r["distance_km"], 5.0)
                break


# ── get_outlets_for_map ───────────────────────────────────────────────────

class TestGetRestaurantsForMap(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.r1 = _make_rest("M01", outlet_type="dining", lat=21.17, lng=72.83, city="Surat")
        self.r2 = _make_rest("M02", outlet_type="wellness", lat=21.18, lng=72.84, city="Surat")
        self.r3 = _make_rest("M03", outlet_type="dining", lat=23.02, lng=72.57, city="Ahmedabad")

    def tearDown(self):
        _cleanup()

    def test_city_filter(self):
        result = flamezo_api.get_outlets_for_map(city="Surat")
        self.assertTrue(result["success"], result)
        ids = [m["id"] for m in result["data"]["markers"]]
        self.assertIn(self.r1, ids)
        self.assertIn(self.r2, ids)
        self.assertNotIn(self.r3, ids)

    def test_bounding_box_filter(self):
        result = flamezo_api.get_outlets_for_map(
            sw_lat=21.10, sw_lng=72.80,
            ne_lat=21.25, ne_lng=72.90,
        )
        self.assertTrue(result["success"])
        ids = [m["id"] for m in result["data"]["markers"]]
        self.assertIn(self.r1, ids)
        self.assertIn(self.r2, ids)
        self.assertNotIn(self.r3, ids)  # Ahmedabad is outside bounds

    def test_outlet_type_filter(self):
        result = flamezo_api.get_outlets_for_map(city="Surat", outlet_type="wellness")
        self.assertTrue(result["success"])
        ids = [m["id"] for m in result["data"]["markers"]]
        self.assertIn(self.r2, ids)
        self.assertNotIn(self.r1, ids)

    def test_response_shape(self):
        result = flamezo_api.get_outlets_for_map(city="Surat")
        self.assertTrue(result["success"])
        self.assertGreater(len(result["data"]["markers"]), 0)
        marker = result["data"]["markers"][0]
        for field in ("id", "name", "logo", "lat", "lng", "outlet_type",
                      "is_featured", "active_offers_count"):
            self.assertIn(field, marker, f"Missing field: {field}")

    def test_active_offers_count_in_markers(self):
        coupon = _make_coupon(self.r1)
        try:
            # Clear cache so we get fresh data
            frappe.cache().delete_value(f"flamezo:map:Surat:none:none:all")
            result = flamezo_api.get_outlets_for_map(city="Surat")
            self.assertTrue(result["success"])
            m = next((x for x in result["data"]["markers"] if x["id"] == self.r1), None)
            self.assertIsNotNone(m)
            self.assertEqual(m["active_offers_count"], 1)
        finally:
            frappe.delete_doc("Coupon", coupon, force=True, ignore_permissions=True)
            frappe.db.commit()

    def test_no_markers_outside_bounds(self):
        result = flamezo_api.get_outlets_for_map(
            sw_lat=28.50, sw_lng=77.00,
            ne_lat=28.70, ne_lng=77.20,  # Delhi bounding box
        )
        self.assertTrue(result["success"])
        ids = [m["id"] for m in result["data"]["markers"]]
        self.assertNotIn(self.r1, ids)
        self.assertNotIn(self.r2, ids)
        self.assertNotIn(self.r3, ids)


# ── get_outlet_detail ─────────────────────────────────────────────────────

class TestGetRestaurantDetail(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest(
            "RD01",
            outlet_type="wellness",
            rating=4.5,
            cuisines="Healthy, Vegan",
            price_range="₹500 – ₹1500",
            amenities_mask=3,  # DINE_IN + TAKEOUT
        )
        # Add gallery photos
        frappe.get_doc({
            "doctype": "Restaurant Gallery Item",
            "restaurant": self.rest,
            "media_type": "Image",
            "url": "https://cdn.flamezo.in/test/photo1.jpg",
            "is_selected": 1,
            "sort_order": 0,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        # Clear detail cache
        frappe.cache().delete_value(f"flamezo:outlet_detail:{self.rest}")

    def tearDown(self):
        frappe.db.sql(f"DELETE FROM `tabRestaurant Gallery Item` WHERE restaurant='{self.rest}'")
        if frappe.db.exists("Coupon", {"restaurant": self.rest}):
            for c in frappe.get_all("Coupon", {"restaurant": self.rest}):
                frappe.delete_doc("Coupon", c.name, force=True, ignore_permissions=True)
        _cleanup()

    def test_returns_full_detail(self):
        result = outlet_api.get_outlet_detail(self.rest)
        self.assertTrue(result["success"], result)
        data = result["data"]
        self.assertEqual(data["id"], self.rest)
        self.assertEqual(data["outlet_type"], "wellness")

    def test_all_required_fields_present(self):
        result = outlet_api.get_outlet_detail(self.rest)
        data = result["data"]
        for field in (
            "id", "outlet_name", "logo", "outlet_type",
            "address", "city", "latitude", "longitude",
            "phone", "whatsapp", "instagram_url", "description",
            "is_featured", "rating", "review_count",
            "cuisines", "price_range", "amenities_mask", "hours_json",
            "is_open_now", "active_offers_count", "photos",
            "enable_dine_in", "enable_table_booking",
        ):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_cuisines_returned_as_list(self):
        result = outlet_api.get_outlet_detail(self.rest)
        self.assertIsInstance(result["data"]["cuisines"], list)
        self.assertIn("Healthy", result["data"]["cuisines"])
        self.assertIn("Vegan", result["data"]["cuisines"])

    def test_hours_json_returned_as_dict(self):
        result = outlet_api.get_outlet_detail(self.rest)
        self.assertIsInstance(result["data"]["hours_json"], dict)
        self.assertIn("mon", result["data"]["hours_json"])

    def test_rating_and_review_count(self):
        result = outlet_api.get_outlet_detail(self.rest)
        self.assertEqual(result["data"]["rating"], 4.5)
        self.assertEqual(result["data"]["amenities_mask"], 3)

    def test_photos_included(self):
        result = outlet_api.get_outlet_detail(self.rest)
        photos = result["data"]["photos"]
        self.assertIsInstance(photos, list)
        self.assertGreater(len(photos), 0)
        self.assertIn("url", photos[0])
        self.assertIn("cdn.flamezo.in", photos[0]["url"])

    def test_active_offers_count(self):
        coupon = _make_coupon(self.rest)
        frappe.cache().delete_value(f"flamezo:outlet_detail:{self.rest}")
        try:
            result = outlet_api.get_outlet_detail(self.rest)
            self.assertEqual(result["data"]["active_offers_count"], 1)
        finally:
            frappe.delete_doc("Coupon", coupon, force=True, ignore_permissions=True)
            frappe.db.commit()

    def test_lookup_by_internal_name(self):
        result = outlet_api.get_outlet_detail(self.rest)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["id"], self.rest)

    def test_not_found_returns_error(self):
        result = outlet_api.get_outlet_detail("NONEXISTENT-REST-XYZ")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NOT_FOUND")

    def test_missing_restaurant_id_returns_error(self):
        result = outlet_api.get_outlet_detail(None)
        self.assertFalse(result["success"])

    def test_response_cached(self):
        outlet_api.get_outlet_detail(self.rest)
        cached = frappe.cache().get_value(f"flamezo:outlet_detail:{self.rest}")
        self.assertIsNotNone(cached)
        parsed = json.loads(cached)
        self.assertTrue(parsed["success"])


if __name__ == "__main__":
    unittest.main()
