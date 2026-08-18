# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the Hot Drops API (hot_drops.py).

Covers:
  Merchant:
    - create_hot_drop: happy path, missing label blocked, end<=start blocked,
      3-slot cap enforced, cross-outlet coupon blocked
    - end_hot_drop_now: happy path, cross-outlet blocked
    - list_merchant_hot_drops: slot-usage counting, live/upcoming flags

  Consumer:
    - get_hot_drops: returns live/upcoming within 48h, excludes ended and
      inactive-outlet drops, city filter

  Analytics:
    - track_hot_drop_event: valid/invalid event types
    - get_hot_drop_analytics: view/tap/claim shape

  Doctype:
    - Hot Drop.validate() backstop cap (bypassing the API layer)
"""

import unittest
import frappe
from frappe.utils import now_datetime, add_to_date

from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-HD"


def _make_restaurant(suffix="01", **kwargs):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type="dining", **kwargs)
    return r.name


def _make_hot_drop(restaurant, label="Flash Deal", hours_from_now=0, duration_hours=2,
                    is_active=1, coupon=None):
    starts = add_to_date(now_datetime(), hours=hours_from_now)
    ends = add_to_date(starts, hours=duration_hours)
    doc = frappe.get_doc({
        "doctype": "Hot Drop",
        "restaurant": restaurant,
        "coupon": coupon,
        "deal_label": label,
        "starts_at": starts,
        "ends_at": ends,
        "is_active": is_active,
        "story_images": "[]",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _cleanup(restaurant):
    frappe.db.delete("Analytics Event", {"restaurant": restaurant})
    frappe.db.delete("Offer Claim", {"restaurant": restaurant})
    frappe.db.delete("Coupon", {"restaurant": restaurant})
    frappe.db.delete("Hot Drop", {"restaurant": restaurant})
    frappe.db.delete("Restaurant", restaurant)
    frappe.db.commit()


class TestCreateHotDrop(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CR01")
        self.other = _make_restaurant("CR02")

    def tearDown(self):
        _cleanup(self.restaurant)
        _cleanup(self.other)

    def test_happy_path(self):
        from flamezo_backend.flamezo.api.hot_drops import create_hot_drop
        starts = now_datetime()
        ends = add_to_date(starts, hours=2)
        res = create_hot_drop(
            outlet_id=self.restaurant, deal_label="50% off tonight",
            starts_at=str(starts), ends_at=str(ends),
        )
        self.assertTrue(res["success"], res)
        self.assertTrue(frappe.db.exists("Hot Drop", res["data"]["name"]))

    def test_missing_label_blocked(self):
        from flamezo_backend.flamezo.api.hot_drops import create_hot_drop
        starts = now_datetime()
        ends = add_to_date(starts, hours=2)
        with self.assertRaises(frappe.ValidationError):
            create_hot_drop(outlet_id=self.restaurant, deal_label="  ",
                             starts_at=str(starts), ends_at=str(ends))

    def test_end_before_start_blocked(self):
        from flamezo_backend.flamezo.api.hot_drops import create_hot_drop
        starts = now_datetime()
        ends = add_to_date(starts, hours=-1)
        with self.assertRaises(frappe.ValidationError):
            create_hot_drop(outlet_id=self.restaurant, deal_label="Bad window",
                             starts_at=str(starts), ends_at=str(ends))

    def test_fourth_concurrent_drop_blocked(self):
        from flamezo_backend.flamezo.api.hot_drops import create_hot_drop
        _make_hot_drop(self.restaurant, hours_from_now=1)
        _make_hot_drop(self.restaurant, hours_from_now=5)
        _make_hot_drop(self.restaurant, hours_from_now=8)
        starts = add_to_date(now_datetime(), hours=10)
        ends = add_to_date(starts, hours=2)
        with self.assertRaises(frappe.ValidationError):
            create_hot_drop(outlet_id=self.restaurant, deal_label="One too many",
                             starts_at=str(starts), ends_at=str(ends))

    def test_already_ended_drops_dont_count_toward_cap(self):
        from flamezo_backend.flamezo.api.hot_drops import create_hot_drop
        # Two PAST drops (already ended) shouldn't occupy a slot.
        _make_hot_drop(self.restaurant, hours_from_now=-10, duration_hours=1)
        _make_hot_drop(self.restaurant, hours_from_now=-5, duration_hours=1)
        starts = now_datetime()
        ends = add_to_date(starts, hours=2)
        res = create_hot_drop(outlet_id=self.restaurant, deal_label="Still room",
                               starts_at=str(starts), ends_at=str(ends))
        self.assertTrue(res["success"], res)

    def test_cross_outlet_coupon_blocked(self):
        from flamezo_backend.flamezo.api.hot_drops import create_hot_drop
        coupon = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.other,
            "code": "TESTHD01",
            "offer_type": "coupon",
            "discount_type": "flat",
            "discount_value": 50,
            "is_active": 1,
        })
        coupon.insert(ignore_permissions=True)
        frappe.db.commit()
        starts = now_datetime()
        ends = add_to_date(starts, hours=2)
        with self.assertRaises(frappe.PermissionError):
            create_hot_drop(outlet_id=self.restaurant, deal_label="Wrong coupon",
                             starts_at=str(starts), ends_at=str(ends), coupon=coupon.name)


class TestEndHotDropNow(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("END01")
        self.other = _make_restaurant("END02")

    def tearDown(self):
        _cleanup(self.restaurant)
        _cleanup(self.other)

    def test_happy_path(self):
        from flamezo_backend.flamezo.api.hot_drops import end_hot_drop_now
        drop = _make_hot_drop(self.restaurant, duration_hours=5)
        res = end_hot_drop_now(outlet_id=self.restaurant, hot_drop_name=drop)
        self.assertTrue(res["success"], res)
        self.assertEqual(frappe.db.get_value("Hot Drop", drop, "is_active"), 0)

    def test_cross_outlet_blocked(self):
        from flamezo_backend.flamezo.api.hot_drops import end_hot_drop_now
        drop = _make_hot_drop(self.other, duration_hours=5)
        with self.assertRaises(frappe.PermissionError):
            end_hot_drop_now(outlet_id=self.restaurant, hot_drop_name=drop)
        # Untouched — the other outlet's drop must still be active.
        self.assertEqual(frappe.db.get_value("Hot Drop", drop, "is_active"), 1)


class TestListMerchantHotDrops(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("LIST01")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_slot_usage_and_flags(self):
        from flamezo_backend.flamezo.api.hot_drops import list_merchant_hot_drops
        _make_hot_drop(self.restaurant, hours_from_now=-1, duration_hours=3)  # live now
        _make_hot_drop(self.restaurant, hours_from_now=5, duration_hours=2)   # upcoming
        _make_hot_drop(self.restaurant, hours_from_now=-10, duration_hours=1)  # ended
        res = list_merchant_hot_drops(outlet_id=self.restaurant)
        self.assertTrue(res["success"], res)
        self.assertEqual(res["data"]["max_slots"], 3)
        self.assertEqual(res["data"]["active_slots_used"], 2)  # live + upcoming, not ended
        self.assertEqual(len(res["data"]["hot_drops"]), 3)
        flags = {d["name"]: d for d in res["data"]["hot_drops"]}
        live = [d for d in flags.values() if d["is_live"]]
        upcoming = [d for d in flags.values() if d["is_upcoming"]]
        self.assertEqual(len(live), 1)
        self.assertEqual(len(upcoming), 1)


class TestGetHotDrops(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("FEED01", city="Surat")
        self.inactive_outlet = _make_restaurant("FEED02", city="Surat", is_active=0)

    def tearDown(self):
        _cleanup(self.restaurant)
        _cleanup(self.inactive_outlet)

    def test_returns_live_and_upcoming_within_48h(self):
        from flamezo_backend.flamezo.api.hot_drops import get_hot_drops
        live = _make_hot_drop(self.restaurant, hours_from_now=-1, duration_hours=3)
        upcoming = _make_hot_drop(self.restaurant, hours_from_now=10, duration_hours=2)
        _make_hot_drop(self.restaurant, hours_from_now=60, duration_hours=2)  # beyond 48h horizon
        res = get_hot_drops(rotation_seed="fixed-seed-for-test")
        self.assertTrue(res["success"], res)
        ids = {d["id"] for d in res["data"]["hot_drops"]}
        self.assertIn(live, ids)
        self.assertIn(upcoming, ids)

    def test_excludes_ended_drops(self):
        from flamezo_backend.flamezo.api.hot_drops import get_hot_drops
        ended = _make_hot_drop(self.restaurant, hours_from_now=-10, duration_hours=1)
        res = get_hot_drops(rotation_seed="fixed-seed-for-test")
        ids = {d["id"] for d in res["data"]["hot_drops"]}
        self.assertNotIn(ended, ids)

    def test_excludes_inactive_outlet(self):
        from flamezo_backend.flamezo.api.hot_drops import get_hot_drops
        drop = _make_hot_drop(self.inactive_outlet, hours_from_now=-1, duration_hours=3)
        res = get_hot_drops(rotation_seed="fixed-seed-for-test")
        ids = {d["id"] for d in res["data"]["hot_drops"]}
        self.assertNotIn(drop, ids)

    def test_live_sorted_before_upcoming(self):
        from flamezo_backend.flamezo.api.hot_drops import get_hot_drops
        upcoming = _make_hot_drop(self.restaurant, hours_from_now=20, duration_hours=2)
        live = _make_hot_drop(self.restaurant, hours_from_now=-1, duration_hours=3)
        res = get_hot_drops(rotation_seed="fixed-seed-for-test")
        ids_in_order = [d["id"] for d in res["data"]["hot_drops"]]
        self.assertLess(ids_in_order.index(live), ids_in_order.index(upcoming))


class TestHotDropAnalytics(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("AN01")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_track_event_valid_types(self):
        from flamezo_backend.flamezo.api.hot_drops import track_hot_drop_event
        drop = _make_hot_drop(self.restaurant)
        res = track_hot_drop_event(hot_drop_name=drop, event_type="hotdrop_view")
        self.assertTrue(res["success"])
        self.assertEqual(
            frappe.db.count("Analytics Event", {"restaurant": self.restaurant, "event_type": "hotdrop_view"}), 1
        )

    def test_track_event_invalid_type_rejected(self):
        from flamezo_backend.flamezo.api.hot_drops import track_hot_drop_event
        drop = _make_hot_drop(self.restaurant)
        res = track_hot_drop_event(hot_drop_name=drop, event_type="something_else")
        self.assertFalse(res["success"])
        self.assertEqual(frappe.db.count("Analytics Event", {"restaurant": self.restaurant}), 0)

    def test_analytics_shape(self):
        from flamezo_backend.flamezo.api.hot_drops import get_hot_drop_analytics, track_hot_drop_event
        drop = _make_hot_drop(self.restaurant)
        track_hot_drop_event(hot_drop_name=drop, event_type="hotdrop_view")
        track_hot_drop_event(hot_drop_name=drop, event_type="hotdrop_view")
        track_hot_drop_event(hot_drop_name=drop, event_type="hotdrop_tap")
        res = get_hot_drop_analytics(outlet_id=self.restaurant, hot_drop_name=drop)
        self.assertTrue(res["success"], res)
        row = res["data"]["drops"][0]
        self.assertEqual(row["views"], 2)
        self.assertEqual(row["taps"], 1)
        self.assertEqual(row["claims"], 0)
        self.assertEqual(row["view_to_claim_rate"], 0)


class TestHotDropDoctypeCapBackstop(unittest.TestCase):
    """Bypasses the API layer entirely -- exercises Hot Drop.validate()'s own
    cap enforcement directly, same as create_hot_drop's own cap check would,
    but via frappe.get_doc().insert() the way Desk UI/data import would."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("VAL01")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_end_before_start_rejected_at_doctype_level(self):
        starts = now_datetime()
        ends = add_to_date(starts, hours=-1)
        doc = frappe.get_doc({
            "doctype": "Hot Drop", "restaurant": self.restaurant, "deal_label": "Bad",
            "starts_at": starts, "ends_at": ends, "is_active": 1,
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_cap_enforced_even_bypassing_api(self):
        _make_hot_drop(self.restaurant, hours_from_now=1)
        _make_hot_drop(self.restaurant, hours_from_now=5)
        _make_hot_drop(self.restaurant, hours_from_now=10)
        starts = add_to_date(now_datetime(), hours=20)
        ends = add_to_date(starts, hours=2)
        doc = frappe.get_doc({
            "doctype": "Hot Drop", "restaurant": self.restaurant, "deal_label": "4th one",
            "starts_at": starts, "ends_at": ends, "is_active": 1,
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
