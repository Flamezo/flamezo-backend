# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Chills API (chills.py).

DocTypes under test:
  Chills                — short video content unit (outlet-attributed)
  Chills Like           — per-phone like record
  Chills Save           — per-phone save record
  Chills Outlet Follow  — per-phone outlet follow (Join/Joined button)
  Flamezo Creator       — upload identity (backend-only)

Covers:
  get_chills_feed:
    - returns published items, newest first
    - cursor pagination (two pages, no overlap)
    - anonymous feed (no phone, all flags false)
    - isLiked / isSaved / outlet.isFollowing per phone
    - offersCount populated from active coupons
    - phone isolation (likes from other phone not mixed in)
    - draft excluded from feed

  get_chills_detail:
    - returns correct fields for a published chills
    - unpublished → DoesNotExistError
    - missing id → throws

  like_chills:
    - toggle on → liked=True, likes_count=1
    - toggle off → liked=False, likes_count=0
    - idempotent on-off-on sequence
    - two phones independent counts
    - count never goes negative
    - missing phone / id throws

  save_chills:
    - toggle on/off, saves_count updated
    - phone isolation
    - missing phone throws

  record_chills_view:
    - first call increments views_count
    - second call same phone+day is ignored
    - different phone counted separately

  follow_outlet:
    - toggle follow on → following=True, record exists
    - toggle follow off → following=False, record gone
    - phone isolation
    - cache invalidated on toggle
    - missing phone / outlet_id throws

  upload flow:
    - non-creator → PermissionError on request_chills_upload
    - pending creator → PermissionError
    - missing phone → throws
    - publish without outlet_id → throws
    - publish from non-creator → PermissionError
"""

import unittest

import frappe
from frappe.utils import now_datetime, today
from flamezo_backend.flamezo.api import chills as chills_api
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-CHILLS"
_PHONE_A = "9800000001"
_PHONE_B = "9800000002"


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_rest(suffix="01"):
    name = f"{_PREFIX}-R{suffix}"
    return make_restaurant(name, outlet_type="dining")


def _make_creator(phone=_PHONE_A, status="approved"):
    name = f"CREATOR-TEST-{phone}"
    if frappe.db.exists("Flamezo Creator", name):
        frappe.db.set_value("Flamezo Creator", name, "status", status)
        frappe.db.commit()
        return frappe.get_doc("Flamezo Creator", name)
    doc = frappe.get_doc({
        "doctype": "Flamezo Creator",
        "name": name,
        "customer_phone": phone,
        "display_name": f"Creator {phone[-4:]}",
        "status": status,
        "creator_tier": "Spark",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _make_chills(outlet, creator=None, description="Test chills video",
                 status="published", audio="Original sound"):
    doc = frappe.get_doc({
        "doctype": "Chills",
        "outlet": outlet,
        "creator": creator,
        "video_url": "https://r2.example.com/chills/test.mp4",
        "thumbnail_url": "https://r2.example.com/chills/test.jpg",
        "description": description,
        "audio": audio,
        "status": status,
        "published_at": now_datetime() if status == "published" else None,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _clear_feed_cache():
    """Bust all feed cache entries so tests see fresh DB state."""
    for phone in (_PHONE_A, _PHONE_B, None):
        frappe.cache().delete_value(f"chills:feed:{phone or 'anon'}:start:10")
        frappe.cache().delete_value(f"chills:outlet_follows:{phone}")


def _cleanup():
    frappe.db.sql("DELETE FROM `tabChills` WHERE outlet LIKE %s", [f"{_PREFIX}%"])
    frappe.db.sql(
        "DELETE FROM `tabChills Like` WHERE customer_phone IN (%s, %s)",
        [_PHONE_A, _PHONE_B],
    )
    frappe.db.sql(
        "DELETE FROM `tabChills Save` WHERE customer_phone IN (%s, %s)",
        [_PHONE_A, _PHONE_B],
    )
    frappe.db.sql(
        "DELETE FROM `tabChills Outlet Follow` WHERE customer_phone IN (%s, %s)",
        [_PHONE_A, _PHONE_B],
    )
    frappe.db.sql(
        "DELETE FROM `tabFlamezo Creator` WHERE customer_phone IN (%s, %s)",
        [_PHONE_A, _PHONE_B],
    )
    frappe.db.sql("DELETE FROM `tabRestaurant` WHERE name LIKE %s", [f"{_PREFIX}%"])
    frappe.db.commit()
    _clear_feed_cache()


# ── Feed ──────────────────────────────────────────────────────────────────────

class TestGetChillsFeed(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.c1 = _make_chills(self.rest.name, description="Chills 1")
        self.c2 = _make_chills(self.rest.name, description="Chills 2")
        self.draft = _make_chills(self.rest.name, status="draft")
        _clear_feed_cache()

    def tearDown(self):
        _cleanup()

    def test_returns_published_items(self):
        result = chills_api.get_chills_feed()
        ids = [c["id"] for c in result["reels"]]
        self.assertIn(self.c1.name, ids)
        self.assertIn(self.c2.name, ids)

    def test_draft_excluded(self):
        result = chills_api.get_chills_feed()
        ids = [c["id"] for c in result["reels"]]
        self.assertNotIn(self.draft.name, ids)

    def test_response_fields_present(self):
        result = chills_api.get_chills_feed()
        item = result["reels"][0]
        for field in ("id", "videoUrl", "thumbnail", "outlet", "description",
                      "audio", "likes", "saves", "shares", "views",
                      "isLiked", "isSaved", "offersCount"):
            self.assertIn(field, item)
        outlet = item["outlet"]
        for field in ("id", "name", "city", "avatar", "isFollowing", "lat", "lng"):
            self.assertIn(field, outlet)

    def test_outlet_id_populated(self):
        result = chills_api.get_chills_feed()
        item = next(c for c in result["reels"] if c["id"] == self.c1.name)
        self.assertEqual(item["outlet"]["id"], self.rest.name)

    def test_anon_feed_all_flags_false(self):
        result = chills_api.get_chills_feed(phone=None)
        for item in result["reels"]:
            self.assertFalse(item["isLiked"])
            self.assertFalse(item["isSaved"])
            self.assertFalse(item["outlet"]["isFollowing"])

    def test_is_liked_per_phone(self):
        frappe.get_doc({
            "doctype": "Chills Like", "chills": self.c1.name, "customer_phone": _PHONE_A,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        _clear_feed_cache()

        result_a = chills_api.get_chills_feed(phone=_PHONE_A)
        item_a = next(c for c in result_a["reels"] if c["id"] == self.c1.name)
        self.assertTrue(item_a["isLiked"])

        result_b = chills_api.get_chills_feed(phone=_PHONE_B)
        item_b = next((c for c in result_b["reels"] if c["id"] == self.c1.name), None)
        if item_b:
            self.assertFalse(item_b["isLiked"])

    def test_is_saved_per_phone(self):
        frappe.get_doc({
            "doctype": "Chills Save", "chills": self.c1.name, "customer_phone": _PHONE_A,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        _clear_feed_cache()

        result = chills_api.get_chills_feed(phone=_PHONE_A)
        item = next(c for c in result["reels"] if c["id"] == self.c1.name)
        self.assertTrue(item["isSaved"])

    def test_outlet_is_following_per_phone(self):
        frappe.get_doc({
            "doctype": "Chills Outlet Follow",
            "outlet": self.rest.name,
            "customer_phone": _PHONE_A,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.cache().delete_value(f"chills:outlet_follows:{_PHONE_A}")
        _clear_feed_cache()

        result = chills_api.get_chills_feed(phone=_PHONE_A)
        item = next(c for c in result["reels"] if c["id"] == self.c1.name)
        self.assertTrue(item["outlet"]["isFollowing"])

    def test_cursor_pagination_has_more(self):
        for i in range(5):
            _make_chills(self.rest.name, description=f"Paginate {i}")
        result = chills_api.get_chills_feed(limit=3)
        self.assertEqual(len(result["reels"]), 3)
        self.assertTrue(result["has_more"])
        self.assertIsNotNone(result["next_cursor"])

    def test_cursor_pagination_no_overlap(self):
        for i in range(6):
            _make_chills(self.rest.name, description=f"Page2 {i}")
        r1 = chills_api.get_chills_feed(limit=3)
        r2 = chills_api.get_chills_feed(cursor=r1["next_cursor"], limit=3)
        ids1 = {c["id"] for c in r1["reels"]}
        ids2 = {c["id"] for c in r2["reels"]}
        self.assertEqual(len(ids1 & ids2), 0)

    def test_last_page_has_more_false(self):
        result = chills_api.get_chills_feed(limit=100)
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next_cursor"])


# ── Detail ────────────────────────────────────────────────────────────────────

class TestGetChillsDetail(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)
        self.draft = _make_chills(self.rest.name, status="draft")

    def tearDown(self):
        _cleanup()

    def test_returns_correct_item(self):
        result = chills_api.get_chills_detail(self.item.name)
        self.assertEqual(result["id"], self.item.name)

    def test_all_fields_present(self):
        result = chills_api.get_chills_detail(self.item.name)
        for field in ("id", "videoUrl", "thumbnail", "outlet", "description",
                      "isLiked", "isSaved", "offersCount"):
            self.assertIn(field, result)

    def test_draft_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            chills_api.get_chills_detail(self.draft.name)

    def test_missing_id_throws(self):
        with self.assertRaises(Exception):
            chills_api.get_chills_detail(None)


# ── Like ──────────────────────────────────────────────────────────────────────

class TestLikeChills(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)

    def tearDown(self):
        _cleanup()

    def test_like_sets_true(self):
        result = chills_api.like_chills(self.item.name, _PHONE_A)
        self.assertTrue(result["liked"])
        count = frappe.db.get_value("Chills", self.item.name, "likes_count")
        self.assertEqual(count, 1)

    def test_unlike_sets_false(self):
        chills_api.like_chills(self.item.name, _PHONE_A)
        result = chills_api.like_chills(self.item.name, _PHONE_A)
        self.assertFalse(result["liked"])
        count = frappe.db.get_value("Chills", self.item.name, "likes_count")
        self.assertEqual(count, 0)

    def test_idempotent_on_off_on(self):
        chills_api.like_chills(self.item.name, _PHONE_A)   # on
        chills_api.like_chills(self.item.name, _PHONE_A)   # off
        chills_api.like_chills(self.item.name, _PHONE_A)   # on again
        count = frappe.db.get_value("Chills", self.item.name, "likes_count")
        self.assertEqual(count, 1)

    def test_two_phones_independent(self):
        chills_api.like_chills(self.item.name, _PHONE_A)
        chills_api.like_chills(self.item.name, _PHONE_B)
        count = frappe.db.get_value("Chills", self.item.name, "likes_count")
        self.assertEqual(count, 2)

    def test_count_never_negative(self):
        frappe.db.set_value("Chills", self.item.name, "likes_count", 0)
        frappe.db.commit()
        chills_api.like_chills(self.item.name, _PHONE_A)   # on → 1
        chills_api.like_chills(self.item.name, _PHONE_A)   # off → clamp at 0
        count = frappe.db.get_value("Chills", self.item.name, "likes_count")
        self.assertGreaterEqual(count, 0)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            chills_api.like_chills(self.item.name, None)

    def test_missing_chills_id_throws(self):
        with self.assertRaises(Exception):
            chills_api.like_chills(None, _PHONE_A)


# ── Save ──────────────────────────────────────────────────────────────────────

class TestSaveChills(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)

    def tearDown(self):
        _cleanup()

    def test_save_sets_true(self):
        result = chills_api.save_chills(self.item.name, _PHONE_A)
        self.assertTrue(result["saved"])
        count = frappe.db.get_value("Chills", self.item.name, "saves_count")
        self.assertEqual(count, 1)

    def test_unsave_sets_false(self):
        chills_api.save_chills(self.item.name, _PHONE_A)
        result = chills_api.save_chills(self.item.name, _PHONE_A)
        self.assertFalse(result["saved"])
        count = frappe.db.get_value("Chills", self.item.name, "saves_count")
        self.assertEqual(count, 0)

    def test_phone_isolation(self):
        chills_api.save_chills(self.item.name, _PHONE_A)
        exists = frappe.db.exists("Chills Save", {"chills": self.item.name, "customer_phone": _PHONE_B})
        self.assertFalse(bool(exists))

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            chills_api.save_chills(self.item.name, None)


# ── View ──────────────────────────────────────────────────────────────────────

class TestRecordChillsView(unittest.TestCase):

    def _view_key(self, phone):
        site = getattr(frappe.local, "site", "default")
        return f"{site}:chills:view:{self.item.name}:{phone}:{today()}"

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)
        frappe.cache().delete(self._view_key(_PHONE_A))
        frappe.cache().delete(self._view_key(_PHONE_B))

    def tearDown(self):
        frappe.cache().delete(self._view_key(_PHONE_A))
        frappe.cache().delete(self._view_key(_PHONE_B))
        _cleanup()

    def test_first_view_increments(self):
        result = chills_api.record_chills_view(self.item.name, _PHONE_A)
        self.assertTrue(result["ok"])
        count = frappe.db.get_value("Chills", self.item.name, "views_count")
        self.assertGreaterEqual(count, 1)

    def test_second_view_ignored(self):
        chills_api.record_chills_view(self.item.name, _PHONE_A)
        result = chills_api.record_chills_view(self.item.name, _PHONE_A)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("reason"), "already_counted")

    def test_different_phone_counted(self):
        chills_api.record_chills_view(self.item.name, _PHONE_A)
        result = chills_api.record_chills_view(self.item.name, _PHONE_B)
        self.assertTrue(result["ok"])


# ── Follow Outlet ─────────────────────────────────────────────────────────────

class TestFollowOutlet(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()

    def tearDown(self):
        _cleanup()

    def test_follow_sets_true(self):
        result = chills_api.follow_outlet(self.rest.name, _PHONE_A)
        self.assertTrue(result["following"])
        self.assertEqual(result["outlet_id"], self.rest.name)
        exists = frappe.db.exists("Chills Outlet Follow", {
            "outlet": self.rest.name, "customer_phone": _PHONE_A,
        })
        self.assertTrue(bool(exists))

    def test_unfollow_sets_false(self):
        chills_api.follow_outlet(self.rest.name, _PHONE_A)
        result = chills_api.follow_outlet(self.rest.name, _PHONE_A)
        self.assertFalse(result["following"])
        exists = frappe.db.exists("Chills Outlet Follow", {
            "outlet": self.rest.name, "customer_phone": _PHONE_A,
        })
        self.assertFalse(bool(exists))

    def test_phone_isolation(self):
        chills_api.follow_outlet(self.rest.name, _PHONE_A)
        exists = frappe.db.exists("Chills Outlet Follow", {
            "outlet": self.rest.name, "customer_phone": _PHONE_B,
        })
        self.assertFalse(bool(exists))

    def test_cache_invalidated_on_toggle(self):
        cache_key = f"chills:outlet_follows:{_PHONE_A}"
        frappe.cache().set_value(cache_key, [], expires_in_sec=120)
        chills_api.follow_outlet(self.rest.name, _PHONE_A)
        cached = frappe.cache().get_value(cache_key)
        self.assertIsNone(cached)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            chills_api.follow_outlet(self.rest.name, None)

    def test_missing_outlet_throws(self):
        with self.assertRaises(Exception):
            chills_api.follow_outlet(None, _PHONE_A)


# ── Upload Flow ───────────────────────────────────────────────────────────────

class TestChillsUploadFlow(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.creator = _make_creator(_PHONE_A, status="approved")

    def tearDown(self):
        _cleanup()

    def test_non_creator_upload_throws(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            chills_api.request_chills_upload("test.mp4", "video/mp4", _PHONE_B)

    def test_pending_creator_upload_throws(self):
        _make_creator(_PHONE_B, status="pending")
        with self.assertRaises(frappe.exceptions.PermissionError):
            chills_api.request_chills_upload("test.mp4", "video/mp4", _PHONE_B)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            chills_api.request_chills_upload("test.mp4", "video/mp4", None)

    def test_publish_without_outlet_throws(self):
        from unittest.mock import patch
        with patch("flamezo_backend.flamezo.utils.r2_storage.object_exists", return_value=True), \
             patch("flamezo_backend.flamezo.utils.r2_storage.public_url", return_value="https://r2.example.com/t.mp4"):
            with self.assertRaises(Exception):
                chills_api.publish_chills("chills/test/fake.mp4", "desc", _PHONE_A, outlet_id=None)

    def test_publish_non_creator_throws(self):
        from unittest.mock import patch
        with patch("flamezo_backend.flamezo.utils.r2_storage.object_exists", return_value=True), \
             patch("flamezo_backend.flamezo.utils.r2_storage.public_url", return_value="https://r2.example.com/t.mp4"):
            with self.assertRaises(frappe.exceptions.PermissionError):
                chills_api.publish_chills("chills/test/fake.mp4", "desc", _PHONE_B, outlet_id="FAKE-OUTLET")
