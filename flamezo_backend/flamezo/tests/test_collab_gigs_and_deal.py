# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for api/collab_gigs.py (Phase 1) and the Collab Deal state
machine (doctype/collab_deal/collab_deal.py) that every deal, regardless
of origin, runs through.
"""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime, today

from flamezo_backend.flamezo.api import collab_gigs as gigs
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-GIG"
_PHONE = "9300000901"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql(f"DELETE FROM `tabCollab Gig` WHERE outlet LIKE '{_PREFIX}%%'")
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestCollabGigs(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-OUTLET"
		if not frappe.db.exists("Outlet", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining", city="Surat")
		cls.other_outlet = f"{_PREFIX}-OUTLET-2"
		if not frappe.db.exists("Outlet", cls.other_outlet):
			make_restaurant(cls.other_outlet, outlet_type="dining", city="Ahmedabad")

	def setUp(self):
		_cleanup()
		self._session_patch = patch(
			"flamezo_backend.flamezo.api.collab_gigs.has_active_customer_session", return_value=True
		)
		self._session_patch.start()

		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "GigTestCreator",
			"status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._session_patch.stop()
		_cleanup()

	def _deliverables(self):
		return [{"type": "native_chills", "count": 2}]

	# ── create_gig ───────────────────────────────────────────────────────

	def test_create_gig_cash_succeeds(self):
		result = gigs.create_gig(self.outlet, "2 Reels", self._deliverables(), budget_inr=1500, category="dining")
		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["status"], "open")

	def test_create_gig_barter_only_succeeds(self):
		result = gigs.create_gig(
			self.outlet, "Barter reel", self._deliverables(), budget_inr=0,
			barter_allowed=1, barter_details="Free meal for two", category="dining",
		)
		self.assertTrue(result["success"])

	def test_create_gig_neither_budget_nor_barter_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.create_gig(self.outlet, "Nothing offered", self._deliverables(), budget_inr=0, barter_allowed=0)

	def test_create_gig_barter_allowed_without_details_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=0, barter_allowed=1)

	def test_create_gig_invalid_deliverables_json_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.create_gig(self.outlet, "x", "not json at all {{{", budget_inr=500)

	def test_create_gig_empty_deliverables_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.create_gig(self.outlet, "x", [], budget_inr=500)

	def test_create_gig_unknown_deliverable_type_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.create_gig(self.outlet, "x", [{"type": "carrier_pigeon", "count": 1}], budget_inr=500)

	def test_create_gig_city_forced_from_outlet_not_spoofable(self):
		result = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=500, category="dining")
		self.assertEqual(frappe.db.get_value("Collab Gig", result["data"]["gig_id"], "city"), "Surat")

	def test_create_gig_open_cap_enforced(self):
		for i in range(10):
			gigs.create_gig(self.outlet, f"Gig {i}", self._deliverables(), budget_inr=500, category="dining")
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.create_gig(self.outlet, "Gig 11", self._deliverables(), budget_inr=500, category="dining")

	# ── list_gigs (creator-facing browse) ─────────────────────────────────

	def test_list_gigs_filters_by_city(self):
		gigs.create_gig(self.outlet, "Surat gig", self._deliverables(), budget_inr=500, category="dining")
		gigs.create_gig(self.other_outlet, "Ahmedabad gig", self._deliverables(), budget_inr=500, category="dining")

		result = gigs.list_gigs(city="Surat")
		titles = [g["title"] for g in result["data"]["gigs"]]
		self.assertIn("Surat gig", titles)
		self.assertNotIn("Ahmedabad gig", titles)

	def test_list_gigs_filters_by_barter_only(self):
		gigs.create_gig(self.outlet, "Cash gig", self._deliverables(), budget_inr=500, category="dining")
		gigs.create_gig(
			self.outlet, "Barter gig", self._deliverables(), budget_inr=0,
			barter_allowed=1, barter_details="meal", category="dining",
		)
		result = gigs.list_gigs(barter_only=1)
		titles = [g["title"] for g in result["data"]["gigs"]]
		self.assertIn("Barter gig", titles)
		self.assertNotIn("Cash gig", titles)

	def test_list_gigs_excludes_filled(self):
		created = gigs.create_gig(self.outlet, "Will be filled", self._deliverables(), budget_inr=500, category="dining")
		gigs.close_gig(self.outlet, created["data"]["gig_id"])
		result = gigs.list_gigs(city="Surat")
		titles = [g["title"] for g in result["data"]["gigs"]]
		self.assertNotIn("Will be filled", titles)

	def test_list_gigs_pagination_has_more(self):
		for i in range(5):
			gigs.create_gig(self.outlet, f"Page gig {i}", self._deliverables(), budget_inr=500, category="dining")
		result = gigs.list_gigs(city="Surat", limit=3)
		self.assertEqual(len(result["data"]["gigs"]), 3)
		self.assertTrue(result["data"]["has_more"])

	# ── apply_to_gig ─────────────────────────────────────────────────────

	def test_apply_creates_offered_deal(self):
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		result = gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])
		self.assertTrue(result["success"])
		deal = frappe.get_doc("Collab Deal", result["data"]["deal_id"])
		self.assertEqual(deal.status, "offered")
		self.assertEqual(deal.deal_type, "cash")
		self.assertEqual(deal.price_inr, 1500)
		self.assertEqual(deal.gig, created["data"]["gig_id"])

	def test_apply_twice_throws(self):
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])

	def test_apply_to_closed_gig_throws(self):
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		gigs.close_gig(self.outlet, created["data"]["gig_id"])
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])

	def test_apply_requesting_cash_on_barter_only_gig_throws(self):
		created = gigs.create_gig(
			self.outlet, "x", self._deliverables(), budget_inr=0,
			barter_allowed=1, barter_details="meal", category="dining",
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"], deal_type="cash")

	def test_apply_to_dual_offer_gig_without_deal_type_throws(self):
		created = gigs.create_gig(
			self.outlet, "x", self._deliverables(), budget_inr=1000,
			barter_allowed=1, barter_details="meal", category="dining",
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])

	def test_apply_to_dual_offer_gig_choosing_barter_succeeds(self):
		created = gigs.create_gig(
			self.outlet, "x", self._deliverables(), budget_inr=1000,
			barter_allowed=1, barter_details="meal", category="dining",
		)
		result = gigs.apply_to_gig(_PHONE, created["data"]["gig_id"], deal_type="barter", proposed_price_inr=400)
		deal = frappe.get_doc("Collab Deal", result["data"]["deal_id"])
		self.assertEqual(deal.deal_type, "barter")
		self.assertEqual(deal.fair_value_inr, 400)
		self.assertEqual(deal.price_inr, 0)

	# ── eligibility filters ──────────────────────────────────────────────

	def test_apply_below_min_followers_throws(self):
		created = gigs.create_gig(
			self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining", min_followers=50000
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])

	def test_apply_meeting_min_followers_succeeds(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, "meta_followers", 10000)
		created = gigs.create_gig(
			self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining", min_followers=5000
		)
		result = gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])
		self.assertTrue(result["success"])

	def test_apply_below_min_badge_tier_throws(self):
		"""A brand-new creator (0 released deals -> 'new_creator' tier)
		can't apply to a gig gated at 'top_rated'."""
		created = gigs.create_gig(
			self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining", min_badge_tier="top_rated"
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])

	def test_apply_no_badge_requirement_open_to_new_creator(self):
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		result = gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])
		self.assertTrue(result["success"])

	def test_list_gigs_with_phone_filters_out_ineligible(self):
		gigs.create_gig(self.outlet, "Open to all", self._deliverables(), budget_inr=500, category="dining")
		gigs.create_gig(
			self.outlet, "Needs 50k followers", self._deliverables(), budget_inr=500,
			category="dining", min_followers=50000,
		)
		result = gigs.list_gigs(city="Surat", phone=_PHONE)
		titles = [g["title"] for g in result["data"]["gigs"]]
		self.assertIn("Open to all", titles)
		self.assertNotIn("Needs 50k followers", titles)

	def test_list_gigs_without_phone_shows_everything(self):
		gigs.create_gig(
			self.outlet, "Needs 50k followers", self._deliverables(), budget_inr=500,
			category="dining", min_followers=50000,
		)
		result = gigs.list_gigs(city="Surat")
		titles = [g["title"] for g in result["data"]["gigs"]]
		self.assertIn("Needs 50k followers", titles)

	# ── pitch slots ──────────────────────────────────────────────────────

	def test_pitch_slots_new_creator_limit_is_three(self):
		result = gigs.get_my_pitch_slots(_PHONE)
		self.assertEqual(result["data"]["tier"], "new_creator")
		self.assertEqual(result["data"]["limit"], 3)
		self.assertEqual(result["data"]["available"], 3)

	def test_pitch_slots_consumed_by_open_applications(self):
		for i in range(3):
			created = gigs.create_gig(self.outlet, f"Gig {i}", self._deliverables(), budget_inr=500, category="dining")
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])

		slots = gigs.get_my_pitch_slots(_PHONE)
		self.assertEqual(slots["data"]["used"], 3)
		self.assertEqual(slots["data"]["available"], 0)

		one_more = gigs.create_gig(self.outlet, "One too many", self._deliverables(), budget_inr=500, category="dining")
		with self.assertRaises(frappe.exceptions.ValidationError):
			gigs.apply_to_gig(_PHONE, one_more["data"]["gig_id"])

	def test_pitch_slot_frees_up_when_gig_closes(self):
		for i in range(3):
			created = gigs.create_gig(self.outlet, f"Gig {i}", self._deliverables(), budget_inr=500, category="dining")
			gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])
			last_gig_id = created["data"]["gig_id"]

		gigs.close_gig(self.outlet, last_gig_id)  # auto-declines that pending application
		slots = gigs.get_my_pitch_slots(_PHONE)
		self.assertEqual(slots["data"]["available"], 1)

	# ── merchant-side: applications, close ────────────────────────────────

	def test_close_gig_auto_declines_pending_applications(self):
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		applied = gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])

		result = gigs.close_gig(self.outlet, created["data"]["gig_id"])
		self.assertEqual(result["data"]["declined_count"], 1)
		self.assertEqual(frappe.db.get_value("Collab Deal", applied["data"]["deal_id"], "status"), "cancelled")

	def test_list_applications_shows_creator_details(self):
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])
		result = gigs.list_applications(self.outlet, created["data"]["gig_id"])
		self.assertEqual(len(result["data"]["applications"]), 1)
		self.assertEqual(result["data"]["applications"][0]["creator_name"], "GigTestCreator")

	def test_list_applications_shows_barter_value_for_barter_applications(self):
		"""Regression: a barter application's actual offered value lives
		in fair_value_inr (price_inr is 0 for barter, per collab_deal.py's
		money validation) — list_applications must surface it, or the
		merchant dashboard has no way to see what a barter applicant
		proposed."""
		created = gigs.create_gig(
			self.outlet, "barter gig", self._deliverables(), budget_inr=0,
			barter_allowed=1, barter_details="Free meal for two", category="dining",
		)
		gigs.apply_to_gig(_PHONE, created["data"]["gig_id"], deal_type="barter", proposed_price_inr=600)
		result = gigs.list_applications(self.outlet, created["data"]["gig_id"])
		row = result["data"]["applications"][0]
		self.assertEqual(row["deal_type"], "barter")
		self.assertEqual(row["proposed_price_inr"], 0)
		self.assertEqual(row["proposed_fair_value_inr"], 600)

	def test_close_gig_wrong_outlet_denied(self):
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		with self.assertRaises(frappe.exceptions.PermissionError):
			gigs.close_gig(self.other_outlet, created["data"]["gig_id"])

	def test_list_applications_wrong_outlet_denied(self):
		"""A merchant must not be able to read another outlet's gig
		applications by guessing/passing the gig_id — cross-tenant data
		leak, not just a write-permission check."""
		created = gigs.create_gig(self.outlet, "x", self._deliverables(), budget_inr=1500, category="dining")
		gigs.apply_to_gig(_PHONE, created["data"]["gig_id"])
		with self.assertRaises(frappe.exceptions.PermissionError):
			gigs.list_applications(self.other_outlet, created["data"]["gig_id"])

	def test_list_applications_no_gig_selected_returns_empty(self):
		"""Regression: the dashboard's useFrappeGetCall fires on component
		mount even when the gating param is still undefined (no real
		conditional-fetch support in this SDK, verified against its actual
		source) — this used to be a raw 500 TypeError on the missing
		positional args before this endpoint learned to degrade cleanly."""
		result = gigs.list_applications()
		self.assertEqual(result["data"]["applications"], [])
		result2 = gigs.list_applications(outlet_id=self.outlet)  # gig_id still missing
		self.assertEqual(result2["data"]["applications"], [])

	def test_list_my_gigs_no_outlet_returns_empty(self):
		result = gigs.list_my_gigs()
		self.assertEqual(result["data"]["gigs"], [])

	def test_list_my_gigs_includes_requirements_for_detail_view(self):
		"""Regression for the gig-detail sheet: it needs the parsed
		deliverables list plus eligibility fields, not just title/budget."""
		gigs.create_gig(
			self.outlet, "detail test", self._deliverables(), budget_inr=1500,
			category="dining", min_followers=5000, min_badge_tier="verified_creator",
		)
		result = gigs.list_my_gigs(self.outlet)
		row = result["data"]["gigs"][0]
		self.assertEqual(row["deliverables"], [{"type": "native_chills", "count": 2}])
		self.assertEqual(row["min_followers"], 5000)
		self.assertEqual(row["min_badge_tier"], "verified_creator")
		self.assertNotIn("deliverables_json", row)


class TestCollabDealStateMachine(unittest.TestCase):
	"""Direct doctype-level tests — Phase 1 only exposes apply_to_gig
	(which creates 'offered' deals); accept/fund/deliver/release get
	real API endpoints in Phase 3, but the state machine underneath them
	is built now and needs to be provably correct before that layer is
	written on top of it."""

	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-SM-OUTLET"
		if not frappe.db.exists("Outlet", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining", city="Surat")

	def setUp(self):
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": "9300000999",
			"display_name": "SMTestCreator", "status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		# A real fixture, not a fake string — Frappe validates every Link
		# field's target actually exists, on every insert/save, same as
		# it would for a genuine deal in production.
		self.invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name,
		})
		self.invite.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator=%s", self.creator.name)
		frappe.db.sql("DELETE FROM `tabCreator Collab Invite` WHERE creator=%s", self.creator.name)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", self.creator.name)
		frappe.db.commit()

	def _fresh_invite(self):
		"""A second real invite fixture, for tests that need more than
		one origin record (e.g. two deals that can't share the same
		direct_invite)."""
		invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name,
		})
		invite.insert(ignore_permissions=True)
		return invite.name

	def _new_cash_deal(self, **overrides):
		data = {
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": self.invite.name,
			"deal_type": "cash", "price_inr": 1000,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		}
		data.update(overrides)
		return frappe.get_doc(data)

	def _new_barter_deal(self, fair_value_inr=1000, **overrides):
		data = {
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": self.invite.name,
			"deal_type": "barter", "fair_value_inr": fair_value_inr,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		}
		data.update(overrides)
		return frappe.get_doc(data)

	# ── origin ───────────────────────────────────────────────────────────

	def test_no_origin_throws(self):
		deal = self._new_cash_deal(direct_invite=None)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.insert(ignore_permissions=True)

	def test_two_origins_throws(self):
		gig = frappe.get_doc({
			"doctype": "Collab Gig", "outlet": self.outlet, "title": "x",
			"deliverables_json": '[{"type":"native_chills","count":1}]', "budget_inr": 500, "category": "dining",
		})
		gig.insert(ignore_permissions=True)
		deal = self._new_cash_deal(gig=gig.name)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.insert(ignore_permissions=True)
		frappe.db.sql("DELETE FROM `tabCollab Gig` WHERE name=%s", gig.name)

	# ── money consistency ────────────────────────────────────────────────

	def test_cash_deal_zero_price_throws(self):
		deal = self._new_cash_deal(price_inr=0)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.insert(ignore_permissions=True)

	def test_cash_deal_with_fair_value_throws(self):
		deal = self._new_cash_deal(fair_value_inr=500)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.insert(ignore_permissions=True)

	def test_barter_deal_zero_fair_value_throws(self):
		deal = self._new_barter_deal(fair_value_inr=0)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.insert(ignore_permissions=True)

	def test_barter_deal_with_price_throws(self):
		deal = self._new_barter_deal(price_inr=200)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.insert(ignore_permissions=True)

	def test_cash_commission_defaults_to_10_pct(self):
		deal = self._new_cash_deal()
		deal.insert(ignore_permissions=True)
		self.assertEqual(deal.commission_pct, 10)

	def test_cash_commission_drops_to_5_pct_with_flamezo_mention(self):
		deal = self._new_cash_deal(flamezo_mention_verified=1)
		deal.insert(ignore_permissions=True)
		self.assertEqual(deal.commission_pct, 5)

	def test_barter_commission_forced_to_zero(self):
		deal = self._new_barter_deal(commission_pct=10)
		deal.insert(ignore_permissions=True)
		self.assertEqual(deal.commission_pct, 0)

	# ── escrow derivation ────────────────────────────────────────────────

	def test_cash_always_requires_escrow(self):
		deal = self._new_cash_deal(price_inr=50)  # even a tiny cash deal
		deal.insert(ignore_permissions=True)
		self.assertEqual(deal.escrow_required, 1)

	def test_barter_under_ceiling_skips_escrow(self):
		deal = self._new_barter_deal(fair_value_inr=250)
		deal.insert(ignore_permissions=True)
		self.assertEqual(deal.escrow_required, 0)

	def test_barter_at_or_above_ceiling_requires_escrow(self):
		deal = self._new_barter_deal(fair_value_inr=300)
		deal.insert(ignore_permissions=True)
		self.assertEqual(deal.escrow_required, 1)

	# ── state transitions ────────────────────────────────────────────────

	def test_new_deal_must_start_offered(self):
		deal = self._new_cash_deal(status="accepted")
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.insert(ignore_permissions=True)

	def test_illegal_transition_offered_to_delivered_throws(self):
		deal = self._new_cash_deal()
		deal.insert(ignore_permissions=True)
		deal.status = "delivered"
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.save(ignore_permissions=True)

	def test_illegal_transition_from_terminal_state_throws(self):
		deal = self._new_barter_deal(fair_value_inr=250)  # escrow-exempt, can reach delivered directly
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"
		deal.save(ignore_permissions=True)
		deal.status = "delivered"
		deal.save(ignore_permissions=True)
		deal.status = "released"
		deal.save(ignore_permissions=True)
		deal.status = "accepted"  # trying to reopen a released deal
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.save(ignore_permissions=True)

	def test_barter_handshake_path_skips_funded(self):
		"""Sub-₹300 barter: accepted -> delivered directly, no funding step
		since escrow_required is false."""
		deal = self._new_barter_deal(fair_value_inr=250)
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"
		deal.save(ignore_permissions=True)
		deal.status = "delivered"
		deal.save(ignore_permissions=True)  # should NOT throw
		self.assertIsNotNone(deal.delivered_at)
		self.assertIsNone(deal.funded_at)

	def test_cash_deal_cannot_skip_funding(self):
		deal = self._new_cash_deal()
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"
		deal.save(ignore_permissions=True)
		deal.status = "delivered"
		with self.assertRaises(frappe.exceptions.ValidationError):
			deal.save(ignore_permissions=True)

	def test_cash_deal_full_happy_path_stamps_all_timestamps(self):
		deal = self._new_cash_deal()
		deal.insert(ignore_permissions=True)
		for status in ("accepted", "funded", "delivered", "released"):
			deal.status = status
			deal.save(ignore_permissions=True)
		self.assertIsNotNone(deal.accepted_at)
		self.assertIsNotNone(deal.funded_at)
		self.assertIsNotNone(deal.delivered_at)
		self.assertIsNotNone(deal.released_at)

	def test_dispute_then_refund_path(self):
		deal = self._new_barter_deal(fair_value_inr=250)
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"; deal.save(ignore_permissions=True)
		deal.status = "delivered"; deal.save(ignore_permissions=True)
		deal.status = "disputed"; deal.save(ignore_permissions=True)
		deal.status = "refunded"; deal.save(ignore_permissions=True)  # should not throw

	# ── barter value tracking (194R) ─────────────────────────────────────

	def test_barter_value_booked_only_on_release(self):
		deal = self._new_barter_deal(fair_value_inr=250)
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"; deal.save(ignore_permissions=True)
		self.assertEqual(flt_ytd(self.creator.name), 0)
		deal.status = "delivered"; deal.save(ignore_permissions=True)
		self.assertEqual(flt_ytd(self.creator.name), 0)  # not yet — only release books it
		deal.status = "released"; deal.save(ignore_permissions=True)
		self.assertEqual(flt_ytd(self.creator.name), 250)

	def test_barter_value_accumulates_across_deals_same_fy(self):
		for _ in range(2):
			deal = self._new_barter_deal(fair_value_inr=250, direct_invite=self._fresh_invite())
			deal.insert(ignore_permissions=True)
			deal.status = "accepted"; deal.save(ignore_permissions=True)
			deal.status = "delivered"; deal.save(ignore_permissions=True)
			deal.status = "released"; deal.save(ignore_permissions=True)
		self.assertEqual(flt_ytd(self.creator.name), 500)

	def test_barter_value_resets_on_fy_rollover(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"barter_value_ytd_inr": 19000, "barter_value_fy": "2020-21",  # a long-past FY
		})
		deal = self._new_barter_deal(fair_value_inr=250)
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"; deal.save(ignore_permissions=True)
		deal.status = "delivered"; deal.save(ignore_permissions=True)
		deal.status = "released"; deal.save(ignore_permissions=True)
		# Should reset to 0 then add 250, NOT accumulate onto the stale 19000
		self.assertEqual(flt_ytd(self.creator.name), 250)

	def test_cash_deal_release_does_not_touch_barter_value(self):
		deal = self._new_cash_deal()
		deal.insert(ignore_permissions=True)
		for status in ("accepted", "funded", "delivered", "released"):
			deal.status = status
			deal.save(ignore_permissions=True)
		self.assertEqual(flt_ytd(self.creator.name), 0)


def flt_ytd(creator_name):
	return frappe.utils.flt(frappe.db.get_value("Flamezo Creator", creator_name, "barter_value_ytd_inr"))


if __name__ == "__main__":
	unittest.main()
