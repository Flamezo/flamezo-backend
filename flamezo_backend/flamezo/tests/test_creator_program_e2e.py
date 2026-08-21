# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Full end-to-end lifecycle test for the Creator Program, exercising every
module built this round as ONE connected system rather than in isolation:

  creator_onboarding (OAuth connect, mocked HTTP)
    -> Creator Club + Creator Club Post (existing clubs.py stack)
    -> creator_collabs (merchant discovers, invites, creator accepts,
       merchant completes + rates)
    -> creator_score_engine (weekly payout run picks up the completed
       collab's quality points + the week's organic engagement)
    -> creator_reward_redemption (creator spends the earned reward at the
       SAME outlet the collab was with, gated on the collab's own post as
       proof, then cooldown blocks a second redemption there)

This is the test that would have caught a wiring mistake between modules
that each module's own isolated test suite couldn't — e.g. a field-name
mismatch between what creator_collabs.py writes and what
creator_score_engine.py reads back out.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, now_datetime

from flamezo_backend.flamezo.api import creator_collabs as collabs
from flamezo_backend.flamezo.api import creator_onboarding as onboarding
from flamezo_backend.flamezo.tests.utils import make_restaurant
from flamezo_backend.flamezo.utils import creator_reward_redemption as redemption
from flamezo_backend.flamezo.utils.creator_score_engine import (
	compute_weekly_score,
	gather_app_signals,
	gather_ig_signals,
)

_PREFIX = "TEST-E2E"
_PHONE = "9300000901"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCreator Reward Redemption` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql("DELETE FROM `tabCreator Reward Ledger` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql("DELETE FROM `tabCreator Collab Invite` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql("DELETE FROM `tabCreator Club Post` WHERE club IN (SELECT name FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s))", _PHONE)
	frappe.db.sql("DELETE FROM `tabCreator Club` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestCreatorProgramFullLifecycle(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-OUTLET"
		if not frappe.db.exists("Outlet", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining")

	def setUp(self):
		_cleanup()

	def tearDown(self):
		_cleanup()

	@patch("flamezo_backend.flamezo.api.creator_collabs.has_active_customer_session", return_value=True)
	def test_full_lifecycle_onboarding_through_redemption(self, _mock_session):
		# ── 1. Creator connects via Instagram OAuth (mocked HTTP), auto-approved ──
		profile = {"followers_count": 4000, "username": "e2e_creator"}
		connect_result = onboarding._apply_connection_result(_PHONE, "IG_E2E_1", "tok_e2e", 5184000, profile)
		self.assertTrue(connect_result["approved"], "creator should auto-approve above the 1,500 floor")
		creator_name = connect_result["creator_id"]
		frappe.db.set_value("Flamezo Creator", creator_name, "city", "Surat")

		# ── 2. Creator creates a Club (self-serve, no separate approval) ──
		club = frappe.get_doc({
			"doctype": "Creator Club",
			"creator": creator_name,
			"club_name": "E2E Foodie Club",
			"niche": "Food",
			"description": "test",
			"cover_image": "https://r2.example.com/x.jpg",
			"category": "dining",
			"is_active": 1,
		})
		club.insert(ignore_permissions=True)

		# ── 3. Merchant discovers the creator ──
		discovery = collabs.discover_creators(category="dining", city="Surat")
		discovered_ids = [c["creator_id"] for c in discovery["data"]["creators"]]
		self.assertIn(creator_name, discovered_ids, "newly-approved creator with an active club should be discoverable")

		# ── 4. Merchant sends a collab invite, creator accepts ──
		invite_result = collabs.send_collab_invite(self.outlet, creator_name, "Free tasting menu for a Reel + Story", "1 Reel + 1 Story")
		invite_id = invite_result["data"]["invite_id"]
		accept_result = collabs.respond_to_invite(invite_id, accept=1, phone=_PHONE)
		self.assertEqual(accept_result["data"]["status"], "accepted")

		# ── 5. Creator posts content about the visit, tagging the outlet ──
		post = frappe.get_doc({
			"doctype": "Creator Club Post",
			"club": club.name,
			"creator": creator_name,
			"post_type": "text",
			"outlet": self.outlet,
			"content": "Had an amazing tasting menu here tonight!",
		})
		post.insert(ignore_permissions=True)
		# A second qualifying post so the week clears the 2-post minimum.
		frappe.get_doc({
			"doctype": "Creator Club Post",
			"club": club.name,
			"creator": creator_name,
			"post_type": "text",
			"content": "Also tried a new cafe today, loved it.",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

		# Some organic engagement on the collab post — likes/comments from
		# OTHER real accounts (self-engagement is excluded by design, and
		# these test phones aren't the creator's own).
		for i, engager_phone in enumerate(["9199990001", "9199990002", "9199990003"]):
			frappe.get_doc({
				"doctype": "Creator Club Post Like",
				"post": post.name,
				"customer_phone": engager_phone,
			}).insert(ignore_permissions=True)
		frappe.get_doc({
			"doctype": "Creator Club Post Comment",
			"post": post.name,
			"customer_phone": "9199990004",
			"customer_name": "Real Fan",
			"content": "Looks delicious!",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

		# ── 6. Merchant marks the collab completed with a strong rating ──
		complete_result = collabs.complete_collab(invite_id, merchant_rating=5)
		self.assertEqual(complete_result["data"]["status"], "completed")

		# ── 7. Weekly score computation picks up the completed collab ──
		week_start = frappe.utils.get_first_day_of_week(frappe.utils.today())
		week_end = frappe.utils.add_days(week_start, 6)

		app_signals = gather_app_signals(creator_name, week_start, week_end)
		self.assertEqual(app_signals.qualifying_posts, 2)
		self.assertGreater(app_signals.likes, 0, "organic likes should flow through, trust-weighted")
		self.assertGreater(app_signals.comments, 0)
		self.assertGreater(
			app_signals.collabs_completed, 0,
			"the completed, 5-rated collab should produce non-zero quality points — "
			"this is the cross-module wiring check: creator_collabs writes what "
			"creator_score_engine actually reads back",
		)
		self.assertAlmostEqual(app_signals.collabs_completed, 1.0, places=2)  # 5/5 rating = 1.0 quality point

		ig_signals = gather_ig_signals(creator_name, week_start, week_end)
		result = compute_weekly_score(app_signals, ig_signals, city_club_members=0)
		self.assertTrue(result.qualified)
		self.assertGreater(result.payout, 0)

		# ── 8. Credit the computed payout to the reward ledger (what
		#      run_weekly_payout does, done explicitly here for a
		#      deterministic assertion on the exact amount), PLUS a
		#      separate top-up so there's deliberately enough balance left
		#      to isolate the cooldown check in step 10 from a balance
		#      check — testing one rule at a time, not conflating two ──
		frappe.get_doc({
			"doctype": "Creator Reward Ledger",
			"creator": creator_name,
			"week_start": week_start,
			"week_end": week_end,
			"amount": result.payout,
			"reason": "E2E test credit",
		}).insert(ignore_permissions=True)
		frappe.get_doc({
			"doctype": "Creator Reward Ledger",
			"creator": creator_name,
			"week_start": add_days(week_start, -7),
			"week_end": add_days(week_start, -1),
			"amount": 1000,
			"reason": "E2E test top-up — ensures balance isn't the bottleneck for step 10",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

		balance = redemption.get_available_balance(creator_name)
		self.assertAlmostEqual(balance, result.payout + 1000, places=2)

		# ── 9. Creator redeems part of their earned reward AT THE SAME
		#      OUTLET the collab was with — allowed because their post
		#      from step 5 tagging that outlet is fresh proof ──
		spend_amount = 200
		redeem_result = redemption.redeem_creator_reward(creator_name, self.outlet, spend_amount)
		self.assertTrue(redeem_result["success"], redeem_result.get("reason"))
		self.assertEqual(
			redemption.get_available_balance(creator_name), balance - spend_amount,
			"balance should reflect the redemption immediately",
		)

		# ── 10. A second redemption at the SAME outlet within 14 days is
		#       blocked by COOLDOWN specifically (plenty of balance left,
		#       isolating this from step 9's balance-sufficiency check) —
		#       this is the mechanism from the "don't let a creator
		#       ragebait one outlet" conversation ──
		second_redeem = redemption.redeem_creator_reward(creator_name, self.outlet, 10)
		self.assertFalse(second_redeem["success"])
		self.assertIn("wait", second_redeem["reason"])

		# ── 11. A new collab invite from the SAME merchant to the SAME
		#       creator is blocked by the 30-day collab cooldown — a
		#       DIFFERENT mechanism than #10, both correctly independent ──
		with self.assertRaises(frappe.exceptions.ValidationError):
			collabs.send_collab_invite(self.outlet, creator_name, "another collab so soon")
