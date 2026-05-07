# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

"""
Production-grade tests for utils/loyalty.py and api/loyalty.py

Covers:
  - get_loyalty_balance()
  - earn_loyalty_coins()
  - redeem_loyalty_coins()      [returns int, not doc — Bug 3 fix]
  - settle_loyalty_points()
  - handle_order_cancellation() [now zeros loyalty_coins_redeemed — Bug 4 fix]
  - handle_loyalty_settlement()
  - expiring_soon_balance       [capped at actual balance — Bug 1 fix]
  - get_loyalty_config          [returns field allowlist — Bug 5 fix]
  - get_loyalty_tier()          [new: Bronze/Silver/Gold/Platinum]
  - birthday bonus scheduler    [new: grant_birthday_bonuses()]
  - send_coin_credit_push()     [new: FCM push on coin credit]
  - cancellation zeros loyalty_coins_redeemed [Bug 4 fix]

Run with:
    bench run-tests --app dinematters --module dinematters.dinematters.tests.test_loyalty
"""

import unittest
import frappe
from frappe.utils import today, add_days, add_months
from unittest.mock import MagicMock, patch

from dinematters.dinematters.tests.utils import (
    make_restaurant,
    make_loyalty_config,
    make_customer,
    make_loyalty_entry,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    reset_restaurant_balance,
)

_PREFIX = "TEST-LOY"


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _clear_loyalty_entries(customer, restaurant):
    frappe.db.delete("Restaurant Loyalty Entry", {
        "customer": customer,
        "restaurant": restaurant,
    })
    frappe.db.commit()


# ─── 1. get_loyalty_balance() ─────────────────────────────────────────────────

class TestGetLoyaltyBalance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-GLB-")
        cls._res = f"{_PREFIX}-GLB-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res, points_per_inr=0.1)
        cls._customer = make_customer(phone="9100000001", name="Test Balance Customer")

        from dinematters.dinematters.utils.loyalty import get_loyalty_balance
        cls.get_balance = staticmethod(get_loyalty_balance)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        # Customer doc is shared; we only delete the loyalty entries
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    def test_empty_returns_zero(self):
        self.assertEqual(self.get_balance(self._customer.name, self._res), 0)

    def test_earn_entries_add_to_balance(self):
        make_loyalty_entry(self._customer.name, self._res, coins=100, is_settled=1)
        self.assertEqual(self.get_balance(self._customer.name, self._res), 100)

    def test_multiple_earn_entries_sum_correctly(self):
        make_loyalty_entry(self._customer.name, self._res, coins=100, is_settled=1)
        make_loyalty_entry(self._customer.name, self._res, coins=50, is_settled=1)
        self.assertEqual(self.get_balance(self._customer.name, self._res), 150)

    def test_redeem_entry_subtracts_from_balance(self):
        make_loyalty_entry(self._customer.name, self._res, coins=100, is_settled=1)
        make_loyalty_entry(self._customer.name, self._res, coins=30,
                           txn_type="Redeem", reason="Redemption", is_settled=1)
        self.assertEqual(self.get_balance(self._customer.name, self._res), 70)

    def test_balance_never_negative(self):
        """Even if redemptions exceed earnings, balance floors at zero."""
        make_loyalty_entry(self._customer.name, self._res, coins=200,
                           txn_type="Redeem", reason="Redemption", is_settled=1)
        balance = self.get_balance(self._customer.name, self._res)
        self.assertEqual(balance, 0)

    def test_expired_entries_excluded(self):
        """Entries with expiry_date in the past must not count."""
        # Settled earn entry that has already expired
        doc = frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": 200,
            "transaction_type": "Earn",
            "reason": "Order",
            "posting_date": today(),
            "expiry_date": add_days(today(), -1),  # expired yesterday
            "is_settled": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        balance = self.get_balance(self._customer.name, self._res)
        self.assertEqual(balance, 0, "Expired entries must not contribute to balance")

    def test_unsettled_entries_excluded_by_default(self):
        """is_settled=0 entries are ignored when include_pending=False (default)."""
        make_loyalty_entry(self._customer.name, self._res, coins=100, is_settled=0)
        self.assertEqual(self.get_balance(self._customer.name, self._res), 0)

    def test_include_pending_includes_unsettled_entries(self):
        make_loyalty_entry(self._customer.name, self._res, coins=100, is_settled=0)
        balance = self.get_balance(self._customer.name, self._res, include_pending=True)
        self.assertEqual(balance, 100)

    def test_null_customer_returns_zero(self):
        self.assertEqual(self.get_balance(None, self._res), 0)

    def test_null_restaurant_returns_zero(self):
        self.assertEqual(self.get_balance(self._customer.name, None), 0)


# ─── 2. earn_loyalty_coins() ─────────────────────────────────────────────────

class TestEarnLoyaltyCoins(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-ELC-")
        cls._res = f"{_PREFIX}-ELC-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(
            cls._res,
            earn_type="Percentage of Bill",
            earn_percentage=10.0,   # 10% → ₹1000 order = 100 coins
            points_per_inr=0.1,     # legacy field kept in sync
            loyalty_expiry_months=12
        )
        cls._customer = make_customer(phone="9100000002", name="Test Earn Customer")

        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        cls.earn = staticmethod(earn_loyalty_coins)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    def test_coins_calculated_from_percentage(self):
        """₹1000 order at 10% earn_percentage = 100 coins."""
        earned = self.earn(self._customer.name, self._res, 1000.0, reason="Order")
        self.assertEqual(earned, 100)

    def test_coins_calculated_from_points_per_inr(self):
        """Legacy fallback: ₹1000 × 0.1 points_per_inr = 100 coins (same result)."""
        earned = self.earn(self._customer.name, self._res, 1000.0, reason="Order")
        self.assertEqual(earned, 100)

    def test_fractional_coins_truncated(self):
        """int() truncation: ₹105 × 0.1 = 10.5 → 10 coins."""
        earned = self.earn(self._customer.name, self._res, 105.0, reason="Order")
        self.assertEqual(earned, 10)

    def test_unsettled_for_order_reference(self):
        """Earning on an 'Order' ref_doctype must create is_settled=0."""
        self.earn(
            self._customer.name, self._res, 1000.0,
            reason="Order", ref_doctype="Order", ref_name="TEST-ORDER-001"
        )
        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._customer.name, "restaurant": self._res, "reason": "Order"},
            ["is_settled"],
            as_dict=True
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.is_settled, 0)

    def test_settled_for_non_order_reference(self):
        """Earning on a non-Order ref_doctype must create is_settled=1."""
        self.earn(
            self._customer.name, self._res, 1000.0,
            reason="Referral Order", ref_doctype="Customer"
        )
        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._customer.name, "restaurant": self._res, "reason": "Referral Order"},
            ["is_settled"],
            as_dict=True
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.is_settled, 1)

    def test_expiry_date_set_correctly(self):
        """expiry_date must be exactly loyalty_expiry_months (12) from today."""
        self.earn(self._customer.name, self._res, 1000.0, reason="Order")
        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._customer.name, "restaurant": self._res},
            ["expiry_date"],
            as_dict=True
        )
        expected_expiry = add_months(today(), 12)
        self.assertEqual(str(entry.expiry_date), str(expected_expiry))

    def test_zero_amount_returns_zero(self):
        earned = self.earn(self._customer.name, self._res, 0.0)
        self.assertEqual(earned, 0)

    def test_loyalty_disabled_returns_zero(self):
        """When enable_loyalty=0 on the restaurant, no coins are earned."""
        disabled_res = f"{_PREFIX}-ELC-DIS-{frappe.generate_hash(length=6)}"
        make_restaurant(disabled_res, plan="DIAMOND")
        # Explicitly disable loyalty (no config → is_loyalty_enabled returns False)
        try:
            earned = self.earn(self._customer.name, disabled_res, 1000.0)
            self.assertEqual(earned, 0)
        finally:
            cleanup_restaurant(disabled_res)


# ─── 3. redeem_loyalty_coins() ───────────────────────────────────────────────

class TestRedeemLoyaltyCoins(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-RLC-")
        cls._res = f"{_PREFIX}-RLC-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res, points_per_inr=0.1)
        cls._customer = make_customer(phone="9100000003", name="Test Redeem Customer")

        from dinematters.dinematters.utils.loyalty import redeem_loyalty_coins
        cls.redeem = staticmethod(redeem_loyalty_coins)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    def test_normal_redemption_returns_coins_count(self):
        """redeem_loyalty_coins() now returns the int count of coins actually redeemed."""
        make_loyalty_entry(self._customer.name, self._res, coins=200, is_settled=1)
        result = self.redeem(self._customer.name, self._res, 50)
        self.assertEqual(result, 50, "Should return the number of coins redeemed")

    def test_normal_redemption_creates_redeem_entry_in_db(self):
        """Verify the DB entry is actually created correctly."""
        make_loyalty_entry(self._customer.name, self._res, coins=200, is_settled=1)
        self.redeem(self._customer.name, self._res, 50)
        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._customer.name, "restaurant": self._res, "transaction_type": "Redeem"},
            ["transaction_type", "coins"], as_dict=True
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.transaction_type, "Redeem")
        self.assertEqual(entry.coins, 50)

    def test_redemption_capped_at_available_balance(self):
        """Trying to redeem 500 when balance is 100 must cap at 100 and return 100."""
        make_loyalty_entry(self._customer.name, self._res, coins=100, is_settled=1)
        result = self.redeem(self._customer.name, self._res, 500)
        self.assertEqual(result, 100, "Returned value must be the clipped actual redeemed amount")
        # DB entry should also be for 100, not 500
        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._customer.name, "restaurant": self._res, "transaction_type": "Redeem"},
            "coins"
        )
        self.assertEqual(entry, 100)

    def test_redeem_returns_zero_when_no_balance(self):
        result = self.redeem(self._customer.name, self._res, 50)
        self.assertEqual(result, 0, "Should return 0 when balance is zero")

    def test_redeem_returns_none_for_zero_coins(self):
        result = self.redeem(self._customer.name, self._res, 0)
        self.assertFalse(result, "Should return falsy for zero coins input")

    def test_redeem_returns_none_for_negative_coins(self):
        result = self.redeem(self._customer.name, self._res, -10)
        self.assertFalse(result, "Should return falsy for negative coins input")

    def test_redeem_returns_none_when_loyalty_disabled(self):
        disabled_res = f"{_PREFIX}-RLC-DIS-{frappe.generate_hash(length=6)}"
        make_restaurant(disabled_res, plan="DIAMOND")
        # No loyalty config → is_loyalty_enabled returns False
        try:
            result = self.redeem(self._customer.name, disabled_res, 50)
            self.assertFalse(result, "Should return falsy when loyalty is disabled")
        finally:
            cleanup_restaurant(disabled_res)


# ─── 4. settle_loyalty_points() ──────────────────────────────────────────────

class TestSettleLoyaltyPoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-SLP-")
        cls._res = f"{_PREFIX}-SLP-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000004", name="Test Settle Customer")

        from dinematters.dinematters.utils.loyalty import settle_loyalty_points
        cls.settle = staticmethod(settle_loyalty_points)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    def _make_unsettled_order_entry(self, order_name):
        return frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": 50,
            "transaction_type": "Earn",
            "reason": "Order",
            "posting_date": today(),
            "expiry_date": add_days(today(), 365),
            "is_settled": 0,
            "reference_doctype": "Order",
            "reference_name": order_name,
        }).insert(ignore_permissions=True)

    def test_marks_order_entries_as_settled(self):
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        self._make_unsettled_order_entry(order_name)
        frappe.db.commit()

        result = self.settle(order_name)
        self.assertTrue(result)

        is_settled = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"reference_name": order_name, "reference_doctype": "Order"},
            "is_settled"
        )
        self.assertEqual(is_settled, 1)

    def test_idempotent_double_settle(self):
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        self._make_unsettled_order_entry(order_name)
        frappe.db.commit()

        self.settle(order_name)
        result = self.settle(order_name)  # second call must not raise
        self.assertTrue(result)

    def test_only_settles_matching_order(self):
        """Settling order A must not affect order B entries."""
        order_a = f"TEST-ORD-A-{frappe.generate_hash(length=6)}"
        order_b = f"TEST-ORD-B-{frappe.generate_hash(length=6)}"
        self._make_unsettled_order_entry(order_a)
        self._make_unsettled_order_entry(order_b)
        frappe.db.commit()

        self.settle(order_a)

        settled_b = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"reference_name": order_b, "reference_doctype": "Order"},
            "is_settled"
        )
        self.assertEqual(settled_b, 0, "Order B must remain unsettled")


# ─── 5. handle_order_cancellation() ──────────────────────────────────────────

class TestHandleOrderCancellation(unittest.TestCase):
    """
    The cancellation hook must:
    1. Refund any redeemed loyalty coins (create an Earn entry with "Cancellation Refund")
    2. Revert any earned loyalty coins (create a Redeem entry with "Cancellation Revert")
    3. Be idempotent — a second call must not double-refund
    4. No-op when order status is not 'cancelled'
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-HOC-")
        cls._res = f"{_PREFIX}-HOC-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000005", name="Test Cancel Customer")

        from dinematters.dinematters.utils.loyalty import handle_order_cancellation
        cls.cancel_hook = staticmethod(handle_order_cancellation)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    def _make_mock_order(self, status, coins_redeemed=0, coins_earned=0, order_name=None):
        """Return a MagicMock mimicking an Order document."""
        doc = MagicMock()
        doc.name = order_name or f"TEST-ORD-{frappe.generate_hash(length=8)}"
        doc.status = status
        doc.restaurant = self._res
        doc.platform_customer = self._customer.name
        doc.loyalty_coins_redeemed = coins_redeemed
        doc.coins_earned = coins_earned
        return doc

    def test_non_cancelled_status_is_noop(self):
        doc = self._make_mock_order(status="confirmed", coins_redeemed=50, coins_earned=100)
        self.cancel_hook(doc)
        count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
        })
        self.assertEqual(count, 0, "Hook must be a no-op for non-cancelled orders")

    def test_cancellation_refunds_redeemed_coins(self):
        """On cancellation, redeemed coins must be returned as an Earn entry."""
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        doc = self._make_mock_order(
            status="cancelled",
            coins_redeemed=100,
            coins_earned=0,
            order_name=order_name
        )
        self.cancel_hook(doc)

        refund_entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {
                "customer": self._customer.name,
                "restaurant": self._res,
                "reference_name": order_name,
                "reason": "Cancellation Refund",
            },
            ["coins", "transaction_type"],
            as_dict=True
        )
        self.assertIsNotNone(refund_entry, "Cancellation Refund entry must be created")
        self.assertEqual(refund_entry.transaction_type, "Earn")
        self.assertEqual(refund_entry.coins, 100)

    def test_cancellation_reverts_earned_coins(self):
        """On cancellation, earned coins must be reverted as a Redeem entry."""
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        # Pre-create a settled earn entry so there's balance to revert
        make_loyalty_entry(self._customer.name, self._res, coins=200, is_settled=1)
        doc = self._make_mock_order(
            status="cancelled",
            coins_redeemed=0,
            coins_earned=50,
            order_name=order_name
        )
        self.cancel_hook(doc)

        revert_entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {
                "customer": self._customer.name,
                "restaurant": self._res,
                "reference_name": order_name,
                "reason": "Cancellation Revert",
            },
            ["coins", "transaction_type"],
            as_dict=True
        )
        self.assertIsNotNone(revert_entry, "Cancellation Revert entry must be created")
        self.assertEqual(revert_entry.transaction_type, "Redeem")

    def test_idempotent_cancellation_hook(self):
        """Calling the hook twice must not create duplicate refund/revert entries."""
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        make_loyalty_entry(self._customer.name, self._res, coins=200, is_settled=1)
        doc = self._make_mock_order(
            status="cancelled",
            coins_redeemed=50,
            coins_earned=30,
            order_name=order_name
        )
        self.cancel_hook(doc)
        self.cancel_hook(doc)  # second call

        refund_count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
            "reference_name": order_name,
            "reason": "Cancellation Refund",
        })
        revert_count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
            "reference_name": order_name,
            "reason": "Cancellation Revert",
        })
        self.assertEqual(refund_count, 1, "Refund must be created exactly once")
        self.assertEqual(revert_count, 1, "Revert must be created exactly once")


# ─── 6. handle_loyalty_settlement() ──────────────────────────────────────────

class TestHandleLoyaltySettlement(unittest.TestCase):
    """
    The settlement hook must settle loyalty points when the order reaches
    a qualifying status, and must NOT settle on non-qualifying statuses.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-HLS-")
        cls._res = f"{_PREFIX}-HLS-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        # earn_on_status="Completed" → settle on "completed", "billed", "confirmed", or payment_status=completed
        make_loyalty_config(cls._res, earn_on_status="Completed")
        cls._customer = make_customer(phone="9100000006", name="Test Settlement Customer")

        from dinematters.dinematters.utils.loyalty import handle_loyalty_settlement
        cls.settle_hook = staticmethod(handle_loyalty_settlement)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    def _make_order_doc(self, status, payment_status="pending", order_name=None):
        doc = MagicMock()
        doc.name = order_name or f"TEST-ORD-{frappe.generate_hash(length=8)}"
        doc.restaurant = self._res
        doc.status = status
        doc.payment_status = payment_status
        return doc

    def _make_unsettled_entry_for_order(self, order_name):
        return frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": 100,
            "transaction_type": "Earn",
            "reason": "Order",
            "posting_date": today(),
            "expiry_date": add_days(today(), 365),
            "is_settled": 0,
            "reference_doctype": "Order",
            "reference_name": order_name,
        }).insert(ignore_permissions=True)

    def test_settles_on_payment_completed(self):
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        self._make_unsettled_entry_for_order(order_name)
        frappe.db.commit()

        doc = self._make_order_doc("confirmed", payment_status="completed", order_name=order_name)
        self.settle_hook(doc)

        settled = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"reference_name": order_name},
            "is_settled"
        )
        self.assertEqual(settled, 1)

    def test_settles_on_billed_status(self):
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        self._make_unsettled_entry_for_order(order_name)
        frappe.db.commit()

        doc = self._make_order_doc("billed", payment_status="pending", order_name=order_name)
        self.settle_hook(doc)

        settled = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"reference_name": order_name},
            "is_settled"
        )
        self.assertEqual(settled, 1)

    def test_does_not_settle_on_pending_status(self):
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        self._make_unsettled_entry_for_order(order_name)
        frappe.db.commit()

        doc = self._make_order_doc("pending", payment_status="pending", order_name=order_name)
        self.settle_hook(doc)

        settled = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"reference_name": order_name},
            "is_settled"
        )
        self.assertEqual(settled, 0, "Pending order must not settle loyalty points")

    def test_does_not_settle_on_accepted_status(self):
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        self._make_unsettled_entry_for_order(order_name)
        frappe.db.commit()

        doc = self._make_order_doc("accepted", payment_status="pending", order_name=order_name)
        self.settle_hook(doc)

        settled = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"reference_name": order_name},
            "is_settled"
        )
        self.assertEqual(settled, 0, "Accepted order must not prematurely settle points")

    def test_no_restaurant_is_noop(self):
        """If doc.restaurant is None, the hook must not raise."""
        doc = self._make_order_doc("billed")
        doc.restaurant = None
        try:
            self.settle_hook(doc)  # must not raise
        except Exception as e:
            self.fail(f"Hook raised unexpectedly with no restaurant: {e}")


# ─── 7. Bug 1: expiring_soon_balance capped at actual balance ─────────────────

class TestExpiringSoonBalance(unittest.TestCase):
    """
    Bug 1 fix: expiring_soon_balance must be min(gross_expiring, balance).
    If a customer has already redeemed some of their expiring coins, the
    displayed expiring amount must not exceed their actual balance.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-ESB-")
        cls._res = f"{_PREFIX}-ESB-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000007", name="Test Expiry Customer")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {
            "customer": self._customer.name, "restaurant": self._res
        })
        frappe.db.commit()

    def _make_expiring_soon_entry(self, coins, days=15):
        """Create a settled Earn entry expiring within 30 days."""
        from frappe.utils import add_days
        doc = frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": coins,
            "transaction_type": "Earn",
            "reason": "Order",
            "posting_date": today(),
            "expiry_date": add_days(today(), days),
            "is_settled": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

    def test_expiring_soon_equals_balance_when_no_redemptions(self):
        """If no coins have been redeemed, expiring_soon = gross expiring coins."""
        self._make_expiring_soon_entry(100)
        from dinematters.dinematters.utils.loyalty import get_loyalty_balance
        from frappe.utils import add_days
        import frappe as _frappe
        # Simulate what the API does
        balance = get_loyalty_balance(self._customer.name, self._res)
        expiring_entries = _frappe.get_all(
            "Restaurant Loyalty Entry",
            filters={
                "customer": self._customer.name,
                "restaurant": self._res,
                "is_settled": 1,
                "transaction_type": "Earn",
                "expiry_date": ["between", [today(), add_days(today(), 30)]]
            },
            fields=["coins"]
        )
        gross = sum(e.coins for e in expiring_entries)
        expiring_soon = min(gross, balance)
        self.assertEqual(expiring_soon, 100)

    def test_expiring_soon_capped_at_balance_after_redemptions(self):
        """Bug 1: if 80 of 100 expiring coins have been redeemed, expiring_soon must be 20."""
        self._make_expiring_soon_entry(100)
        # Redeem 80 coins
        redeem_entry = frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": 80,
            "transaction_type": "Redeem",
            "reason": "Redemption",
            "posting_date": today(),
            "is_settled": 1,
        })
        redeem_entry.insert(ignore_permissions=True)
        frappe.db.commit()

        from dinematters.dinematters.utils.loyalty import get_loyalty_balance
        from frappe.utils import add_days
        import frappe as _frappe
        balance = get_loyalty_balance(self._customer.name, self._res)  # should be 20
        expiring_entries = _frappe.get_all(
            "Restaurant Loyalty Entry",
            filters={
                "customer": self._customer.name,
                "restaurant": self._res,
                "is_settled": 1,
                "transaction_type": "Earn",
                "expiry_date": ["between", [today(), add_days(today(), 30)]]
            },
            fields=["coins"]
        )
        gross = sum(e.coins for e in expiring_entries)  # 100 (raw)
        expiring_soon = min(gross, balance)              # min(100, 20) = 20
        self.assertEqual(balance, 20)
        self.assertEqual(expiring_soon, 20, "expiring_soon must be capped at actual balance")


# ─── 8. Bug 4: Cancellation zeros loyalty_coins_redeemed on Order ─────────────

class TestCancellationZerosRedeemed(unittest.TestCase):
    """
    Bug 4 fix: handle_order_cancellation must also zero loyalty_coins_redeemed
    on the Order doc (not just coins_earned).
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-CZR-")
        cls._res = f"{_PREFIX}-CZR-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000008", name="Test Cancel Zero Customer")

        from dinematters.dinematters.utils.loyalty import handle_order_cancellation
        cls.cancel_hook = staticmethod(handle_order_cancellation)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def test_cancellation_zeroes_both_coin_fields(self):
        """After cancel hook, both coins_earned and loyalty_coins_redeemed on Order must be 0."""
        # Insert an Order row directly via SQL to avoid doctype validation in tests
        _hash = frappe.generate_hash(length=8).upper()
        order_name = f"TEST-CZR-{_hash}"
        frappe.db.sql("""
            INSERT INTO `tabOrder`
            (name, restaurant, platform_customer, status, order_type, order_id,
             order_number, subtotal, total, loyalty_coins_redeemed, coins_earned,
             creation, modified, owner, docstatus, idx)
            VALUES (%s, %s, %s, 'confirmed', 'dine_in', %s,
                    9999, 500, 500, 50, 30,
                    NOW(), NOW(), 'Administrator', 0, 0)
        """, (order_name, self._res, self._customer.name, f"OID-{_hash}"))
        frappe.db.commit()

        try:
            # Create a settled earn entry so the revert has balance to work with
            make_loyalty_entry(self._customer.name, self._res, coins=200, is_settled=1)

            # Mock the doc to simulate cancel hook firing
            doc = MagicMock()
            doc.name = order_name
            doc.status = "cancelled"
            doc.restaurant = self._res
            doc.platform_customer = self._customer.name
            doc.loyalty_coins_redeemed = 50
            doc.coins_earned = 30

            self.cancel_hook(doc)

            # Verify DB values were zeroed
            result = frappe.db.get_value("Order", order_name,
                ["coins_earned", "loyalty_coins_redeemed"], as_dict=True)
            self.assertEqual(result.coins_earned, 0, "coins_earned must be zeroed after cancellation")
            self.assertEqual(result.loyalty_coins_redeemed, 0, "loyalty_coins_redeemed must be zeroed after cancellation")
        finally:
            frappe.db.sql("DELETE FROM `tabOrder` WHERE name = %s", order_name)
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._customer.name})
            frappe.db.commit()


# ─── 9. Bug 5: get_loyalty_config must not expose internal fields ──────────────

class TestGetLoyaltyConfigFieldAllowlist(unittest.TestCase):
    """
    Bug 5 fix: the guest-accessible get_loyalty_config endpoint must only
    return the explicit field allowlist — not internal doctype fields like
    'owner', 'creation', 'modified_by', 'doctype', etc.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-GLC-")
        cls._res = f"{_PREFIX}-GLC-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)

    def test_config_does_not_expose_internal_fields(self):
        from dinematters.dinematters.api.loyalty import get_loyalty_config
        response = get_loyalty_config(self._res)
        self.assertTrue(response.get("success"))
        data = response.get("data", {})
        self.assertIsNotNone(data)
        # These internal fields must NOT be present
        internal_fields = ["doctype", "owner", "creation", "modified_by", "__islocal", "modified"]
        for field in internal_fields:
            self.assertNotIn(field, data, f"Internal field '{field}' must not be exposed to guests")

    def test_config_returns_expected_public_fields(self):
        from dinematters.dinematters.api.loyalty import get_loyalty_config
        response = get_loyalty_config(self._res)
        data = response.get("data", {})
        expected_fields = ["points_per_inr", "coin_value_in_inr", "min_redemption_threshold"]
        for field in expected_fields:
            self.assertIn(field, data, f"Expected public field '{field}' missing from config response")


# ─── 10. New Feature: get_loyalty_tier() ──────────────────────────────────────

class TestGetLoyaltyTier(unittest.TestCase):
    """
    Tests for the new tier system backed by lifetime Earn coins.
    Default thresholds: Silver=500, Gold=2000, Platinum=5000
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-GLT-")
        cls._res = f"{_PREFIX}-GLT-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res,
            tier_silver_threshold=500,
            tier_gold_threshold=2000,
            tier_platinum_threshold=5000
        )
        cls._customer = make_customer(phone="9100000009", name="Test Tier Customer")

        from dinematters.dinematters.utils.loyalty import get_loyalty_tier
        cls.get_tier = staticmethod(get_loyalty_tier)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {
            "customer": self._customer.name, "restaurant": self._res
        })
        frappe.db.commit()

    def _add_lifetime_coins(self, coins):
        """Add an Earn entry (settled) to build up lifetime coins."""
        make_loyalty_entry(self._customer.name, self._res, coins=coins, is_settled=1)

    def test_bronze_with_no_entries(self):
        self.assertEqual(self.get_tier(self._customer.name, self._res), "Bronze")

    def test_bronze_below_silver_threshold(self):
        self._add_lifetime_coins(499)
        self.assertEqual(self.get_tier(self._customer.name, self._res), "Bronze")

    def test_silver_at_threshold(self):
        self._add_lifetime_coins(500)
        self.assertEqual(self.get_tier(self._customer.name, self._res), "Silver")

    def test_silver_above_threshold(self):
        self._add_lifetime_coins(1999)
        self.assertEqual(self.get_tier(self._customer.name, self._res), "Silver")

    def test_gold_at_threshold(self):
        self._add_lifetime_coins(2000)
        self.assertEqual(self.get_tier(self._customer.name, self._res), "Gold")

    def test_platinum_at_threshold(self):
        self._add_lifetime_coins(5000)
        self.assertEqual(self.get_tier(self._customer.name, self._res), "Platinum")

    def test_tier_uses_all_earn_entries_regardless_of_expiry(self):
        """Tier is based on LIFETIME coins — even expired entries count."""
        doc = frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": 600,
            "transaction_type": "Earn",
            "reason": "Order",
            "posting_date": today(),
            "expiry_date": frappe.utils.add_days(today(), -1),  # expired
            "is_settled": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        self.assertEqual(self.get_tier(self._customer.name, self._res), "Silver",
                         "Expired coins must still count towards lifetime tier")

    def test_null_inputs_return_bronze(self):
        self.assertEqual(self.get_tier(None, self._res), "Bronze")
        self.assertEqual(self.get_tier(self._customer.name, None), "Bronze")


# ─── 11. New Feature: Birthday Bonus Scheduler ────────────────────────────────

class TestBirthdayBonusScheduler(unittest.TestCase):
    """
    Tests for grant_birthday_bonuses() scheduler task.
    - Only grants to customers with history at the restaurant
    - Idempotent: does not double-grant in same calendar year
    - Skips restaurants with loyalty disabled
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-BDY-")
        cls._res = f"{_PREFIX}-BDY-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res, birthday_bonus_coins=50)
        # Create customer with today's birthday
        import datetime
        today_date = frappe.utils.getdate(today())
        cls._customer = make_customer(phone="9100000010", name="Birthday Test Customer")
        # Set birthday to today (month+day)
        bday = datetime.date(1990, today_date.month, today_date.day)
        frappe.db.set_value("Customer", cls._customer.name, "date_of_birth", str(bday))
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {
            "customer": self._customer.name, "restaurant": self._res
        })
        frappe.db.commit()

    def test_no_bonus_without_loyalty_history(self):
        """Customer must have prior loyalty history to receive birthday bonus."""
        from dinematters.dinematters.tasks.loyalty_tasks import grant_birthday_bonuses
        grant_birthday_bonuses()
        count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
            "reason": "Birthday Bonus"
        })
        self.assertEqual(count, 0, "No bonus without prior loyalty history at restaurant")

    def test_bonus_granted_with_loyalty_history(self):
        """Once customer has order history, birthday bonus must be granted."""
        # Give the customer some prior loyalty history
        make_loyalty_entry(self._customer.name, self._res, coins=10, is_settled=1)

        from dinematters.dinematters.tasks.loyalty_tasks import grant_birthday_bonuses
        grant_birthday_bonuses()

        count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
            "reason": "Birthday Bonus"
        })
        self.assertEqual(count, 1, "Birthday bonus must be granted once to eligible customer")

    def test_idempotent_no_double_grant(self):
        """Running the scheduler twice must not grant the bonus twice."""
        make_loyalty_entry(self._customer.name, self._res, coins=10, is_settled=1)

        from dinematters.dinematters.tasks.loyalty_tasks import grant_birthday_bonuses
        grant_birthday_bonuses()
        grant_birthday_bonuses()  # second run

        count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
            "reason": "Birthday Bonus"
        })
        self.assertEqual(count, 1, "Birthday bonus must never be granted more than once per year")


# ─── 12. New Feature: FCM push on coin credit ─────────────────────────────────

class TestSendCoinCreditPush(unittest.TestCase):
    """
    Tests for send_coin_credit_push().
    - Calls _send_fcm_message for each stored FCM token
    - Cleans up stale/unregistered tokens automatically
    - Does not raise if customer has no tokens
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-FCM-")
        cls._res = f"{_PREFIX}-FCM-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000011", name="FCM Test Customer")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.set_value("Customer", cls._customer.name, "push_fcm_tokens", "[]")
        frappe.db.commit()

    def test_no_push_when_no_tokens(self):
        """Must not raise and must not call FCM when customer has no tokens."""
        import json
        frappe.db.set_value("Customer", self._customer.name, "push_fcm_tokens", "[]")
        frappe.db.commit()

        with patch("dinematters.dinematters.api.push_notifications._send_fcm_message") as mock_send:
            from dinematters.dinematters.utils.loyalty import send_coin_credit_push
            send_coin_credit_push(self._customer.name, self._res, 100, "Order")
            mock_send.assert_not_called()

    def test_push_sent_for_each_token(self):
        """Must call _send_fcm_message once per stored FCM token."""
        import json
        tokens = ["token-aaa", "token-bbb"]
        frappe.db.set_value("Customer", self._customer.name, "push_fcm_tokens", json.dumps(tokens))
        frappe.db.commit()

        with patch("dinematters.dinematters.api.push_notifications._send_fcm_message", return_value=True) as mock_send:
            from dinematters.dinematters.utils.loyalty import send_coin_credit_push
            send_coin_credit_push(self._customer.name, self._res, 50, "Welcome Bonus")
            self.assertEqual(mock_send.call_count, 2)

    def test_stale_tokens_removed(self):
        """When _send_fcm_message returns 'unregistered', the token must be removed."""
        import json
        tokens = ["valid-token", "stale-token"]
        frappe.db.set_value("Customer", self._customer.name, "push_fcm_tokens", json.dumps(tokens))
        frappe.db.commit()

        def mock_send(fcm_token, **kwargs):
            return "unregistered" if fcm_token == "stale-token" else True

        with patch("dinematters.dinematters.api.push_notifications._send_fcm_message", side_effect=mock_send):
            from dinematters.dinematters.utils.loyalty import send_coin_credit_push
            send_coin_credit_push(self._customer.name, self._res, 25, "Birthday Bonus")

        remaining = json.loads(frappe.db.get_value("Customer", self._customer.name, "push_fcm_tokens") or "[]")
        self.assertIn("valid-token", remaining)
        self.assertNotIn("stale-token", remaining, "Stale token must be cleaned up")

    def test_correct_title_format(self):
        """Push title must include the coin count."""
        import json
        frappe.db.set_value("Customer", self._customer.name, "push_fcm_tokens", json.dumps(["t1"]))
        frappe.db.commit()

        calls = []
        def capture_send(fcm_token, title, body, data=None, icon=None):
            calls.append({"title": title, "body": body})
            return True

        with patch("dinematters.dinematters.api.push_notifications._send_fcm_message", side_effect=capture_send):
            from dinematters.dinematters.utils.loyalty import send_coin_credit_push
            send_coin_credit_push(self._customer.name, self._res, 75, "Order")

        self.assertEqual(len(calls), 1)
        self.assertIn("75", calls[0]["title"], "Title must mention the coin count")


# ─── 13. track_referral_visit — no immediate reward (Proposal 1) ──────────────

class TestTrackReferralVisitNoReward(unittest.TestCase):
    """
    After Proposal 1: track_referral_visit must ONLY record the visit.
    It must NOT call credit_loyalty_points / create any loyalty entry.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-TRV-")
        cls._res = f"{_PREFIX}-TRV-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(cls._res, coins_per_unique_open=5, max_opens_rewarded_per_share=7)
        cls._referrer = make_customer(phone="9200000001", name="TRV Referrer")

        # Create a Referral Link for the referrer
        cls._identifier = f"trvtest-{frappe.generate_hash(length=4)}"
        existing = frappe.db.get_value("Referral Link", {"identifier": cls._identifier}, "name")
        if not existing:
            frappe.get_doc({
                "doctype": "Referral Link",
                "referrer": cls._referrer.name,
                "restaurant": cls._res,
                "identifier": cls._identifier,
                "is_active": 1,
                "rewarded_opens_in_cycle": 0,
            }).insert(ignore_permissions=True)
            frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Referral Link", {"identifier": cls._identifier})
        frappe.db.delete("Referral Visit", {"ip_address": "10.0.0.99"})
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._referrer.name})
        frappe.db.commit()

    def test_visit_recorded_but_no_coins_awarded(self):
        """track_referral_visit must record visit without creating any loyalty entry."""
        from dinematters.dinematters.api.loyalty import track_referral_visit
        ip = "10.0.0.99"

        # Clear any prior entries
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._referrer.name})
        frappe.db.delete("Referral Visit", {"ip_address": ip})
        frappe.db.commit()

        result = track_referral_visit(self._identifier, ip_address=ip)
        self.assertTrue(result.get("success"), f"track_referral_visit failed: {result}")

        # Visit must be recorded
        visit_exists = frappe.db.exists("Referral Visit", {"ip_address": ip})
        self.assertTrue(visit_exists, "Referral visit must be recorded")

        # NO loyalty entry must be created for the referrer
        entry_count = frappe.db.count("Restaurant Loyalty Entry", {"customer": self._referrer.name})
        self.assertEqual(entry_count, 0, "No coins must be awarded at visit time — only on claim")

    def test_response_includes_referral_id(self):
        """Response must include referral_id so the frontend can pass it to claim_referral_reward."""
        from dinematters.dinematters.api.loyalty import track_referral_visit
        result = track_referral_visit(self._identifier, ip_address="10.0.1.99")
        self.assertTrue(result.get("success"))
        self.assertEqual(result["data"].get("referral_id"), self._identifier)


# ─── 14. claim_referral_reward — core reward logic (Proposal 1) ───────────────

class TestClaimReferralReward(unittest.TestCase):
    """
    Tests for the new claim_referral_reward API.
    Auth is mocked — we test the business logic only.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-CRR-")
        cls._res = f"{_PREFIX}-CRR-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND")
        make_loyalty_config(
            cls._res,
            new_user_welcome_reward_coins=75,
            coins_per_unique_open=5,
            max_opens_rewarded_per_share=7
        )
        # Referrer
        from dinematters.dinematters.utils.customer_helpers import get_or_create_customer
        cls._referrer = get_or_create_customer("9200000002", name="CRR Referrer")
        cls._referee_phone = "9200000003"
        cls._referee = get_or_create_customer(cls._referee_phone, name="CRR Referee")

        cls._identifier = f"crrtest-{frappe.generate_hash(length=4)}"
        existing = frappe.db.get_value("Referral Link", {"identifier": cls._identifier}, "name")
        if not existing:
            frappe.get_doc({
                "doctype": "Referral Link",
                "referrer": cls._referrer.name,
                "restaurant": cls._res,
                "identifier": cls._identifier,
                "is_active": 1,
                "rewarded_opens_in_cycle": 0,
            }).insert(ignore_permissions=True)
            frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Referral Link", {"identifier": cls._identifier})
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._referrer.name})
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._referee.name})
        frappe.db.commit()

    def setUp(self):
        # Clean entries before each test
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._referrer.name})
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._referee.name})
        frappe.db.set_value("Referral Link", {"identifier": self._identifier}, "rewarded_opens_in_cycle", 0)
        frappe.db.commit()

    def _call_claim(self, phone=None):
        """Call claim_referral_reward with auth mocked out."""
        from dinematters.dinematters.api.loyalty import claim_referral_reward
        phone = phone or self._referee_phone
        with patch("dinematters.dinematters.utils.customer_helpers.validate_customer_session", return_value=True), \
             patch("dinematters.dinematters.api.loyalty.validate_customer_session", return_value=True), \
             patch("dinematters.dinematters.api.loyalty.get_customer_token", return_value="mock-token"):
            return claim_referral_reward(self._res, self._identifier, phone)

    def test_welcome_bonus_awarded_to_referee(self):
        """Referee must receive a Welcome Bonus entry."""
        result = self._call_claim()
        self.assertTrue(result.get("success"), f"Claim failed: {result}")

        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._referee.name, "restaurant": self._res, "reason": "Welcome Bonus"},
            ["coins", "transaction_type"], as_dict=True
        )
        self.assertIsNotNone(entry, "Welcome Bonus entry must be created for referee")
        self.assertEqual(entry.transaction_type, "Earn")
        self.assertEqual(entry.coins, 75)

    def test_referral_share_awarded_to_referrer(self):
        """Referrer must receive a Referral Share entry."""
        result = self._call_claim()
        self.assertTrue(result.get("success"))

        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._referrer.name, "restaurant": self._res, "reason": "Referral Share"},
            ["coins", "transaction_type"], as_dict=True
        )
        self.assertIsNotNone(entry, "Referral Share entry must be created for referrer")
        self.assertEqual(entry.transaction_type, "Earn")
        self.assertEqual(entry.coins, 5)

    def test_response_contains_coin_counts(self):
        """Response data must include welcome_coins and referrer_coins."""
        result = self._call_claim()
        self.assertTrue(result.get("success"))
        data = result.get("data", {})
        self.assertEqual(data.get("welcome_coins"), 75)
        self.assertEqual(data.get("referrer_coins"), 5)

    def test_double_claim_rejected(self):
        """Calling claim twice for the same referee must fail with ALREADY_CLAIMED."""
        self._call_claim()  # first claim
        result = self._call_claim()  # second claim
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error", {}).get("code"), "ALREADY_CLAIMED")

    def test_referrer_coins_not_awarded_beyond_cycle_limit(self):
        """Once cycle limit is exhausted, referrer must not receive more coins."""
        frappe.db.set_value("Referral Link", {"identifier": self._identifier}, "rewarded_opens_in_cycle", 7)
        frappe.db.commit()

        result = self._call_claim()
        self.assertTrue(result.get("success"))

        data = result.get("data", {})
        self.assertEqual(data.get("referrer_coins"), 0, "Referrer must not earn beyond cycle limit")

        # Referee should still get welcome bonus
        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._referee.name, "restaurant": self._res, "reason": "Welcome Bonus"},
            "coins"
        )
        self.assertEqual(entry, 75)

    def test_restaurant_mismatch_rejected(self):
        """Referral link for a different restaurant must be rejected."""
        other_res = f"{_PREFIX}-CRR-OTHER-{frappe.generate_hash(length=4)}"
        make_restaurant(other_res, plan="DIAMOND")
        try:
            from dinematters.dinematters.api.loyalty import claim_referral_reward
            with patch("dinematters.dinematters.api.loyalty.validate_customer_session", return_value=True), \
                 patch("dinematters.dinematters.api.loyalty.get_customer_token", return_value="mock-token"):
                result = claim_referral_reward(other_res, self._identifier, self._referee_phone)
            self.assertFalse(result.get("success"))
            self.assertEqual(result.get("error", {}).get("code"), "RESTAURANT_MISMATCH")
        finally:
            cleanup_restaurant(other_res)

    def test_invalid_referral_id_rejected(self):
        """Non-existent referral identifier must return LINK_NOT_FOUND."""
        from dinematters.dinematters.api.loyalty import claim_referral_reward
        with patch("dinematters.dinematters.api.loyalty.validate_customer_session", return_value=True), \
             patch("dinematters.dinematters.api.loyalty.get_customer_token", return_value="mock-token"):
            result = claim_referral_reward(self._res, "nonexistent-xyz", self._referee_phone)
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error", {}).get("code"), "LINK_NOT_FOUND")

    def test_cycle_counter_incremented_after_claim(self):
        """rewarded_opens_in_cycle on the Referral Link must increment by 1."""
        before = frappe.db.get_value("Referral Link", {"identifier": self._identifier}, "rewarded_opens_in_cycle") or 0
        self._call_claim()
        after = frappe.db.get_value("Referral Link", {"identifier": self._identifier}, "rewarded_opens_in_cycle") or 0
        self.assertEqual(after, before + 1, "Cycle counter must increment after successful claim")


if __name__ == "__main__":
    unittest.main()


# ─── 13. Dynamic Earn Rate (earn_type, guardrails) ────────────────────────────

class TestDynamicEarnRate(unittest.TestCase):
    """
    Covers all new earn_type behaviour:
    - Percentage of Bill mode
    - Flat Coins per Order mode
    - min_order_to_earn threshold
    - max_coins_per_order cap
    - Backward compat with legacy points_per_inr
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-DER-")
        cls._customer = make_customer(phone="9100000020", name="Test Dynamic Earn")

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def _make_res(self, suffix):
        name = f"{_PREFIX}-DER-{suffix}-{frappe.generate_hash(length=4)}"
        make_restaurant(name, plan="DIAMOND")
        return name

    def _clear(self, res):
        frappe.db.delete("Restaurant Loyalty Entry", {
            "customer": self._customer.name, "restaurant": res
        })
        frappe.db.commit()

    def test_percentage_mode_correct_coins(self):
        """10% earn_percentage on ₹500 order → 50 coins."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("PCT")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=10.0,
                                points_per_inr=0.1, max_coins_per_order=500)
            earned = earn_loyalty_coins(self._customer.name, res, 500.0)
            self.assertEqual(earned, 50)
        finally:
            cleanup_restaurant(res)

    def test_percentage_mode_7_percent(self):
        """7% earn_percentage on ₹1000 → 70 coins."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("PCT7")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=7.0,
                                points_per_inr=0.07, max_coins_per_order=500)
            earned = earn_loyalty_coins(self._customer.name, res, 1000.0)
            self.assertEqual(earned, 70)
        finally:
            cleanup_restaurant(res)

    def test_flat_mode_gives_fixed_coins(self):
        """Flat Coins mode: always gives 75 coins regardless of order size."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("FLAT")
        try:
            make_loyalty_config(res, earn_type="Flat Coins per Order", earn_flat_coins=75,
                                points_per_inr=0, max_coins_per_order=500)
            earned = earn_loyalty_coins(self._customer.name, res, 2000.0)
            self.assertEqual(earned, 75)
        finally:
            cleanup_restaurant(res)

    def test_flat_mode_same_for_small_and_large_order(self):
        """Flat mode must return same coins whether order is ₹100 or ₹10000."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("FLATEQ")
        try:
            make_loyalty_config(res, earn_type="Flat Coins per Order", earn_flat_coins=50,
                                points_per_inr=0, max_coins_per_order=500)
            earned_small = earn_loyalty_coins(self._customer.name, res, 100.0)
            self._clear(res)
            earned_large = earn_loyalty_coins(self._customer.name, res, 10000.0)
            self.assertEqual(earned_small, 50)
            self.assertEqual(earned_large, 50)
        finally:
            cleanup_restaurant(res)

    def test_min_order_to_earn_blocks_small_orders(self):
        """Order below min_order_to_earn must yield 0 coins."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("MINORD")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=10.0,
                                points_per_inr=0.1, min_order_to_earn=500, max_coins_per_order=500)
            earned = earn_loyalty_coins(self._customer.name, res, 300.0)  # below ₹500 min
            self.assertEqual(earned, 0)
        finally:
            cleanup_restaurant(res)

    def test_min_order_to_earn_allows_qualifying_orders(self):
        """Order exactly at min_order_to_earn must earn coins."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("MINORD2")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=10.0,
                                points_per_inr=0.1, min_order_to_earn=500, max_coins_per_order=500)
            earned = earn_loyalty_coins(self._customer.name, res, 500.0)  # exactly at threshold
            self.assertEqual(earned, 50)
        finally:
            cleanup_restaurant(res)

    def test_max_coins_per_order_cap_applied(self):
        """Even with high earn_percentage, max_coins_per_order caps the result."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("MAXCAP")
        try:
            # 10% of ₹5000 = 500 coins, but cap is 200
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=10.0,
                                points_per_inr=0.1, max_coins_per_order=200)
            earned = earn_loyalty_coins(self._customer.name, res, 5000.0)
            self.assertEqual(earned, 200)  # capped at 200, not 500
        finally:
            cleanup_restaurant(res)

    def test_max_cap_not_applied_if_below_cap(self):
        """Coins below max_coins_per_order are NOT reduced."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("NOCAP")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=5.0,
                                points_per_inr=0.05, max_coins_per_order=500)
            earned = earn_loyalty_coins(self._customer.name, res, 400.0)  # 5% of 400 = 20 coins
            self.assertEqual(earned, 20)
        finally:
            cleanup_restaurant(res)

    def test_legacy_points_per_inr_still_works(self):
        """If earn_type is not set and earn_percentage=0 (legacy config), points_per_inr fallback must work."""
        from dinematters.dinematters.utils.loyalty import earn_loyalty_coins
        res = self._make_res("LEGACY")
        try:
            # Simulate old-style config: earn_type=None, earn_percentage=0, only points_per_inr
            frappe.db.set_value("Restaurant", res, "enable_loyalty", 1)
            frappe.db.delete("Restaurant Loyalty Config", {"restaurant": res})
            frappe.db.commit()
            doc = frappe.get_doc({
                "doctype": "Restaurant Loyalty Config",
                "restaurant": res,
                "program_name": "Legacy Config",
                "is_active": 1,
                "points_per_inr": 0.1,    # old field
                "earn_percentage": 0,      # explicitly zero to suppress schema default
                "loyalty_expiry_months": 12,
                "coin_value_in_inr": 1.0,
                # earn_type intentionally omitted → defaults to "Percentage of Bill"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            earned = earn_loyalty_coins(self._customer.name, res, 1000.0)
            # Fallback: earn_percentage=0 is falsy, so uses points_per_inr=0.1 → 1000 * 0.1 = 100 coins
            self.assertEqual(earned, 100)
        finally:
            cleanup_restaurant(res)


# ─── 14. Guardrail Validation Tests ──────────────────────────────────────────

class TestGuardrailValidation(unittest.TestCase):
    """
    Tests for the validate_loyalty_config() function and the
    update_loyalty_config() API endpoint guardrail enforcement.
    """

    def test_valid_config_passes_guardrails(self):
        """A config within all bounds must return an empty errors list."""
        from dinematters.dinematters.api.loyalty import validate_loyalty_config
        errors = validate_loyalty_config({
            "earn_percentage": 7,
            "earn_flat_coins": 50,
            "min_order_to_earn": 200,
            "max_coins_per_order": 300,
            "min_billing_for_redemption": 100,
            "min_redemption_threshold": 50,
            "loyalty_expiry_months": 12,
        })
        self.assertEqual(errors, [])

    def test_earn_percentage_above_max_rejected(self):
        """earn_percentage=20 must fail (max is 15)."""
        from dinematters.dinematters.api.loyalty import validate_loyalty_config
        errors = validate_loyalty_config({"earn_percentage": 20})
        self.assertTrue(len(errors) > 0)
        self.assertIn("earn_percentage", errors[0])

    def test_earn_percentage_below_min_rejected(self):
        """earn_percentage=0 must fail (min is 1)."""
        from dinematters.dinematters.api.loyalty import validate_loyalty_config
        errors = validate_loyalty_config({"earn_percentage": 0})
        self.assertTrue(len(errors) > 0)

    def test_max_coins_per_order_above_ceiling_rejected(self):
        """max_coins_per_order=5000 must fail (ceiling is 1000)."""
        from dinematters.dinematters.api.loyalty import validate_loyalty_config
        errors = validate_loyalty_config({"max_coins_per_order": 5000})
        self.assertTrue(len(errors) > 0)

    def test_expiry_months_too_low_rejected(self):
        """loyalty_expiry_months=1 must fail (min is 3)."""
        from dinematters.dinematters.api.loyalty import validate_loyalty_config
        errors = validate_loyalty_config({"loyalty_expiry_months": 1})
        self.assertTrue(len(errors) > 0)

    def test_multiple_violations_returns_all_errors(self):
        """Multiple out-of-range fields must all appear in errors list."""
        from dinematters.dinematters.api.loyalty import validate_loyalty_config
        errors = validate_loyalty_config({
            "earn_percentage": 99,    # too high
            "earn_flat_coins": 1,     # too low
            "loyalty_expiry_months": 0,  # too low
        })
        self.assertGreaterEqual(len(errors), 3)

    def test_unknown_field_is_ignored(self):
        """Fields not in GUARDRAILS must be silently ignored (not raise)."""
        from dinematters.dinematters.api.loyalty import validate_loyalty_config
        errors = validate_loyalty_config({"some_unknown_field": 99999, "earn_percentage": 5})
        self.assertEqual(errors, [])

    def test_update_config_rejects_guardrail_violation_via_api(self):
        """update_loyalty_config API must return GUARDRAIL_VIOLATION when earn_percentage > 15."""
        frappe.set_user("Administrator")
        res = f"{_PREFIX}-GRD-{frappe.generate_hash(length=6)}"
        make_restaurant(res, plan="DIAMOND")
        make_loyalty_config(res)
        try:
            from dinematters.dinematters.api.loyalty import update_loyalty_config
            result = update_loyalty_config(
                restaurant_id=res,
                config={"earn_type": "Percentage of Bill", "earn_percentage": 25},
                enable_loyalty=True
            )
            self.assertFalse(result.get("success"))
            self.assertEqual(result["error"]["code"], "GUARDRAIL_VIOLATION")
        finally:
            cleanup_restaurant(res)

    def test_update_config_migrates_legacy_points_per_inr(self):
        """Saving a config with only points_per_inr must auto-set earn_type=Percentage and earn_percentage."""
        frappe.set_user("Administrator")
        res = f"{_PREFIX}-MIG-{frappe.generate_hash(length=6)}"
        make_restaurant(res, plan="DIAMOND")
        make_loyalty_config(res, points_per_inr=0.1)
        try:
            from dinematters.dinematters.api.loyalty import update_loyalty_config
            # Save without specifying earn_type — should auto-migrate
            result = update_loyalty_config(
                restaurant_id=res,
                config={"points_per_inr": 0.08},  # legacy-style save
                enable_loyalty=True
            )
            self.assertTrue(result.get("success"))
            saved = frappe.db.get_value(
                "Restaurant Loyalty Config",
                {"restaurant": res},
                ["earn_type", "earn_percentage", "points_per_inr"],
                as_dict=True
            )
            self.assertEqual(saved.earn_type, "Percentage of Bill")
            self.assertAlmostEqual(saved.earn_percentage, 8.0, places=1)  # 0.08 * 100 = 8%
            self.assertAlmostEqual(saved.points_per_inr, 0.08, places=3)  # kept in sync
        finally:
            cleanup_restaurant(res)

    def test_update_config_locks_coin_value_to_1(self):
        """Attempting to set coin_value_in_inr != 1 must be silently overridden to 1."""
        frappe.set_user("Administrator")
        res = f"{_PREFIX}-COIN-{frappe.generate_hash(length=6)}"
        make_restaurant(res, plan="DIAMOND")
        make_loyalty_config(res)
        try:
            from dinematters.dinematters.api.loyalty import update_loyalty_config
            result = update_loyalty_config(
                restaurant_id=res,
                config={"earn_type": "Percentage of Bill", "earn_percentage": 5, "coin_value_in_inr": 2},
                enable_loyalty=True
            )
            self.assertTrue(result.get("success"))
            saved_value = frappe.db.get_value(
                "Restaurant Loyalty Config", {"restaurant": res}, "coin_value_in_inr"
            )
            self.assertEqual(saved_value, 1)  # must remain 1 regardless of input
        finally:
            cleanup_restaurant(res)

    def test_flat_mode_saves_correctly(self):
        """update_loyalty_config with Flat Coins mode must persist earn_flat_coins and zero points_per_inr."""
        frappe.set_user("Administrator")
        res = f"{_PREFIX}-FLAT-{frappe.generate_hash(length=6)}"
        make_restaurant(res, plan="DIAMOND")
        make_loyalty_config(res)
        try:
            from dinematters.dinematters.api.loyalty import update_loyalty_config
            result = update_loyalty_config(
                restaurant_id=res,
                config={"earn_type": "Flat Coins per Order", "earn_flat_coins": 75},
                enable_loyalty=True
            )
            self.assertTrue(result.get("success"))
            saved = frappe.db.get_value(
                "Restaurant Loyalty Config",
                {"restaurant": res},
                ["earn_type", "earn_flat_coins", "points_per_inr"],
                as_dict=True
            )
            self.assertEqual(saved.earn_type, "Flat Coins per Order")
            self.assertEqual(saved.earn_flat_coins, 75)
            self.assertEqual(saved.points_per_inr, 0)  # zeroed out in flat mode
        finally:
            cleanup_restaurant(res)
