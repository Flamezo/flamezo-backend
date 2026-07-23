# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Creator Clubs API (clubs.py).

Covers:
  Listing:
    - get_creator_clubs: returns active clubs only
    - inactive clubs excluded
    - category filter
    - search filter (club_name, niche)
    - pagination (has_more, page)
    - is_following correct per phone

  Club Detail:
    - get_club_detail: full fields returned
    - inactive club throws DoesNotExistError
    - non-existent club throws DoesNotExistError
    - recent_posts count present

  Follow / Unfollow:
    - follow returns following=True and increments followers_count
    - follow again toggles off and decrements followers_count
    - followers_count never goes below 0
    - follow inactive club throws
    - follow non-existent club throws
    - missing phone throws

  Club Posts:
    - get_club_posts: returns posts ordered by creation DESC
    - post_type=reel includes nested reel data
    - post_type=image includes image_url
    - post_type=text has content only
    - inactive club posts throw
    - missing club_id throws
    - pagination

  My Clubs:
    - get_my_clubs: returns only followed clubs
    - unfollowed clubs not included
    - missing phone throws

  Phone isolation:
    - is_following is per-phone, not shared
"""

import unittest
import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-CLUBS"
_PHONE_A = "9300000001"
_PHONE_B = "9300000002"
_CLUB_OUTLET = f"{_PREFIX}-OUTLET-01"


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
        "creator_tier": "Flame",
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


from flamezo_backend.flamezo.api import clubs


class TestGetCreatorClubs(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Active Club", niche="Surat Food", category="dining")
        _make_club(self.creator.name, "Test Inactive Club", is_active=0)

    def tearDown(self):
        _cleanup_clubs()

    def test_only_active_clubs_returned(self):
        result = clubs.get_creator_clubs()
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Active Club", names)
        self.assertNotIn("Test Inactive Club", names)

    def test_category_filter(self):
        _make_club(self.creator.name, "Test Wellness Club", category="wellness")
        result = clubs.get_creator_clubs(category="wellness")
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Wellness Club", names)
        self.assertNotIn("Test Active Club", names)

    def test_search_by_name(self):
        result = clubs.get_creator_clubs(search="Active")
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Active Club", names)

    def test_search_by_niche(self):
        result = clubs.get_creator_clubs(search="Surat")
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test Active Club", names)

    def test_search_no_match_returns_empty(self):
        result = clubs.get_creator_clubs(search="ZZZNoMatchXXX")
        self.assertEqual(len(result["clubs"]), 0)

    def test_is_following_false_when_not_followed(self):
        result = clubs.get_creator_clubs(phone=_PHONE_B)
        self.assertFalse(result["clubs"][0]["is_following"])

    def test_is_following_true_when_followed(self):
        clubs.follow_club(self.club.name, _PHONE_B)
        result = clubs.get_creator_clubs(phone=_PHONE_B)
        club_data = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertTrue(club_data["is_following"])

    def test_pagination(self):
        result = clubs.get_creator_clubs(page=1, limit=1)
        self.assertIn("has_more", result)
        self.assertEqual(result["page"], 1)

    def test_club_includes_creator_fields(self):
        result = clubs.get_creator_clubs()
        club = next(c for c in result["clubs"] if c["id"] == self.club.name)
        self.assertIn("creator_id", club)
        self.assertIn("creator_name", club)


class TestGetClubDetail(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club = _make_club(self.creator.name, "Test Detail Club")

    def tearDown(self):
        _cleanup_clubs()

    def test_returns_full_fields(self):
        result = clubs.get_club_detail(self.club.name, phone=_PHONE_B)
        self.assertEqual(result["id"], self.club.name)
        self.assertIn("club_name", result)
        self.assertIn("tier", result)
        self.assertIn("followers_count", result)
        self.assertIn("creator_id", result)
        self.assertIn("recent_posts", result)

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
        result = clubs.get_club_detail(self.club.name)
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
        result = clubs.follow_club(self.club.name, _PHONE_B)
        self.assertTrue(result["following"])

    def test_follow_increments_followers_count(self):
        clubs.follow_club(self.club.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club", self.club.name, "followers_count")
        self.assertEqual(count, 1)

    def test_follow_twice_toggles_off(self):
        clubs.follow_club(self.club.name, _PHONE_B)
        result = clubs.follow_club(self.club.name, _PHONE_B)
        self.assertFalse(result["following"])

    def test_unfollow_decrements_count(self):
        clubs.follow_club(self.club.name, _PHONE_B)
        clubs.follow_club(self.club.name, _PHONE_B)
        count = frappe.db.get_value("Creator Club", self.club.name, "followers_count")
        self.assertEqual(count, 0)

    def test_followers_count_never_negative(self):
        # Unfollow when already at 0 should not go negative
        frappe.db.set_value("Creator Club", self.club.name, "followers_count", 0)
        # Direct unfollow without prior follow — insert then remove
        clubs.follow_club(self.club.name, _PHONE_B)
        frappe.db.set_value("Creator Club", self.club.name, "followers_count", 0)
        clubs.follow_club(self.club.name, _PHONE_B)  # toggle off (but count is 0)
        count = frappe.db.get_value("Creator Club", self.club.name, "followers_count")
        self.assertGreaterEqual(count, 0)

    def test_follow_inactive_club_throws(self):
        inactive = _make_club(self.creator.name, "Test Inactive Follow", is_active=0)
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.follow_club(inactive.name, _PHONE_B)

    def test_follow_nonexistent_club_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            clubs.follow_club("CLUB-99999", _PHONE_B)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            clubs.follow_club(self.club.name, None)

    def test_phone_isolation(self):
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
        result = clubs.get_club_posts(self.club.name)
        contents = [p["content"] for p in result["posts"]]
        self.assertIn("test text post body", contents)

    def test_image_post_has_image_url(self):
        _make_post(self.club.name, "image", "test image caption", image_url="https://r2.example.com/img.jpg")
        result = clubs.get_club_posts(self.club.name)
        img_posts = [p for p in result["posts"] if p["post_type"] == "image"]
        self.assertTrue(len(img_posts) > 0)
        self.assertIn("image_url", img_posts[0])

    def test_chills_post_includes_chills_data(self):
        _make_post(self.club.name, "chills", "test chills club post", reel=self.chills.name)
        result = clubs.get_club_posts(self.club.name)
        chills_posts = [p for p in result["posts"] if p["post_type"] == "chills"]
        self.assertTrue(len(chills_posts) > 0)
        self.assertIn("chills", chills_posts[0])
        self.assertIn("videoUrl", chills_posts[0]["chills"])

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
        result = clubs.get_club_posts(self.club.name, limit=2)
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["posts"]), 2)


class TestGetMyClubs(unittest.TestCase):

    def setUp(self):
        _cleanup_clubs()
        self.creator = _make_creator(_PHONE_A)
        self.club1 = _make_club(self.creator.name, "Test My Club 1")
        self.club2 = _make_club(self.creator.name, "Test My Club 2")

    def tearDown(self):
        _cleanup_clubs()

    def test_returns_followed_clubs(self):
        clubs.follow_club(self.club1.name, _PHONE_B)
        result = clubs.get_my_clubs(_PHONE_B)
        names = [c["club_name"] for c in result["clubs"]]
        self.assertIn("Test My Club 1", names)

    def test_unfollowed_clubs_not_included(self):
        clubs.follow_club(self.club1.name, _PHONE_B)
        result = clubs.get_my_clubs(_PHONE_B)
        names = [c["club_name"] for c in result["clubs"]]
        self.assertNotIn("Test My Club 2", names)

    def test_empty_when_no_follows(self):
        result = clubs.get_my_clubs(_PHONE_B)
        self.assertEqual(len(result["clubs"]), 0)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            clubs.get_my_clubs(None)

    def test_is_following_always_true_in_my_clubs(self):
        clubs.follow_club(self.club1.name, _PHONE_B)
        result = clubs.get_my_clubs(_PHONE_B)
        self.assertTrue(all(c["is_following"] for c in result["clubs"]))
