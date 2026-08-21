# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for api/creator_analytics.py — the creator-facing "Instagram
Insights"-style dashboard (Chills + Club Talks aggregate stats, own-content
lists, follower trend). Mirrors test_creator_rewards_api.py's own-creator
auth pattern; mirrors test_chills_e2e.py's Chills fixture shape.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import today, add_days, now_datetime

from flamezo_backend.flamezo.api import creator_analytics as analytics_api
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PHONE = "9300000901"
_OTHER_PHONE = "9300000902"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCreator Follower Snapshot` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabCreator Follow` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabCreator Club Post` WHERE club IN (SELECT name FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s)))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabChills` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s)", (_PHONE, _OTHER_PHONE))
	frappe.db.commit()


def _verified_session():
	return patch("flamezo_backend.flamezo.api.creator_analytics.has_active_customer_session", return_value=True)


def _make_chills(outlet, creator, views=0, likes=0, saves=0, shares=0, status="published"):
	doc = frappe.get_doc({
		"doctype": "Chills",
		"outlet": outlet,
		"creator": creator,
		"video_url": "https://r2.example.com/chills/test.mp4",
		"thumbnail_url": "https://r2.example.com/chills/test.jpg",
		"description": "Test chills video",
		"audio": "Original sound",
		"status": status,
		"published_at": now_datetime() if status == "published" else None,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.set_value("Chills", doc.name, {
		"views_count": views, "likes_count": likes, "saves_count": saves, "shares_count": shares,
	})
	frappe.db.commit()
	return frappe.get_doc("Chills", doc.name)


class TestCreatorAnalyticsApi(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = "TEST-CREATOR-ANALYTICS-OUTLET"
		if not frappe.db.exists("Restaurant", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining")

	def setUp(self):
		_cleanup()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "AnalyticsTestCreator",
			"status": "approved",
			"meta_followers": 500,
		})
		self.creator.insert(ignore_permissions=True)
		self.club = frappe.get_doc({
			"doctype": "Creator Club",
			"creator": self.creator.name,
			"club_name": "Analytics Test Club",
			"niche": "Food",
			"description": "test",
			"cover_image": "https://r2.example.com/x.jpg",
			"category": "dining",
			"is_active": 1,
		})
		self.club.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		_cleanup()

	# ── auth ─────────────────────────────────────────────────────────

	def test_unverified_session_denied(self):
		with patch("flamezo_backend.flamezo.api.creator_analytics.has_active_customer_session", return_value=False):
			with self.assertRaises(frappe.exceptions.AuthenticationError):
				analytics_api.get_my_chills_analytics(_PHONE)

	def test_phone_with_no_creator_profile_denied(self):
		with _verified_session():
			with self.assertRaises(frappe.exceptions.DoesNotExistError):
				analytics_api.get_my_chills_analytics("9300099998")

	# ── Chills analytics ─────────────────────────────────────────────

	def test_chills_analytics_aggregates_only_my_own_published_videos(self):
		_make_chills(self.outlet, self.creator.name, views=100, likes=10, saves=5, shares=2)
		_make_chills(self.outlet, self.creator.name, views=200, likes=20, saves=10, shares=4)
		_make_chills(self.outlet, self.creator.name, views=999, likes=1, saves=1, shares=1, status="draft")  # excluded

		other_creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": _OTHER_PHONE,
			"display_name": "OtherCreator", "status": "approved",
		})
		other_creator.insert(ignore_permissions=True)
		frappe.db.commit()
		_make_chills(self.outlet, other_creator.name, views=5000, likes=500, saves=500, shares=500)  # not mine

		with _verified_session():
			result = analytics_api.get_my_chills_analytics(_PHONE)

		data = result["data"]
		self.assertEqual(data["total_videos"], 2)
		self.assertEqual(data["total_views"], 300)
		self.assertEqual(data["total_likes"], 30)
		self.assertEqual(data["total_saves"], 15)
		self.assertEqual(data["total_shares"], 6)
		self.assertEqual(data["avg_views_per_video"], 150.0)
		self.assertAlmostEqual(data["engagement_rate"], round((30 + 15) / 300 * 100, 1))
		self.assertEqual(data["top_video"]["views"], 200)

		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name = %s", other_creator.name)
		frappe.db.sql("DELETE FROM `tabChills` WHERE creator = %s", other_creator.name)
		frappe.db.commit()

	def test_chills_analytics_with_zero_videos_returns_zeros_not_error(self):
		with _verified_session():
			result = analytics_api.get_my_chills_analytics(_PHONE)
		data = result["data"]
		self.assertEqual(data["total_videos"], 0)
		self.assertEqual(data["avg_views_per_video"], 0)
		self.assertEqual(data["engagement_rate"], 0)
		self.assertIsNone(data["top_video"])

	def test_my_chills_list_excludes_removed_and_paginates(self):
		v1 = _make_chills(self.outlet, self.creator.name, views=1)
		_make_chills(self.outlet, self.creator.name, views=2, status="removed")

		with _verified_session():
			result = analytics_api.get_my_chills(_PHONE, limit=20)
		ids = [v["id"] for v in result["data"]["videos"]]
		self.assertIn(v1.name, ids)
		self.assertEqual(len(ids), 1)  # removed one excluded

	# ── Club Talks analytics ──────────────────────────────────────────

	def test_club_analytics_aggregates_across_all_my_clubs(self):
		post = frappe.get_doc({
			"doctype": "Creator Club Post",
			"club": self.club.name,
			"creator": self.creator.name,
			"post_type": "text",
			"content": "hello world",
		})
		post.insert(ignore_permissions=True)
		frappe.db.set_value("Creator Club Post", post.name, {
			"likes_count": 12, "comments_count": 3, "views_count": 80,
		})
		frappe.db.commit()

		with _verified_session():
			result = analytics_api.get_my_club_analytics(_PHONE)
		data = result["data"]
		self.assertEqual(data["total_posts"], 1)
		self.assertEqual(data["total_likes"], 12)
		self.assertEqual(data["total_comments"], 3)
		self.assertGreaterEqual(data["total_views"], 80)
		self.assertEqual(data["top_post"]["id"], post.name)

	def test_club_analytics_with_zero_posts_returns_zeros_not_error(self):
		with _verified_session():
			result = analytics_api.get_my_club_analytics(_PHONE)
		data = result["data"]
		self.assertEqual(data["total_posts"], 0)
		self.assertIsNone(data["top_post"])

	# ── Follower trend ─────────────────────────────────────────────────

	def test_follower_trend_reflects_real_in_app_follow_count(self):
		frappe.get_doc({
			"doctype": "Creator Follow", "creator": self.creator.name, "customer_phone": "9111111111",
		}).insert(ignore_permissions=True)
		frappe.get_doc({
			"doctype": "Creator Follow", "creator": self.creator.name, "customer_phone": "9222222222",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

		with _verified_session():
			result = analytics_api.get_my_follower_trend(_PHONE)
		data = result["data"]
		self.assertEqual(data["current_in_app_followers"], 2)
		self.assertEqual(data["current_ig_followers"], 500)

	def test_follower_trend_history_only_within_window_and_own_creator(self):
		frappe.get_doc({
			"doctype": "Creator Follower Snapshot", "creator": self.creator.name,
			"snapshot_date": add_days(today(), -5), "in_app_followers": 3, "ig_followers": 480,
		}).insert(ignore_permissions=True)
		frappe.get_doc({
			"doctype": "Creator Follower Snapshot", "creator": self.creator.name,
			"snapshot_date": add_days(today(), -200), "in_app_followers": 1, "ig_followers": 400,
		}).insert(ignore_permissions=True)  # outside default 90-day window
		frappe.db.commit()

		with _verified_session():
			result = analytics_api.get_my_follower_trend(_PHONE, days=90)
		history = result["data"]["history"]
		self.assertEqual(len(history), 1)
		self.assertEqual(history[0]["in_app_followers"], 3)

	# ── Daily snapshot job ───────────────────────────────────────────

	def test_daily_snapshot_job_is_idempotent_same_day(self):
		first = analytics_api.daily_follower_snapshot()
		self.assertEqual(first["snapshotted"], 1)  # only our one approved creator

		second = analytics_api.daily_follower_snapshot()
		self.assertEqual(second["snapshotted"], 0)  # already snapshotted today

		count = frappe.db.count("Creator Follower Snapshot", {"creator": self.creator.name})
		self.assertEqual(count, 1)


if __name__ == "__main__":
	unittest.main()
