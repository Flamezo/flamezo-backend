# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Unit tests (pure core) + E2E tests (real doctypes) for
utils/creator_reward_redemption.py — the 14-day per-outlet cooldown,
content-gated FlameZO Cash redemption.

Run:
	bench --site flamezo.localhost run-tests --app flamezo_backend \
		--module flamezo_backend.flamezo.tests.test_creator_reward_redemption
"""

import unittest
from datetime import datetime, timedelta

import frappe

from flamezo_backend.flamezo.tests.utils import make_restaurant
from flamezo_backend.flamezo.utils.creator_reward_redemption import (
	COOLDOWN_DAYS,
	PROOF_WINDOW_DAYS,
	check_redemption,
	get_available_balance,
	redeem_creator_reward,
)

_PREFIX = "TEST-REDEEM"
_PHONE = "9300000501"


class TestCheckRedemptionPure(unittest.TestCase):
	"""No DB — every input handed in explicitly."""

	def test_insufficient_balance_denied(self):
		result = check_redemption(
			available_balance=100, amount=500,
			last_redemption_at_outlet=None, has_qualifying_proof_post=True,
		)
		self.assertFalse(result.allowed)
		self.assertIn("Insufficient balance", result.reason)

	def test_zero_or_negative_amount_denied(self):
		self.assertFalse(check_redemption(1000, 0, None, True).allowed)
		self.assertFalse(check_redemption(1000, -50, None, True).allowed)

	def test_no_proof_post_denied(self):
		result = check_redemption(
			available_balance=1000, amount=200,
			last_redemption_at_outlet=None, has_qualifying_proof_post=False,
		)
		self.assertFalse(result.allowed)
		self.assertIn("Club post", result.reason)

	def test_first_ever_redemption_at_outlet_allowed(self):
		result = check_redemption(
			available_balance=1000, amount=200,
			last_redemption_at_outlet=None, has_qualifying_proof_post=True,
		)
		self.assertTrue(result.allowed)
		self.assertIsNone(result.reason)

	def test_within_cooldown_denied(self):
		now = datetime(2026, 8, 11, 12, 0, 0)
		last = now - timedelta(days=5)
		result = check_redemption(
			available_balance=1000, amount=200,
			last_redemption_at_outlet=last, has_qualifying_proof_post=True,
			now=now,
		)
		self.assertFalse(result.allowed)
		self.assertIn("wait", result.reason)

	def test_exactly_at_cooldown_boundary_allowed(self):
		now = datetime(2026, 8, 11, 12, 0, 0)
		last = now - timedelta(days=COOLDOWN_DAYS)
		result = check_redemption(
			available_balance=1000, amount=200,
			last_redemption_at_outlet=last, has_qualifying_proof_post=True,
			now=now,
		)
		self.assertTrue(result.allowed)

	def test_past_cooldown_allowed(self):
		now = datetime(2026, 8, 11, 12, 0, 0)
		last = now - timedelta(days=COOLDOWN_DAYS + 10)
		result = check_redemption(
			available_balance=1000, amount=200,
			last_redemption_at_outlet=last, has_qualifying_proof_post=True,
			now=now,
		)
		self.assertTrue(result.allowed)

	def test_denial_always_has_a_reason(self):
		"""Explainability requirement — mirrors the score engine's anomaly
		reasons. A denial with no explanation is a bug, not just a
		style nit."""
		cases = [
			check_redemption(100, 500, None, True),
			check_redemption(1000, 0, None, True),
			check_redemption(1000, 200, None, False),
			check_redemption(1000, 200, datetime.now(), True, now=datetime.now()),
		]
		for result in cases:
			if not result.allowed:
				self.assertIsNotNone(result.reason)
				self.assertGreater(len(result.reason), 0)


class TestRedemptionE2E(unittest.TestCase):
	"""Real doctypes — Flamezo Creator, Creator Club, Creator Club Post,
	Creator Reward Ledger, Restaurant, Creator Reward Redemption."""

	@classmethod
	def setUpClass(cls):
		cls.outlet_a = f"{_PREFIX}-OUTLET-A"
		cls.outlet_b = f"{_PREFIX}-OUTLET-B"
		if not frappe.db.exists("Outlet", cls.outlet_a):
			make_restaurant(cls.outlet_a, outlet_type="dining")
		if not frappe.db.exists("Outlet", cls.outlet_b):
			make_restaurant(cls.outlet_b, outlet_type="dining")

	def setUp(self):
		self._cleanup()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "RedeemTestCreator",
			"meta_followers": 5000,
			"status": "approved",
		})
		self.creator.insert(ignore_permissions=True)

		self.club = frappe.get_doc({
			"doctype": "Creator Club",
			"creator": self.creator.name,
			"club_name": "Redeem Test Club",
			"niche": "Food",
			"description": "test",
			"cover_image": "https://r2.example.com/x.jpg",
			"category": "dining",
			"is_active": 1,
		})
		self.club.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._cleanup()

	def _cleanup(self):
		frappe.db.sql("DELETE FROM `tabCreator Reward Redemption` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
		frappe.db.sql("DELETE FROM `tabCreator Reward Ledger` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
		frappe.db.sql("DELETE FROM `tabCreator Club Post` WHERE club IN (SELECT name FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s))", _PHONE)
		frappe.db.sql("DELETE FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
		frappe.db.commit()

	def _credit(self, amount, week_start="2026-08-01"):
		frappe.get_doc({
			"doctype": "Creator Reward Ledger",
			"creator": self.creator.name,
			"week_start": week_start,
			"week_end": "2026-08-07",
			"amount": amount,
			"reason": "test credit",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

	def _post_about(self, outlet):
		post = frappe.get_doc({
			"doctype": "Creator Club Post",
			"club": self.club.name,
			"creator": self.creator.name,
			"post_type": "text",
			"outlet": outlet,
			"content": "test post about outlet",
		})
		post.insert(ignore_permissions=True)
		frappe.db.commit()
		return post

	def test_balance_reflects_ledger_minus_redemptions(self):
		self._credit(1000)
		self.assertEqual(get_available_balance(self.creator.name), 1000)

	def test_redeem_without_proof_post_fails(self):
		self._credit(1000)
		result = redeem_creator_reward(self.creator.name, self.outlet_a, 200)
		self.assertFalse(result["success"])
		self.assertIn("Club post", result["reason"])

	def test_redeem_with_proof_post_succeeds_and_deducts_balance(self):
		self._credit(1000)
		self._post_about(self.outlet_a)
		result = redeem_creator_reward(self.creator.name, self.outlet_a, 300)
		self.assertTrue(result["success"], result.get("reason"))
		self.assertEqual(get_available_balance(self.creator.name), 700)

	def test_second_redemption_same_outlet_within_cooldown_fails(self):
		self._credit(1000)
		self._post_about(self.outlet_a)
		first = redeem_creator_reward(self.creator.name, self.outlet_a, 200)
		self.assertTrue(first["success"])

		self._post_about(self.outlet_a)  # fresh proof, still shouldn't matter — cooldown is per-outlet
		second = redeem_creator_reward(self.creator.name, self.outlet_a, 100)
		self.assertFalse(second["success"])
		self.assertIn("wait", second["reason"])

	def test_redemption_at_a_different_outlet_not_blocked_by_cooldown(self):
		self._credit(1000)
		self._post_about(self.outlet_a)
		first = redeem_creator_reward(self.creator.name, self.outlet_a, 200)
		self.assertTrue(first["success"])

		self._post_about(self.outlet_b)
		second = redeem_creator_reward(self.creator.name, self.outlet_b, 200)
		self.assertTrue(second["success"], second.get("reason"))

	def test_redemption_exceeding_balance_fails(self):
		self._credit(100)
		self._post_about(self.outlet_a)
		result = redeem_creator_reward(self.creator.name, self.outlet_a, 500)
		self.assertFalse(result["success"])
		self.assertIn("Insufficient", result["reason"])

	def test_redemption_stores_proof_post_reference(self):
		self._credit(1000)
		post = self._post_about(self.outlet_a)
		result = redeem_creator_reward(self.creator.name, self.outlet_a, 200)
		self.assertTrue(result["success"])
		stored = frappe.db.get_value("Creator Reward Redemption", result["redemption"], "proof_post")
		self.assertEqual(stored, post.name)

	def test_unknown_creator_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			redeem_creator_reward("NOT-A-REAL-CREATOR", self.outlet_a, 100)

	def test_unknown_outlet_throws(self):
		self._credit(1000)
		with self.assertRaises(frappe.exceptions.ValidationError):
			redeem_creator_reward(self.creator.name, "NOT-A-REAL-OUTLET", 100)
