# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
End-to-end tests for the Route KYC merchant onboarding flow.

Three surfaces under test:

  1. **`flamezo_backend.flamezo.api.commission.submit_route_kyc`** — the
     public whitelisted endpoint the merchant dashboard form calls.
       * Persists the 6 KYC fields to the Restaurant doc
       * Normalises PAN + IFSC to uppercase, trims whitespace
       * Calls the Route adapter to create a Linked Account (idempotent —
         returns existing on second submission)
       * Returns `incomplete_kyc` when fields are missing
       * Partial updates only overwrite fields the caller explicitly passed

  2. **`flamezo_backend.flamezo.api.webhooks.handle_account_status`** —
     the webhook dispatcher that maps `account.*` events to the Route
     adapter's status updater.
       * Extracts status from event suffix when entity.status is absent
       * Prefers entity.status when both are present
       * Safe no-op when account_id can't be resolved

  3. **`flamezo_backend.flamezo.api.payments.create_tokenization_order`** —
     verifies the May 2026 fix where Razorpay's `total_count` cap of 10
     for yearly subscriptions was being exceeded (used to be 120, broke
     mandate setup with "Exceeds the maximum total_count (10) allowed").

Run with:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_route_kyc
"""

import unittest
from unittest.mock import patch, MagicMock

import frappe

from flamezo_backend.flamezo.tests.utils import (
    make_restaurant,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
)

_PREFIX = "TEST-RKYC"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _full_kyc_kwargs():
    """Return a dict of all KYC fields with realistic-looking dummy values.
    Use as **kwargs to submit_route_kyc."""
    return dict(
        legal_name="Test Bites Pvt Ltd",
        business_type="proprietorship",
        pan_number="ABCDE1234F",
        bank_account_number="50100123456789",
        bank_ifsc="HDFC0001234",
        bank_holder_name="Test Bites Pvt Ltd",
    )


def _pre_populate_kyc(restaurant_name, **overrides):
    """Stamp KYC fields straight onto the Restaurant doc (bypassing the
    submit_route_kyc API) so a test can pre-stage a "fully KYC'd"
    restaurant without going through the Razorpay client mock."""
    defaults = _full_kyc_kwargs()
    defaults.update({"address": "1 Test Lane", "city": "Surat", "state": "Gujarat",
                     "zip_code": "395003", "owner_email": "owner@test.local",
                     "owner_phone": "9876543210"})
    defaults.update(overrides)
    frappe.db.set_value("Outlet", restaurant_name, defaults)
    frappe.db.commit()


# ─── 1. submit_route_kyc — the merchant dashboard endpoint ───────────────────

class TestSubmitRouteKycApi(unittest.TestCase):
    """Integration tests for the public API. Razorpay client is mocked so
    we never hit the live KYC service."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-SRK-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-SRK-")

    def setUp(self):
        self._res = f"{_PREFIX}-SRK-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD",
                        # KYC needs a believable address + contact to pass
                        # the adapter's _missing_kyc_fields() check.
                        address="1 Test Lane", city="Surat", state="Gujarat",
                        zip_code="395003", owner_email="owner@test.local",
                        owner_phone="9876543210",
                        razorpay_account_id="", razorpay_kyc_status="",
                        route_mode="flamezo_hold")
        from flamezo_backend.flamezo.api.commission import submit_route_kyc
        self.submit = submit_route_kyc

    def tearDown(self):
        cleanup_restaurant(self._res)

    # ── Happy path ──

    def test_full_submission_persists_all_six_fields(self):
        """Every KYC field passed to the API must land on the Restaurant doc."""
        with patch("flamezo_backend.flamezo.utils.razorpay_route.get_razorpay_client") as mock_client:
            fake = MagicMock()
            fake.account.create.return_value = {"id": "acc_HAPPY_PATH"}
            fake.request.return_value = {"id": "acc_HAPPY_PATH"}
            mock_client.return_value = fake
            res = self.submit(self._res, **_full_kyc_kwargs())

        self.assertTrue(res.get("success"), msg=f"submit failed: {res!r}")
        row = frappe.db.get_value(
            "Outlet", self._res,
            ["legal_name", "business_type", "pan_number",
             "bank_account_number", "bank_ifsc", "bank_holder_name"],
            as_dict=True,
        )
        self.assertEqual(row["legal_name"], "Test Bites Pvt Ltd")
        self.assertEqual(row["business_type"], "proprietorship")
        self.assertEqual(row["pan_number"], "ABCDE1234F")
        self.assertEqual(row["bank_account_number"], "50100123456789")
        self.assertEqual(row["bank_ifsc"], "HDFC0001234")
        self.assertEqual(row["bank_holder_name"], "Test Bites Pvt Ltd")

    def test_pan_is_uppercased_and_trimmed(self):
        """`abcde1234f` → `ABCDE1234F`; leading/trailing whitespace dropped."""
        with patch("flamezo_backend.flamezo.utils.razorpay_route.get_razorpay_client") as mock_client:
            fake = MagicMock()
            fake.account.create.return_value = {"id": "acc_PAN_NORM"}
            fake.request.return_value = {"id": "acc_PAN_NORM"}
            mock_client.return_value = fake
            kwargs = _full_kyc_kwargs()
            kwargs["pan_number"] = "  abcde1234f  "
            self.submit(self._res, **kwargs)
        stored = frappe.db.get_value("Outlet", self._res, "pan_number")
        self.assertEqual(stored, "ABCDE1234F")

    def test_ifsc_is_uppercased_and_trimmed(self):
        """IFSC is forced UPPER and whitespace-stripped (Razorpay rejects lower)."""
        with patch("flamezo_backend.flamezo.utils.razorpay_route.get_razorpay_client") as mock_client:
            fake = MagicMock()
            fake.account.create.return_value = {"id": "acc_IFSC_NORM"}
            fake.request.return_value = {"id": "acc_IFSC_NORM"}
            mock_client.return_value = fake
            kwargs = _full_kyc_kwargs()
            kwargs["bank_ifsc"] = " hdfc0001234 "
            self.submit(self._res, **kwargs)
        stored = frappe.db.get_value("Outlet", self._res, "bank_ifsc")
        self.assertEqual(stored, "HDFC0001234")

    def test_first_submission_sets_under_review_and_flamezo_hold(self):
        """After a successful first submit, the Restaurant must be in
        `under_review` + `flamezo_hold` so payments keep flowing while
        Razorpay validates."""
        with patch("flamezo_backend.flamezo.utils.razorpay_route.get_razorpay_client") as mock_client:
            fake = MagicMock()
            fake.account.create.return_value = {"id": "acc_FIRST_SUB"}
            fake.request.return_value = {"id": "acc_FIRST_SUB"}
            mock_client.return_value = fake
            res = self.submit(self._res, **_full_kyc_kwargs())

        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("created"), "First submission should set created=True")
        stored = frappe.db.get_value(
            "Outlet", self._res,
            ["razorpay_account_id", "razorpay_kyc_status", "route_mode"],
            as_dict=True,
        )
        self.assertEqual(stored["razorpay_account_id"], "acc_FIRST_SUB")
        self.assertEqual(stored["razorpay_kyc_status"], "under_review")
        self.assertEqual(stored["route_mode"], "flamezo_hold")

    # ── Idempotency ──

    def test_second_submission_returns_existing_account_no_create(self):
        """Once a Razorpay Linked Account is on file, re-submitting must
        return the existing id and NOT hit `client.account.create` again."""
        # Pre-stage an already-linked account.
        frappe.db.set_value("Outlet", self._res, {
            "razorpay_account_id": "acc_ALREADY_THERE",
            "razorpay_kyc_status": "under_review",
        })
        frappe.db.commit()

        with patch("flamezo_backend.flamezo.utils.razorpay_route.get_razorpay_client") as mock_client:
            res = self.submit(self._res, **_full_kyc_kwargs())
            # Razorpay client must NEVER be invoked when an account is on file.
            mock_client.assert_not_called()

        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("created"), "Idempotent re-submit must report created=False")
        self.assertEqual(res.get("linked_account_id"), "acc_ALREADY_THERE")

    # ── Partial updates ──

    def test_partial_update_only_overwrites_provided_fields(self):
        """Caller passes only `bank_holder_name`; PAN must remain untouched."""
        # Stage the doc with full KYC + linked account so the adapter
        # returns existing without creating a new one.
        _pre_populate_kyc(self._res,
                          razorpay_account_id="acc_PARTIAL",
                          razorpay_kyc_status="under_review",
                          pan_number="OLDPN1234X")

        self.submit(self._res, bank_holder_name="New Holder")

        row = frappe.db.get_value(
            "Outlet", self._res,
            ["pan_number", "bank_holder_name"],
            as_dict=True,
        )
        self.assertEqual(row["pan_number"], "OLDPN1234X", "PAN was not passed; must not change")
        self.assertEqual(row["bank_holder_name"], "New Holder")

    # ── Validation: incomplete KYC ──

    def test_missing_required_fields_returns_incomplete_kyc(self):
        """Adapter refuses to call Razorpay if PAN / bank fields aren't set."""
        # Restaurant exists but has no KYC fields (setUp left them blank).
        # Submit only the easy fields, leave PAN + bank blank.
        res = self.submit(self._res,
                          legal_name="Test Bites Pvt Ltd",
                          business_type="proprietorship")
        # Adapter returns the error envelope as-is.
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("error"), "incomplete_kyc")
        self.assertIsInstance(res.get("missing_fields"), list)
        # PAN + Bank account number + IFSC + holder all required.
        missing = res["missing_fields"]
        self.assertIn("PAN Number", missing)
        self.assertIn("Bank Account Number", missing)
        self.assertIn("Bank IFSC", missing)
        self.assertIn("Bank Holder Name", missing)


# ─── 2. handle_account_status — the webhook dispatcher ───────────────────────

class TestHandleAccountStatusWebhook(unittest.TestCase):
    """Razorpay sends `account.*` events when KYC moves through states.
    `handle_account_status` resolves the linked-account id + status, then
    calls the adapter. Verify dispatch + extraction logic."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-WBH-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-WBH-")

    def setUp(self):
        self._res = f"{_PREFIX}-WBH-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD",
                        razorpay_account_id="acc_WEBHOOK_TEST",
                        razorpay_kyc_status="under_review",
                        route_mode="flamezo_hold")
        from flamezo_backend.flamezo.api.webhooks import handle_account_status
        self.handle = handle_account_status

    def tearDown(self):
        cleanup_restaurant(self._res)

    def test_extracts_status_from_event_suffix_when_entity_missing(self):
        """If Razorpay's payload only carries an account_id (no entity.status),
        the handler should fall back to the part after the dot in the event
        name — e.g. `account.activated` → status=activated."""
        payload = {
            "event": "account.activated",
            "account_id": "acc_WEBHOOK_TEST",
            "payload": {"account": {"entity": {"id": "acc_WEBHOOK_TEST"}}},
        }
        res = self.handle(payload)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("status"), "activated")
        stored = frappe.db.get_value(
            "Outlet", self._res,
            ["razorpay_kyc_status", "route_mode"], as_dict=True,
        )
        self.assertEqual(stored["razorpay_kyc_status"], "activated")
        self.assertEqual(stored["route_mode"], "direct_split")

    def test_prefers_entity_status_when_both_are_present(self):
        """If the payload includes `entity.status = 'suspended'` AND the
        event name is `account.updated`, the entity.status wins. This is
        critical for Standard-tier accounts where suspension comes via
        `account.updated` with status in the entity body."""
        payload = {
            "event": "account.updated",
            "payload": {"account": {"entity": {"id": "acc_WEBHOOK_TEST", "status": "suspended"}}},
        }
        res = self.handle(payload)
        self.assertTrue(res.get("success"))
        stored = frappe.db.get_value(
            "Outlet", self._res,
            ["razorpay_kyc_status", "route_mode"], as_dict=True,
        )
        self.assertEqual(stored["razorpay_kyc_status"], "suspended")
        # Suspended must NOT leave route_mode at direct_split.
        self.assertEqual(stored["route_mode"], "flamezo_hold")

    def test_missing_account_id_returns_error_without_raising(self):
        """A malformed payload (no account id anywhere) must be a graceful
        skip — never raise (would crash the worker)."""
        payload = {
            "event": "account.activated",
            "payload": {"account": {"entity": {}}},  # no id
        }
        res = self.handle(payload)
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("error"), "no_account_id")

    def test_unknown_account_id_does_not_corrupt_restaurant_row(self):
        """Receiving an account.activated event for an account_id we've
        never seen (e.g. webhook for a different platform tenant) must not
        update our restaurant."""
        payload = {
            "event": "account.activated",
            "payload": {"account": {"entity": {"id": "acc_TOTALLY_UNKNOWN"}}},
        }
        self.handle(payload)
        # Our restaurant should still be under_review (untouched).
        stored = frappe.db.get_value(
            "Outlet", self._res, "razorpay_kyc_status",
        )
        self.assertEqual(stored, "under_review")


# ─── 3. create_tokenization_order — total_count: 10 fix ──────────────────────

class TestCreateTokenizationOrder(unittest.TestCase):
    """The autopay mandate uses Razorpay's Subscriptions API. As of mid-2026
    Razorpay rejects `total_count > 10` for `period: yearly`, returning:
       'Exceeds the maximum total_count (10) allowed for the given period
        and interval'
    We patched `create_tokenization_order` to send 10 instead of the old
    120. Pin this with a test so a future regression doesn't silently
    break Setup Autopay."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-TOK-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-TOK-")

    def setUp(self):
        self._res = f"{_PREFIX}-TOK-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD",
                        owner_email="owner@test.local",
                        owner_phone="9876543210")
        from flamezo_backend.flamezo.api.payments import create_tokenization_order
        self.create = create_tokenization_order

    def tearDown(self):
        # Clean up any Tokenization Attempt docs we created.
        frappe.db.delete("Tokenization Attempt", {"restaurant": self._res})
        frappe.db.commit()
        cleanup_restaurant(self._res)

    def test_subscription_payload_has_total_count_within_yearly_cap(self):
        """The subscription request sent to Razorpay must have
        `total_count <= 10` so Razorpay accepts it."""
        with patch("flamezo_backend.flamezo.api.payments.get_razorpay_client") as mock_get_client, \
             patch("flamezo_backend.flamezo.api.payments.get_or_create_razorpay_customer", return_value="cust_TEST"), \
             patch("flamezo_backend.flamezo.api.payments.get_or_create_mandate_plan", return_value="plan_TEST"):
            fake = MagicMock()
            fake.subscription.create.return_value = {"id": "sub_TEST"}
            mock_get_client.return_value = fake

            res = self.create(self._res)

        self.assertTrue(res.get("success"), msg=f"create_tokenization_order failed: {res!r}")
        # Inspect the subscription payload that was sent to Razorpay.
        self.assertEqual(fake.subscription.create.call_count, 1)
        payload = fake.subscription.create.call_args[0][0]
        self.assertLessEqual(payload["total_count"], 10,
                             msg=f"total_count={payload['total_count']} exceeds Razorpay's yearly cap of 10")
        # Sanity-check the rest of the payload while we're here.
        self.assertEqual(payload["plan_id"], "plan_TEST")
        self.assertEqual(payload["customer_id"], "cust_TEST")
        self.assertEqual(payload["notes"]["type"], "tokenization")
        self.assertEqual(payload["notes"]["outlet_id"], self._res)

    def test_subscription_payload_total_count_is_exactly_ten(self):
        """We deliberately use the MAX allowed (10) so the tokenization
        subscription has the longest possible validity before cancel —
        gives Razorpay maximum room before they'd auto-renew. Pin this
        exact value so an accidental "let's be conservative and drop it
        to 5" PR doesn't silently shorten mandate validity."""
        with patch("flamezo_backend.flamezo.api.payments.get_razorpay_client") as mock_get_client, \
             patch("flamezo_backend.flamezo.api.payments.get_or_create_razorpay_customer", return_value="cust_TEST"), \
             patch("flamezo_backend.flamezo.api.payments.get_or_create_mandate_plan", return_value="plan_TEST"):
            fake = MagicMock()
            fake.subscription.create.return_value = {"id": "sub_TEST"}
            mock_get_client.return_value = fake

            self.create(self._res)

        payload = fake.subscription.create.call_args[0][0]
        self.assertEqual(payload["total_count"], 10)


if __name__ == "__main__":
    unittest.main()
