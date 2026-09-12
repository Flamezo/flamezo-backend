# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for api/collab_disputes.py — the Phase 4 dispute lifecycle
(raise -> evidence -> review -> resolved -> optional appeal -> closed),
its money-movement on resolution, the SLA sweep job, and the badge
consequence wired into utils/creator_badges.py.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, add_to_date, now_datetime, today

from flamezo_backend.flamezo.api import collab_deals as deals
from flamezo_backend.flamezo.api import collab_disputes as disputes
from flamezo_backend.flamezo.tests.utils import make_restaurant
from flamezo_backend.flamezo.utils import creator_badges

_PREFIX = "TEST-DISP"
_PHONE = "9300000901"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCollab Dispute` WHERE deal IN (SELECT name FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s))", _PHONE)
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


class TestCollabDisputes(unittest.TestCase):
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
		self._session_patch_disp = patch(
			"flamezo_backend.flamezo.api.collab_disputes.has_active_customer_session", return_value=True
		)
		self._session_patch_disp.start()

		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": _PHONE,
			"display_name": "DisputeTestCreator", "status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		self.invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name,
		})
		self.invite.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._session_patch.stop()
		self._session_patch_disp.stop()
		_cleanup()

	def _chills_post(self):
		post = frappe.get_doc({
			"doctype": "Chills", "outlet": self.outlet, "creator": self.creator.name,
			"status": "published", "video_url": "https://example.com/test.mp4",
		})
		post.insert(ignore_permissions=True)
		return post.name

	def _delivered_cash_deal(self, price_inr=1000):
		"""Cash deal walked all the way to 'delivered' — the only state a
		dispute can be raised against."""
		client = _fake_razorpay_client()
		with patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client", return_value=client):
			deal = frappe.get_doc({
				"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
				"direct_invite": self.invite.name, "deal_type": "cash", "price_inr": price_inr,
				"terms_json": "{}", "deadline": add_days(today(), 7),
			})
			deal.insert(ignore_permissions=True)
			deal.status = "accepted"
			deal.save(ignore_permissions=True)
			deals.fund_deal(self.outlet, deal.name)
			deals.mark_deal_funded(deal.name, "pay_DISPTEST")
			deal.reload()
			post_id = self._chills_post()
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
			deal.reload()
		return deal

	def _delivered_barter_deal(self, fair_value_inr=100):
		deal = frappe.get_doc({
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": self.invite.name, "deal_type": "barter", "fair_value_inr": fair_value_inr,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		})
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"
		deal.save(ignore_permissions=True)
		post_id = self._chills_post()
		deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post_id)
		deal.reload()
		return deal

	# ── raise_dispute ────────────────────────────────────────────────────

	def test_raise_dispute_by_merchant_moves_deal_and_escrow_to_disputed(self):
		deal = self._delivered_cash_deal()
		result = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)
		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["status"], "evidence")
		deal.reload()
		self.assertEqual(deal.status, "disputed")
		self.assertEqual(
			frappe.db.get_value("Escrow Transaction", {"deal": deal.name}, "state"), "disputed"
		)

	def test_raise_dispute_by_creator_succeeds(self):
		deal = self._delivered_barter_deal()
		result = disputes.raise_dispute(deal.name, "low_quality", phone=_PHONE)
		self.assertTrue(result["success"])

	def test_raise_dispute_wrong_status_throws(self):
		deal = self._delivered_barter_deal()
		deals.approve_release(self.outlet, deal.name)  # already released
		with self.assertRaises(frappe.exceptions.ValidationError):
			disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)

	def test_raise_second_dispute_while_open_throws(self):
		deal = self._delivered_barter_deal()
		disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)
		with self.assertRaises(frappe.exceptions.ValidationError):
			disputes.raise_dispute(deal.name, "low_quality", phone=_PHONE)

	def test_raise_dispute_wrong_outlet_throws(self):
		deal = self._delivered_barter_deal()
		with self.assertRaises(frappe.exceptions.PermissionError):
			disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.other_outlet)

	def test_raise_dispute_blocks_release(self):
		"""The whole point of Phase 4 — collab_deals.approve_release must
		refuse once a dispute exists (its _has_dispute_doctype check
		activates the moment this doctype is real)."""
		deal = self._delivered_barter_deal()
		disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)
		with self.assertRaises(frappe.exceptions.ValidationError):
			deals.approve_release(self.outlet, deal.name)

	def test_raise_dispute_blocks_auto_release(self):
		deal = self._delivered_barter_deal()
		disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)
		frappe.db.set_value(
			"Collab Deal", deal.name, "delivered_at",
			add_to_date(now_datetime(), hours=-(deals.OBJECTION_WINDOW_HOURS + 1)),
		)
		frappe.db.commit()
		deals.auto_release_escrow()
		deal.reload()
		self.assertEqual(deal.status, "disputed")  # must NOT have auto-released

	# ── submit_evidence ──────────────────────────────────────────────────

	def test_submit_evidence_both_sides_advances_to_review(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		disputes.submit_evidence(d, text="merchant side", outlet_id=self.outlet)
		result = disputes.submit_evidence(d, text="creator side", phone=_PHONE)
		self.assertEqual(result["data"]["status"], "review")

	def test_submit_evidence_one_side_stays_in_evidence(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		result = disputes.submit_evidence(d, text="merchant side", outlet_id=self.outlet)
		self.assertEqual(result["data"]["status"], "evidence")

	def test_submit_evidence_empty_throws(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with self.assertRaises(frappe.exceptions.ValidationError):
			disputes.submit_evidence(d, outlet_id=self.outlet)

	def test_submit_evidence_not_your_dispute_throws(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with self.assertRaises(frappe.exceptions.PermissionError):
			disputes.submit_evidence(d, text="x", outlet_id=self.other_outlet)

	def test_submit_evidence_wrong_stage_throws(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		disputes.submit_evidence(d, text="a", outlet_id=self.outlet)
		disputes.submit_evidence(d, text="b", phone=_PHONE)  # now in review
		with self.assertRaises(frappe.exceptions.ValidationError):
			disputes.submit_evidence(d, text="late", outlet_id=self.outlet)

	# ── resolve_dispute — permissions ───────────────────────────────────

	def test_resolve_dispute_denied_for_non_admin(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["Customer"]):
			with self.assertRaises(frappe.exceptions.PermissionError):
				disputes.resolve_dispute(d, "release_full", "none")

	# ── resolve_dispute — cash money movement ───────────────────────────

	def test_resolve_dispute_release_full_pays_creator_and_releases_escrow(self):
		deal = self._delivered_cash_deal(price_inr=1000)
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = disputes.resolve_dispute(d, "release_full", "none", resolution_notes="creator delivered fine")
		self.assertEqual(result["data"]["status"], "resolved")
		self.assertEqual(result["data"]["deal_status"], "released")
		escrow = frappe.db.get_value("Escrow Transaction", {"deal": deal.name}, "state")
		self.assertEqual(escrow, "released")
		dispute = frappe.get_doc("Collab Dispute", d)
		self.assertEqual(dispute.resolved_creator_amount_inr, 900)  # 1000 - 10% platform fee
		self.assertEqual(dispute.resolved_merchant_refund_inr, 0)

	def test_resolve_dispute_refund_full_refunds_merchant_via_razorpay(self):
		deal = self._delivered_cash_deal(price_inr=1000)
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		client = MagicMock()
		with patch("flamezo_backend.flamezo.api.collab_disputes.get_razorpay_client", return_value=client):
			with patch("frappe.get_roles", return_value=["System Manager"]):
				result = disputes.resolve_dispute(d, "refund_full", "creator", resolution_notes="never posted")
		self.assertEqual(result["data"]["deal_status"], "refunded")
		self.assertEqual(frappe.db.get_value("Escrow Transaction", {"deal": deal.name}, "state"), "refunded")
		client.payment.refund.assert_called_once()
		amount_paise = client.payment.refund.call_args[0][1]["amount"]
		self.assertEqual(amount_paise, 100000)  # 1000 INR in paise, the full amount
		dispute = frappe.get_doc("Collab Dispute", d)
		self.assertEqual(dispute.resolved_merchant_refund_inr, 1000)

	def test_resolve_dispute_split_partial_computes_correct_amounts(self):
		deal = self._delivered_cash_deal(price_inr=1000)
		d = disputes.raise_dispute(deal.name, "low_quality", outlet_id=self.outlet)["data"]["dispute_id"]
		client = MagicMock()
		with patch("flamezo_backend.flamezo.api.collab_disputes.get_razorpay_client", return_value=client):
			with patch("frappe.get_roles", return_value=["System Manager"]):
				result = disputes.resolve_dispute(d, "split_partial", "creator", split_creator_pct=60)
		self.assertEqual(result["data"]["deal_status"], "released")
		dispute = frappe.get_doc("Collab Dispute", d)
		self.assertEqual(dispute.resolved_creator_amount_inr, 600)
		self.assertEqual(dispute.resolved_merchant_refund_inr, 400)
		amount_paise = client.payment.refund.call_args[0][1]["amount"]
		self.assertEqual(amount_paise, 40000)  # merchant's 400 INR share only

	def test_resolve_dispute_split_partial_missing_pct_throws(self):
		deal = self._delivered_cash_deal()
		d = disputes.raise_dispute(deal.name, "low_quality", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			with self.assertRaises(frappe.exceptions.ValidationError):
				disputes.resolve_dispute(d, "split_partial", "creator")

	def test_resolve_dispute_barter_no_escrow_calls(self):
		deal = self._delivered_barter_deal(fair_value_inr=200)
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		client = MagicMock()
		with patch("flamezo_backend.flamezo.api.collab_disputes.get_razorpay_client", return_value=client):
			with patch("frappe.get_roles", return_value=["System Manager"]):
				result = disputes.resolve_dispute(d, "refund_full", "creator")
		self.assertEqual(result["data"]["deal_status"], "refunded")
		client.payment.refund.assert_not_called()  # nothing to refund, barter never held cash

	def test_resolve_dispute_invalid_outcome_throws(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			with self.assertRaises(frappe.exceptions.ValidationError):
				disputes.resolve_dispute(d, "made_up_outcome", "creator")

	def test_resolve_dispute_wrong_status_throws(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "release_full", "none")
			with self.assertRaises(frappe.exceptions.ValidationError):
				disputes.resolve_dispute(d, "release_full", "none")  # already resolved

	# ── appeal ───────────────────────────────────────────────────────────

	def test_request_appeal_then_resolve_appeal(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "refund_full", "creator")
		result = disputes.request_appeal(d, "the evidence was ignored", phone=_PHONE)
		self.assertEqual(result["data"]["status"], "appealed")
		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = disputes.resolve_appeal(d, "overturned", "re-reviewed, creator was right")
		self.assertEqual(result["data"]["status"], "closed")
		dispute = frappe.get_doc("Collab Dispute", d)
		self.assertEqual(dispute.appeal_outcome, "overturned")

	def test_request_appeal_twice_throws(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "release_full", "none")
		disputes.request_appeal(d, "reason one", phone=_PHONE)
		with self.assertRaises(frappe.exceptions.ValidationError):
			disputes.request_appeal(d, "reason two", phone=_PHONE)

	def test_request_appeal_window_expired_throws(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "release_full", "none")
		frappe.db.set_value(
			"Collab Dispute", d, "resolved_at",
			add_to_date(now_datetime(), hours=-(disputes.APPEAL_WINDOW_HOURS + 1)),
		)
		frappe.db.commit()
		with self.assertRaises(frappe.exceptions.ValidationError):
			disputes.request_appeal(d, "too late", phone=_PHONE)

	def test_resolve_appeal_denied_for_non_admin(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "release_full", "none")
		disputes.request_appeal(d, "reason", phone=_PHONE)
		with patch("frappe.get_roles", return_value=["Customer"]):
			with self.assertRaises(frappe.exceptions.PermissionError):
				disputes.resolve_appeal(d, "upheld")

	# ── get_dispute / list ───────────────────────────────────────────────

	def test_get_dispute_shows_both_sides_evidence(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		disputes.submit_evidence(d, text="merchant evidence", outlet_id=self.outlet)
		result = disputes.get_dispute(d, phone=_PHONE)
		self.assertEqual(len(result["data"]["merchant_evidence"]), 1)
		self.assertEqual(result["data"]["merchant_evidence"][0]["text"], "merchant evidence")
		self.assertEqual(result["data"]["your_role"], "creator")

	def test_get_dispute_no_id_returns_null(self):
		result = disputes.get_dispute()
		self.assertIsNone(result["data"])

	def test_list_my_disputes(self):
		deal = self._delivered_barter_deal()
		disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)
		result = disputes.list_my_disputes(_PHONE)
		self.assertEqual(len(result["data"]["disputes"]), 1)

	def test_list_outlet_disputes(self):
		deal = self._delivered_barter_deal()
		disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)
		result = disputes.list_outlet_disputes(self.outlet)
		self.assertEqual(len(result["data"]["disputes"]), 1)

	def test_list_pending_review_denied_for_non_admin(self):
		with patch("frappe.get_roles", return_value=["Customer"]):
			with self.assertRaises(frappe.exceptions.PermissionError):
				disputes.list_pending_review()

	# ── sweep_dispute_slas ───────────────────────────────────────────────

	def test_sweep_advances_expired_evidence_window(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		frappe.db.set_value(
			"Collab Dispute", d, "evidence_due_at", add_to_date(now_datetime(), hours=-1)
		)
		frappe.db.commit()
		disputes.sweep_dispute_slas()
		self.assertEqual(frappe.db.get_value("Collab Dispute", d, "status"), "review")

	def test_sweep_leaves_fresh_evidence_window_alone(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		disputes.sweep_dispute_slas()
		self.assertEqual(frappe.db.get_value("Collab Dispute", d, "status"), "evidence")

	def test_sweep_auto_closes_stale_resolved_with_no_appeal(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "release_full", "none")
		frappe.db.set_value(
			"Collab Dispute", d, "resolved_at",
			add_to_date(now_datetime(), hours=-(disputes.APPEAL_WINDOW_HOURS + 1)),
		)
		frappe.db.commit()
		disputes.sweep_dispute_slas()
		self.assertEqual(frappe.db.get_value("Collab Dispute", d, "status"), "closed")

	def test_sweep_does_not_close_appealed_disputes(self):
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "release_full", "none")
		disputes.request_appeal(d, "reason", phone=_PHONE)
		frappe.db.set_value(
			"Collab Dispute", d, "resolved_at",
			add_to_date(now_datetime(), hours=-(disputes.APPEAL_WINDOW_HOURS + 1)),
		)
		frappe.db.commit()
		disputes.sweep_dispute_slas()
		self.assertEqual(frappe.db.get_value("Collab Dispute", d, "status"), "appealed")

	# ── badge consequence (utils/creator_badges.py) ─────────────────────

	def _make_top_rated_deal_history(self):
		"""15 released deals, all on-time, avg rating >= 4.5 — the raw
		numbers Top Rated needs before the dispute check even applies."""
		for i in range(15):
			deal = frappe.get_doc({
				"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
				"direct_invite": self.invite.name, "deal_type": "barter", "fair_value_inr": 50,
				"terms_json": "{}", "deadline": add_days(today(), 7), "status": "offered",
			})
			deal.insert(ignore_permissions=True)
			deal.status = "accepted"
			deal.save(ignore_permissions=True)
			post_id = self._chills_post()
			deal.status = "delivered"
			deal.save(ignore_permissions=True)
			deal.status = "released"
			deal.save(ignore_permissions=True)
		self.invite.merchant_rating = 5
		self.invite.save(ignore_permissions=True)
		frappe.db.commit()

	def test_badge_tier_excludes_top_rated_after_lost_dispute(self):
		self._make_top_rated_deal_history()
		self.assertEqual(creator_badges.get_creator_badge_tier(self.creator.name), "top_rated")

		deal = self._delivered_barter_deal()  # barter — no Razorpay refund call to mock
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "refund_full", "creator", resolution_notes="never delivered")

		self.assertNotEqual(creator_badges.get_creator_badge_tier(self.creator.name), "top_rated")

	def test_badge_tier_unaffected_by_merchant_at_fault_dispute(self):
		self._make_top_rated_deal_history()
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "non_payment", phone=_PHONE)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "release_full", "merchant", resolution_notes="merchant was wrong")

		self.assertEqual(creator_badges.get_creator_badge_tier(self.creator.name), "top_rated")

	def test_badge_tier_restored_after_overturned_appeal(self):
		self._make_top_rated_deal_history()
		deal = self._delivered_barter_deal()
		d = disputes.raise_dispute(deal.name, "not_delivered", outlet_id=self.outlet)["data"]["dispute_id"]
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_dispute(d, "refund_full", "creator")
		self.assertNotEqual(creator_badges.get_creator_badge_tier(self.creator.name), "top_rated")

		disputes.request_appeal(d, "unfair", phone=_PHONE)
		with patch("frappe.get_roles", return_value=["System Manager"]):
			disputes.resolve_appeal(d, "overturned", "creator was right after all")

		self.assertEqual(creator_badges.get_creator_badge_tier(self.creator.name), "top_rated")


if __name__ == "__main__":
	unittest.main()
