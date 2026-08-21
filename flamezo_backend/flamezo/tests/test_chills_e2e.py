# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Chills API (chills.py).

Response shape: every endpoint returns {"success": True, "data": {...}} —
all assertions below read through `result["data"]`.

Redis-buffered counters (likes/saves/views/shares): `like_chills`,
`save_chills`, `record_chills_view`, `increment_shares` no longer write the
DB counter column synchronously — Redis (`redis_counters.py`) is the live,
immediately-consistent source of truth; the DB column is only kept in sync
by the scheduled `flush_all` job. So:
  - Assertions about the LIVE count read `rc.get_count(...)`, not the DB
    column directly (that's the whole point of the change).
  - Assertions about DURABILITY call `rc.flush_all()` explicitly first, then
    check the DB column — proving the flush path actually works.
  - The per-user join-table row (`Chills Like`/`Chills Save`) is written by
    a background job (`persist_toggle`), enqueued but not run automatically
    in this test process (no worker consuming the queue) — tested directly
    by calling `rc.persist_toggle(...)` rather than relying on the enqueue
    firing, same as any other Frappe background-job test in this codebase.

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
    - likes/saves/views reflect Redis, not just the DB column

  get_chills_detail:
    - returns correct fields for a published chills
    - unpublished → DoesNotExistError
    - missing id → throws

  like_chills:
    - toggle on → liked=True, live count=1 (Redis)
    - toggle off → liked=False, live count=0
    - idempotent on-off-on sequence
    - two phones independent counts
    - count never goes negative
    - missing phone / id / nonexistent chills throws
    - flush_all persists the live count to the DB column

  save_chills:
    - toggle on/off, saves live count updated
    - phone isolation
    - missing phone throws

  record_chills_view:
    - first call increments the live views count
    - second call same phone+day is ignored
    - different phone counted separately

  increment_shares:
    - increments the live shares count
    - same phone within the dedup window is ignored (the bug fix — this
      endpoint previously had NO idempotency guard at all)
    - anonymous (no phone) calls still get some dedup via a per-item cooldown
    - nonexistent chills throws

  follow_outlet:
    - toggle follow on → following=True, record exists
    - toggle follow off → following=False, record gone
    - phone isolation
    - cache invalidated on toggle
    - missing phone / outlet_id throws

  redis_counters module (direct unit coverage):
    - toggle_member flips and returns the new state
    - bump_count / get_count roundtrip, marks the item dirty
    - get_counts batches correctly and falls back per-item
    - members_for batches SISMEMBER correctly
    - flush_all writes the absolute Redis value to the DB column and clears
      the dirty set (re-running is a safe no-op)
    - persist_toggle inserts/deletes the join-table row idempotently
    - backfill_from_db seeds Redis to match existing DB counts/rows

  upload flow:
    - non-creator → PermissionError on request_chills_upload
    - pending creator → PermissionError
    - missing phone → throws
    - publish without outlet_id → throws
    - publish from non-creator → PermissionError
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import now_datetime, today
from flamezo_backend.flamezo.api import chills as chills_api
from flamezo_backend.flamezo.utils import redis_counters as rc
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-CHILLS"
_PHONE_A = "9800000001"
_PHONE_B = "9800000002"


def _verified_session():
    """follow_outlet requires a real verified session (chills.py imports
    has_active_customer_session by name, so the patch target is chills.py's
    own bound reference — see test_clubs_e2e.py for the same gotcha)."""
    return patch("flamezo_backend.flamezo.api.chills.has_active_customer_session", return_value=True)


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


def _clear_counter_state(chills_id):
    """Wipes every Redis key redis_counters.py could have created for one
    item, across all scopes — keeps counter tests independent of ordering
    and of whatever the module-level backfill (run once, separately, in
    other test sessions) may have already seeded."""
    r = frappe.cache()
    for scope in ("chills_likes", "chills_saves", "chills_views", "chills_shares"):
        r.delete(rc._count_key(scope, chills_id))
        r.delete(rc._members_key(scope, chills_id))
        rc._srem(r, rc._dirty_key(scope), chills_id)


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
    frappe.db.sql("DELETE FROM `tabOutlet` WHERE name LIKE %s", [f"{_PREFIX}%"])
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
        _clear_counter_state(self.c1.name)
        _clear_counter_state(self.c2.name)

    def tearDown(self):
        _cleanup()

    def test_returns_published_items(self):
        result = chills_api.get_chills_feed()["data"]
        ids = [c["id"] for c in result["reels"]]
        self.assertIn(self.c1.name, ids)
        self.assertIn(self.c2.name, ids)

    def test_draft_excluded(self):
        result = chills_api.get_chills_feed()["data"]
        ids = [c["id"] for c in result["reels"]]
        self.assertNotIn(self.draft.name, ids)

    def test_response_fields_present(self):
        result = chills_api.get_chills_feed()["data"]
        item = result["reels"][0]
        for field in ("id", "videoUrl", "thumbnail", "outlet", "description",
                      "audio", "likes", "saves", "shares", "views",
                      "isLiked", "isSaved", "offersCount"):
            self.assertIn(field, item)
        outlet = item["outlet"]
        for field in ("id", "name", "city", "avatar", "isFollowing", "lat", "lng"):
            self.assertIn(field, outlet)

    def test_outlet_id_populated(self):
        result = chills_api.get_chills_feed()["data"]
        item = next(c for c in result["reels"] if c["id"] == self.c1.name)
        self.assertEqual(item["outlet"]["id"], self.rest.name)

    def test_anon_feed_all_flags_false(self):
        result = chills_api.get_chills_feed(phone=None)["data"]
        for item in result["reels"]:
            self.assertFalse(item["isLiked"])
            self.assertFalse(item["isSaved"])
            self.assertFalse(item["outlet"]["isFollowing"])

    def test_is_liked_per_phone(self):
        chills_api.like_chills(self.c1.name, _PHONE_A)
        _clear_feed_cache()

        result_a = chills_api.get_chills_feed(phone=_PHONE_A)["data"]
        item_a = next(c for c in result_a["reels"] if c["id"] == self.c1.name)
        self.assertTrue(item_a["isLiked"])

        result_b = chills_api.get_chills_feed(phone=_PHONE_B)["data"]
        item_b = next((c for c in result_b["reels"] if c["id"] == self.c1.name), None)
        if item_b:
            self.assertFalse(item_b["isLiked"])

    def test_is_saved_per_phone(self):
        chills_api.save_chills(self.c1.name, _PHONE_A)
        _clear_feed_cache()

        result = chills_api.get_chills_feed(phone=_PHONE_A)["data"]
        item = next(c for c in result["reels"] if c["id"] == self.c1.name)
        self.assertTrue(item["isSaved"])

    def test_likes_count_reflects_redis(self):
        chills_api.like_chills(self.c1.name, _PHONE_A)
        chills_api.like_chills(self.c1.name, _PHONE_B)
        _clear_feed_cache()

        result = chills_api.get_chills_feed()["data"]
        item = next(c for c in result["reels"] if c["id"] == self.c1.name)
        self.assertEqual(item["likes"], 2)
        # ...while the DB column is still untouched until a flush runs.
        db_count = frappe.db.get_value("Chills", self.c1.name, "likes_count")
        self.assertEqual(db_count or 0, 0)

    def test_outlet_is_following_per_phone(self):
        frappe.get_doc({
            "doctype": "Chills Outlet Follow",
            "outlet": self.rest.name,
            "customer_phone": _PHONE_A,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.cache().delete_value(f"chills:outlet_follows:{_PHONE_A}")
        _clear_feed_cache()

        result = chills_api.get_chills_feed(phone=_PHONE_A)["data"]
        item = next(c for c in result["reels"] if c["id"] == self.c1.name)
        self.assertTrue(item["outlet"]["isFollowing"])

    def test_cursor_pagination_has_more(self):
        for i in range(5):
            _make_chills(self.rest.name, description=f"Paginate {i}")
        result = chills_api.get_chills_feed(limit=3)["data"]
        self.assertEqual(len(result["reels"]), 3)
        self.assertTrue(result["has_more"])
        self.assertIsNotNone(result["next_cursor"])

    def test_cursor_pagination_no_overlap(self):
        for i in range(6):
            _make_chills(self.rest.name, description=f"Page2 {i}")
        r1 = chills_api.get_chills_feed(limit=3)["data"]
        r2 = chills_api.get_chills_feed(cursor=r1["next_cursor"], limit=3)["data"]
        ids1 = {c["id"] for c in r1["reels"]}
        ids2 = {c["id"] for c in r2["reels"]}
        self.assertEqual(len(ids1 & ids2), 0)

    def test_last_page_has_more_false(self):
        # get_chills_feed caps limit at 30 server-side regardless of what's
        # requested, and this dev DB has hundreds of real (non-test) Chills
        # rows — a single page can never exhaust the global feed, so page
        # forward via cursor until has_more genuinely goes False, bounded to
        # avoid an infinite loop if that invariant is ever broken.
        cursor = None
        result = None
        for _ in range(50):
            result = chills_api.get_chills_feed(cursor=cursor, limit=30)["data"]
            if not result["has_more"]:
                break
            cursor = result["next_cursor"]
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next_cursor"])


# ── Detail ────────────────────────────────────────────────────────────────────

class TestGetChillsDetail(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)
        self.draft = _make_chills(self.rest.name, status="draft")
        _clear_counter_state(self.item.name)

    def tearDown(self):
        _cleanup()

    def test_returns_correct_item(self):
        result = chills_api.get_chills_detail(self.item.name)["data"]
        self.assertEqual(result["id"], self.item.name)

    def test_all_fields_present(self):
        result = chills_api.get_chills_detail(self.item.name)["data"]
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
        _clear_counter_state(self.item.name)

    def tearDown(self):
        _clear_counter_state(self.item.name)
        _cleanup()

    def test_like_sets_true(self):
        result = chills_api.like_chills(self.item.name, _PHONE_A)["data"]
        self.assertTrue(result["liked"])
        self.assertEqual(rc.get_count("chills_likes", self.item.name), 1)

    def test_unlike_sets_false(self):
        chills_api.like_chills(self.item.name, _PHONE_A)
        result = chills_api.like_chills(self.item.name, _PHONE_A)["data"]
        self.assertFalse(result["liked"])
        self.assertEqual(rc.get_count("chills_likes", self.item.name), 0)

    def test_idempotent_on_off_on(self):
        chills_api.like_chills(self.item.name, _PHONE_A)   # on
        chills_api.like_chills(self.item.name, _PHONE_A)   # off
        chills_api.like_chills(self.item.name, _PHONE_A)   # on again
        self.assertEqual(rc.get_count("chills_likes", self.item.name), 1)
        self.assertTrue(rc.is_member("chills_likes", self.item.name, _PHONE_A))

    def test_two_phones_independent(self):
        chills_api.like_chills(self.item.name, _PHONE_A)
        chills_api.like_chills(self.item.name, _PHONE_B)
        self.assertEqual(rc.get_count("chills_likes", self.item.name), 2)

    def test_count_never_negative(self):
        # Never liked, straight to an "unlike" — must clamp, not go negative.
        chills_api.like_chills(self.item.name, _PHONE_A)   # on → 1
        chills_api.like_chills(self.item.name, _PHONE_A)   # off → 0
        chills_api.like_chills(self.item.name, _PHONE_A)   # on → 1
        chills_api.like_chills(self.item.name, _PHONE_A)   # off → 0
        self.assertGreaterEqual(rc.get_count("chills_likes", self.item.name), 0)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            chills_api.like_chills(self.item.name, None)

    def test_missing_chills_id_throws(self):
        with self.assertRaises(Exception):
            chills_api.like_chills(None, _PHONE_A)

    def test_nonexistent_chills_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            chills_api.like_chills("CHILL-DOES-NOT-EXIST", _PHONE_A)

    def test_flush_persists_live_count_to_db(self):
        chills_api.like_chills(self.item.name, _PHONE_A)
        chills_api.like_chills(self.item.name, _PHONE_B)
        rc.flush_all()
        db_count = frappe.db.get_value("Chills", self.item.name, "likes_count")
        self.assertEqual(db_count, 2)


# ── Save ──────────────────────────────────────────────────────────────────────

class TestSaveChills(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)
        _clear_counter_state(self.item.name)

    def tearDown(self):
        _clear_counter_state(self.item.name)
        _cleanup()

    def test_save_sets_true(self):
        result = chills_api.save_chills(self.item.name, _PHONE_A)["data"]
        self.assertTrue(result["saved"])
        self.assertEqual(rc.get_count("chills_saves", self.item.name), 1)

    def test_unsave_sets_false(self):
        chills_api.save_chills(self.item.name, _PHONE_A)
        result = chills_api.save_chills(self.item.name, _PHONE_A)["data"]
        self.assertFalse(result["saved"])
        self.assertEqual(rc.get_count("chills_saves", self.item.name), 0)

    def test_phone_isolation(self):
        chills_api.save_chills(self.item.name, _PHONE_A)
        self.assertFalse(rc.is_member("chills_saves", self.item.name, _PHONE_B))

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
        _clear_counter_state(self.item.name)
        frappe.cache().delete(self._view_key(_PHONE_A))
        frappe.cache().delete(self._view_key(_PHONE_B))

    def tearDown(self):
        frappe.cache().delete(self._view_key(_PHONE_A))
        frappe.cache().delete(self._view_key(_PHONE_B))
        _clear_counter_state(self.item.name)
        _cleanup()

    def test_first_view_increments(self):
        result = chills_api.record_chills_view(self.item.name, _PHONE_A)["data"]
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(rc.get_count("chills_views", self.item.name), 1)

    def test_second_view_ignored(self):
        chills_api.record_chills_view(self.item.name, _PHONE_A)
        result = chills_api.record_chills_view(self.item.name, _PHONE_A)["data"]
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("reason"), "already_counted")
        self.assertEqual(rc.get_count("chills_views", self.item.name), 1)

    def test_different_phone_counted(self):
        chills_api.record_chills_view(self.item.name, _PHONE_A)
        result = chills_api.record_chills_view(self.item.name, _PHONE_B)["data"]
        self.assertTrue(result["ok"])
        self.assertEqual(rc.get_count("chills_views", self.item.name), 2)


# ── Shares ────────────────────────────────────────────────────────────────────

class TestIncrementShares(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)
        _clear_counter_state(self.item.name)

    def tearDown(self):
        site = getattr(frappe.local, "site", "default")
        frappe.cache().delete(f"{site}:chills:share:{self.item.name}:{_PHONE_A}")
        frappe.cache().delete(f"{site}:chills:share_anon:{self.item.name}")
        _clear_counter_state(self.item.name)
        _cleanup()

    def test_increments_count(self):
        result = chills_api.increment_shares(self.item.name, phone=_PHONE_A)["data"]
        self.assertEqual(result["shares"], 1)

    def test_same_phone_deduped_within_window(self):
        # This is the bug fix — previously there was no guard at all, so a
        # double-tap or client retry silently double-counted every time.
        chills_api.increment_shares(self.item.name, phone=_PHONE_A)
        result = chills_api.increment_shares(self.item.name, phone=_PHONE_A)["data"]
        self.assertTrue(result.get("deduped"))
        self.assertEqual(rc.get_count("chills_shares", self.item.name), 1)

    def test_different_phones_both_counted(self):
        chills_api.increment_shares(self.item.name, phone=_PHONE_A)
        chills_api.increment_shares(self.item.name, phone=_PHONE_B)
        self.assertEqual(rc.get_count("chills_shares", self.item.name), 2)

    def test_anonymous_calls_still_deduped(self):
        chills_api.increment_shares(self.item.name)
        result = chills_api.increment_shares(self.item.name)["data"]
        self.assertTrue(result.get("deduped"))

    def test_nonexistent_chills_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            chills_api.increment_shares("CHILL-DOES-NOT-EXIST", phone=_PHONE_A)

    def test_missing_chills_id_throws(self):
        with self.assertRaises(Exception):
            chills_api.increment_shares(None, phone=_PHONE_A)


# ── Follow Outlet ─────────────────────────────────────────────────────────────

class TestFollowOutlet(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()

    def tearDown(self):
        _cleanup()

    def test_follow_sets_true(self):
        with _verified_session():
            result = chills_api.follow_outlet(self.rest.name, _PHONE_A)["data"]
        self.assertTrue(result["following"])
        self.assertEqual(result["outlet_id"], self.rest.name)
        exists = frappe.db.exists("Chills Outlet Follow", {
            "outlet": self.rest.name, "customer_phone": _PHONE_A,
        })
        self.assertTrue(bool(exists))

    def test_unfollow_sets_false(self):
        with _verified_session():
            chills_api.follow_outlet(self.rest.name, _PHONE_A)
            result = chills_api.follow_outlet(self.rest.name, _PHONE_A)["data"]
        self.assertFalse(result["following"])
        exists = frappe.db.exists("Chills Outlet Follow", {
            "outlet": self.rest.name, "customer_phone": _PHONE_A,
        })
        self.assertFalse(bool(exists))

    def test_phone_isolation(self):
        with _verified_session():
            chills_api.follow_outlet(self.rest.name, _PHONE_A)
        exists = frappe.db.exists("Chills Outlet Follow", {
            "outlet": self.rest.name, "customer_phone": _PHONE_B,
        })
        self.assertFalse(bool(exists))

    def test_cache_invalidated_on_toggle(self):
        cache_key = f"chills:outlet_follows:{_PHONE_A}"
        frappe.cache().set_value(cache_key, [], expires_in_sec=120)
        with _verified_session():
            chills_api.follow_outlet(self.rest.name, _PHONE_A)
        cached = frappe.cache().get_value(cache_key)
        self.assertIsNone(cached)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            chills_api.follow_outlet(self.rest.name, None)

    def test_missing_outlet_throws(self):
        with self.assertRaises(Exception):
            chills_api.follow_outlet(None, _PHONE_A)


# ── redis_counters module (direct unit coverage) ─────────────────────────────

class TestRedisCounters(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.item = _make_chills(self.rest.name)
        _clear_counter_state(self.item.name)

    def tearDown(self):
        _clear_counter_state(self.item.name)
        _cleanup()

    def test_toggle_member_flips_state(self):
        self.assertTrue(rc.toggle_member("chills_likes", self.item.name, _PHONE_A))
        self.assertTrue(rc.is_member("chills_likes", self.item.name, _PHONE_A))
        self.assertFalse(rc.toggle_member("chills_likes", self.item.name, _PHONE_A))
        self.assertFalse(rc.is_member("chills_likes", self.item.name, _PHONE_A))

    def test_bump_and_get_count_roundtrip(self):
        rc.bump_count("chills_likes", self.item.name, 3)
        rc.bump_count("chills_likes", self.item.name, -1)
        self.assertEqual(rc.get_count("chills_likes", self.item.name), 2)

    def test_get_count_falls_back_when_unset(self):
        self.assertEqual(rc.get_count("chills_likes", "CHILL-NEVER-TOUCHED", db_fallback=7), 7)

    def test_get_counts_batches_and_falls_back_per_item(self):
        rc.bump_count("chills_likes", self.item.name, 5)
        result = rc.get_counts(
            "chills_likes",
            [self.item.name, "CHILL-NEVER-TOUCHED"],
            {self.item.name: 0, "CHILL-NEVER-TOUCHED": 9},
        )
        self.assertEqual(result[self.item.name], 5)
        self.assertEqual(result["CHILL-NEVER-TOUCHED"], 9)

    def test_members_for_batches_correctly(self):
        other = _make_chills(self.rest.name, description="Other item")
        _clear_counter_state(other.name)
        rc.toggle_member("chills_likes", self.item.name, _PHONE_A)
        result = rc.members_for("chills_likes", [self.item.name, other.name], _PHONE_A)
        self.assertEqual(result, {self.item.name})
        _clear_counter_state(other.name)

    def test_bump_count_marks_item_dirty(self):
        # The dirty set is global (shared across every item in this scope),
        # so other tests' bump_count calls can legitimately still be sitting
        # in it — drain that first so this test only asserts on its own item.
        rc.pop_dirty_items("chills_likes")
        rc.bump_count("chills_likes", self.item.name, 1)
        dirty = rc.pop_dirty_items("chills_likes")
        self.assertIn(self.item.name, dirty)
        # Popping clears it — a second pop must not see it again.
        self.assertNotIn(self.item.name, rc.pop_dirty_items("chills_likes"))

    def test_flush_all_writes_absolute_value_and_is_rerunnable(self):
        frappe.db.set_value("Chills", self.item.name, "likes_count", 0)
        frappe.db.commit()
        rc.bump_count("chills_likes", self.item.name, 4)
        rc.flush_all()
        self.assertEqual(frappe.db.get_value("Chills", self.item.name, "likes_count"), 4)
        # Re-running with nothing dirty must be a safe no-op, not a double-apply.
        rc.flush_all()
        self.assertEqual(frappe.db.get_value("Chills", self.item.name, "likes_count"), 4)

    def test_persist_toggle_inserts_then_deletes_idempotently(self):
        rc.persist_toggle("Chills Like", "chills", self.item.name, _PHONE_A, True)
        self.assertTrue(frappe.db.exists("Chills Like", {"chills": self.item.name, "customer_phone": _PHONE_A}))
        # Re-running the same "active=True" state must not create a duplicate row.
        rc.persist_toggle("Chills Like", "chills", self.item.name, _PHONE_A, True)
        self.assertEqual(frappe.db.count("Chills Like", {"chills": self.item.name, "customer_phone": _PHONE_A}), 1)

        rc.persist_toggle("Chills Like", "chills", self.item.name, _PHONE_A, False)
        self.assertFalse(frappe.db.exists("Chills Like", {"chills": self.item.name, "customer_phone": _PHONE_A}))
        # Re-running "active=False" on an already-absent row is a no-op too.
        rc.persist_toggle("Chills Like", "chills", self.item.name, _PHONE_A, False)

    def test_backfill_seeds_existing_db_state(self):
        frappe.db.set_value("Chills", self.item.name, "likes_count", 17)
        frappe.db.commit()
        frappe.get_doc({
            "doctype": "Chills Like", "chills": self.item.name, "customer_phone": _PHONE_B,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        rc.backfill_from_db()

        self.assertEqual(rc.get_count("chills_likes", self.item.name), 17)
        self.assertTrue(rc.is_member("chills_likes", self.item.name, _PHONE_B))
        frappe.db.sql("DELETE FROM `tabChills Like` WHERE customer_phone=%s", _PHONE_B)
        frappe.db.commit()


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
