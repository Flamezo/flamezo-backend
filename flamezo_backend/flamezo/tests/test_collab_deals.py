# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for api/collab_deals.py — the deal lifecycle beyond 'offered'
(accept, fund, deliver, release) plus escrow bookkeeping and the
objection-window auto-release job.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, add_to_date, now_datetime, today

from flamezo_backend.flamezo.api import collab_deals as deals
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-DEAL"
_PHONE = "9300000801"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabEscrow Transaction` WHERE deal IN (SELECT name FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s))", _PHONE)
	frappe.db.sql("DELETE FROM `tabDelivery Proof` WHERE deal IN (SELECT name FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s))", _PHONE)
	frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql(f"DELETE FROM `tabCreator Collab Invite` WHERE outlet LIKE '{_PREFIX}%%'")
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.sql(f"DELETE FROM `tabChills` WHERE outlet LIKE '{_PREFIX}%%'")
	frappe.db.commit()


def _fake_razorpay_client(order_id="order_TESTFAKE123"):
	client = MagicMock()
	client.order.create.return_value = {"id": order_id}
	return client


class TestCollabDeals(unittest.TestCase):
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
			"flamezo_backend.flamezo.api.collab_deals.has_active_customer_session", return_value=True
		)
		self._session_patch.start()

		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": _PHONE,
			"display_name": "DealTestCreator", "status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		self.invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name,
		})
		self.invite.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._session_patch.stop()
		_cleanup()

	def _cash_deal(self, status="offered", price_inr=1000, **overrides):
		data = {
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": self.invite.name, "deal_type": "cash", "price_inr": price_inr,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		}
		data.update(overrides)
		doc = frappe.get_doc(data)
		doc.insert(ignore_permissions=True)
		if status != "offered":
			self._advance(doc, status)
		return doc

	def _barter_deal(self, status="offered", fair_value_inr=1000, **overrides):
		data = {
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": self.invite.name, "deal_type": "barter", "fair_value_inr": fair_value_inr,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		}
		data.update(overrides)
		doc = frappe.get_doc(data)
		doc.insert(ignore_permissions=True)
		if status != "offered":
			self._advance(doc, status)
		return doc

	def _advance(self, doc, target_status):
		"""Walk a deal through the real state machine up to target_status —
		exercises collab_deal.py's own transition validation rather than
		writing straight to the DB."""
		path = ["offered", "accepted", "funded", "delivered", "released"]
		for status in path[1:path.index(target_status) + 1]:
			if status == "funded" and doc.deal_type == "barter":
				continue  # barter skips funded
			doc.status = status
			doc.save(ignore_permissions=True)
		return doc

	def _chills_post(self, creator=None):
		post = frappe.get_doc({
			"doctype": "Chills", "outlet": self.outlet, "creator": creator or self.creator.name,
			"status": "published", "video_url": "https://example.com/test.mp4",
		})
		post.insert(ignore_permissions=True)
		return post.name

	# ── accept_application (merchant) ───────────────────────────────────

	def test_accept_application_succeeds(self):
		deal = self._cash_deal()
		result = deals.accept_application(self.outlet, deal.name)
		self.assertEqual(result["data"]["status"], "accepted")

	def test_accept_application_wrong_outlet_throws(self):
		deal = self._cash_deal()
		with self.assertRaises(frappe.exceptions.PermissionError):
			deals.accept_application(self.other_outlet, deal.name)

	def test_accept_application_wrong_status_throws(self):
		deal = self._cash_deal(status="accepted")
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.accept_application(self.outlet, deal.name)

	# ── accept_deal (creator, direct invite) ────────────────────────────

	def test_accept_deal_direct_invite_succeeds(self):
		deal = self._cash_deal()
		result = deals.accept_deal(_PHONE, deal.name)
		self.assertEqual(result["data"]["status"], "accepted")

	def test_accept_deal_not_yours_throws(self):
		other = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": "9300000802",
			"display_name": "OtherCreator", "status": "approved",
		})
		other.insert(ignore_permissions=True)
		deal = self._cash_deal()
		with self.assertRaises(frappe.exceptions.PermissionError):
			deals.accept_deal("9300000802", deal.name)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", other.name)
		frappe.db.commit()

	# ── fund_deal ────────────────────────────────────────────────────────

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_fund_deal_creates_order_and_escrow_row(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted")
		result = deals.fund_deal(self.outlet, deal.name)
		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["razorpay_order_id"], "order_TESTFAKE123")

		escrow = frappe.db.get_value(
			"Escrow Transaction", {"deal": deal.name},
			["amount_inr", "platform_fee_inr", "creator_net_inr", "state"], as_dict=True,
		)
		self.assertEqual(escrow.amount_inr, 1000)
		self.assertEqual(escrow.platform_fee_inr, 100)  # 10% flat commission
		self.assertEqual(escrow.creator_net_inr, 900)
		self.assertEqual(escrow.state, "held")

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_fund_deal_wrong_status_throws(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal()  # still offered
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.fund_deal(self.outlet, deal.name)

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_fund_deal_barter_throws(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._barter_deal(status="accepted", fair_value_inr=1000)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.fund_deal(self.outlet, deal.name)

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_fund_deal_twice_throws(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted")
		deals.fund_deal(self.outlet, deal.name)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.fund_deal(self.outlet, deal.name)

	# ── webhook confirmation path ────────────────────────────────────────

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_mark_deal_funded_advances_status(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted")
		deals.fund_deal(self.outlet, deal.name)
		deals.mark_deal_funded(deal.name, "pay_TESTFAKE123")
		deal.reload()
		self.assertEqual(deal.status, "funded")
		self.assertEqual(
			frappe.db.get_value("Escrow Transaction", {"deal": deal.name}, "razorpay_payment_id"),
			"pay_TESTFAKE123",
		)

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_mark_deal_funded_is_idempotent_on_retry(self, mock_client_factory):
		"""Razorpay retries webhooks until it gets a 2xx — a duplicate
		delivery must not throw or double-advance."""
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted")
		deals.fund_deal(self.outlet, deal.name)
		deals.mark_deal_funded(deal.name, "pay_TESTFAKE123")
		deals.mark_deal_funded(deal.name, "pay_TESTFAKE123")  # should no-op, not throw
		deal.reload()
		self.assertEqual(deal.status, "funded")

	# ── mark_delivered — native ──────────────────────────────────────────
	# Uses barter deals under the ₹300 handshake ceiling (real
	# escrow_required=0, not an override — cash always forces
	# escrow_required=1 by design, see collab_deal.py's
	# _derive_escrow_required) so these tests exercise the generic
	# delivery flow without needing a funded cash deal first. Funded-cash
	# specific behaviour is covered separately below.

	def test_mark_delivered_native_chills_succeeds(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		result = deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		self.assertEqual(result["data"]["status"], "delivered")
		proof = frappe.db.get_value(
			"Delivery Proof", {"deal": deal.name},
			["verification_method", "disclosure_verified"], as_dict=True,
		)
		self.assertEqual(proof.verification_method, "native_first_party")
		self.assertEqual(proof.disclosure_verified, 1)

	def test_mark_delivered_native_post_not_yours_throws(self):
		other = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": "9300000803",
			"display_name": "OtherCreator2", "status": "approved",
		})
		other.insert(ignore_permissions=True)
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post(creator=other.name)
		with self.assertRaises(frappe.exceptions.PermissionError):
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		frappe.db.sql("DELETE FROM `tabChills` WHERE name=%s", post_id)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", other.name)
		frappe.db.commit()

	def test_mark_delivered_native_post_wrong_outlet_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post = frappe.get_doc({
			"doctype": "Chills", "outlet": self.other_outlet, "creator": self.creator.name,
			"status": "published", "video_url": "https://example.com/test.mp4",
		})
		post.insert(ignore_permissions=True)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post.name)

	def test_mark_delivered_cash_requires_funded_when_escrow_required(self):
		deal = self._cash_deal(status="accepted")  # escrow_required always true for cash
		post_id = self._chills_post()
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)

	def test_mark_delivered_reused_proof_throws(self):
		deal1 = self._barter_deal(status="accepted", fair_value_inr=100)
		deal2 = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal1.name, "native_chills", native_post_id=post_id)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal2.name, "native_chills", native_post_id=post_id)

	# ── mark_delivered — instagram (stubbed pending verification) ───────

	def test_mark_delivered_instagram_reel_records_pending(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		result = deals.mark_delivered(_PHONE, deal.name, "instagram_reel", instagram_media_id="ig_media_123")
		self.assertEqual(result["data"]["status"], "pending_verification")
		deal.reload()
		self.assertEqual(deal.status, "accepted")  # must NOT advance on an unverified claim

	def test_mark_delivered_instagram_missing_media_id_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "instagram_reel")

	def test_mark_delivered_instagram_story_requires_screenshot(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "instagram_story", instagram_media_id="ig_media_456")

	# ── release ──────────────────────────────────────────────────────────

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_approve_release_cash_transitions_and_releases_escrow(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted")
		deals.fund_deal(self.outlet, deal.name)
		deals.mark_deal_funded(deal.name, "pay_X")
		deal.reload()
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)

		result = deals.approve_release(self.outlet, deal.name)
		self.assertEqual(result["data"]["status"], "released")
		self.assertEqual(
			frappe.db.get_value("Escrow Transaction", {"deal": deal.name}, "state"), "released"
		)

	def test_approve_release_barter_books_value_and_needs_no_escrow_row(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)  # under the ₹300 handshake ceiling
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		deals.approve_release(self.outlet, deal.name)
		deal.reload()
		self.assertEqual(deal.status, "released")
		self.assertFalse(frappe.db.exists("Escrow Transaction", {"deal": deal.name}))
		self.assertEqual(
			frappe.db.get_value("Flamezo Creator", self.creator.name, "barter_value_ytd_inr"), 100
		)

	def test_approve_release_wrong_status_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.approve_release(self.outlet, deal.name)

	def test_approve_release_wrong_outlet_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		with self.assertRaises(frappe.exceptions.PermissionError):
			deals.approve_release(self.other_outlet, deal.name)

	# ── get_deal / list ──────────────────────────────────────────────────

	def test_get_deal_as_creator(self):
		deal = self._cash_deal()
		result = deals.get_deal(deal.name, phone=_PHONE)
		self.assertEqual(result["data"]["deal_id"], deal.name)

	def test_get_deal_as_merchant(self):
		deal = self._cash_deal()
		result = deals.get_deal(deal.name, outlet_id=self.outlet)
		self.assertEqual(result["data"]["deal_id"], deal.name)

	def test_get_deal_no_identity_throws(self):
		deal = self._cash_deal()
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.get_deal(deal.name)

	def test_get_deal_objection_window_present_when_delivered(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		result = deals.get_deal(deal.name, phone=_PHONE)
		self.assertIsNotNone(result["data"]["objection_window_ends_at"])

	def test_list_my_deals(self):
		self._cash_deal()
		result = deals.list_my_deals(_PHONE)
		self.assertEqual(len(result["data"]["deals"]), 1)

	def test_list_my_deals_origin_direct_invite(self):
		"""Regression: a direct-invite deal must report origin
		'direct_invite' so the client knows accept_deal is valid for it."""
		self._cash_deal()
		result = deals.list_my_deals(_PHONE)
		self.assertEqual(result["data"]["deals"][0]["origin"], "direct_invite")

	def test_list_my_deals_origin_gig(self):
		"""Regression for a real bug: a gig-application deal also starts
		'offered', but accept_deal rejects it (already creator-committed
		by applying) — the client needs `origin` to know NOT to show an
		Accept action for this one."""
		gig = frappe.get_doc({
			"doctype": "Collab Gig", "outlet": self.outlet, "title": "origin test",
			"deliverables_json": '[{"type":"native_chills","count":1}]', "budget_inr": 500, "category": "dining",
		})
		gig.insert(ignore_permissions=True)
		deal = frappe.get_doc({
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"gig": gig.name, "deal_type": "cash", "price_inr": 500,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		})
		deal.insert(ignore_permissions=True)

		result = deals.list_my_deals(_PHONE)
		row = next(r for r in result["data"]["deals"] if r["name"] == deal.name)
		self.assertEqual(row["origin"], "gig")
		self.assertEqual(row["status"], "offered")
		# And accept_deal genuinely rejects it — this is the scenario the
		# `origin` field exists to let the client avoid triggering.
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.accept_deal(_PHONE, deal.name)

		frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE name=%s", deal.name)
		frappe.db.sql("DELETE FROM `tabCollab Gig` WHERE name=%s", gig.name)
		frappe.db.commit()

	def test_get_deal_includes_origin(self):
		deal = self._cash_deal()
		result = deals.get_deal(deal.name, phone=_PHONE)
		self.assertEqual(result["data"]["origin"], "direct_invite")

	def test_get_deal_includes_creator_identity_and_timeline(self):
		"""Regression for the deal-detail sheet: it needs the creator's
		name/photo (not just the raw ID) and real transition timestamps
		to render a status timeline, not just the current status."""
		deal = self._cash_deal(status="accepted")
		result = deals.get_deal(deal.name, outlet_id=self.outlet)
		data = result["data"]
		self.assertEqual(data["creator_name"], self.creator.display_name)
		self.assertIn("creator_profile_image", data)
		self.assertEqual(data["outlet_name"], "Test Restaurant " + self.outlet)
		self.assertIsNotNone(data["accepted_at"])
		self.assertIsNone(data["funded_at"])
		self.assertIsNone(data["delivered_at"])
		self.assertIsNone(data["released_at"])

	def test_list_outlet_deals(self):
		self._cash_deal()
		result = deals.list_outlet_deals(self.outlet)
		self.assertEqual(len(result["data"]["deals"]), 1)

	def test_list_outlet_deals_filtered_by_status(self):
		self._cash_deal(status="accepted", escrow_required=0)
		self._cash_deal()  # offered
		result = deals.list_outlet_deals(self.outlet, status="accepted")
		self.assertEqual(len(result["data"]["deals"]), 1)

	def test_list_outlet_deals_no_outlet_returns_empty(self):
		"""Regression: useFrappeGetCall fires on mount even before
		selectedOutlet resolves — must degrade cleanly, not 500."""
		result = deals.list_outlet_deals()
		self.assertEqual(result["data"]["deals"], [])

	def test_list_outlet_deals_includes_creator_identity(self):
		"""Regression for a real UX gap: the dashboard used to show a raw
		creator ID with no name/photo — list_outlet_deals must join
		through to Flamezo Creator for creator_name/creator_profile_image."""
		self._cash_deal()
		result = deals.list_outlet_deals(self.outlet)
		row = result["data"]["deals"][0]
		self.assertIn("creator_name", row)
		self.assertIn("creator_profile_image", row)
		self.assertEqual(row["creator_name"], self.creator.display_name)

	# ── auto_release_escrow job ──────────────────────────────────────────

	def test_auto_release_escrow_releases_past_window(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		frappe.db.set_value(
			"Collab Deal", deal.name, "delivered_at",
			add_to_date(now_datetime(), hours=-(deals.OBJECTION_WINDOW_HOURS + 1)),
		)
		frappe.db.commit()
		deals.auto_release_escrow()
		deal.reload()
		self.assertEqual(deal.status, "released")

	def test_auto_release_escrow_skips_within_window(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		deals.auto_release_escrow()
		deal.reload()
		self.assertEqual(deal.status, "delivered")

	# ── adversarial / edge cases ─────────────────────────────────────────

	def test_barter_above_ceiling_full_lifecycle_release_does_not_crash(self):
		"""Regression for a real bug: a barter deal >= the 300 handshake
		ceiling has escrow_required=1 but fund_deal refuses barter
		outright — release used to crash trying to load an Escrow
		Transaction row that could never exist."""
		deal = self._barter_deal(status="accepted", fair_value_inr=500)
		self.assertEqual(deal.escrow_required, 1)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		result = deals.approve_release(self.outlet, deal.name)
		self.assertEqual(result["data"]["status"], "released")
		self.assertFalse(frappe.db.exists("Escrow Transaction", {"deal": deal.name}))

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_fund_deal_fee_math_with_fractional_price(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted", price_inr=999.99)
		deals.fund_deal(self.outlet, deal.name)
		escrow = frappe.db.get_value(
			"Escrow Transaction", {"deal": deal.name},
			["amount_inr", "platform_fee_inr", "creator_net_inr"], as_dict=True,
		)
		self.assertAlmostEqual(escrow.amount_inr, 999.99, places=2)
		self.assertAlmostEqual(escrow.platform_fee_inr, 99.999, places=2)
		self.assertAlmostEqual(escrow.creator_net_inr, 899.991, places=2)
		self.assertAlmostEqual(escrow.platform_fee_inr + escrow.creator_net_inr, escrow.amount_inr, places=2)

	def test_mark_delivered_twice_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		post_id_2 = self._chills_post()
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id_2)

	def test_approve_release_twice_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		deals.approve_release(self.outlet, deal.name)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.approve_release(self.outlet, deal.name)

	def test_mark_delivered_without_active_session_throws(self):
		self._session_patch.stop()
		try:
			with patch(
				"flamezo_backend.flamezo.api.collab_deals.has_active_customer_session", return_value=False
			):
				deal = self._barter_deal(status="accepted", fair_value_inr=100)
				post_id = self._chills_post()
				with self.assertRaises(frappe.exceptions.AuthenticationError):
					deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		finally:
			self._session_patch.start()

	def test_accept_deal_nonexistent_deal_throws(self):
		with self.assertRaises(frappe.exceptions.DoesNotExistError):
			deals.accept_deal(_PHONE, "DEAL-DOES-NOT-EXIST")

	def test_get_deal_nonexistent_deal_throws(self):
		with self.assertRaises(frappe.exceptions.DoesNotExistError):
			deals.get_deal("DEAL-DOES-NOT-EXIST", phone=_PHONE)

	def test_get_deal_no_deal_id_returns_null_data(self):
		"""Regression: useFrappeGetCall fires on mount even before a deal
		is selected — must degrade cleanly, not 500."""
		result = deals.get_deal()
		self.assertIsNone(result["data"])

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_fund_deal_wrong_outlet_throws(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted")
		with self.assertRaises(frappe.exceptions.PermissionError):
			deals.fund_deal(self.other_outlet, deal.name)
		# and no escrow row was created by the rejected attempt
		self.assertFalse(frappe.db.exists("Escrow Transaction", {"deal": deal.name}))

	def test_mark_delivered_native_deliverable_missing_post_id_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=None)

	def test_mark_delivered_unknown_deliverable_type_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "tiktok_video", native_post_id="x")

	def test_mark_delivered_nonexistent_native_post_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)
		with self.assertRaises(frappe.exceptions.DoesNotExistError):
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id="CHILLS-DOES-NOT-EXIST")

	# ── deadline enforcement ─────────────────────────────────────────────

	def test_mark_delivered_past_deadline_throws(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100, deadline=add_days(today(), -1))
		post_id = self._chills_post()
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)

	def test_mark_delivered_on_deadline_day_succeeds(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100, deadline=today())
		post_id = self._chills_post()
		result = deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		self.assertEqual(result["data"]["status"], "delivered")

	# ── expire_overdue_deals job ─────────────────────────────────────────

	def test_expire_overdue_deals_cancels_never_funded_barter(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100, deadline=add_days(today(), -1))
		deals.expire_overdue_deals()
		deal.reload()
		self.assertEqual(deal.status, "cancelled")

	def test_expire_overdue_deals_leaves_future_deadline_untouched(self):
		deal = self._barter_deal(status="accepted", fair_value_inr=100)  # default deadline is +7 days
		deals.expire_overdue_deals()
		deal.reload()
		self.assertEqual(deal.status, "accepted")

	def test_expire_overdue_deals_leaves_delivered_untouched(self):
		"""A deal already delivered before its deadline shouldn't be
		swept up as a no-show just because the deadline has now passed —
		auto_release_escrow (objection window), not this job, owns it."""
		deal = self._barter_deal(status="accepted", fair_value_inr=100, deadline=add_days(today(), -1))
		post_id = self._chills_post()
		frappe.db.set_value("Collab Deal", deal.name, "deadline", add_days(today(), 1))
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		frappe.db.set_value("Collab Deal", deal.name, "deadline", add_days(today(), -1))
		frappe.db.commit()
		deals.expire_overdue_deals()
		deal.reload()
		self.assertEqual(deal.status, "delivered")

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_expire_overdue_deals_refunds_funded_cash_deal(self, mock_client_factory):
		client = _fake_razorpay_client()
		mock_client_factory.return_value = client
		deal = self._cash_deal(status="accepted", deadline=add_days(today(), 1))
		deals.fund_deal(self.outlet, deal.name)
		deals.mark_deal_funded(deal.name, "pay_OVERDUE1")
		frappe.db.set_value("Collab Deal", deal.name, "deadline", add_days(today(), -1))
		frappe.db.commit()

		deals.expire_overdue_deals()

		deal.reload()
		self.assertEqual(deal.status, "cancelled")
		escrow_state = frappe.db.get_value("Escrow Transaction", {"deal": deal.name}, "state")
		self.assertEqual(escrow_state, "refunded")
		client.payment.refund.assert_called_once()
		refund_call_args = client.payment.refund.call_args
		self.assertEqual(refund_call_args[0][0], "pay_OVERDUE1")

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_expire_overdue_deals_no_refund_for_unfunded_accepted_cash_deal(self, mock_client_factory):
		client = _fake_razorpay_client()
		mock_client_factory.return_value = client
		deal = self._cash_deal(status="accepted", deadline=add_days(today(), -1))
		deals.expire_overdue_deals()
		deal.reload()
		self.assertEqual(deal.status, "cancelled")
		client.payment.refund.assert_not_called()

	# ── verify_deal_payment (synchronous dashboard-side confirmation) ────

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_verify_deal_payment_valid_signature_funds_deal(self, mock_client_factory):
		client = _fake_razorpay_client()
		client.utility.verify_payment_signature.return_value = True
		mock_client_factory.return_value = client
		deal = self._cash_deal(status="accepted")
		deals.fund_deal(self.outlet, deal.name)

		result = deals.verify_deal_payment(
			self.outlet, deal.name, "order_TESTFAKE123", "pay_SYNC1", "sig_SYNC1",
		)
		self.assertEqual(result["data"]["status"], "funded")
		deal.reload()
		self.assertEqual(deal.status, "funded")
		client.utility.verify_payment_signature.assert_called_once_with({
			"razorpay_order_id": "order_TESTFAKE123",
			"razorpay_payment_id": "pay_SYNC1",
			"razorpay_signature": "sig_SYNC1",
		})

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_verify_deal_payment_bad_signature_does_not_fund(self, mock_client_factory):
		client = _fake_razorpay_client()
		client.utility.verify_payment_signature.side_effect = Exception("bad signature")
		mock_client_factory.return_value = client
		deal = self._cash_deal(status="accepted")
		deals.fund_deal(self.outlet, deal.name)

		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.verify_deal_payment(
				self.outlet, deal.name, "order_TESTFAKE123", "pay_BAD", "sig_BAD",
			)
		deal.reload()
		self.assertEqual(deal.status, "accepted")  # must NOT advance on a failed verification

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_verify_deal_payment_then_webhook_retry_is_idempotent(self, mock_client_factory):
		"""The sync-verify path and the async webhook path both call
		mark_deal_funded — whichever lands first must not let the second
		double-advance or error."""
		client = _fake_razorpay_client()
		client.utility.verify_payment_signature.return_value = True
		mock_client_factory.return_value = client
		deal = self._cash_deal(status="accepted")
		deals.fund_deal(self.outlet, deal.name)

		deals.verify_deal_payment(self.outlet, deal.name, "order_TESTFAKE123", "pay_SYNC2", "sig_SYNC2")
		deals.mark_deal_funded(deal.name, "pay_SYNC2")  # webhook arrives after, same payment
		deal.reload()
		self.assertEqual(deal.status, "funded")

	@patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client")
	def test_verify_deal_payment_wrong_outlet_throws(self, mock_client_factory):
		mock_client_factory.return_value = _fake_razorpay_client()
		deal = self._cash_deal(status="accepted")
		with self.assertRaises(frappe.exceptions.PermissionError):
			deals.verify_deal_payment(self.other_outlet, deal.name, "order_X", "pay_X", "sig_X")


if __name__ == "__main__":
	unittest.main()
