# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for api/standing_offers.py — creator-marketplace-blueprint.html
§17. Covers create/list (merchant), discover/redeem (creator), the
matching-key gates, caps, cooldown reuse, and merchant-accountability
renege flagging.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from flamezo_backend.flamezo.api import standing_offers as so
from flamezo_backend.flamezo.tests.utils import make_restaurant, make_menu_product

_PREFIX = "TEST-SO"
_PHONE = "9300001001"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql(f"DELETE FROM `tabMerchant Standing Offer` WHERE outlet LIKE '{_PREFIX}%%'")
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestStandingOffers(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-OUTLET"
		if not frappe.db.exists("Outlet", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining", city="Surat")
		cls.other_outlet = f"{_PREFIX}-OUTLET-2"
		if not frappe.db.exists("Outlet", cls.other_outlet):
			make_restaurant(cls.other_outlet, outlet_type="dining", city="Ahmedabad")
		cls.menu_item = make_menu_product(cls.outlet, f"{_PREFIX}-ITEM").name

	def setUp(self):
		_cleanup()
		self._session_patch = patch(
			"flamezo_backend.flamezo.api.standing_offers.has_active_customer_session", return_value=True
		)
		self._session_patch.start()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": _PHONE,
			"display_name": "StandingOfferCreator", "status": "approved", "meta_followers": 6000,
		})
		self.creator.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._session_patch.stop()
		_cleanup()

	def _offer(self, **overrides):
		result = so.create_standing_offer(
			self.outlet, "native_chills", "free_item", 250,
			reward_item=overrides.pop("reward_item", self.menu_item),
			min_followers=overrides.pop("min_followers", 0),
			**overrides,
		)
		return frappe.get_doc("Merchant Standing Offer", result["data"]["offer_id"])

	# ── create / list (merchant) ─────────────────────────────────────────

	def test_create_standing_offer_succeeds(self):
		offer = self._offer()
		self.assertEqual(offer.outlet, self.outlet)
		self.assertEqual(offer.active, 1)
		self.assertEqual(offer.suspended, 0)

	def test_create_requires_reward_item_for_free_item_type(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			so.create_standing_offer(self.outlet, "native_chills", "free_item", 250, reward_item=None)

	def test_create_invalid_day_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			so.create_standing_offer(
				self.outlet, "native_chills", "free_item", 250,
				valid_days_of_week="Funday",
			)

	def test_list_my_standing_offers(self):
		self._offer()
		result = so.list_my_standing_offers(self.outlet)
		self.assertEqual(len(result["data"]["offers"]), 1)

	def test_list_my_standing_offers_no_outlet_returns_empty(self):
		result = so.list_my_standing_offers()
		self.assertEqual(result["data"]["offers"], [])

	def test_update_standing_offer_wrong_outlet_throws(self):
		offer = self._offer()
		with self.assertRaises(frappe.exceptions.PermissionError):
			so.update_standing_offer(self.other_outlet, offer.name, active=0)

	def test_update_standing_offer_succeeds(self):
		offer = self._offer()
		so.update_standing_offer(self.outlet, offer.name, active=0)
		offer.reload()
		self.assertEqual(offer.active, 0)

	# ── discover (creator) ───────────────────────────────────────────────

	def test_list_available_includes_qualifying_offer(self):
		self._offer(min_followers=1000)
		result = so.list_available_standing_offers(_PHONE)
		self.assertEqual(len(result["data"]["offers"]), 1)

	def test_list_available_excludes_followers_too_low(self):
		self._offer(min_followers=100000)  # creator only has 6000
		result = so.list_available_standing_offers(_PHONE)
		self.assertEqual(result["data"]["offers"], [])

	def test_list_available_excludes_inactive_offer(self):
		offer = self._offer()
		so.update_standing_offer(self.outlet, offer.name, active=0)
		result = so.list_available_standing_offers(_PHONE)
		self.assertEqual(result["data"]["offers"], [])

	def test_list_available_excludes_suspended_offer(self):
		offer = self._offer()
		frappe.db.set_value("Merchant Standing Offer", offer.name, "suspended", 1)
		result = so.list_available_standing_offers(_PHONE)
		self.assertEqual(result["data"]["offers"], [])

	# ── redeem (creator) ─────────────────────────────────────────────────

	def test_redeem_creates_real_collab_deal(self):
		offer = self._offer()
		result = so.redeem_standing_offer(_PHONE, offer.name)
		deal = frappe.get_doc("Collab Deal", result["data"]["deal_id"])
		self.assertEqual(deal.standing_offer, offer.name)
		self.assertEqual(deal.deal_type, "barter")
		self.assertEqual(deal.escrow_required, 0)  # 250 < 300 handshake ceiling
		self.assertEqual(deal.fair_value_inr, 250)
		self.assertEqual(deal.status, "accepted")
		self.assertIsNone(deal.gig)
		self.assertIsNone(deal.direct_invite)

	def test_redeem_increments_redeemed_count(self):
		offer = self._offer()
		so.redeem_standing_offer(_PHONE, offer.name)
		offer.reload()
		self.assertEqual(offer.redeemed_count, 1)

	def test_redeem_requires_delivery_proof_before_release(self):
		"""Regression guard for the exact bug the blueprint's Sept fix
		closed — a redemption must still go through real verification,
		never an instant free release."""
		offer = self._offer()
		result = so.redeem_standing_offer(_PHONE, offer.name)
		deal_id = result["data"]["deal_id"]
		from flamezo_backend.flamezo.api import collab_deals as deals
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.approve_release(self.outlet, deal_id)  # still 'accepted', not 'delivered' yet

	def test_redeem_ineligible_throws(self):
		offer = self._offer(min_followers=100000)
		with self.assertRaises(frappe.exceptions.ValidationError):
			so.redeem_standing_offer(_PHONE, offer.name)

	def test_redeem_respects_daily_cap(self):
		offer = self._offer(daily_cap=1)
		so.redeem_standing_offer(_PHONE, offer.name)
		# Second redemption same day, different creator, should hit the cap —
		# use a fresh creator since cooldown would otherwise also block a repeat.
		other = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": "9300001002",
			"display_name": "OtherSOCreator", "status": "approved", "meta_followers": 6000,
		})
		other.insert(ignore_permissions=True)
		with patch("flamezo_backend.flamezo.api.standing_offers.has_active_customer_session", return_value=True):
			with self.assertRaises(frappe.exceptions.ValidationError):
				so.redeem_standing_offer("9300001002", offer.name)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", other.name)
		frappe.db.commit()

	def test_redeem_cooldown_blocks_repeat_at_same_outlet(self):
		"""After a real released deal at this outlet, the same
		creator can't redeem again from this outlet within COOLDOWN_DAYS
		— reuses the exact 30-day constant, not a separate rule."""
		offer = self._offer()
		result = so.redeem_standing_offer(_PHONE, offer.name)
		deal = frappe.get_doc("Collab Deal", result["data"]["deal_id"])
		deal.status = "delivered"
		deal.save(ignore_permissions=True)
		deal.status = "released"
		deal.save(ignore_permissions=True)

		with self.assertRaises(frappe.exceptions.ValidationError):
			so.redeem_standing_offer(_PHONE, offer.name)

	def test_redeem_nonexistent_offer_throws(self):
		with self.assertRaises(frappe.exceptions.DoesNotExistError):
			so.redeem_standing_offer(_PHONE, "SO-DOES-NOT-EXIST")

	# ── merchant accountability ──────────────────────────────────────────

	def test_flag_renege_increments_strikes(self):
		offer = self._offer()
		result = so.redeem_standing_offer(_PHONE, offer.name)
		result2 = so.flag_renege(_PHONE, result["data"]["deal_id"], reason="charged me anyway")
		self.assertEqual(result2["data"]["renege_strikes"], 1)
		self.assertFalse(result2["data"]["suspended"])

	def test_flag_renege_second_strike_suspends(self):
		offer = self._offer()
		d1 = so.redeem_standing_offer(_PHONE, offer.name)["data"]["deal_id"]
		so.flag_renege(_PHONE, d1, reason="first strike")
		frappe.db.set_value("Collab Deal", d1, "status", "released")  # free the cooldown-adjacent path for a 2nd redeem attempt isn't needed — flag directly again on a fresh deal instead
		offer.reload()
		frappe.db.set_value("Merchant Standing Offer", offer.name, "redeemed_count", 0)  # allow another redemption for the test's sake
		# Simulate a second reneged redemption directly (bypassing cooldown
		# machinery, which isn't what this test is about).
		deal2 = frappe.get_doc({
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"standing_offer": offer.name, "deal_type": "barter", "fair_value_inr": 250,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		})
		deal2.insert(ignore_permissions=True)
		result = so.flag_renege(_PHONE, deal2.name, reason="second strike")
		self.assertEqual(result["data"]["renege_strikes"], 2)
		self.assertTrue(result["data"]["suspended"])
		self.assertFalse(frappe.db.get_value("Merchant Standing Offer", offer.name, "active") == 0)  # config untouched
		self.assertTrue(frappe.db.get_value("Merchant Standing Offer", offer.name, "suspended"))

	def test_flag_renege_not_your_deal_throws(self):
		offer = self._offer()
		result = so.redeem_standing_offer(_PHONE, offer.name)
		other = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": "9300001003",
			"display_name": "NotYoursCreator", "status": "approved",
		})
		other.insert(ignore_permissions=True)
		with patch("flamezo_backend.flamezo.api.standing_offers.has_active_customer_session", return_value=True):
			with self.assertRaises(frappe.exceptions.PermissionError):
				so.flag_renege("9300001003", result["data"]["deal_id"])
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", other.name)
		frappe.db.commit()

	def test_flag_renege_non_standing_offer_deal_throws(self):
		invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name,
		})
		invite.insert(ignore_permissions=True)
		deal = frappe.get_doc({
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": invite.name, "deal_type": "barter", "fair_value_inr": 100,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		})
		deal.insert(ignore_permissions=True)
		with self.assertRaises(frappe.exceptions.ValidationError):
			so.flag_renege(_PHONE, deal.name)
		frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE name=%s", deal.name)
		frappe.db.sql("DELETE FROM `tabCreator Collab Invite` WHERE name=%s", invite.name)
		frappe.db.commit()


if __name__ == "__main__":
	unittest.main()
