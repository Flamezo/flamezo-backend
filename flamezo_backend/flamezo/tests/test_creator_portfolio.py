# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for api/creator_portfolio.py — slug generation, visibility gates,
stale follower detection, rate-limited view recording, QR code, and all
creator self-serve endpoints.
"""

import base64
import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, today

from flamezo_backend.flamezo.api import creator_portfolio as portfolio_api
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-PORTFOLIO"
_PHONE = "9300000899"


def _cleanup():
    frappe.db.sql(
        "DELETE FROM `tabCreator Portfolio View` WHERE creator IN "
        "(SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)",
        _PHONE,
    )
    frappe.db.sql(
        "DELETE FROM `tabCreator Portfolio` WHERE creator IN "
        "(SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)",
        _PHONE,
    )
    frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
    frappe.db.commit()


def _make_creator(display_name="PortfolioTester", status="approved", meta_followers=12000,
                  follower_count_last_synced=None):
    creator = frappe.get_doc({
        "doctype": "Flamezo Creator",
        "customer_phone": _PHONE,
        "display_name": display_name,
        "instagram_handle": "portfolio_tester",
        "meta_followers": meta_followers,
        "meta_avg_views": 3000,
        "follower_count_last_synced": follower_count_last_synced or today(),
        "city": "Surat",
        "status": status,
    })
    creator.insert(ignore_permissions=True)
    frappe.db.commit()
    return creator


class TestSlugGeneration(unittest.TestCase):
    """_slugify and _make_unique_slug behave correctly."""

    def test_slugify_basic(self):
        self.assertEqual(portfolio_api._slugify("Dhyey Mehta"), "dhyeymehta")

    def test_slugify_special_chars(self):
        # "Café" normalises to "cafe", "Co" to "co" → "cafeco"
        self.assertEqual(portfolio_api._slugify("Café & Co."), "cafeco")

    def test_slugify_empty_fallback(self):
        self.assertEqual(portfolio_api._slugify("@@@"), "creator")

    def test_slugify_truncation(self):
        long = "a" * 50
        self.assertEqual(len(portfolio_api._slugify(long)), 40)

    def test_make_unique_slug_no_collision(self):
        # _make_unique_slug enforces a 40-char cap; the input is 41 chars, so truncated
        slug = portfolio_api._make_unique_slug("totally-unique-test-slug-xyz-no-collision")
        self.assertEqual(slug, "totally-unique-test-slug-xyz-no-collisio")

    def test_make_unique_slug_collision_adds_suffix(self):
        _cleanup()
        creator = _make_creator()
        # Create a portfolio directly with the target slug to force a collision
        portfolio_api._ensure_portfolio(creator.name, "testslugcreator")
        first_slug = frappe.db.get_value("Creator Portfolio", {"creator": creator.name}, "slug")
        # Now requesting the same base slug should get -2
        next_slug = portfolio_api._make_unique_slug(first_slug)
        self.assertTrue(next_slug.endswith("-2") or next_slug != first_slug)
        _cleanup()


class TestEnsurePortfolio(unittest.TestCase):
    def setUp(self):
        _cleanup()
        self.creator = _make_creator()

    def tearDown(self):
        _cleanup()

    def test_creates_portfolio_on_first_call(self):
        name = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)
        self.assertTrue(frappe.db.exists("Creator Portfolio", name))

    def test_idempotent_second_call(self):
        n1 = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)
        n2 = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)
        self.assertEqual(n1, n2)

    def test_default_visibility_is_unlisted(self):
        name = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)
        vis = frappe.db.get_value("Creator Portfolio", name, "visibility")
        self.assertEqual(vis, "unlisted")


class TestGetPublicPortfolio(unittest.TestCase):
    def setUp(self):
        _cleanup()
        self.creator = _make_creator()
        self.portfolio_name = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)
        # Set to public so the endpoint doesn't 404
        frappe.db.set_value("Creator Portfolio", self.portfolio_name, "visibility", "public")
        frappe.db.commit()
        self.slug = frappe.db.get_value("Creator Portfolio", self.portfolio_name, "slug")

        self._session_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio.has_active_customer_session",
            return_value=True,
        )
        self._session_patch.start()
        self._badge_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio._compute_badge_details",
            return_value=("rising", {}),
        )
        self._badge_patch.start()
        self._weekly_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio._accepted_this_week_count",
            return_value=0,
        )
        self._weekly_patch.start()
        self._record_view_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio._record_view",
        )
        self._record_view_patch.start()

    def tearDown(self):
        self._session_patch.stop()
        self._badge_patch.stop()
        self._weekly_patch.stop()
        self._record_view_patch.stop()
        _cleanup()

    def test_returns_identity_block(self):
        result = portfolio_api.get_public_portfolio(self.slug)
        self.assertTrue(result["success"])
        d = result["data"]
        self.assertEqual(d["display_name"], "PortfolioTester")
        self.assertEqual(d["slug"], self.slug)

    def test_returns_verified_reach_block(self):
        result = portfolio_api.get_public_portfolio(self.slug)
        reach = result["data"]["verified_reach"]
        self.assertEqual(reach["meta_followers"], 12000)
        self.assertFalse(reach["is_stale"])

    def test_private_portfolio_raises(self):
        frappe.db.set_value("Creator Portfolio", self.portfolio_name, "visibility", "private")
        frappe.db.commit()
        with self.assertRaises(frappe.PermissionError):
            portfolio_api.get_public_portfolio(self.slug)

    def test_unknown_slug_raises(self):
        with self.assertRaises(frappe.DoesNotExistError):
            portfolio_api.get_public_portfolio("totally-nonexistent-slug-zzz")

    def test_unapproved_creator_raises(self):
        frappe.db.set_value("Flamezo Creator", self.creator.name, "status", "pending")
        frappe.db.commit()
        with self.assertRaises(frappe.DoesNotExistError):
            portfolio_api.get_public_portfolio(self.slug)


class TestStaleFollowers(unittest.TestCase):
    def setUp(self):
        _cleanup()
        stale_date = add_days(today(), -35)
        self.creator = _make_creator(follower_count_last_synced=stale_date)
        self.portfolio_name = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)
        frappe.db.set_value("Creator Portfolio", self.portfolio_name, "visibility", "public")
        frappe.db.commit()
        self.slug = frappe.db.get_value("Creator Portfolio", self.portfolio_name, "slug")

        self._badge_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio._compute_badge_details",
            return_value=("rising", {}),
        )
        self._badge_patch.start()
        self._weekly_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio._accepted_this_week_count",
            return_value=0,
        )
        self._weekly_patch.start()
        self._record_view_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio._record_view",
        )
        self._record_view_patch.start()

    def tearDown(self):
        self._badge_patch.stop()
        self._weekly_patch.stop()
        self._record_view_patch.stop()
        _cleanup()

    def test_stale_flag_set_when_sync_old(self):
        result = portfolio_api.get_public_portfolio(self.slug)
        reach = result["data"]["verified_reach"]
        self.assertTrue(reach["is_stale"])
        # follower count is still returned (not hidden)
        self.assertEqual(reach["meta_followers"], 12000)

    def test_sync_age_days_accurate(self):
        result = portfolio_api.get_public_portfolio(self.slug)
        age = result["data"]["verified_reach"]["sync_age_days"]
        self.assertGreaterEqual(age, 35)


class TestSelfServeGetAndUpdate(unittest.TestCase):
    def setUp(self):
        _cleanup()
        self.creator = _make_creator()
        self._session_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio.has_active_customer_session",
            return_value=True,
        )
        self._session_patch.start()

    def tearDown(self):
        self._session_patch.stop()
        _cleanup()

    def test_get_my_portfolio_creates_and_returns(self):
        result = portfolio_api.get_my_portfolio(_PHONE)
        self.assertTrue(result["success"])
        d = result["data"]
        self.assertIn("slug", d)
        self.assertIn("portfolio_url", d)
        self.assertEqual(d["visibility"], "unlisted")

    def test_update_headline(self):
        portfolio_api.get_my_portfolio(_PHONE)  # ensure creation
        result = portfolio_api.update_my_portfolio(_PHONE, headline="Food reviewer in Surat")
        self.assertTrue(result["success"])
        pname = frappe.db.get_value("Creator Portfolio", {"creator": self.creator.name}, "name")
        self.assertEqual(frappe.db.get_value("Creator Portfolio", pname, "headline"), "Food reviewer in Surat")

    def test_update_visibility_public(self):
        portfolio_api.get_my_portfolio(_PHONE)
        result = portfolio_api.update_my_portfolio(_PHONE, visibility="public")
        self.assertTrue(result["success"])
        pname = frappe.db.get_value("Creator Portfolio", {"creator": self.creator.name}, "name")
        self.assertEqual(frappe.db.get_value("Creator Portfolio", pname, "visibility"), "public")

    def test_update_invalid_visibility_raises(self):
        portfolio_api.get_my_portfolio(_PHONE)
        with self.assertRaises(frappe.ValidationError):
            portfolio_api.update_my_portfolio(_PHONE, visibility="hidden")

    def test_update_featured_posts_validates_type(self):
        portfolio_api.get_my_portfolio(_PHONE)
        result = portfolio_api.update_my_portfolio(
            _PHONE,
            featured_posts_json=json.dumps([
                {"type": "native_chills", "id": "TEST-CHILL-1"},
                {"type": "bad_type", "id": "x"},  # should be stripped
            ]),
        )
        self.assertTrue(result["success"])
        pname = frappe.db.get_value("Creator Portfolio", {"creator": self.creator.name}, "name")
        pinned = json.loads(frappe.db.get_value("Creator Portfolio", pname, "featured_posts_json") or "[]")
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0]["type"], "native_chills")

    def test_update_featured_posts_capped_at_6(self):
        portfolio_api.get_my_portfolio(_PHONE)
        posts = [{"type": "native_chills", "id": f"C-{i}"} for i in range(10)]
        portfolio_api.update_my_portfolio(_PHONE, featured_posts_json=json.dumps(posts))
        pname = frappe.db.get_value("Creator Portfolio", {"creator": self.creator.name}, "name")
        pinned = json.loads(frappe.db.get_value("Creator Portfolio", pname, "featured_posts_json") or "[]")
        self.assertLessEqual(len(pinned), 6)

    def test_headline_truncated_at_200(self):
        long_headline = "x" * 300
        portfolio_api.get_my_portfolio(_PHONE)
        portfolio_api.update_my_portfolio(_PHONE, headline=long_headline)
        pname = frappe.db.get_value("Creator Portfolio", {"creator": self.creator.name}, "name")
        saved = frappe.db.get_value("Creator Portfolio", pname, "headline")
        self.assertLessEqual(len(saved), 200)

    def test_unauthenticated_raises(self):
        with patch(
            "flamezo_backend.flamezo.api.creator_portfolio.has_active_customer_session",
            return_value=False,
        ):
            with self.assertRaises(frappe.AuthenticationError):
                portfolio_api.get_my_portfolio(_PHONE)

    def test_non_creator_raises(self):
        # Phone has a session but no Flamezo Creator record
        frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
        frappe.db.commit()
        with self.assertRaises(frappe.DoesNotExistError):
            portfolio_api.get_my_portfolio(_PHONE)


class TestViewRecording(unittest.TestCase):
    def setUp(self):
        _cleanup()
        self.creator = _make_creator()
        self.portfolio_name = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)

    def tearDown(self):
        _cleanup()

    def test_record_view_inserts_row(self):
        before = frappe.db.count("Creator Portfolio View", {"creator": self.creator.name})
        with patch("frappe.request", None):
            portfolio_api._record_view(self.creator.name)
        after = frappe.db.count("Creator Portfolio View", {"creator": self.creator.name})
        self.assertEqual(after, before + 1)

    def test_rate_limit_blocks_excess_views(self):
        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_key"
        mock_cache.get_value.return_value = portfolio_api._VIEW_HOURLY_CAP_PER_IP  # already at cap
        with patch("frappe.cache", return_value=mock_cache), patch("frappe.request", None):
            before = frappe.db.count("Creator Portfolio View", {"creator": self.creator.name})
            portfolio_api._record_view(self.creator.name)
            after = frappe.db.count("Creator Portfolio View", {"creator": self.creator.name})
        self.assertEqual(before, after)  # blocked

    def test_record_view_never_crashes_page(self):
        """Even a totally broken cache must not raise."""
        with patch("frappe.cache", side_effect=Exception("redis down")), patch("frappe.request", None):
            try:
                portfolio_api._record_view(self.creator.name)
            except Exception:
                self.fail("_record_view raised outside its own try/except")


class TestPortfolioAnalytics(unittest.TestCase):
    def setUp(self):
        _cleanup()
        self.creator = _make_creator()
        self._session_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio.has_active_customer_session",
            return_value=True,
        )
        self._session_patch.start()

    def tearDown(self):
        self._session_patch.stop()
        _cleanup()

    def _insert_view(self, source="direct", days_ago=0):
        frappe.get_doc({
            "doctype": "Creator Portfolio View",
            "creator": self.creator.name,
            "view_date": add_days(today(), -days_ago),
            "source": source,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

    def test_analytics_counts_by_source(self):
        self._insert_view("qr")
        self._insert_view("link")
        self._insert_view("qr")
        result = portfolio_api.get_my_portfolio_analytics(_PHONE)
        self.assertTrue(result["success"])
        by_source = result["data"]["by_source"]
        self.assertEqual(by_source.get("qr"), 2)
        self.assertEqual(by_source.get("link"), 1)

    def test_analytics_excludes_views_older_than_30_days(self):
        self._insert_view("direct", days_ago=5)
        self._insert_view("direct", days_ago=35)  # should be excluded
        result = portfolio_api.get_my_portfolio_analytics(_PHONE)
        self.assertEqual(result["data"]["total_views_30d"], 1)

    def test_analytics_daily_trend_sorted(self):
        self._insert_view("direct", days_ago=2)
        self._insert_view("direct", days_ago=1)
        result = portfolio_api.get_my_portfolio_analytics(_PHONE)
        dates = [r["date"] for r in result["data"]["daily_trend"]]
        self.assertEqual(dates, sorted(dates))


class TestQRCode(unittest.TestCase):
    def setUp(self):
        _cleanup()
        self.creator = _make_creator()
        self._session_patch = patch(
            "flamezo_backend.flamezo.api.creator_portfolio.has_active_customer_session",
            return_value=True,
        )
        self._session_patch.start()

    def tearDown(self):
        self._session_patch.stop()
        _cleanup()

    def test_qr_code_returns_valid_base64_png(self):
        result = portfolio_api.get_my_qr_code(_PHONE)
        self.assertTrue(result["success"])
        qr_b64 = result["data"]["qr_code_base64"]
        # Decode and check it's a PNG
        raw = base64.b64decode(qr_b64)
        self.assertTrue(raw[:4] == b"\x89PNG", "QR code is not a valid PNG")

    def test_qr_code_url_contains_source_param(self):
        result = portfolio_api.get_my_qr_code(_PHONE)
        url = result["data"]["portfolio_url"]
        self.assertIn("source=qr", url)

    def test_qr_code_url_contains_slug(self):
        result = portfolio_api.get_my_qr_code(_PHONE)
        slug = result["data"]["slug"]
        self.assertIn(slug, result["data"]["portfolio_url"])

    def test_qr_code_url_format(self):
        result = portfolio_api.get_my_qr_code(_PHONE)
        url = result["data"]["portfolio_url"]
        self.assertTrue(url.startswith("https://flamezo.in/c/"))


class TestReportPortfolio(unittest.TestCase):
    def setUp(self):
        _cleanup()
        self.creator = _make_creator()
        self.portfolio_name = portfolio_api._ensure_portfolio(self.creator.name, self.creator.display_name)
        self.slug = frappe.db.get_value("Creator Portfolio", self.portfolio_name, "slug")

    def tearDown(self):
        _cleanup()

    def test_report_increments_count(self):
        before = frappe.db.get_value("Creator Portfolio", self.portfolio_name, "report_count") or 0
        # bypass IP rate limit by patching cache to return None
        mock_cache = MagicMock()
        mock_cache.make_key.return_value = "test_report_key"
        mock_cache.get_value.return_value = None
        with patch("frappe.cache", return_value=mock_cache), patch("frappe.request", None):
            result = portfolio_api.report_portfolio(self.slug)
        self.assertTrue(result["success"])
        after = frappe.db.get_value("Creator Portfolio", self.portfolio_name, "report_count") or 0
        self.assertEqual(after, before + 1)

    def test_report_nonexistent_slug_raises(self):
        with self.assertRaises(frappe.DoesNotExistError):
            portfolio_api.report_portfolio("does-not-exist-zzz")


if __name__ == "__main__":
    unittest.main()
