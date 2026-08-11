# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for api/creator_collabs.py — merchant collab invites: the
monthly per-outlet send cap, the 30-day per-(creator,outlet) cooldown
after completion, and the weekly per-creator accept cap (waitlisting the
overflow instead of confirming it).
"""

import unittest
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime

from flamezo_backend.flamezo.api import creator_collabs as collabs
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-COLLAB"
_PHONE = "9300000701"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCreator Collab Invite` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql("DELETE FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestCreatorCollabs(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-OUTLET"
		if not frappe.db.exists("Restaurant", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining")

	def setUp(self):
		_cleanup()
		# respond_to_invite requires a verified session for the responding
		# creator's own phone — mocked True for the whole test class, same
		# pattern test_clubs_e2e.py uses (patches the source module's
		# attribute directly, since creator_collabs.py imports it by name).
		self._session_patch = patch(
			"flamezo_backend.flamezo.api.creator_collabs.has_active_customer_session", return_value=True
		)
		self._session_patch.start()

		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "CollabTestCreator",
			"meta_followers": 5000,
			"city": "Surat",
			"status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		self.club = frappe.get_doc({
			"doctype": "Creator Club",
			"creator": self.creator.name,
			"club_name": "Collab Test Club",
			"niche": "Food",
			"description": "test",
			"cover_image": "https://r2.example.com/x.jpg",
			"category": "dining",
			"is_active": 1,
		})
		self.club.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._session_patch.stop()
		_cleanup()

	# ── send invite ──────────────────────────────────────────────────

	def test_send_invite_succeeds(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "Free meal for a Reel", "1 Reel")
		self.assertTrue(result["success"])
		self.assertTrue(frappe.db.exists("Creator Collab Invite", result["data"]["invite_id"]))

	def test_send_invite_unknown_outlet_throws(self):
		with self.assertRaises(frappe.exceptions.DoesNotExistError):
			collabs.send_collab_invite("NOT-REAL", self.creator.name, "offer")

	def test_send_invite_unknown_creator_throws(self):
		with self.assertRaises(frappe.exceptions.DoesNotExistError):
			collabs.send_collab_invite(self.outlet, "NOT-REAL", "offer")

	def test_monthly_cap_enforced(self):
		for _ in range(collabs.MONTHLY_INVITE_CAP):
			collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		with self.assertRaises(frappe.exceptions.ValidationError):
			collabs.send_collab_invite(self.outlet, self.creator.name, "one too many")

	# ── accept / decline ─────────────────────────────────────────────

	def test_accept_within_weekly_cap_confirms(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		response = collabs.respond_to_invite(result["data"]["invite_id"], accept=1, phone=_PHONE)
		self.assertEqual(response["data"]["status"], "accepted")

	def test_decline_sets_declined(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		response = collabs.respond_to_invite(result["data"]["invite_id"], accept=0, phone=_PHONE)
		self.assertEqual(response["data"]["status"], "declined")

	def test_responding_twice_throws(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		collabs.respond_to_invite(result["data"]["invite_id"], accept=1, phone=_PHONE)
		with self.assertRaises(frappe.exceptions.ValidationError):
			collabs.respond_to_invite(result["data"]["invite_id"], accept=1, phone=_PHONE)

	def test_weekly_accept_cap_waitlists_overflow(self):
		# Need distinct outlets to avoid tripping the monthly-per-outlet cap
		# while sending WEEKLY_ACCEPT_CAP + 1 invites to the same creator.
		outlets = []
		for i in range(collabs.WEEKLY_ACCEPT_CAP + 1):
			name = f"{_PREFIX}-OUTLET-W{i}"
			if not frappe.db.exists("Restaurant", name):
				make_restaurant(name, outlet_type="dining")
			outlets.append(name)

		statuses = []
		for outlet in outlets:
			result = collabs.send_collab_invite(outlet, self.creator.name, "offer")
			response = collabs.respond_to_invite(result["data"]["invite_id"], accept=1, phone=_PHONE)
			statuses.append(response["data"]["status"])

		self.assertEqual(statuses.count("accepted"), collabs.WEEKLY_ACCEPT_CAP)
		self.assertEqual(statuses.count("waitlisted"), 1)

	# ── complete + cooldown ──────────────────────────────────────────

	def test_complete_collab_with_rating(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		invite_id = result["data"]["invite_id"]
		collabs.respond_to_invite(invite_id, accept=1, phone=_PHONE)
		response = collabs.complete_collab(invite_id, merchant_rating=4)
		self.assertEqual(response["data"]["status"], "completed")
		doc = frappe.get_doc("Creator Collab Invite", invite_id)
		self.assertEqual(doc.merchant_rating, 4)
		self.assertIsNotNone(doc.completed_at)

	def test_complete_invalid_rating_throws(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		invite_id = result["data"]["invite_id"]
		collabs.respond_to_invite(invite_id, accept=1, phone=_PHONE)
		with self.assertRaises(frappe.exceptions.ValidationError):
			collabs.complete_collab(invite_id, merchant_rating=7)

	def test_complete_pending_invite_throws(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		with self.assertRaises(frappe.exceptions.ValidationError):
			collabs.complete_collab(result["data"]["invite_id"], merchant_rating=5)

	def test_cooldown_blocks_reinvite_after_completion(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		invite_id = result["data"]["invite_id"]
		collabs.respond_to_invite(invite_id, accept=1, phone=_PHONE)
		collabs.complete_collab(invite_id, merchant_rating=5)

		with self.assertRaises(frappe.exceptions.ValidationError):
			collabs.send_collab_invite(self.outlet, self.creator.name, "offer again so soon")

	def test_cooldown_expired_allows_reinvite(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		invite_id = result["data"]["invite_id"]
		collabs.respond_to_invite(invite_id, accept=1, phone=_PHONE)
		collabs.complete_collab(invite_id, merchant_rating=5)
		# Backdate completed_at past the cooldown window directly in DB.
		frappe.db.set_value(
			"Creator Collab Invite", invite_id, "completed_at",
			add_days(now_datetime(), -(collabs.COOLDOWN_DAYS + 1)),
		)
		frappe.db.commit()

		result2 = collabs.send_collab_invite(self.outlet, self.creator.name, "offer, cooldown passed")
		self.assertTrue(result2["success"])

	def test_cooldown_is_per_outlet_not_global(self):
		other_outlet = f"{_PREFIX}-OUTLET-OTHER"
		if not frappe.db.exists("Restaurant", other_outlet):
			make_restaurant(other_outlet, outlet_type="dining")

		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		invite_id = result["data"]["invite_id"]
		collabs.respond_to_invite(invite_id, accept=1, phone=_PHONE)
		collabs.complete_collab(invite_id, merchant_rating=5)

		result2 = collabs.send_collab_invite(other_outlet, self.creator.name, "different outlet, no cooldown")
		self.assertTrue(result2["success"])

	# ── authorization — closes the "anyone could act on anyone's behalf" gap ──

	def test_send_invite_denied_for_user_without_outlet_access(self):
		"""Proves the fix is real, not just that admin-bypass tests still
		pass: a non-privileged user with no restaurant access is denied,
		via the SAME `validate_restaurant_for_api` helper every other
		merchant-portal endpoint in the app relies on."""
		with patch("flamezo_backend.flamezo.utils.permissions.validate_restaurant_access", return_value=False), \
			patch("frappe.get_roles", return_value=["Restaurant Manager"]):  # not a global-admin role
			with self.assertRaises(frappe.exceptions.PermissionError):
				collabs.send_collab_invite(self.outlet, self.creator.name, "offer")

	def test_complete_collab_denied_for_user_without_outlet_access(self):
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		invite_id = result["data"]["invite_id"]
		collabs.respond_to_invite(invite_id, accept=1, phone=_PHONE)

		with patch("flamezo_backend.flamezo.utils.permissions.validate_restaurant_access", return_value=False), \
			patch("frappe.get_roles", return_value=["Restaurant Manager"]):
			with self.assertRaises(frappe.exceptions.PermissionError):
				collabs.complete_collab(invite_id, merchant_rating=5)

	def test_respond_denied_for_wrong_phone(self):
		"""A different creator's phone can't accept/decline someone else's
		invite, even with a valid verified session of their own."""
		result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		with self.assertRaises(frappe.exceptions.PermissionError):
			collabs.respond_to_invite(result["data"]["invite_id"], accept=1, phone="9300000799")

	def test_respond_denied_without_verified_session(self):
		self._session_patch.stop()  # this test wants the REAL (unmocked) session check
		try:
			result = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
			with self.assertRaises(frappe.exceptions.AuthenticationError):
				collabs.respond_to_invite(result["data"]["invite_id"], accept=1, phone=_PHONE)
		finally:
			self._session_patch.start()  # tearDown expects to stop() an active patch

	# ── creator's own invite list ────────────────────────────────────

	def test_get_my_collab_invites_requires_session(self):
		self._session_patch.stop()
		try:
			with self.assertRaises(frappe.exceptions.AuthenticationError):
				collabs.get_my_collab_invites(_PHONE)
		finally:
			self._session_patch.start()

	def test_get_my_collab_invites_returns_own_invites(self):
		collabs.send_collab_invite(self.outlet, self.creator.name, "offer one")
		result = collabs.get_my_collab_invites(_PHONE)
		self.assertEqual(len(result["data"]["invites"]), 1)
		self.assertEqual(result["data"]["invites"][0]["outlet"], self.outlet)

	def test_get_my_collab_invites_filters_by_status(self):
		sent = collabs.send_collab_invite(self.outlet, self.creator.name, "offer")
		collabs.respond_to_invite(sent["data"]["invite_id"], accept=1, phone=_PHONE)

		accepted_only = collabs.get_my_collab_invites(_PHONE, status="accepted")
		pending_only = collabs.get_my_collab_invites(_PHONE, status="pending")
		self.assertEqual(len(accepted_only["data"]["invites"]), 1)
		self.assertEqual(len(pending_only["data"]["invites"]), 0)

	def test_get_my_collab_invites_empty_for_non_creator_phone(self):
		result = collabs.get_my_collab_invites("9300099999")
		self.assertEqual(result["data"]["invites"], [])

	# ── discovery ────────────────────────────────────────────────────

	def test_discover_creators_finds_active_club(self):
		result = collabs.discover_creators(category="dining", city="Surat")
		ids = [c["creator_id"] for c in result["data"]["creators"]]
		self.assertIn(self.creator.name, ids)

	def test_discover_creators_filters_by_min_followers(self):
		result = collabs.discover_creators(min_followers=10000)
		ids = [c["creator_id"] for c in result["data"]["creators"]]
		self.assertNotIn(self.creator.name, ids)

	def test_discover_creators_available_this_week_flag(self):
		result = collabs.discover_creators(city="Surat")
		match = next(c for c in result["data"]["creators"] if c["creator_id"] == self.creator.name)
		self.assertTrue(match["available_this_week"])
