# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for utils/creator_payout.py + api/creator_kyc.py (Razorpay
Route linked-account onboarding for creators) and the real payout wiring
in collab_deals.py / collab_disputes.py that replaced the old explicit
stub.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, today

from flamezo_backend.flamezo.api import collab_deals as deals
from flamezo_backend.flamezo.api import creator_kyc
from flamezo_backend.flamezo.api import webhooks
from flamezo_backend.flamezo.tests.utils import make_restaurant
from flamezo_backend.flamezo.utils import creator_payout

_PREFIX = "TEST-PAYOUT"
_PHONE = "9300001101"

_FULL_KYC = {
	"legal_name": "Test Creator Legal Name", "pan_number": "ABCDE1234F",
	"owner_email": "creator@example.com", "address": "123 Test St",
	"kyc_city": "Surat", "state": "Gujarat", "zip_code": "395001",
	"bank_account_number": "1234567890", "bank_ifsc": "HDFC0000001",
	"bank_holder_name": "Test Creator Legal Name",
}


def _cleanup():
	frappe.db.sql("DELETE FROM `tabEscrow Transaction` WHERE deal IN (SELECT name FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s))", _PHONE)
	frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql(f"DELETE FROM `tabCreator Collab Invite` WHERE outlet LIKE '{_PREFIX}%%'")
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestCreatorPayout(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-OUTLET"
		if not frappe.db.exists("Outlet", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining", city="Surat")

	def setUp(self):
		_cleanup()
		self._session_patch = patch(
			"flamezo_backend.flamezo.api.creator_kyc.has_active_customer_session", return_value=True
		)
		self._session_patch.start()
		self._deals_session_patch = patch(
			"flamezo_backend.flamezo.api.collab_deals.has_active_customer_session", return_value=True
		)
		self._deals_session_patch.start()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": _PHONE,
			"display_name": "PayoutTestCreator", "status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		self.invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name,
		})
		self.invite.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._session_patch.stop()
		self._deals_session_patch.stop()
		_cleanup()

	# ── ensure_creator_linked_account ────────────────────────────────────

	def test_ensure_linked_account_incomplete_kyc_returns_missing_fields(self):
		result = creator_payout.ensure_creator_linked_account(self.creator.name)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "incomplete_kyc")
		self.assertIn("pan_number", result["missing_fields"])

	@patch("flamezo_backend.flamezo.utils.creator_payout.requests.patch")
	@patch("flamezo_backend.flamezo.utils.creator_payout.requests.post")
	def test_ensure_linked_account_creates_real_account(self, mock_post, mock_patch):
		for k, v in _FULL_KYC.items():
			self.creator.set(k, v)
		self.creator.save(ignore_permissions=True)

		account_resp = MagicMock(); account_resp.json.return_value = {"id": "acc_TESTCREATOR1"}
		stakeholder_resp = MagicMock(); stakeholder_resp.ok = True; stakeholder_resp.text = "{}"
		product_resp = MagicMock(); product_resp.ok = True; product_resp.json.return_value = {"id": "prod_TEST1"}
		mock_post.side_effect = [account_resp, stakeholder_resp, product_resp]
		settlements_resp = MagicMock(); settlements_resp.ok = True
		mock_patch.return_value = settlements_resp

		result = creator_payout.ensure_creator_linked_account(self.creator.name)
		self.assertTrue(result["success"])
		self.assertEqual(result["linked_account_id"], "acc_TESTCREATOR1")
		self.assertTrue(result["created"])

		self.creator.reload()
		self.assertEqual(self.creator.razorpay_linked_account_id, "acc_TESTCREATOR1")
		self.assertEqual(self.creator.razorpay_kyc_status, "under_review")

		# Payload sent for account creation used individual/stakeholder-PAN shape.
		account_call_json = mock_post.call_args_list[0][1]["json"]
		self.assertEqual(account_call_json["business_type"], "individual")
		self.assertNotIn("legal_info", account_call_json)

	def test_ensure_linked_account_idempotent_when_already_linked(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_ALREADY", "razorpay_kyc_status": "activated",
		})
		result = creator_payout.ensure_creator_linked_account(self.creator.name)
		self.assertTrue(result["success"])
		self.assertFalse(result["created"])
		self.assertEqual(result["linked_account_id"], "acc_ALREADY")

	# ── creator_payout_ready / update_creator_kyc_status ─────────────────

	def test_creator_payout_ready_false_when_no_account(self):
		self.assertFalse(creator_payout.creator_payout_ready(self.creator.name))

	def test_creator_payout_ready_true_only_when_activated(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_X", "razorpay_kyc_status": "under_review",
		})
		self.assertFalse(creator_payout.creator_payout_ready(self.creator.name))
		frappe.db.set_value("Flamezo Creator", self.creator.name, "razorpay_kyc_status", "activated")
		self.assertTrue(creator_payout.creator_payout_ready(self.creator.name))

	def test_update_creator_kyc_status_created_maps_to_activated(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, "razorpay_linked_account_id", "acc_Y")
		creator_payout.update_creator_kyc_status("acc_Y", "created")
		self.assertEqual(
			frappe.db.get_value("Flamezo Creator", self.creator.name, "razorpay_kyc_status"), "activated"
		)

	def test_update_creator_kyc_status_monotonic_guard(self):
		"""Once activated, a stale out-of-order pending status must never
		downgrade it — same guard as the Outlet version."""
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_Z", "razorpay_kyc_status": "activated",
		})
		creator_payout.update_creator_kyc_status("acc_Z", "under_review")
		self.assertEqual(
			frappe.db.get_value("Flamezo Creator", self.creator.name, "razorpay_kyc_status"), "activated"
		)

	def test_update_creator_kyc_status_suspended_always_wins(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_W", "razorpay_kyc_status": "activated",
		})
		creator_payout.update_creator_kyc_status("acc_W", "suspended")
		self.assertEqual(
			frappe.db.get_value("Flamezo Creator", self.creator.name, "razorpay_kyc_status"), "suspended"
		)

	# ── execute_route_transfer ────────────────────────────────────────────

	def test_execute_route_transfer_not_ready_fails_cleanly(self):
		result = creator_payout.execute_route_transfer(self.creator.name, "pay_X", 500)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "creator_not_payout_ready")

	@patch("flamezo_backend.flamezo.utils.creator_payout.get_razorpay_client")
	def test_execute_route_transfer_success(self, mock_client_factory):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_READY", "razorpay_kyc_status": "activated",
		})
		client = MagicMock()
		client.payment.transfer.return_value = {"items": [{"id": "trf_TEST123"}]}
		mock_client_factory.return_value = client

		result = creator_payout.execute_route_transfer(self.creator.name, "pay_X", 900)
		self.assertTrue(result["success"])
		self.assertEqual(result["transfer_id"], "trf_TEST123")

		call_args = client.payment.transfer.call_args
		self.assertEqual(call_args[0][0], "pay_X")
		transfer = call_args[0][1]["transfers"][0]
		self.assertEqual(transfer["account"], "acc_READY")
		self.assertEqual(transfer["amount"], 90000)  # 900 INR in paise
		self.assertEqual(transfer["currency"], "INR")

	@patch("flamezo_backend.flamezo.utils.creator_payout.get_razorpay_client")
	def test_execute_route_transfer_razorpay_error_fails_cleanly(self, mock_client_factory):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_READY2", "razorpay_kyc_status": "activated",
		})
		client = MagicMock()
		client.payment.transfer.side_effect = Exception("razorpay says no")
		mock_client_factory.return_value = client
		result = creator_payout.execute_route_transfer(self.creator.name, "pay_X", 500)
		self.assertFalse(result["success"])

	# ── api/creator_kyc.py ────────────────────────────────────────────────

	def test_submit_creator_kyc_saves_fields_and_reports_missing(self):
		partial = dict(_FULL_KYC)
		partial.pop("bank_ifsc")
		result = creator_kyc.submit_creator_kyc(_PHONE, **partial)
		self.assertFalse(result["success"])
		self.assertEqual(result["data"]["error"], "incomplete_kyc")
		self.assertIn("bank_ifsc", result["data"]["missing_fields"])
		self.creator.reload()
		self.assertEqual(self.creator.pan_number, "ABCDE1234F")

	def test_get_creator_kyc_status_reports_missing_fields(self):
		result = creator_kyc.get_creator_kyc_status(_PHONE)
		self.assertFalse(result["data"]["has_linked_account"])
		self.assertIn("pan_number", result["data"]["missing_fields"])

	def test_get_creator_kyc_status_after_full_submission(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_DONE", "razorpay_kyc_status": "activated", **_FULL_KYC,
		})
		result = creator_kyc.get_creator_kyc_status(_PHONE)
		self.assertTrue(result["data"]["has_linked_account"])
		self.assertEqual(result["data"]["kyc_status"], "activated")
		self.assertEqual(result["data"]["missing_fields"], [])

	# ── real payout wiring in collab_deals.approve_release ────────────────

	def _delivered_cash_deal(self, price_inr=1000):
		client = MagicMock()
		client.order.create.return_value = {"id": "order_PAYOUTTEST"}
		with patch("flamezo_backend.flamezo.api.collab_deals.get_razorpay_client", return_value=client):
			deal = frappe.get_doc({
				"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
				"direct_invite": self.invite.name, "deal_type": "cash", "price_inr": price_inr,
				"terms_json": "{}", "deadline": add_days(today(), 7),
			})
			deal.insert(ignore_permissions=True)
			deal.status = "accepted"; deal.save(ignore_permissions=True)
			deals.fund_deal(self.outlet, deal.name)
			deals.mark_deal_funded(deal.name, "pay_PAYOUTTEST")
			deal.reload()
			post = frappe.get_doc({
				"doctype": "Chills", "outlet": self.outlet, "creator": self.creator.name,
				"status": "published", "video_url": "https://example.com/test.mp4",
			})
			post.insert(ignore_permissions=True)
			deals.mark_delivered(_PHONE, deal.name, "native_chills", native_post_id=post.name)
			deal.reload()
		return deal

	def test_approve_release_without_creator_kyc_logs_and_does_not_crash(self):
		"""The whole point of the fallback — a real cash deal releasing
		for a creator who hasn't done payout KYC yet must not crash the
		release; it must still mark the deal released and just log that
		no transfer went out."""
		deal = self._delivered_cash_deal()
		result = deals.approve_release(self.outlet, deal.name)
		self.assertEqual(result["data"]["status"], "released")
		self.assertIsNone(
			frappe.db.get_value("Escrow Transaction", {"deal": deal.name}, "razorpay_transfer_id") or None
		)

	@patch("flamezo_backend.flamezo.utils.creator_payout.get_razorpay_client")
	def test_approve_release_with_creator_kyc_sends_real_transfer(self, mock_payout_client_factory):
		frappe.db.set_value("Flamezo Creator", self.creator.name, {
			"razorpay_linked_account_id": "acc_LIVE", "razorpay_kyc_status": "activated",
		})
		deal = self._delivered_cash_deal(price_inr=1000)

		transfer_client = MagicMock()
		transfer_client.payment.transfer.return_value = {"items": [{"id": "trf_RELEASE1"}]}
		mock_payout_client_factory.return_value = transfer_client

		result = deals.approve_release(self.outlet, deal.name)
		self.assertEqual(result["data"]["status"], "released")

		escrow = frappe.db.get_value(
			"Escrow Transaction", {"deal": deal.name}, ["state", "razorpay_transfer_id"], as_dict=True
		)
		self.assertEqual(escrow.state, "released")
		self.assertEqual(escrow.razorpay_transfer_id, "trf_RELEASE1")

		transfer_call = transfer_client.payment.transfer.call_args
		self.assertEqual(transfer_call[0][0], "pay_PAYOUTTEST")
		self.assertEqual(transfer_call[0][1]["transfers"][0]["account"], "acc_LIVE")
		self.assertEqual(transfer_call[0][1]["transfers"][0]["amount"], 90000)  # 900 = 1000 - 10% commission

	# ── webhooks.py dispatch (real gap found + fixed: account.* events for a
	#    creator's linked account were never reaching Flamezo Creator at all) ──

	def test_account_webhook_updates_creator_kyc_status(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, "razorpay_linked_account_id", "acc_WEBHOOK1")
		payload = {
			"event": "account.activated",
			"payload": {"account": {"entity": {"id": "acc_WEBHOOK1", "status": "activated"}}},
		}
		result = webhooks.handle_account_status(payload)
		self.assertTrue(result["success"])
		self.assertEqual(
			frappe.db.get_value("Flamezo Creator", self.creator.name, "razorpay_kyc_status"), "activated"
		)

	def test_account_webhook_for_unknown_account_is_a_clean_noop(self):
		"""Neither an Outlet nor a Flamezo Creator owns this account_id —
		must not throw, must not touch any record."""
		payload = {
			"event": "account.activated",
			"payload": {"account": {"entity": {"id": "acc_BELONGS_TO_NOBODY", "status": "activated"}}},
		}
		result = webhooks.handle_account_status(payload)
		self.assertTrue(result["success"])

	def test_account_webhook_status_derived_from_event_suffix_for_creator(self):
		"""Some account.* events carry status only in the event name, not
		the entity body — same fallback the Outlet path already relies on."""
		frappe.db.set_value("Flamezo Creator", self.creator.name, "razorpay_linked_account_id", "acc_WEBHOOK2")
		payload = {
			"event": "account.suspended",
			"payload": {"account": {"entity": {"id": "acc_WEBHOOK2"}}},
		}
		webhooks.handle_account_status(payload)
		self.assertEqual(
			frappe.db.get_value("Flamezo Creator", self.creator.name, "razorpay_kyc_status"), "suspended"
		)


if __name__ == "__main__":
	unittest.main()
