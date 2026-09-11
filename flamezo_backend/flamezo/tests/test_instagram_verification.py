# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for utils/instagram_verification.py — the real Graph API
delivery-verification polling job, plus the caption-parsing helpers
(handle extraction, mention matching, ASCI disclosure-tag matching)
covered directly since they're pure functions worth pinning precisely.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, today

from flamezo_backend.flamezo.api import collab_deals as deals
from flamezo_backend.flamezo.tests.utils import make_restaurant
from flamezo_backend.flamezo.utils import instagram_verification as iv

_PREFIX = "TEST-IGVERIFY"
_PHONE = "9300001201"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabDelivery Proof` WHERE deal IN (SELECT name FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s))", _PHONE)
	frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql(f"DELETE FROM `tabCreator Collab Invite` WHERE outlet LIKE '{_PREFIX}%%'")
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestCaptionHelpers(unittest.TestCase):
	"""Pure functions — no DB, no mocking needed."""

	def test_extract_handle_from_full_url(self):
		self.assertEqual(iv._extract_handle("https://instagram.com/spice.route.cafe/"), "spice.route.cafe")

	def test_extract_handle_from_www_url(self):
		self.assertEqual(iv._extract_handle("https://www.instagram.com/spice.route.cafe"), "spice.route.cafe")

	def test_extract_handle_from_bare_at_handle(self):
		self.assertEqual(iv._extract_handle("@Spice.Route.Cafe"), "spice.route.cafe")

	def test_extract_handle_strips_query_string(self):
		self.assertEqual(iv._extract_handle("https://instagram.com/spice.route.cafe?hl=en"), "spice.route.cafe")

	def test_extract_handle_blank_returns_empty(self):
		self.assertEqual(iv._extract_handle(""), "")
		self.assertEqual(iv._extract_handle(None), "")

	def test_caption_mentions_handle_case_insensitive(self):
		self.assertTrue(iv.caption_mentions_handle("Loved it @Spice.Route.Cafe today!", "spice.route.cafe"))

	def test_caption_mentions_handle_false_when_absent(self):
		self.assertFalse(iv.caption_mentions_handle("Loved brunch today!", "spice.route.cafe"))

	def test_caption_disclosure_tag_variants(self):
		for tag in ("#Ad", "#SPONSORED", "#promotion", "#PaidPartnership"):
			self.assertTrue(iv.caption_has_disclosure_tag(f"Great food today {tag}"), f"{tag} should qualify")

	def test_caption_disclosure_tag_absent(self):
		self.assertFalse(iv.caption_has_disclosure_tag("Great food today #foodie #yum"))

	def test_caption_disclosure_tag_empty_caption(self):
		self.assertFalse(iv.caption_has_disclosure_tag(""))
		self.assertFalse(iv.caption_has_disclosure_tag(None))


class TestVerifyPendingInstagramProof(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-OUTLET"
		if not frappe.db.exists("Outlet", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining", city="Surat")
		frappe.db.set_value("Outlet", cls.outlet, "instagram_url", "https://instagram.com/testigverifyoutlet")

	def setUp(self):
		_cleanup()
		self._session_patch = patch(
			"flamezo_backend.flamezo.api.collab_deals.has_active_customer_session", return_value=True
		)
		self._session_patch.start()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": _PHONE,
			"display_name": "IGVerifyCreator", "status": "approved",
			"oauth_token": "fake_long_lived_token",
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

	def _pending_ig_deal_and_proof(self, deliverable_type="instagram_reel"):
		deal = frappe.get_doc({
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": self.invite.name, "deal_type": "barter", "fair_value_inr": 100,
			"terms_json": "{}", "deadline": add_days(today(), 7),
		})
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"
		deal.save(ignore_permissions=True)
		screenshot = "https://example.com/screenshot.jpg" if deliverable_type == "instagram_story" else None
		result = deals.mark_delivered(
			_PHONE, deal.name, deliverable_type, instagram_media_id="ig_media_999", screenshot_backup=screenshot,
		)
		self.assertEqual(result["data"]["status"], "pending_verification")
		proof_name = frappe.db.get_value("Delivery Proof", {"deal": deal.name}, "name")
		return deal, proof_name

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_verify_matches_and_advances_deal(self, mock_fetch):
		deal, proof_name = self._pending_ig_deal_and_proof()
		mock_fetch.return_value = {
			"caption": "Amazing dinner @testigverifyoutlet tonight! #Ad",
			"timestamp": frappe.utils.now_datetime().isoformat(),
			"permalink": "https://instagram.com/p/xyz",
			"username": "igverifycreator",
		}
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertTrue(result["verified"])

		proof = frappe.get_doc("Delivery Proof", proof_name)
		self.assertEqual(proof.verification_method, "graph_api")
		self.assertEqual(proof.disclosure_verified, 1)
		self.assertIsNotNone(proof.verified_at)

		deal.reload()
		self.assertEqual(deal.status, "delivered")

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_verify_fails_when_no_handle_mention(self, mock_fetch):
		deal, proof_name = self._pending_ig_deal_and_proof()
		mock_fetch.return_value = {
			"caption": "Amazing dinner tonight! #Ad", "timestamp": frappe.utils.now_datetime().isoformat(),
		}
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertFalse(result["verified"])
		self.assertEqual(result["reason"], "caption_does_not_mention_outlet")
		deal.reload()
		self.assertNotEqual(deal.status, "delivered")

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_verify_fails_without_disclosure_tag(self, mock_fetch):
		"""Regression guard for the exact ASCI-compliance rule the
		blueprint requires — a real venue mention with NO disclosure must
		still fail, never silently pass."""
		deal, proof_name = self._pending_ig_deal_and_proof()
		mock_fetch.return_value = {
			"caption": "Amazing dinner @testigverifyoutlet tonight!",
			"timestamp": frappe.utils.now_datetime().isoformat(),
		}
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertFalse(result["verified"])
		self.assertEqual(result["reason"], "missing_disclosure_tag")

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_verify_fails_outside_plausible_window(self, mock_fetch):
		deal, proof_name = self._pending_ig_deal_and_proof()
		old_timestamp = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-60).isoformat()
		mock_fetch.return_value = {
			"caption": "Amazing dinner @testigverifyoutlet tonight! #Sponsored",
			"timestamp": old_timestamp,
		}
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertFalse(result["verified"])
		self.assertEqual(result["reason"], "posted_outside_plausible_window")

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_verify_handles_graph_api_error_gracefully(self, mock_fetch):
		deal, proof_name = self._pending_ig_deal_and_proof()
		mock_fetch.return_value = {"error": {"message": "Media not found", "code": 100}}
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertFalse(result["verified"])
		self.assertIn("graph_api_error", result["reason"])

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_verify_handles_fetch_exception_gracefully(self, mock_fetch):
		deal, proof_name = self._pending_ig_deal_and_proof()
		mock_fetch.side_effect = Exception("network timeout")
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertFalse(result["verified"])
		self.assertEqual(result["reason"], "fetch_failed")

	def test_verify_no_creator_token_fails_cleanly(self):
		frappe.db.set_value("Flamezo Creator", self.creator.name, "oauth_token", "")
		deal, proof_name = self._pending_ig_deal_and_proof()
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertFalse(result["verified"])
		self.assertEqual(result["reason"], "no_valid_creator_token")

	def test_verify_no_outlet_handle_fails_cleanly(self):
		frappe.db.set_value("Outlet", self.outlet, "instagram_url", "")
		deal, proof_name = self._pending_ig_deal_and_proof()
		result = iv.verify_pending_instagram_proof(proof_name)
		frappe.db.set_value("Outlet", self.outlet, "instagram_url", "https://instagram.com/testigverifyoutlet")  # restore for other tests
		self.assertFalse(result["verified"])
		self.assertEqual(result["reason"], "outlet_has_no_instagram_handle_on_file")

	# ── story deliverable (needs screenshot, per existing mark_delivered rule) ─

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_verify_story_deliverable_matches(self, mock_fetch):
		deal, proof_name = self._pending_ig_deal_and_proof(deliverable_type="instagram_story")
		mock_fetch.return_value = {
			"caption": "@testigverifyoutlet #Ad", "timestamp": frappe.utils.now_datetime().isoformat(),
		}
		result = iv.verify_pending_instagram_proof(proof_name)
		self.assertTrue(result["verified"])

	# ── poll_pending_instagram_deliveries job ────────────────────────────

	@patch("flamezo_backend.flamezo.utils.instagram_verification.fetch_media_detail")
	def test_poll_job_verifies_matching_and_skips_cancelled_deals(self, mock_fetch):
		deal1, proof1 = self._pending_ig_deal_and_proof()
		mock_fetch.return_value = {
			"caption": "@testigverifyoutlet #Ad", "timestamp": frappe.utils.now_datetime().isoformat(),
		}
		# A second deal that's already cancelled shouldn't be scanned at all.
		deal2, proof2 = self._pending_ig_deal_and_proof()
		frappe.db.set_value("Collab Deal", deal2.name, "status", "cancelled")
		frappe.db.commit()

		result = iv.poll_pending_instagram_deliveries()
		self.assertEqual(result["scanned"], 1)
		self.assertEqual(result["verified"], 1)
		self.assertEqual(result["errors"], 0)

		deal1.reload()
		self.assertEqual(deal1.status, "delivered")

	def test_poll_job_one_bad_row_does_not_block_others(self):
		deal1, proof1 = self._pending_ig_deal_and_proof()

		def _side_effect(proof):
			if proof == proof1:
				raise Exception("boom")
			return {"verified": False, "reason": "n/a"}

		with patch(
			"flamezo_backend.flamezo.utils.instagram_verification.verify_pending_instagram_proof",
			side_effect=_side_effect,
		):
			result = iv.poll_pending_instagram_deliveries()
		self.assertEqual(result["errors"], 1)


if __name__ == "__main__":
	unittest.main()
