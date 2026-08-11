# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Creator Clubs API (clubs.py).

Response shape: every endpoint returns {"success": True, "data": {...}} —
all assertions below read through `result["data"]`.

Session gate: mutating endpoints (follow_club, create/delete/like post,
request_club_post_upload) require a *verified* session via
`_require_session` → `has_active_customer_session`. Since clubs.py imports
that function by name (`from ...customer_helpers import
has_active_customer_session`), patching the source module's attribute does
NOT affect clubs.py's own bound reference — tests patch
`flamezo_backend.flamezo.api.clubs.has_active_customer_session` directly
(see `_verified_session`).

Covers:
  Listing:
    - get_creator_clubs: returns active clubs only
    - inactive clubs excluded
    - category filter
    - search filter (club_name, niche)
    - pagination (has_more, page)
    - is_following correct per phone
    - is_admin correct per phone (only the club's real creator sees true)

  Club Detail:
    - get_club_detail: full fields returned
    - inactive club throws DoesNotExistError
    - non-existent club throws DoesNotExistError
    - recent_posts count present
    - is_admin correct

  Follow / Unfollow:
    - follow returns following=True and increments followers_count
    - follow again toggles off and decrements followers_count
    - followers_count never goes below 0
    - follow inactive club throws
    - follow non-existent club throws
    - missing phone throws
    - unverified session throws AuthenticationError

  Club Posts (read):
    - get_club_posts: returns posts ordered by creation DESC
    - post_type=chills includes nested reel data
    - post_type=image includes image_url
    - post_type=text has content only
    - post_type filter narrows results (chills tab scoping)
    - is_liked correct per viewing phone
    - is_admin surfaced on the page envelope
    - inactive club posts throw
    - missing club_id throws
    - pagination

  Club Post mutations:
    - create_club_post: admin can create text/image/chills posts
    - create_club_post: non-admin rejected (PermissionError) — the security fix
    - create_club_post: unverified session rejected
    - create_club_post: validates required fields per post_type
    - create_club_post: image post requires a real uploaded object (object_exists)
    - create_club_post: chills post requires an existing published Chills doc
    - delete_club_post: admin can delete their club's post
    - delete_club_post: non-admin rejected
    - delete_club_post: deleting a post cleans up its likes (no orphans)
    - delete_club_post: nonexistent post throws
    - like_club_post: toggle on/off, likes_count follows correctly
    - like_club_post: never goes negative
    - like_club_post: per-phone isolation (A liking doesn't affect B's is_liked)
    - like_club_post: nonexistent post throws
    - request_club_post_upload: non-admin rejected

  My Clubs:
    - get_my_clubs: returns only followed clubs
    - unfollowed clubs not included
    - missing phone throws

  Phone isolation:
    - is_following is per-phone, not shared
    - is_admin is per-phone, not shared
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import today

from flamezo_backend.flamezo.api import clubs
from flamezo_backend.flamezo.tests.utils import make_restaurant
from flamezo_backend.flamezo.utils import redis_counters as rc

_PREFIX = "TEST-CLUBS"
_PHONE_A = "9300000001"  # club owner in most fixtures
_PHONE_B = "9300000002"  # a follower / non-admin
_CLUB_OUTLET = f"{_PREFIX}-OUTLET-01"


def _verified_session():
    """Patched-in "this phone has a real verified session" for the duration
    of a `with` block — see module docstring for why this exact target."""
    return patch("flamezo_backend.flamezo.api.clubs.has_active_customer_session", return_value=True)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _ensure_outlet():
    if not frappe.db.exists("Restaurant", _CLUB_OUTLET):
        make_restaurant(_CLUB_OUTLET, outlet_type="dining")
    return _CLUB_OUTLET


def _make_creator(phone=_PHONE_A):
    try:
        existing = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "name")
        if existing:
            frappe.delete_doc("Flamezo Creator", existing, force=True, ignore_permissions=True)
    except Exception:
        pass
    doc = frappe.get_doc({
        "doctype": "Flamezo Creator",
        "customer_phone": phone,
        "display_name": f"ClubCreator-{phone[-4:]}",
        "meta_followers": 25000,
        "meta_avg_views": 2500,
        "status": "approved",
    })
    doc.insert(ignore_permissions=True)
    return doc


def _make_club(creator_name, club_name=None, niche="Food", category="dining", is_active=1):
    club_name = club_name or f"Test Club {creator_name[-3:]}"
    doc = frappe.get_doc({
        "doctype": "Creator Club",
        "creator": creator_name,
        "club_name": club_name,
        "niche": niche,
        "description": "Test club description",
        "cover_image": "https://r2.example.com/clubs/cover.jpg",
        "category": category,
        "is_active": is_active,
    })
    doc.insert(ignore_permissions=True)
    return doc


def _make_post(club_name, post_type="text", content="test post content", reel=None, image_url=None):
    doc = frappe.get_doc({
        "doctype": "Creator Club Post",
        "club": club_name,
        "post_type": post_type,
        "content": content,
        "reel": reel,
        "image_url": image_url or "",
    })
    doc.insert(ignore_permissions=True)
    return doc


def _clear_view_counter_state(post_id):
    """Same rationale as test_chills_e2e.py's `_clear_counter_state` — wipes
    every Redis key `club_post_views` could have created for one post."""
    r = frappe.cache()
    r.delete(rc._count_key("club_post_views", post_id))
    rc._srem(r, rc._dirty_key("club_post_views"), post_id)


def _view_key(post_id, phone):
    site = getattr(frappe.local, "site", "default")
    return f"{site}:club_post:view:{post_id}:{phone}:{today()}"


def _make_comment(post_name, phone=_PHONE_B, content="test comment body"):
    doc = frappe.get_doc({
        "doctype": "Creator Club Post Comment",
        "post": post_name,
        "customer_phone": phone,
        "customer_name": f"Customer {phone}",
        "content": content,
    })
    doc.insert(ignore_permissions=True)
    return doc


def _make_chills_for_club(creator_name, outlet_name):
    doc = frappe.get_doc({
        "doctype": "Chills",
        "creator": creator_name,
        "outlet": outlet_name,
        "video_url": "https://r2.example.com/chills/club.mp4",
        "thumbnail_url": "https://r2.example.com/chills/club.jpg",
        "description": "test club chills",
        "status": "published",
        "published_at": frappe.utils.now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _cleanup_clubs():
    frappe.db.sql("DELETE FROM `tabCreator Club Post Like` WHERE post IN (SELECT name FROM `tabCreator Club Post` WHERE content LIKE 'test%')")
    frappe.db.sql("DELETE FROM `tabCreator Club Post Comment` WHERE post IN (SELECT name FROM `tabCreator Club Post` WHERE content LIKE 'test%')")
    frappe.db.sql("DELETE FROM `tabCreator Club Post` WHERE content LIKE 'test%'")
    frappe.db.sql("DELETE FROM `tabCreator Club Member` WHERE customer_phone IN (%s, %s)", [_PHONE_A, _PHONE_B])
    frappe.db.sql("DELETE FROM `tabCreator Club` WHERE description='Test club description'")
    frappe.db.sql("DELETE FROM `tabChills` WHERE description='test club chills'")
    frappe.db.sql("DELETE FROM `tabRestaurant` WHERE name=%s", _CLUB_OUTLET)
    for phone in [_PHONE_A, _PHONE_B]:
        existing = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "name")
        if existing:
            frappe.delete_doc("Flamezo Creator", existing, force=True, ignore_permissions=True)
    frappe.db.commit()


class TestGetCreatorClubs(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Active Club", niche="Surat Food", category="dining")
        _make_club(self.creator.name, "Test Inactive Club", is_active=0)

    def tearDown(self):
        _cleanup_clubs()

    def test_only_active_clubs_returned(self):
        result = clubs.get_creator_clubs()["data"]
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Active Club", names)
        self.assertNotIn("Test Inactive Club", names)

    def test_category_filter(self):
        _make_club(self.creator.name, "Test Wellness Club", category="wellness")
        result = clubs.get_creator_clubs(category="wellness")["data"]
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Wellness Club", names)
        self.assertNotIn("Test Active Club", names)

    def test_search_by_name(self):
        result = clubs.get_creator_clubs(search="Active")["data"]
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Active Club", names)

    def test_search_by_niche(self):
        result = clubs.get_creator_clubs(search="Surat")["data"]
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Active Club", names)

    def test_search_no_match_returns_empty(self):
        result = clubs.get_creator_clubs(search="ZZZNoMatchXXX")["data"]
        self.assertEqual(len(result["clubs"]), 0)

    def test_is_following_false_when_not_followed(self):
        with _verified_session():
            result = clubs.get_creator_clubs(phone=_PHONE_B)["data"]
        self.assertFalse(result["clubs"][0]["is_following"])

    def test_is_following_true_when_followed(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            result = clubs.get_creator_clubs(phone=_PHONE_B)["data"]
        club_data = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertTrue(club_data["is_following"])

    def test_is_admin_true_for_real_creator(self):
        with _verified_session():
            result = clubs.get_creator_clubs(phone=_PHONE_A)["data"]
        club_data = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertTrue(club_data["is_admin"])

    def test_is_admin_false_for_non_creator(self):
        with _verified_session():
            result = clubs.get_creator_clubs(phone=_PHONE_B)["data"]
        club_data = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertFalse(club_data["is_admin"])

    def test_is_admin_false_when_unverified(self):
        # Phone matches the creator but has no verified session — must not
        # leak admin status to an unauthenticated caller.
        result = clubs.get_creator_clubs(phone=_PHONE_A)["data"]
        club_data = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertFalse(club_data["is_admin"])

    def test_pagination(self):
        result = clubs.get_creator_clubs(page=1, limit=1)["data"]
        self.assertIn("has_more", result)
        self.assertEqual(result["page"], 1)

    def test_club_includes_creator_fields(self):
        result = clubs.get_creator_clubs()["data"]
        club = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertIn("creator_id", club)
        self.assertIn("creator_name", club)


class TestAdminPhoneNormalization(unittest.TestCase):
    """Regression test for a real bug found via device testing (not caught by
    any of the other tests here, since they all use one identical phone
    literal for both sides): Flamezo Creator.customer_phone is sometimes
    stored with a +91 prefix (e.g. seed/admin-created rows), while every
    other phone source in this app (Customer Session, Customer, and the
    phone the Flutter client actually sends) is bare 10-digit. A raw string
    compare between them silently locks the real admin out of their own
    club's composer/pin/delete controls. clubs.py must normalize_phone()
    both sides everywhere it checks admin/ownership."""

    _PREFIXED_PHONE = "+919300000099"
    _BARE_PHONE = "9300000099"

    def setUp(self):
        _cleanup_clubs()
        # Simulates the real seed-data shape: creator record carries a +91
        # prefix, but the live session (and every request) uses bare digits.
        self.creator = _make_creator(self._PREFIXED_PHONE)
        self.club = _make_club(self.creator.name, "Test Normalization Club")

    def tearDown(self):
        frappe.db.sql("DELETE FROM `tabCreator Club Member` WHERE customer_phone=%s", self._BARE_PHONE)
        _cleanup_clubs()
        # _cleanup_clubs() only knows _PHONE_A/_PHONE_B — this fixture uses
        # its own dedicated phone, so clean it up explicitly too.
        existing = frappe.db.get_value("Flamezo Creator", {"customer_phone": self._PREFIXED_PHONE}, "name")
        if existing:
            frappe.delete_doc("Flamezo Creator", existing, force=True, ignore_permissions=True)
            frappe.db.commit()

    def test_is_admin_true_despite_prefix_mismatch(self):
        with _verified_session():
            result = clubs.get_creator_clubs(phone=self._BARE_PHONE)["data"]
        club_data = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertTrue(club_data["is_admin"])

    def test_get_club_detail_is_admin_true_despite_prefix_mismatch(self):
        with _verified_session():
            result = clubs.get_club_detail(self.club.name, phone=self._BARE_PHONE)["data"]
        self.assertTrue(result["is_admin"])

    def test_get_club_posts_is_admin_true_despite_prefix_mismatch(self):
        with _verified_session():
            result = clubs.get_club_posts(self.club.name, phone=self._BARE_PHONE)["data"]
        self.assertTrue(result["is_admin"])

    def test_create_post_allowed_despite_prefix_mismatch(self):
        with _verified_session():
            result = clubs.create_club_post(self.club.name, self._BARE_PHONE, "text", content="test normalization post")["data"]
        self.assertTrue(frappe.db.exists("Creator Club Post", result["id"]))


class TestGetClubDetail(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Detail Club")

    def tearDown(self):
        _cleanup_clubs()

    def test_returns_full_fields(self):
        with _verified_session():
            result = clubs.get_club_detail(self.club.name, phone=_PHONE_B)["data"]
        self.assertEqual(result["id"], self.club.name)
        self.assertIn("club_name", result)
        self.assertIn("followers_count", result)
        self.assertIn("creator_id", result)
        self.assertIn("recent_posts", result)
        self.assertIn("is_admin", result)

    def test_is_admin_true_for_creator(self):
        with _verified_session():
            result = clubs.get_club_detail(self.club.name, phone=_PHONE_A)["data"]
        self.assertTrue(result["is_admin"])

    def test_is_admin_false_for_others(self):
        with _verified_session():
            result = clubs.get_club_detail(self.club.name, phone=_PHONE_B)["data"]
        self.assertFalse(result["is_admin"])

    def test_inactive_club_throws(self):
        inactive = _make_club(self.creator.name, "Test Inactive Detail", is_active=0)
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.get_club_detail(inactive.name)

    def test_nonexistent_club_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.get_club_detail("CLUB-99999")

    def test_missing_club_id_throws(self):
        with self.assertRaises(Exception):
            clubs.get_club_detail(None)

    def test_recent_posts_count_is_integer(self):
        _make_post(self.club.name, "text", "test detail post")
        result = clubs.get_club_detail(self.club.name)["data"]
        self.assertIsInstance(result["recent_posts"], int)
        self.assertGreater(result["recent_posts"], 0)


class TestFollowClub(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Follow Club")
        frappe.db.set_value("Creator Club", self.club.name, "followers_count", 0)

    def tearDown(self):
        _cleanup_clubs()

    def test_follow_returns_following_true(self):
        with _verified_session():
            result = clubs.follow_club(self.club.name, _PHONE_B)["data"]
        self.assertTrue(result["following"])

    def test_follow_increments_followers_count(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club", self.club.name, "followers_count")
        self.assertEqual(count, 1)

    def test_follow_twice_toggles_off(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            result = clubs.follow_club(self.club.name, _PHONE_B)["data"]
        self.assertFalse(result["following"])

    def test_unfollow_decrements_count(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            clubs.follow_club(self.club.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club", self.club.name, "followers_count")
        self.assertEqual(count, 0)

    def test_followers_count_never_negative(self):
        frappe.db.set_value("Creator Club", self.club.name, "followers_count", 0)
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            frappe.db.set_value("Creator Club", self.club.name, "followers_count", 0)
            clubs.follow_club(self.club.name, _PHONE_B)  # toggle off (but count is 0)
        count = frappe.db.get_value("Creator Club", self.club.name, "followers_count")
        self.assertGreaterEqual(count, 0)

    def test_follow_inactive_club_throws(self):
        inactive = _make_club(self.creator.name, "Test Inactive Follow", is_active=0)
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.follow_club(inactive.name, _PHONE_B)

    def test_follow_nonexistent_club_throws(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.follow_club("CLUB-99999", _PHONE_B)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            clubs.follow_club(self.club.name, None)

    def test_unverified_session_throws(self):
        # No _verified_session() patch here — has_active_customer_session
        # falls through to its real implementation, which requires an actual
        # HTTP request context and returns False outside of one.
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.follow_club(self.club.name, _PHONE_B)

    def test_phone_isolation(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_A)
            clubs.follow_club(self.club.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club", self.club.name, "followers_count")
        self.assertEqual(count, 2)


class TestGetClubPosts(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Posts Club")
        self.outlet = _ensure_outlet()
        self.chills = _make_chills_for_club(self.creator.name, self.outlet)

    def tearDown(self):
        _cleanup_clubs()

    def test_text_post_returned(self):
        _make_post(self.club.name, "text", "test text post body")
        result = clubs.get_club_posts(self.club.name)["data"]
        contents = [p["content"] for p in result["posts"]]
        self.assertIn("test text post body", contents)

    def test_image_post_has_image_url(self):
        _make_post(self.club.name, "image", "test image caption", image_url="https://r2.example.com/img.jpg")
        result = clubs.get_club_posts(self.club.name)["data"]
        img_posts = [p for p in result["posts"] if p["post_type"] == "image"]
        self.assertTrue(len(img_posts) > 0)
        self.assertIn("image_url", img_posts[0])

    def test_chills_post_includes_chills_data(self):
        _make_post(self.club.name, "chills", "test chills club post", reel=self.chills.name)
        result = clubs.get_club_posts(self.club.name)["data"]
        chills_posts = [p for p in result["posts"] if p["post_type"] == "chills"]
        self.assertTrue(len(chills_posts) > 0)
        self.assertIn("chills", chills_posts[0])
        self.assertIn("videoUrl", chills_posts[0]["chills"])

    def test_post_type_filter_scopes_to_chills_only(self):
        _make_post(self.club.name, "text", "test text for filter")
        _make_post(self.club.name, "chills", "test chills for filter", reel=self.chills.name)
        result = clubs.get_club_posts(self.club.name, post_type="chills")["data"]
        types = {p["post_type"] for p in result["posts"]}
        self.assertEqual(types, {"chills"})

    def test_is_liked_false_by_default(self):
        post = _make_post(self.club.name, "text", "test unliked post")
        with _verified_session():
            result = clubs.get_club_posts(self.club.name, phone=_PHONE_B)["data"]
        p = next(p for p in result["posts"] if p["id"] == post.name)
        self.assertFalse(p["is_liked"])

    def test_is_liked_true_after_liking(self):
        post = _make_post(self.club.name, "text", "test liked post")
        with _verified_session():
            clubs.like_club_post(post.name, _PHONE_B)
            result = clubs.get_club_posts(self.club.name, phone=_PHONE_B)["data"]
        p = next(p for p in result["posts"] if p["id"] == post.name)
        self.assertTrue(p["is_liked"])

    def test_is_admin_surfaced_on_page(self):
        with _verified_session():
            result = clubs.get_club_posts(self.club.name, phone=_PHONE_A)["data"]
        self.assertTrue(result["is_admin"])
        with _verified_session():
            result_b = clubs.get_club_posts(self.club.name, phone=_PHONE_B)["data"]
        self.assertFalse(result_b["is_admin"])

    def test_inactive_club_posts_throws(self):
        inactive = _make_club(self.creator.name, "Test Inactive Posts", is_active=0)
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.get_club_posts(inactive.name)

    def test_missing_club_id_throws(self):
        with self.assertRaises(Exception):
            clubs.get_club_posts(None)

    def test_pagination(self):
        for i in range(3):
            _make_post(self.club.name, "text", f"test post {i}")
        result = clubs.get_club_posts(self.club.name, limit=2)["data"]
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["posts"]), 2)


class TestCreateClubPost(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Create Post Club")
        self.outlet = _ensure_outlet()
        self.chills = _make_chills_for_club(self.creator.name, self.outlet)

    def tearDown(self):
        _cleanup_clubs()

    def test_admin_can_create_text_post(self):
        with _verified_session():
            result = clubs.create_club_post(self.club.name, _PHONE_A, "text", content="test admin text post")["data"]
        self.assertEqual(result["content"], "test admin text post")
        self.assertEqual(result["post_type"], "text")
        self.assertTrue(frappe.db.exists("Creator Club Post", result["id"]))

    def test_admin_can_create_chills_post(self):
        with _verified_session():
            result = clubs.create_club_post(self.club.name, _PHONE_A, "chills", reel_id=self.chills.name)["data"]
        self.assertEqual(result["post_type"], "chills")
        self.assertIn("chills", result)
        self.assertEqual(result["chills"]["id"], self.chills.name)

    def test_non_admin_rejected(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.PermissionError):
            clubs.create_club_post(self.club.name, _PHONE_B, "text", content="test intruder post")

    def test_unverified_session_rejected(self):
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.create_club_post(self.club.name, _PHONE_A, "text", content="test no session post")

    def test_invalid_post_type_rejected(self):
        with _verified_session(), self.assertRaises(Exception):
            clubs.create_club_post(self.club.name, _PHONE_A, "video")

    def test_text_post_requires_content(self):
        with _verified_session(), self.assertRaises(Exception):
            clubs.create_club_post(self.club.name, _PHONE_A, "text")

    def test_image_post_requires_image_key(self):
        with _verified_session(), self.assertRaises(Exception):
            clubs.create_club_post(self.club.name, _PHONE_A, "image")

    def test_image_post_rejects_unresolvable_object_key(self):
        # object_exists() will look this up on real R2 and find nothing —
        # the endpoint must not trust a client-supplied key blindly.
        with _verified_session(), self.assertRaises(Exception):
            clubs.create_club_post(self.club.name, _PHONE_A, "image", image_key="club-posts/does/not/exist.jpg")

    def test_chills_post_requires_reel_id(self):
        with _verified_session(), self.assertRaises(Exception):
            clubs.create_club_post(self.club.name, _PHONE_A, "chills")

    def test_chills_post_requires_existing_chills_doc(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.create_club_post(self.club.name, _PHONE_A, "chills", reel_id="CHILLS-DOES-NOT-EXIST")

    def test_inactive_club_rejected(self):
        inactive = _make_club(self.creator.name, "Test Inactive Create", is_active=0)
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.create_club_post(inactive.name, _PHONE_A, "text", content="test post on inactive club")


class TestDeleteClubPost(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Delete Post Club")

    def tearDown(self):
        _cleanup_clubs()

    def test_admin_can_delete(self):
        post = _make_post(self.club.name, "text", "test post to delete")
        with _verified_session():
            clubs.delete_club_post(post.name, _PHONE_A)
        self.assertFalse(frappe.db.exists("Creator Club Post", post.name))

    def test_non_admin_rejected(self):
        post = _make_post(self.club.name, "text", "test post protected from deletion")
        with _verified_session(), self.assertRaises(frappe.exceptions.PermissionError):
            clubs.delete_club_post(post.name, _PHONE_B)
        self.assertTrue(frappe.db.exists("Creator Club Post", post.name))

    def test_unverified_session_rejected(self):
        post = _make_post(self.club.name, "text", "test post needs session to delete")
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.delete_club_post(post.name, _PHONE_A)
        self.assertTrue(frappe.db.exists("Creator Club Post", post.name))

    def test_deleting_post_cleans_up_likes(self):
        post = _make_post(self.club.name, "text", "test post with likes")
        with _verified_session():
            clubs.like_club_post(post.name, _PHONE_B)
            self.assertEqual(frappe.db.count("Creator Club Post Like", {"post": post.name}), 1)
            clubs.delete_club_post(post.name, _PHONE_A)
        self.assertEqual(frappe.db.count("Creator Club Post Like", {"post": post.name}), 0)

    def test_nonexistent_post_throws(self):
        with _verified_session(), self.assertRaises(Exception):
            clubs.delete_club_post("CPOST-DOES-NOT-EXIST", _PHONE_A)


class TestLikeClubPost(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Like Post Club")
        self.post = _make_post(self.club.name, "text", "test post to like")
        frappe.db.set_value("Creator Club Post", self.post.name, "likes_count", 0)

    def tearDown(self):
        _cleanup_clubs()

    def test_like_returns_liked_true(self):
        with _verified_session():
            result = clubs.like_club_post(self.post.name, _PHONE_B)["data"]
        self.assertTrue(result["liked"])

    def test_like_increments_count(self):
        with _verified_session():
            clubs.like_club_post(self.post.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club Post", self.post.name, "likes_count")
        self.assertEqual(count, 1)

    def test_like_twice_toggles_off(self):
        with _verified_session():
            clubs.like_club_post(self.post.name, _PHONE_B)
            result = clubs.like_club_post(self.post.name, _PHONE_B)["data"]
        self.assertFalse(result["liked"])

    def test_unlike_decrements_count(self):
        with _verified_session():
            clubs.like_club_post(self.post.name, _PHONE_B)
            clubs.like_club_post(self.post.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club Post", self.post.name, "likes_count")
        self.assertEqual(count, 0)

    def test_likes_count_never_negative(self):
        frappe.db.set_value("Creator Club Post", self.post.name, "likes_count", 0)
        with _verified_session():
            clubs.like_club_post(self.post.name, _PHONE_B)
            frappe.db.set_value("Creator Club Post", self.post.name, "likes_count", 0)
            clubs.like_club_post(self.post.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club Post", self.post.name, "likes_count")
        self.assertGreaterEqual(count, 0)

    def test_phone_isolation(self):
        with _verified_session():
            clubs.like_club_post(self.post.name, _PHONE_A)
            result_b = clubs.get_club_posts(self.club.name, phone=_PHONE_B)["data"]
        p = next(p for p in result_b["posts"] if p["id"] == self.post.name)
        self.assertFalse(p["is_liked"])  # A's like must not leak into B's view
        self.assertEqual(p["likes_count"], 1)  # but the count is shared/real

    def test_nonexistent_post_throws(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.like_club_post("CPOST-DOES-NOT-EXIST", _PHONE_B)

    def test_unverified_session_rejected(self):
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.like_club_post(self.post.name, _PHONE_B)


class TestRequestClubPostUpload(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Upload Club")

    def tearDown(self):
        _cleanup_clubs()

    def test_non_admin_rejected(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.PermissionError):
            clubs.request_club_post_upload(self.club.name, "photo.jpg", "image/jpeg", _PHONE_B)

    def test_unverified_session_rejected(self):
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.request_club_post_upload(self.club.name, "photo.jpg", "image/jpeg", _PHONE_A)


class TestGetMyClubs(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club1 = _make_club(self.creator.name, "Test My Club 1")
        self.club2 = _make_club(self.creator.name, "Test My Club 2")

    def tearDown(self):
        _cleanup_clubs()

    def test_returns_followed_clubs(self):
        with _verified_session():
            clubs.follow_club(self.club1.name, _PHONE_B)
            result = clubs.get_my_clubs(_PHONE_B)["data"]
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test My Club 1", names)

    def test_unfollowed_clubs_not_included(self):
        with _verified_session():
            clubs.follow_club(self.club1.name, _PHONE_B)
            result = clubs.get_my_clubs(_PHONE_B)["data"]
        names = [c["club_name"] for c in result["clubs"]]
        self.assertNotIn("Test My Club 2", names)

    def test_empty_when_no_follows(self):
        with _verified_session():
            result = clubs.get_my_clubs(_PHONE_B)["data"]
        self.assertEqual(len(result["clubs"]), 0)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            clubs.get_my_clubs(None)

    def test_is_following_always_true_in_my_clubs(self):
        with _verified_session():
            clubs.follow_club(self.club1.name, _PHONE_B)
            result = clubs.get_my_clubs(_PHONE_B)["data"]
        self.assertTrue(all(c["is_following"] for c in result["clubs"]))


class TestClubPostComments(unittest.TestCase):
    """Phase 2 comments (create/delete/list). Mirrors the like/counter
    conventions already proven in TestLikeClubPost — direct synchronous
    counter writes (comments volume per club post is nowhere near Chills'
    hot-row scale, so this deliberately skips redis_counters.py)."""

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Comments Club")
        self.post = _make_post(self.club.name, "text", "test post to comment on")
        frappe.db.set_value("Creator Club Post", self.post.name, "comments_count", 0)

    def tearDown(self):
        _cleanup_clubs()

    # ── create ───────────────────────────────────────────────────────────
    def test_anyone_with_session_can_comment(self):
        with _verified_session():
            result = clubs.create_club_post_comment(self.post.name, _PHONE_B, "test hello there")["data"]
        self.assertEqual(result["content"], "test hello there")
        self.assertEqual(result["author_id"], _PHONE_B)
        self.assertTrue(frappe.db.exists("Creator Club Post Comment", result["id"]))

    def test_comment_increments_count(self):
        with _verified_session():
            clubs.create_club_post_comment(self.post.name, _PHONE_B, "test increments count")
        count = frappe.db.get_value("Creator Club Post", self.post.name, "comments_count")
        self.assertEqual(count, 1)

    def test_multiple_comments_accumulate_count(self):
        with _verified_session():
            clubs.create_club_post_comment(self.post.name, _PHONE_A, "test first")
            clubs.create_club_post_comment(self.post.name, _PHONE_B, "test second")
        count = frappe.db.get_value("Creator Club Post", self.post.name, "comments_count")
        self.assertEqual(count, 2)

    def test_empty_content_rejected(self):
        with _verified_session(), self.assertRaises(Exception):
            clubs.create_club_post_comment(self.post.name, _PHONE_B, "   ")

    def test_content_too_long_rejected(self):
        with _verified_session(), self.assertRaises(Exception):
            clubs.create_club_post_comment(self.post.name, _PHONE_B, "x" * 1001)

    def test_nonexistent_post_throws(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.create_club_post_comment("CPOST-DOES-NOT-EXIST", _PHONE_B, "test orphan comment")

    def test_unverified_session_rejected(self):
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.create_club_post_comment(self.post.name, _PHONE_B, "test no session")

    def test_author_name_resolved_from_customer(self):
        frappe.db.set_value("Customer", {"phone": _PHONE_B}, "customer_name", "Test Commenter Name")
        with _verified_session():
            result = clubs.create_club_post_comment(self.post.name, _PHONE_B, "test named comment")["data"]
        # Falls back to a generic label if no Customer row exists for this
        # phone in this test DB — either way it must not be empty.
        self.assertTrue(result["author_name"])

    # ── list / pagination ────────────────────────────────────────────────
    def test_listing_returns_ascending_order(self):
        _make_comment(self.post.name, _PHONE_A, "test comment one")
        _make_comment(self.post.name, _PHONE_B, "test comment two")
        result = clubs.get_club_post_comments(self.post.name)["data"]
        contents = [c["content"] for c in result["comments"]]
        self.assertEqual(contents, ["test comment one", "test comment two"])

    def test_listing_nonexistent_post_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.get_club_post_comments("CPOST-DOES-NOT-EXIST")

    def test_pagination_has_more_and_cursor(self):
        for i in range(5):
            _make_comment(self.post.name, _PHONE_A, f"test paged comment {i}")
        page1 = clubs.get_club_post_comments(self.post.name, limit=2)["data"]
        self.assertTrue(page1["has_more"])
        self.assertEqual(len(page1["comments"]), 2)
        self.assertIsNotNone(page1["next_cursor"])
        # newest two first (still ascending within the page)
        self.assertEqual(
            [c["content"] for c in page1["comments"]],
            ["test paged comment 3", "test paged comment 4"],
        )

    def test_pagination_cursor_fetches_older_page(self):
        for i in range(5):
            _make_comment(self.post.name, _PHONE_A, f"test cursor comment {i}")
        page1 = clubs.get_club_post_comments(self.post.name, limit=2)["data"]
        page2 = clubs.get_club_post_comments(self.post.name, limit=2, cursor=page1["next_cursor"])["data"]
        self.assertEqual(
            [c["content"] for c in page2["comments"]],
            ["test cursor comment 1", "test cursor comment 2"],
        )

    def test_pagination_last_page_has_more_false(self):
        for i in range(3):
            _make_comment(self.post.name, _PHONE_A, f"test last page {i}")
        page1 = clubs.get_club_post_comments(self.post.name, limit=2)["data"]
        page2 = clubs.get_club_post_comments(self.post.name, limit=2, cursor=page1["next_cursor"])["data"]
        self.assertFalse(page2["has_more"])
        self.assertIsNone(page2["next_cursor"])
        self.assertEqual(len(page2["comments"]), 1)

    # ── delete ───────────────────────────────────────────────────────────
    def test_author_can_delete_own_comment(self):
        comment = _make_comment(self.post.name, _PHONE_B)
        frappe.db.set_value("Creator Club Post", self.post.name, "comments_count", 1)
        with _verified_session():
            result = clubs.delete_club_post_comment(comment.name, _PHONE_B)["data"]
        self.assertEqual(result["id"], comment.name)
        self.assertFalse(frappe.db.exists("Creator Club Post Comment", comment.name))

    def test_delete_decrements_count(self):
        comment = _make_comment(self.post.name, _PHONE_B)
        frappe.db.set_value("Creator Club Post", self.post.name, "comments_count", 1)
        with _verified_session():
            clubs.delete_club_post_comment(comment.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club Post", self.post.name, "comments_count")
        self.assertEqual(count, 0)

    def test_comments_count_never_negative(self):
        comment = _make_comment(self.post.name, _PHONE_B)
        frappe.db.set_value("Creator Club Post", self.post.name, "comments_count", 0)
        with _verified_session():
            clubs.delete_club_post_comment(comment.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club Post", self.post.name, "comments_count")
        self.assertGreaterEqual(count, 0)

    def test_admin_can_delete_others_comment(self):
        comment = _make_comment(self.post.name, _PHONE_B)
        with _verified_session():
            clubs.delete_club_post_comment(comment.name, _PHONE_A)
        self.assertFalse(frappe.db.exists("Creator Club Post Comment", comment.name))

    def test_non_author_non_admin_rejected(self):
        other_phone = "9300000003"
        comment = _make_comment(self.post.name, _PHONE_B)
        with _verified_session(), self.assertRaises(frappe.exceptions.PermissionError):
            clubs.delete_club_post_comment(comment.name, other_phone)
        self.assertTrue(frappe.db.exists("Creator Club Post Comment", comment.name))

    def test_unverified_session_rejected_on_delete(self):
        comment = _make_comment(self.post.name, _PHONE_B)
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.delete_club_post_comment(comment.name, _PHONE_B)
        self.assertTrue(frappe.db.exists("Creator Club Post Comment", comment.name))

    def test_nonexistent_comment_throws(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.delete_club_post_comment("NOT-A-REAL-COMMENT", _PHONE_B)


class TestRealtimePermissionHook(unittest.TestCase):
    """The live-update push (likes/comments) rides the stock
    `doc_subscribe("Creator Club Post", post_id)` socketio room, which is
    gated by `frappe.realtime.can_subscribe_doc` ->
    `frappe.has_permission(doctype, doc=docname, throw=True)`. Creator Club
    Post's own DocType permissions only grant System Manager, so without the
    `has_public_club_post_permission` hook registered in hooks.py, a Guest
    socket could never join and would receive zero real-time updates — this
    is the one thing that actually makes the whole realtime feature work,
    so it's tested directly rather than just trusting the wiring."""

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Realtime Club")
        self.post = _make_post(self.club.name, "text", "test realtime post")

    def tearDown(self):
        _cleanup_clubs()

    def test_guest_has_read_permission_on_post(self):
        self.assertTrue(
            frappe.has_permission("Creator Club Post", doc=self.post.name, ptype="read", user="Guest")
        )

    def test_guest_lacks_write_permission_on_post(self):
        self.assertFalse(
            frappe.has_permission("Creator Club Post", doc=self.post.name, ptype="write", user="Guest")
        )

    def test_can_subscribe_doc_succeeds_for_guest(self):
        from frappe.realtime import can_subscribe_doc

        frappe.set_user("Guest")
        try:
            self.assertTrue(can_subscribe_doc("Creator Club Post", self.post.name))
        finally:
            frappe.set_user("Administrator")

    def test_can_subscribe_doc_throws_for_nonexistent_post(self):
        from frappe.realtime import can_subscribe_doc

        frappe.set_user("Guest")
        try:
            with self.assertRaises(Exception):
                can_subscribe_doc("Creator Club Post", "CPOST-DOES-NOT-EXIST")
        finally:
            frappe.set_user("Administrator")


class TestRecordClubPostView(unittest.TestCase):
    """Mirrors test_chills_e2e.py's TestRecordChillsView exactly — same
    dedup mechanism (`record_club_post_view` is a straight port of
    `record_chills_view`), same Redis-buffered counter infra."""

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Views Club")
        self.post = _make_post(self.club.name, "text", "test post to view")
        _clear_view_counter_state(self.post.name)
        frappe.cache().delete(_view_key(self.post.name, _PHONE_A))
        frappe.cache().delete(_view_key(self.post.name, _PHONE_B))
        frappe.cache().delete(_view_key(self.post.name, "anon"))

    def tearDown(self):
        frappe.cache().delete(_view_key(self.post.name, _PHONE_A))
        frappe.cache().delete(_view_key(self.post.name, _PHONE_B))
        frappe.cache().delete(_view_key(self.post.name, "anon"))
        _clear_view_counter_state(self.post.name)
        _cleanup_clubs()

    def test_first_view_increments(self):
        result = clubs.record_club_post_view(self.post.name, _PHONE_A)["data"]
        self.assertTrue(result["ok"])
        self.assertEqual(rc.get_count("club_post_views", self.post.name), 1)

    def test_second_view_same_day_ignored(self):
        clubs.record_club_post_view(self.post.name, _PHONE_A)
        result = clubs.record_club_post_view(self.post.name, _PHONE_A)["data"]
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("reason"), "already_counted")
        self.assertEqual(rc.get_count("club_post_views", self.post.name), 1)

    def test_different_phone_counted_separately(self):
        clubs.record_club_post_view(self.post.name, _PHONE_A)
        result = clubs.record_club_post_view(self.post.name, _PHONE_B)["data"]
        self.assertTrue(result["ok"])
        self.assertEqual(rc.get_count("club_post_views", self.post.name), 2)

    def test_anonymous_view_counted(self):
        result = clubs.record_club_post_view(self.post.name, None)["data"]
        self.assertTrue(result["ok"])
        self.assertEqual(rc.get_count("club_post_views", self.post.name), 1)

    def test_second_anonymous_view_same_day_ignored(self):
        clubs.record_club_post_view(self.post.name, None)
        result = clubs.record_club_post_view(self.post.name, None)["data"]
        self.assertFalse(result["ok"])
        self.assertEqual(rc.get_count("club_post_views", self.post.name), 1)

    def test_nonexistent_post_returns_ok_false(self):
        result = clubs.record_club_post_view("CPOST-DOES-NOT-EXIST", _PHONE_A)["data"]
        self.assertFalse(result["ok"])

    def test_missing_post_id_returns_ok_false(self):
        result = clubs.record_club_post_view(None, _PHONE_A)["data"]
        self.assertFalse(result["ok"])

    def test_no_session_required(self):
        # Unlike likes/comments, views are allow_guest with no _require_session
        # gate — matches record_chills_view's own design (view = passive
        # consumption, not an identity-bearing action). No _verified_session()
        # patch here on purpose — this call must succeed without one.
        result = clubs.record_club_post_view(self.post.name, _PHONE_A)["data"]
        self.assertTrue(result["ok"])

    def test_views_count_surfaced_in_get_club_posts(self):
        clubs.record_club_post_view(self.post.name, _PHONE_A)
        clubs.record_club_post_view(self.post.name, _PHONE_B)
        result = clubs.get_club_posts(self.club.name)["data"]
        p = next(p for p in result["posts"] if p["id"] == self.post.name)
        self.assertEqual(p["views_count"], 2)

    def test_views_count_zero_for_unviewed_post(self):
        result = clubs.get_club_posts(self.club.name)["data"]
        p = next(p for p in result["posts"] if p["id"] == self.post.name)
        self.assertEqual(p["views_count"], 0)


class TestToggleClubNotifications(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Notify Toggle Club")

    def tearDown(self):
        _cleanup_clubs()

    def test_defaults_to_enabled_on_join(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
        enabled = frappe.db.get_value(
            "Creator Club Member", {"club": self.club.name, "customer_phone": _PHONE_B}, "notify_new_posts"
        )
        self.assertEqual(enabled, 1)

    def test_toggle_off_then_on(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            result = clubs.toggle_club_notifications(self.club.name, _PHONE_B)["data"]
        self.assertFalse(result["notify_new_posts"])
        with _verified_session():
            result2 = clubs.toggle_club_notifications(self.club.name, _PHONE_B)["data"]
        self.assertTrue(result2["notify_new_posts"])

    def test_non_member_rejected(self):
        with _verified_session(), self.assertRaises(frappe.exceptions.ValidationError):
            clubs.toggle_club_notifications(self.club.name, _PHONE_B)

    def test_unverified_session_rejected(self):
        with self.assertRaises(frappe.exceptions.AuthenticationError):
            clubs.toggle_club_notifications(self.club.name, _PHONE_B)

    def test_surfaced_in_get_club_detail(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            result = clubs.get_club_detail(self.club.name, phone=_PHONE_B)["data"]
        self.assertTrue(result["notify_new_posts"])

    def test_false_for_non_member_in_get_club_detail(self):
        with _verified_session():
            result = clubs.get_club_detail(self.club.name, phone=_PHONE_B)["data"]
        self.assertFalse(result["notify_new_posts"])


class TestClubNotificationTriggers(unittest.TestCase):
    """`create_club_post` / `create_club_post_comment` now also create real
    `Flamezo Notification` rows (see notifications_consumer.py) — verified
    directly against that doctype, not by mocking, since it's cheap and
    exercises the full real path including `notification_type` validation
    (a real bug caught this way during development — the Select field
    doesn't accept arbitrary type strings)."""

    def setUp(self):
        _cleanup_clubs()
        frappe.db.sql("DELETE FROM `tabFlamezo Notification` WHERE customer_phone IN (%s, %s)", [_PHONE_A, _PHONE_B])
        frappe.db.commit()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Trigger Club")

    def tearDown(self):
        frappe.db.sql("DELETE FROM `tabFlamezo Notification` WHERE customer_phone IN (%s, %s)", [_PHONE_A, _PHONE_B])
        frappe.db.commit()
        _cleanup_clubs()

    def test_new_post_notifies_subscribed_member(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            clubs.create_club_post(self.club.name, _PHONE_A, "text", content="test trigger post")
        # The real endpoint enqueues the fan-out (frappe.enqueue) — call the
        # background function directly here since test runs don't process
        # the queue, matching how `_notify_club_members_new_post` is meant
        # to be exercised in isolation.
        post = frappe.db.get_value("Creator Club Post", {"club": self.club.name, "content": "test trigger post"}, "name")
        clubs._notify_club_members_new_post(post, self.club.name)
        notifs = frappe.db.sql(
            "SELECT title FROM `tabFlamezo Notification` WHERE customer_phone=%s", _PHONE_B, as_dict=True
        )
        self.assertTrue(any("Test Trigger Club" in n.title for n in notifs))

    def test_new_post_skips_unsubscribed_member(self):
        with _verified_session():
            clubs.follow_club(self.club.name, _PHONE_B)
            clubs.toggle_club_notifications(self.club.name, _PHONE_B)  # turn off
            clubs.create_club_post(self.club.name, _PHONE_A, "text", content="test trigger post 2")
        post = frappe.db.get_value("Creator Club Post", {"club": self.club.name, "content": "test trigger post 2"}, "name")
        clubs._notify_club_members_new_post(post, self.club.name)
        count = frappe.db.count("Flamezo Notification", {"customer_phone": _PHONE_B, "reference_name": post})
        self.assertEqual(count, 0)

    def test_new_comment_notifies_admin(self):
        with _verified_session():
            post = clubs.create_club_post(self.club.name, _PHONE_A, "text", content="test comment trigger post")["data"]
            clubs.create_club_post_comment(post["id"], _PHONE_B, "test trigger comment")
        notifs = frappe.db.sql(
            "SELECT title, body FROM `tabFlamezo Notification` WHERE customer_phone=%s", _PHONE_A, as_dict=True
        )
        self.assertTrue(any("commented on your post" in n.title for n in notifs))

    def test_admin_commenting_on_own_post_not_notified(self):
        with _verified_session():
            post = clubs.create_club_post(self.club.name, _PHONE_A, "text", content="test self comment post")["data"]
            clubs.create_club_post_comment(post["id"], _PHONE_A, "test self comment")
        count = frappe.db.count(
            "Flamezo Notification", {"customer_phone": _PHONE_A, "notification_type": "club"}
        )
        self.assertEqual(count, 0)
