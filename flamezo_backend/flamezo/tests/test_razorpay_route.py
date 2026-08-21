# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Production-grade tests for utils/razorpay_route.py — the modular Route adapter.

Covers:

  - decide_route_mode()
      * explicit route_mode='disabled' → disabled
      * explicit route_mode='flamezo_hold' → flamezo_hold
      * Linked Account + KYC activated → direct_split
      * Linked Account but KYC under_review → flamezo_hold
      * No linked account → flamezo_hold (fail-closed)

  - build_transfer_payload()
      * merchant_slice = total - platform_keep
      * Returns single-element list shaped for Razorpay
      * Platform-keep cap protected (≤ total)
      * order_name embedded in notes

  - _normalize_phone() (private helper, exercised via module)
      * +91 prefix stripped
      * Non-digits removed
      * 10-digit max retained

  - _missing_kyc_fields() (via ensure_linked_account dry-run)
      * Empty restaurant → incomplete_kyc with field list
      * Full restaurant → falls through to Razorpay call (which we mock)

  - update_kyc_status()
      * activated flips route_mode to direct_split
      * rejected forces flamezo_hold
      * Unknown status defaults to under_review

Run with:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_razorpay_route
"""

import unittest
from unittest.mock import patch, MagicMock

import frappe

from flamezo_backend.flamezo.tests.utils import (
    make_restaurant,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
)

_PREFIX = "TEST-RR"


# ─── 1. decide_route_mode() ──────────────────────────────────────────────────

class TestDecideRouteMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-DR-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-DR-")

    def setUp(self):
        self._res = f"{_PREFIX}-DR-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD")
        from flamezo_backend.flamezo.utils.razorpay_route import decide_route_mode
        self.decide = decide_route_mode

    def tearDown(self):
        cleanup_restaurant(self._res)

    def _patch_restaurant(self, **fields):
        frappe.db.set_value("Outlet", self._res, fields)
        frappe.db.commit()

    def test_explicit_disabled(self):
        self._patch_restaurant(route_mode="disabled")
        dec = self.decide(self._res)
        self.assertEqual(dec.mode, "disabled")
        self.assertIsNone(dec.linked_account_id)

    def test_explicit_flamezo_hold(self):
        self._patch_restaurant(route_mode="flamezo_hold")
        dec = self.decide(self._res)
        self.assertEqual(dec.mode, "flamezo_hold")

    def test_kyc_activated_with_linked_account_returns_direct_split(self):
        self._patch_restaurant(
            route_mode="",  # let engine derive from KYC
            razorpay_account_id="acc_test123",
            razorpay_kyc_status="activated",
        )
        dec = self.decide(self._res)
        self.assertEqual(dec.mode, "direct_split")
        self.assertEqual(dec.linked_account_id, "acc_test123")
        self.assertEqual(dec.reason, "kyc_activated")

    def test_kyc_under_review_falls_back_to_hold(self):
        self._patch_restaurant(
            route_mode="",
            razorpay_account_id="acc_test_pending",
            razorpay_kyc_status="under_review",
        )
        dec = self.decide(self._res)
        self.assertEqual(dec.mode, "flamezo_hold")
        self.assertIn("kyc_", dec.reason)

    def test_no_linked_account_falls_back_to_hold(self):
        self._patch_restaurant(
            route_mode="",
            razorpay_account_id="",
            razorpay_kyc_status="",
        )
        dec = self.decide(self._res)
        self.assertEqual(dec.mode, "flamezo_hold")

    def test_kyc_rejected_returns_flamezo_hold(self):
        self._patch_restaurant(
            route_mode="",
            razorpay_account_id="acc_rejected",
            razorpay_kyc_status="rejected",
        )
        dec = self.decide(self._res)
        self.assertEqual(dec.mode, "flamezo_hold")


# ─── 2. build_transfer_payload() ─────────────────────────────────────────────

class TestBuildTransferPayload(unittest.TestCase):
    """Pure function — no DB."""

    def setUp(self):
        from flamezo_backend.flamezo.utils.razorpay_route import build_transfer_payload
        self.build = build_transfer_payload

    def test_split_math_basic(self):
        """₹1000 total, ₹15 platform keep → ₹985 merchant slice."""
        payload = self.build("acc_X", 100_000, 1_500, "ORD-1")
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["account"], "acc_X")
        self.assertEqual(payload[0]["amount"], 100_000 - 1_500)
        self.assertEqual(payload[0]["currency"], "INR")
        self.assertEqual(payload[0]["on_hold"], 0)
        self.assertEqual(payload[0]["notes"]["order"], "ORD-1")

    def test_zero_keep_sends_full_to_merchant(self):
        payload = self.build("acc_X", 100_000, 0)
        self.assertEqual(payload[0]["amount"], 100_000)

    def test_negative_keep_treated_as_zero(self):
        payload = self.build("acc_X", 100_000, -500)
        self.assertEqual(payload[0]["amount"], 100_000)

    def test_keep_equal_to_total_yields_zero_merchant(self):
        payload = self.build("acc_X", 100_000, 100_000)
        self.assertEqual(payload[0]["amount"], 0)

    def test_keep_above_total_clamped_to_zero_merchant(self):
        """Defensive — caller in payments.py guards this, but if it slips
        through, merchant_slice must not go negative."""
        payload = self.build("acc_X", 100_000, 999_999)
        self.assertEqual(payload[0]["amount"], 0)

    def test_no_order_name_omits_notes_field(self):
        payload = self.build("acc_X", 100_000, 1_500)
        self.assertEqual(payload[0]["notes"], {})


# ─── 3. _normalize_phone() ───────────────────────────────────────────────────

class TestNormalizePhone(unittest.TestCase):
    def setUp(self):
        from flamezo_backend.flamezo.utils.razorpay_route import _normalize_phone
        self.norm = _normalize_phone

    def test_strips_plus_91(self):
        self.assertEqual(self.norm("+919876543210"), "9876543210")

    def test_strips_leading_91(self):
        self.assertEqual(self.norm("919876543210"), "9876543210")

    def test_strips_spaces_and_dashes(self):
        self.assertEqual(self.norm("+91 98765-43210"), "9876543210")

    def test_keeps_last_ten_when_longer(self):
        # Input has 14 digits; helper must keep the trailing 10.
        self.assertEqual(self.norm("12345987654321"), "5987654321")

    def test_empty_returns_empty(self):
        self.assertEqual(self.norm(""), "")
        self.assertEqual(self.norm(None), "")


# ─── 4. ensure_linked_account() — KYC validation ─────────────────────────────

class TestEnsureLinkedAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-EL-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-EL-")

    def setUp(self):
        self._res = f"{_PREFIX}-EL-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD")
        from flamezo_backend.flamezo.utils.razorpay_route import ensure_linked_account
        self.ensure = ensure_linked_account

    def tearDown(self):
        cleanup_restaurant(self._res)

    def test_returns_existing_when_account_already_present(self):
        frappe.db.set_value("Outlet", self._res, {
            "razorpay_account_id": "acc_existing",
            "razorpay_kyc_status": "activated",
        })
        frappe.db.commit()
        # No Razorpay call should be made — test that no client is invoked.
        with patch("flamezo_backend.flamezo.utils.razorpay_route.get_razorpay_client") as mock_client:
            res = self.ensure(self._res)
            mock_client.assert_not_called()
        self.assertTrue(res["success"])
        self.assertEqual(res["linked_account_id"], "acc_existing")
        self.assertFalse(res["created"])

    def test_returns_incomplete_kyc_when_fields_missing(self):
        """No PAN, no bank account, etc. → adapter must refuse."""
        res = self.ensure(self._res)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "incomplete_kyc")
        self.assertIn("PAN Number", res["missing_fields"])
        self.assertIn("Bank Account Number", res["missing_fields"])

    def test_creates_account_when_kyc_complete(self):
        """Stub the Razorpay client; verify the adapter persists the new id."""
        frappe.db.set_value("Outlet", self._res, {
            "owner_email": "owner@test.com",
            "owner_phone": "+919876543210",
            "owner_name": "Test Owner",
            "pan_number": "ABCDE1234F",
            "bank_account_number": "11223344556677",
            "bank_ifsc": "HDFC0001234",
            "bank_holder_name": "Test Owner",
            "business_type": "proprietorship",
            "address": "123 Street",
            "city": "Surat",
            "state": "Gujarat",
            "zip_code": "395003",
            "gst_number": "27ABCDE1234F1Z5",
        })
        frappe.db.commit()

        fake_client = MagicMock()
        # Adapter calls either client.account.create or client.request — stub
        # both to support either SDK version.
        fake_client.account.create.return_value = {"id": "acc_NEW123"}
        fake_client.request.return_value = {"id": "acc_NEW123"}

        with patch("flamezo_backend.flamezo.utils.razorpay_route.get_razorpay_client",
                   return_value=fake_client):
            res = self.ensure(self._res)

        self.assertTrue(res["success"])
        self.assertEqual(res["linked_account_id"], "acc_NEW123")
        self.assertTrue(res["created"])
        # Persisted to the restaurant
        stored = frappe.db.get_value("Outlet", self._res,
                                     ["razorpay_account_id", "razorpay_kyc_status", "route_mode"],
                                     as_dict=True)
        self.assertEqual(stored["razorpay_account_id"], "acc_NEW123")
        self.assertEqual(stored["razorpay_kyc_status"], "under_review")
        self.assertEqual(stored["route_mode"], "flamezo_hold")


# ─── 5. update_kyc_status() ──────────────────────────────────────────────────

class TestUpdateKycStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-UK-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-UK-")

    def setUp(self):
        self._res = f"{_PREFIX}-UK-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD",
                        razorpay_account_id="acc_TEST_KYC",
                        razorpay_kyc_status="under_review",
                        route_mode="flamezo_hold")
        from flamezo_backend.flamezo.utils.razorpay_route import update_kyc_status
        self.update = update_kyc_status

    def tearDown(self):
        cleanup_restaurant(self._res)

    def test_activated_flips_route_mode_to_direct_split(self):
        self.update("acc_TEST_KYC", "activated")
        stored = frappe.db.get_value("Outlet", self._res,
                                     ["razorpay_kyc_status", "route_mode"], as_dict=True)
        self.assertEqual(stored["razorpay_kyc_status"], "activated")
        self.assertEqual(stored["route_mode"], "direct_split")

    def test_rejected_forces_flamezo_hold(self):
        # Even if route_mode was direct_split, rejection brings it back.
        frappe.db.set_value("Outlet", self._res, "route_mode", "direct_split")
        frappe.db.commit()
        self.update("acc_TEST_KYC", "rejected")
        stored = frappe.db.get_value("Outlet", self._res,
                                     ["razorpay_kyc_status", "route_mode"], as_dict=True)
        self.assertEqual(stored["razorpay_kyc_status"], "rejected")
        self.assertEqual(stored["route_mode"], "flamezo_hold")

    def test_unknown_status_defaults_to_under_review(self):
        self.update("acc_TEST_KYC", "some_new_razorpay_status")
        stored = frappe.db.get_value("Outlet", self._res,
                                     "razorpay_kyc_status")
        self.assertEqual(stored, "under_review")

    def test_unknown_account_id_is_safe_noop(self):
        # Must not raise.
        self.update("acc_DOES_NOT_EXIST", "activated")

    def test_instantly_activated_acts_like_activated(self):
        """`account.instantly_activated` is Razorpay's fast-path for simple
        business types — same effect as a manual `activated`."""
        self.update("acc_TEST_KYC", "instantly_activated")
        stored = frappe.db.get_value("Outlet", self._res,
                                     ["razorpay_kyc_status", "route_mode"], as_dict=True)
        self.assertEqual(stored["razorpay_kyc_status"], "activated")
        self.assertEqual(stored["route_mode"], "direct_split")

    def test_activated_kyc_pending_keeps_route_in_hold(self):
        """`account.activated_kyc_pending` means Razorpay accepted the KYC
        paperwork but full transfer activation is still pending ops review
        — restaurant must NOT be flipped to direct_split yet."""
        self.update("acc_TEST_KYC", "activated_kyc_pending")
        stored = frappe.db.get_value("Outlet", self._res,
                                     ["razorpay_kyc_status", "route_mode"], as_dict=True)
        self.assertEqual(stored["razorpay_kyc_status"], "under_review")
        # Don't promote to direct_split — Razorpay isn't ready to transfer.
        self.assertNotEqual(stored["route_mode"], "direct_split")


if __name__ == "__main__":
    unittest.main()
