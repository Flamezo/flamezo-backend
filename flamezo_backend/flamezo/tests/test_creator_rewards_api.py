# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for api/creator_rewards.py — the HTTP layer wrapping
creator_score_engine.py and creator_reward_redemption.py. Focus is on
correct auth (own-creator-only, admin-only for review actions) and
correct pass-through to the already-tested underlying engines, not
re-testing the engines' own internal logic.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import today

from flamezo_backend.flamezo.api import creator_rewards as rewards_api
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PHONE = "9300000801"
_OTHER_PHONE = "9300000802"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCreator Reward Redemption` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabCreator Reward Ledger` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabCreator Weekly Score` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabCreator Club Post` WHERE club IN (SELECT name FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s)))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s))", (_PHONE, _OTHER_PHONE))
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone IN (%s,%s)", (_PHONE, _OTHER_PHONE))
	frappe.db.commit()


def _verified_session():
	return patch("flamezo_backend.flamezo.api.creator_rewards.has_active_customer_session", return_value=True)


class TestCreatorRewardsApi(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = "TEST-REWARDS-API-OUTLET"
		if not frappe.db.exists("Restaurant", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining")

	def setUp(self):
		_cleanup()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "RewardsApiCreator",
			"status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		self.club = frappe.get_doc({
			"doctype": "Creator Club",
			"creator": self.creator.name,
			"club_name": "Rewards API Club",
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
		with patch("flamezo_backend.flamezo.api.creator_rewards.has_active_customer_session", return_value=False):
			with self.assertRaises(frappe.exceptions.AuthenticationError):
				rewards_api.get_my_wallet_balance(_PHONE)

	def test_phone_with_no_creator_profile_denied(self):
		with _verified_session():
			with self.assertRaises(frappe.exceptions.DoesNotExistError):
				rewards_api.get_my_wallet_balance("9300099999")

	# ── balance / weekly scores ──────────────────────────────────────

	def test_balance_reflects_real_ledger(self):
		frappe.get_doc({
			"doctype": "Creator Reward Ledger", "creator": self.creator.name,
			"week_start": today(), "week_end": today(), "amount": 500, "reason": "test",
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		with _verified_session():
			result = rewards_api.get_my_wallet_balance(_PHONE)
		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["balance"], 500)

	def test_weekly_scores_returns_own_receipts_only(self):
		frappe.get_doc({
			"doctype": "Creator Weekly Score", "creator": self.creator.name,
			"week_start": today(), "week_end": today(), "qualified": 1, "final_score": 200, "payout_inr": 1000,
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		with _verified_session():
			result = rewards_api.get_my_weekly_scores(_PHONE)
		self.assertEqual(len(result["data"]["weeks"]), 1)
		self.assertEqual(result["data"]["weeks"][0]["payout_inr"], 1000)

	# ── redemption pass-through ──────────────────────────────────────

	def test_redeem_without_proof_post_fails_through_the_api(self):
		frappe.get_doc({
			"doctype": "Creator Reward Ledger", "creator": self.creator.name,
			"week_start": today(), "week_end": today(), "amount": 500, "reason": "test",
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		with _verified_session():
			result = rewards_api.redeem_my_reward(_PHONE, self.outlet, 100)
		self.assertFalse(result["success"])
		self.assertIn("Club post", result["data"]["reason"])

	def test_redeem_with_proof_post_succeeds_through_the_api(self):
		frappe.get_doc({
			"doctype": "Creator Reward Ledger", "creator": self.creator.name,
			"week_start": today(), "week_end": today(), "amount": 500, "reason": "test",
		}).insert(ignore_permissions=True)
		frappe.get_doc({
			"doctype": "Creator Club Post", "club": self.club.name, "creator": self.creator.name,
			"post_type": "text", "outlet": self.outlet, "content": "great visit",
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		with _verified_session():
			result = rewards_api.redeem_my_reward(_PHONE, self.outlet, 100)
		self.assertTrue(result["success"], result["data"].get("reason"))

	# ── admin review queue ───────────────────────────────────────────

	def test_review_queue_denied_for_non_admin(self):
		with patch("frappe.get_roles", return_value=["Customer"]):
			with self.assertRaises(frappe.exceptions.PermissionError):
				rewards_api.get_pending_review_weeks()

	def test_review_queue_allowed_for_system_manager(self):
		frappe.get_doc({
			"doctype": "Creator Weekly Score", "creator": self.creator.name,
			"week_start": today(), "week_end": today(), "qualified": 1,
			"final_score": 500, "payout_inr": 1800, "review_status": "pending_review",
			"anomaly_flagged": 1, "anomaly_reason": "test anomaly",
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = rewards_api.get_pending_review_weeks()
		self.assertEqual(len(result["data"]["weeks"]), 1)

	def test_approve_review_credits_the_reward(self):
		score = frappe.get_doc({
			"doctype": "Creator Weekly Score", "creator": self.creator.name,
			"week_start": today(), "week_end": today(), "qualified": 1,
			"final_score": 500, "payout_inr": 1800, "review_status": "pending_review",
		})
		score.insert(ignore_permissions=True)
		frappe.db.commit()

		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = rewards_api.approve_review(score.name)
		self.assertTrue(result["success"])

		from flamezo_backend.flamezo.utils.creator_reward_redemption import get_available_balance
		self.assertEqual(get_available_balance(self.creator.name), 1800)
		self.assertEqual(frappe.db.get_value("Creator Weekly Score", score.name, "review_status"), "approved")

	def test_reject_review_does_not_credit(self):
		score = frappe.get_doc({
			"doctype": "Creator Weekly Score", "creator": self.creator.name,
			"week_start": today(), "week_end": today(), "qualified": 1,
			"final_score": 500, "payout_inr": 1800, "review_status": "pending_review",
		})
		score.insert(ignore_permissions=True)
		frappe.db.commit()

		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = rewards_api.reject_review(score.name)
		self.assertTrue(result["success"])

		from flamezo_backend.flamezo.utils.creator_reward_redemption import get_available_balance
		self.assertEqual(get_available_balance(self.creator.name), 0)
		self.assertEqual(frappe.db.get_value("Creator Weekly Score", score.name, "review_status"), "rejected")
