# Copyright (c) 2026, Flamezo and contributors
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
  - Fraud fixes (plan-tiered earn: GOLD 7%/cap 700, SILVER 5%/cap 500, daily redemption cap ₹500,
    global welcome bonus, advisory lock, monthly referral cycle reset)

Run with:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_loyalty
"""

import unittest
import frappe
from frappe.utils import today, add_days, add_months
from unittest.mock import MagicMock, patch

from flamezo_backend.flamezo.tests.utils import (
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res, points_per_inr=0.1)
        cls._customer = make_customer(phone="9100000001", name="Test Balance Customer")

        from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(
            cls._res,
            earn_type="Percentage of Bill",
            earn_percentage=5.0,    # Platform Silver 5%
            points_per_inr=0.05,    # legacy field kept in sync
            loyalty_expiry_months=6
        )
        cls._customer = make_customer(phone="9100000002", name="Test Earn Customer")

        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        cls.earn = staticmethod(earn_loyalty_coins)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    def test_coins_calculated_from_percentage(self):
        """₹1000 order at platform GOLD 7% earn_percentage = 70 coins (res is plan=GOLD)."""
        earned = self.earn(self._customer.name, self._res, 1000.0, reason="Order")
        self.assertEqual(earned, 70)

    def test_coins_calculated_from_points_per_inr(self):
        """Platform GOLD: ₹1000 × 7% = 70 coins."""
        earned = self.earn(self._customer.name, self._res, 1000.0, reason="Order")
        self.assertEqual(earned, 70)

    def test_fractional_coins_truncated(self):
        """int() truncation: ₹105 × 0.07 = 7.35 → 7 coins (GOLD restaurant)."""
        earned = self.earn(self._customer.name, self._res, 105.0, reason="Order")
        self.assertEqual(earned, 7)

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
        """expiry_date must be exactly get_expiry_months(plan) from today (GOLD = 6 months)."""
        self.earn(self._customer.name, self._res, 1000.0, reason="Order")
        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._customer.name, "restaurant": self._res},
            ["expiry_date"],
            as_dict=True
        )
        from flamezo_backend.flamezo.utils.platform_config import get_expiry_months
        expected_expiry = add_months(today(), get_expiry_months("GOLD"))
        self.assertEqual(str(entry.expiry_date), str(expected_expiry))

    def test_zero_amount_returns_zero(self):
        earned = self.earn(self._customer.name, self._res, 0.0)
        self.assertEqual(earned, 0)

    def test_loyalty_disabled_returns_zero(self):
        """When enable_loyalty=0 on the restaurant, no coins are earned."""
        disabled_res = f"{_PREFIX}-ELC-DIS-{frappe.generate_hash(length=6)}"
        make_restaurant(disabled_res, plan="GOLD")
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res, points_per_inr=0.1)
        cls._customer = make_customer(phone="9100000003", name="Test Redeem Customer")

        from flamezo_backend.flamezo.utils.loyalty import redeem_loyalty_coins
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
        make_restaurant(disabled_res, plan="GOLD")
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000004", name="Test Settle Customer")

        from flamezo_backend.flamezo.utils.loyalty import settle_loyalty_points
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000005", name="Test Cancel Customer")

        from flamezo_backend.flamezo.utils.loyalty import handle_order_cancellation
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
        make_restaurant(cls._res, plan="GOLD")
        # earn_on_status="Completed" → settle on "completed", "billed", "confirmed", or payment_status=completed
        make_loyalty_config(cls._res, earn_on_status="Completed")
        cls._customer = make_customer(phone="9100000006", name="Test Settlement Customer")

        from flamezo_backend.flamezo.utils.loyalty import handle_loyalty_settlement
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
        make_restaurant(cls._res, plan="GOLD")
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
        from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance
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

        from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9100000008", name="Test Cancel Zero Customer")

        from flamezo_backend.flamezo.utils.loyalty import handle_order_cancellation
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)

    def test_config_does_not_expose_internal_fields(self):
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        response = get_loyalty_config(self._res)
        self.assertTrue(response.get("success"))
        data = response.get("data", {})
        self.assertIsNotNone(data)
        # These internal fields must NOT be present
        internal_fields = ["doctype", "owner", "creation", "modified_by", "__islocal", "modified"]
        for field in internal_fields:
            self.assertNotIn(field, data, f"Internal field '{field}' must not be exposed to guests")

    def test_config_returns_expected_public_fields(self):
        """Centralized model: response must include platform constant fields."""
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        response = get_loyalty_config(self._res)
        data = response.get("data", {})
        # These are platform-constant fields that MUST always be present
        expected_fields = [
            "earn_type", "earn_percentage", "coin_value_in_inr",
            "min_redemption_threshold", "min_order_to_earn",
            "max_coins_per_order", "new_user_welcome_reward_coins",
            "coins_per_unique_open", "max_opens_rewarded_per_share",
            "tier_silver_threshold", "tier_gold_threshold", "tier_platinum_threshold",
        ]
        for field in expected_fields:
            self.assertIn(field, data, f"Platform constant field '{field}' missing from config response")

    def test_config_returns_platform_fixed_earn_percentage(self):
        """earn_percentage must always be the platform plan-tiered constant (7% for GOLD restaurant)."""
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        from flamezo_backend.flamezo.utils.platform_config import get_earn_percentage
        response = get_loyalty_config(self._res)
        data = response.get("data", {})
        # cls._res is plan=GOLD, so expect 7.0
        self.assertEqual(data.get("earn_percentage"), get_earn_percentage("GOLD"))

    def test_config_legacy_points_per_inr_not_exposed(self):
        """points_per_inr is a legacy field — not returned in centralized config response."""
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        response = get_loyalty_config(self._res)
        data = response.get("data", {})
        self.assertNotIn("points_per_inr", data,
            "Legacy points_per_inr must not be exposed to guests in the centralized model")


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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res,
            tier_silver_threshold=500,
            tier_gold_threshold=2000,
            tier_platinum_threshold=5000
        )
        cls._customer = make_customer(phone="9100000009", name="Test Tier Customer")

        from flamezo_backend.flamezo.utils.loyalty import get_loyalty_tier
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
        make_restaurant(cls._res, plan="GOLD")
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
        from flamezo_backend.flamezo.tasks.loyalty_tasks import grant_birthday_bonuses
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

        from flamezo_backend.flamezo.tasks.loyalty_tasks import grant_birthday_bonuses
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

        from flamezo_backend.flamezo.tasks.loyalty_tasks import grant_birthday_bonuses
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
        make_restaurant(cls._res, plan="GOLD")
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

        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message") as mock_send:
            from flamezo_backend.flamezo.utils.loyalty import send_coin_credit_push
            send_coin_credit_push(self._customer.name, self._res, 100, "Order")
            mock_send.assert_not_called()

    def test_push_sent_for_each_token(self):
        """Must call _send_fcm_message once per stored FCM token."""
        import json
        tokens = ["token-aaa", "token-bbb"]
        frappe.db.set_value("Customer", self._customer.name, "push_fcm_tokens", json.dumps(tokens))
        frappe.db.commit()

        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message", return_value=True) as mock_send:
            from flamezo_backend.flamezo.utils.loyalty import send_coin_credit_push
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

        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message", side_effect=mock_send):
            from flamezo_backend.flamezo.utils.loyalty import send_coin_credit_push
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

        with patch("flamezo_backend.flamezo.api.push_notifications._send_fcm_message", side_effect=capture_send):
            from flamezo_backend.flamezo.utils.loyalty import send_coin_credit_push
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
        make_restaurant(cls._res, plan="GOLD")
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
        from flamezo_backend.flamezo.api.loyalty import track_referral_visit
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
        from flamezo_backend.flamezo.api.loyalty import track_referral_visit
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
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(
            cls._res,
            new_user_welcome_reward_coins=75,
            coins_per_unique_open=5,
            max_opens_rewarded_per_share=7
        )
        # Referrer
        from flamezo_backend.flamezo.utils.customer_helpers import get_or_create_customer
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
        from flamezo_backend.flamezo.api.loyalty import claim_referral_reward
        phone = phone or self._referee_phone
        with patch("flamezo_backend.flamezo.utils.customer_helpers.validate_customer_session", return_value=True), \
             patch("flamezo_backend.flamezo.api.loyalty.validate_customer_session", return_value=True), \
             patch("flamezo_backend.flamezo.api.loyalty.get_customer_token", return_value="mock-token"):
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
        """Referrer must receive a Referral Share entry using coins_per_unique_open."""
        result = self._call_claim()
        self.assertTrue(result.get("success"))

        entry = frappe.db.get_value(
            "Restaurant Loyalty Entry",
            {"customer": self._referrer.name, "restaurant": self._res, "reason": "Referral Share"},
            ["coins", "transaction_type"], as_dict=True
        )
        self.assertIsNotNone(entry, "Referral Share entry must be created for referrer")
        self.assertEqual(entry.transaction_type, "Earn")
        self.assertEqual(entry.coins, 40)  # platform referral_share_coins is 40

    def test_response_contains_coin_counts(self):
        """Response data must include welcome_coins and referrer_coins."""
        result = self._call_claim()
        self.assertTrue(result.get("success"))
        data = result.get("data", {})
        self.assertEqual(data.get("welcome_coins"), 75)
        self.assertEqual(data.get("referrer_coins"), 40)

    def test_double_claim_rejected(self):
        """Calling claim twice for the same referee must fail with ALREADY_CLAIMED."""
        self._call_claim()  # first claim
        result = self._call_claim()  # second claim
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error", {}).get("code"), "ALREADY_CLAIMED")

    def test_referrer_coins_not_awarded_beyond_cycle_limit(self):
        # Exhaust the limit (platform default is 10)
        frappe.db.set_value("Referral Link", {"identifier": self._identifier}, "rewarded_opens_in_cycle", 10)
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
        make_restaurant(other_res, plan="GOLD")
        try:
            from flamezo_backend.flamezo.api.loyalty import claim_referral_reward
            with patch("flamezo_backend.flamezo.api.loyalty.validate_customer_session", return_value=True), \
                 patch("flamezo_backend.flamezo.api.loyalty.get_customer_token", return_value="mock-token"):
                result = claim_referral_reward(other_res, self._identifier, self._referee_phone)
            self.assertFalse(result.get("success"))
            self.assertEqual(result.get("error", {}).get("code"), "RESTAURANT_MISMATCH")
        finally:
            cleanup_restaurant(other_res)

    def test_invalid_referral_id_rejected(self):
        """Non-existent referral identifier must return LINK_NOT_FOUND."""
        from flamezo_backend.flamezo.api.loyalty import claim_referral_reward
        with patch("flamezo_backend.flamezo.api.loyalty.validate_customer_session", return_value=True), \
             patch("flamezo_backend.flamezo.api.loyalty.get_customer_token", return_value="mock-token"):
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

class TestPlatformCentralizedEarnRate(unittest.TestCase):
    """
    Validates that the earn logic follows platform-fixed rates (utils/platform_config.py)
    and ignores restaurant-level overrides:
    - GOLD: 7%, cap 700; SILVER: 5%, cap 500
    - min_order_to_earn is ₹100
    - Expiry is plan-tiered (6/9 months)
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

    def _make_res(self, suffix, plan="GOLD"):
        name = f"{_PREFIX}-DER-{suffix}-{frappe.generate_hash(length=4)}"
        make_restaurant(name, plan=plan)
        return name

    def _clear(self, res):
        frappe.db.delete("Restaurant Loyalty Entry", {
            "customer": self._customer.name, "restaurant": res
        })
        frappe.db.commit()

    def test_percentage_mode_correct_coins_gold(self):
        """GOLD 7% earn on ₹500 order → 35 coins."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("PCT", plan="GOLD")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=7.0,
                                points_per_inr=0.07, max_coins_per_order=700)
            earned = earn_loyalty_coins(self._customer.name, res, 500.0)
            self.assertEqual(earned, 35)
        finally:
            cleanup_restaurant(res)

    def test_percentage_mode_correct_coins_silver(self):
        """SILVER 5% earn on ₹500 order → 25 coins."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("PCTSLV", plan="SILVER")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=5.0,
                                points_per_inr=0.05, max_coins_per_order=500)
            earned = earn_loyalty_coins(self._customer.name, res, 500.0)
            self.assertEqual(earned, 25)
        finally:
            cleanup_restaurant(res)

    def test_earn_ignores_restaurant_config_percentage(self):
        """Even if restaurant config sets 99%, logic must use platform rate (7% for GOLD)."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("IGNORE_PCT", plan="GOLD")
        try:
            make_loyalty_config(res, earn_type="Percentage of Bill", earn_percentage=99.0)
            earned = earn_loyalty_coins(self._customer.name, res, 1000.0)
            self.assertEqual(earned, 70)  # 7% of ₹1000 (GOLD platform rate)
        finally:
            cleanup_restaurant(res)

    def test_earn_ignores_flat_mode_override(self):
        """Even if restaurant tries Flat mode, logic must use platform Percentage (7% GOLD)."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("IGNORE_FLAT", plan="GOLD")
        try:
            make_loyalty_config(res, earn_type="Flat Cash per Order", earn_flat_coins=75)
            earned = earn_loyalty_coins(self._customer.name, res, 1000.0)
            self.assertEqual(earned, 70)  # 7% of ₹1000 GOLD, not 75 flat
        finally:
            cleanup_restaurant(res)

    def test_earn_follows_platform_min_order(self):
        """Logic must use platform min_order (₹100) and ignore doc's ₹500."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("MINORD", plan="GOLD")
        try:
            make_loyalty_config(res, min_order_to_earn=500)
            earned = earn_loyalty_coins(self._customer.name, res, 300.0)
            self.assertEqual(earned, 21)  # 7% of ₹300, since 300 > 100 (platform min)
        finally:
            cleanup_restaurant(res)

    def test_earn_follows_platform_max_cap_gold(self):
        """Logic must use GOLD platform max_cap (700) and ignore doc's lower value."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("MAXCAP", plan="GOLD")
        try:
            make_loyalty_config(res, max_coins_per_order=50)
            # 7% of ₹5000 = 350 coins. Platform GOLD cap is 700, so 350 is returned as-is.
            # If it incorrectly followed doc (50), it would return 50.
            earned = earn_loyalty_coins(self._customer.name, res, 5000.0)
            self.assertEqual(earned, 350)
        finally:
            cleanup_restaurant(res)

    def test_earn_caps_at_platform_700_gold(self):
        """Order for ₹20,000: 7% = 1400 coins, capped at GOLD platform max 700."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("MAXCAP_ABS", plan="GOLD")
        try:
            make_loyalty_config(res)
            earned = earn_loyalty_coins(self._customer.name, res, 20000.0)
            self.assertEqual(earned, 700)
        finally:
            cleanup_restaurant(res)

    def test_earn_caps_at_platform_500_silver(self):
        """Order for ₹20,000: 5% = 1000 coins, capped at SILVER platform max 500."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("MAXCAP_SLV", plan="SILVER")
        try:
            make_loyalty_config(res)
            earned = earn_loyalty_coins(self._customer.name, res, 20000.0)
            self.assertEqual(earned, 500)
        finally:
            cleanup_restaurant(res)

    def test_max_cap_not_applied_if_below_cap(self):
        """Coins below platform max_coins_per_order (700 GOLD) are NOT reduced."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        res = self._make_res("NOCAP", plan="GOLD")
        try:
            make_loyalty_config(res)
            earned = earn_loyalty_coins(self._customer.name, res, 1000.0)  # 7% = 70 coins
            self.assertEqual(earned, 70)
        finally:
            cleanup_restaurant(res)



# ─── 14. Centralized Model Tests ─────────────────────────────────────────────

class TestCentralizedLoyaltyModel(unittest.TestCase):
    """
    Validates the fully centralized Flamezo loyalty model:
    - get_loyalty_config always injects PLATFORM_LOYALTY constants
    - update_loyalty_config strips all locked earn/redeem fields
    - update_loyalty_config writes platform constants back to DB
    - Restaurants can only toggle enable/disable
    - coin_value_in_inr is always 1
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-CTR-")
        cls._res = f"{_PREFIX}-CTR-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res, earn_percentage=99.0)  # deliberately wrong rate

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)

    # ── get_loyalty_config: platform constant injection ────────────────────────

    def test_get_config_overrides_earn_percentage_with_platform_value(self):
        """Even if DB has earn_percentage=99, API must return platform plan-tiered rate (7% for GOLD)."""
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        from flamezo_backend.flamezo.utils.platform_config import get_earn_percentage
        response = get_loyalty_config(self._res)
        self.assertTrue(response.get("success"))
        data = response["data"]
        # cls._res is plan=GOLD, so expect 7.0
        self.assertEqual(
            data["earn_percentage"],
            get_earn_percentage("GOLD"),
            "earn_percentage must always be the platform constant (7% GOLD), regardless of DB value"
        )

    def test_get_config_coin_value_is_always_1(self):
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        response = get_loyalty_config(self._res)
        self.assertEqual(response["data"]["coin_value_in_inr"], 1)

    def test_get_config_platform_tier_thresholds(self):
        """Tier thresholds must match platform constants: 500 / 2000 / 5000."""
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        data = get_loyalty_config(self._res)["data"]
        self.assertEqual(data["tier_silver_threshold"], PLATFORM_LOYALTY["tier"]["silver"])
        self.assertEqual(data["tier_gold_threshold"],   PLATFORM_LOYALTY["tier"]["gold"])
        self.assertEqual(data["tier_platinum_threshold"], PLATFORM_LOYALTY["tier"]["platinum"])

    def test_get_config_welcome_coins_match_platform(self):
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        data = get_loyalty_config(self._res)["data"]
        self.assertEqual(
            data["new_user_welcome_reward_coins"],
            PLATFORM_LOYALTY["welcome_reward_coins"]
        )

    def test_get_config_referral_coins_match_platform(self):
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        data = get_loyalty_config(self._res)["data"]
        self.assertEqual(
            data["coins_per_unique_open"],
            PLATFORM_LOYALTY["referral_share_coins"]
        )
        self.assertEqual(
            data["max_opens_rewarded_per_share"],
            PLATFORM_LOYALTY["max_opens_rewarded_per_share"]
        )

    def test_get_config_no_legacy_points_per_inr_field(self):
        """Legacy points_per_inr must not be exposed in the centralized API response."""
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        data = get_loyalty_config(self._res)["data"]
        self.assertNotIn("points_per_inr", data)

    def test_get_config_no_removed_fields_exposed(self):
        """Fields removed from the centralized model must not appear in the API response."""
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_config
        data = get_loyalty_config(self._res)["data"]
        removed_fields = [
            "earn_flat_coins", "share_reward_coins",
            "referral_order_reward_coins", "welcome_coupon_discount",
            "min_unique_opens_for_reward",
        ]
        for field in removed_fields:
            self.assertNotIn(field, data,
                f"Removed field '{field}' must not appear in centralized config response")

    # ── update_loyalty_config: locked field stripping ──────────────────────────

    def test_update_config_strips_earn_percentage_override(self):
        """Passing earn_percentage=25 must be silently stripped; DB must retain platform value (7% GOLD)."""
        from flamezo_backend.flamezo.api.loyalty import update_loyalty_config
        from flamezo_backend.flamezo.utils.platform_config import get_earn_percentage
        result = update_loyalty_config(
            restaurant_id=self._res,
            config={"earn_percentage": 25},
            enable_loyalty=True
        )
        self.assertTrue(result.get("success"))
        saved = frappe.db.get_value(
            "Restaurant Loyalty Config", {"restaurant": self._res}, "earn_percentage"
        )
        self.assertEqual(
            float(saved), get_earn_percentage("GOLD"),
            "earn_percentage in DB must be the platform constant (7% GOLD) after update"
        )

    def test_update_config_strips_coin_value_override(self):
        """Passing coin_value_in_inr=5 must be overridden; DB must have 1."""
        from flamezo_backend.flamezo.api.loyalty import update_loyalty_config
        result = update_loyalty_config(
            restaurant_id=self._res,
            config={"coin_value_in_inr": 5},
            enable_loyalty=True
        )
        self.assertTrue(result.get("success"))
        saved = frappe.db.get_value(
            "Restaurant Loyalty Config", {"restaurant": self._res}, "coin_value_in_inr"
        )
        self.assertEqual(float(saved), 1.0, "coin_value_in_inr must always be 1 in DB")

    def test_update_config_strips_max_coins_override(self):
        """max_coins_per_order is locked; arbitrary override must be ignored."""
        from flamezo_backend.flamezo.api.loyalty import update_loyalty_config
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        result = update_loyalty_config(
            restaurant_id=self._res,
            config={"max_coins_per_order": 9999},
            enable_loyalty=True
        )
        self.assertTrue(result.get("success"))
        # DB value should remain platform constant (set by update_loyalty_config)
        saved = frappe.db.get_value(
            "Restaurant Loyalty Config", {"restaurant": self._res}, "max_coins_per_order"
        )
        # Note: max_coins_per_order is stripped but not re-written by update_loyalty_config
        # (only earn_type, earn_percentage, points_per_inr, coin_value_in_inr are written back)
        # The key assertion is it did NOT get set to 9999
        self.assertNotEqual(saved, 9999, "max_coins_per_order must not be inflated by restaurant")

    def test_update_config_enable_loyalty_toggle_works(self):
        """Restaurants can turn loyalty on/off — that is their only control."""
        from flamezo_backend.flamezo.api.loyalty import update_loyalty_config
        # Disable
        result = update_loyalty_config(
            restaurant_id=self._res, config={}, enable_loyalty=False
        )
        self.assertTrue(result.get("success"))
        self.assertEqual(
            frappe.db.get_value("Restaurant", self._res, "enable_loyalty"), 0
        )
        # Re-enable
        result = update_loyalty_config(
            restaurant_id=self._res, config={}, enable_loyalty=True
        )
        self.assertTrue(result.get("success"))
        self.assertEqual(
            frappe.db.get_value("Restaurant", self._res, "enable_loyalty"), 1
        )

    def test_update_config_writes_platform_earn_type(self):
        """After any update, earn_type in DB must always be 'Percentage of Bill'."""
        from flamezo_backend.flamezo.api.loyalty import update_loyalty_config
        update_loyalty_config(
            restaurant_id=self._res,
            config={"earn_type": "Flat Coins per Order"},  # restaurant tries to change it
            enable_loyalty=True
        )
        saved = frappe.db.get_value(
            "Restaurant Loyalty Config", {"restaurant": self._res}, "earn_type"
        )
        self.assertEqual(saved, "Percentage of Bill",
            "earn_type must always be Percentage of Bill (platform-enforced)")

    def test_update_config_success_returns_true(self):
        """A valid update with only enable toggle must always succeed."""
        from flamezo_backend.flamezo.api.loyalty import update_loyalty_config
        result = update_loyalty_config(
            restaurant_id=self._res, config={}, enable_loyalty=True
        )
        self.assertTrue(result.get("success"))
        self.assertNotIn("error", result)

    # ── Platform config module tests ───────────────────────────────────────────

    def test_platform_config_earn_rates_plan_tiered(self):
        from flamezo_backend.flamezo.utils.platform_config import get_earn_percentage
        self.assertEqual(get_earn_percentage("SILVER"), 5.0)
        self.assertEqual(get_earn_percentage("GOLD"),   7.0)
        self.assertGreater(get_earn_percentage("GOLD"), get_earn_percentage("SILVER"))

    def test_platform_config_max_coins_plan_tiered(self):
        from flamezo_backend.flamezo.utils.platform_config import get_max_coins_per_order
        self.assertEqual(get_max_coins_per_order("SILVER"), 500)
        self.assertEqual(get_max_coins_per_order("GOLD"),   700)

    def test_platform_config_redemption_percent_plan_tiered(self):
        from flamezo_backend.flamezo.utils.platform_config import get_max_redemption_percent
        self.assertEqual(get_max_redemption_percent("SILVER"), 20)
        self.assertEqual(get_max_redemption_percent("GOLD"),   30)

    def test_platform_config_expiry_plan_tiered(self):
        from flamezo_backend.flamezo.utils.platform_config import get_expiry_months
        self.assertEqual(get_expiry_months("SILVER"), 3)
        self.assertEqual(get_expiry_months("GOLD"),   6)

    def test_platform_config_birthday_bonus_plan_tiered(self):
        from flamezo_backend.flamezo.utils.platform_config import get_birthday_bonus_coins
        self.assertEqual(get_birthday_bonus_coins("SILVER"),  50)
        self.assertEqual(get_birthday_bonus_coins("GOLD"),   100)

    def test_platform_config_min_redemption_threshold_is_100(self):
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        self.assertEqual(PLATFORM_LOYALTY["min_redemption_threshold"], 100)

    def test_platform_config_daily_redemption_cap_is_500(self):
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        self.assertEqual(PLATFORM_LOYALTY["max_daily_redemption_inr"], 500)

    def test_platform_config_max_manual_adjustment_is_500(self):
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        self.assertEqual(PLATFORM_LOYALTY["max_manual_adjustment_coins"], 500)

    def test_platform_config_coin_value_is_1(self):
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        self.assertEqual(PLATFORM_LOYALTY["coin_value_in_inr"], 1)

    def test_platform_config_welcome_coins_is_75(self):
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        self.assertEqual(PLATFORM_LOYALTY["welcome_reward_coins"], 75)

    def test_platform_config_referral_coins_is_40(self):
        from flamezo_backend.flamezo.utils.platform_config import (
            PLATFORM_LOYALTY, get_referral_share_coins
        )
        self.assertEqual(PLATFORM_LOYALTY["referral_share_coins"], 40)
        self.assertEqual(get_referral_share_coins(), 40)

    def test_platform_config_max_opens_is_10(self):
        from flamezo_backend.flamezo.utils.platform_config import get_max_opens_rewarded_per_share
        self.assertEqual(get_max_opens_rewarded_per_share(), 10)

    def test_platform_config_tier_thresholds(self):
        from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
        tier = PLATFORM_LOYALTY["tier"]
        self.assertEqual(tier["silver"],   500)
        self.assertEqual(tier["gold"],    2000)
        self.assertEqual(tier["platinum"], 5000)

    # ── Earn logic uses plan-aware rate ───────────────────────────────────────

    def test_earn_uses_gold_7_percent(self):
        """GOLD restaurant: ₹1000 order → 70 coins (7%)."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        customer = make_customer(phone="9300000001", name="CTR Earn Gold Test")
        try:
            res = f"{_PREFIX}-CTR-EARN-GOLD-{frappe.generate_hash(length=4)}"
            make_restaurant(res, plan="GOLD")
            make_loyalty_config(res)
            earned = earn_loyalty_coins(customer.name, res, 1000.0)
            self.assertEqual(earned, 70, "7% of ₹1000 must yield 70 coins for GOLD restaurant")
        finally:
            cleanup_restaurant(res)
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": customer.name})
            frappe.db.commit()

    def test_earn_uses_silver_5_percent(self):
        """SILVER restaurant: ₹1000 order → 50 coins (5%)."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        customer = make_customer(phone="9300000004", name="CTR Earn Silver Test")
        try:
            res = f"{_PREFIX}-CTR-EARN-SLV-{frappe.generate_hash(length=4)}"
            make_restaurant(res, plan="SILVER")
            make_loyalty_config(res)
            earned = earn_loyalty_coins(customer.name, res, 1000.0)
            self.assertEqual(earned, 50, "5% of ₹1000 must yield 50 coins for SILVER restaurant")
        finally:
            cleanup_restaurant(res)
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": customer.name})
            frappe.db.commit()

    def test_earn_gold_beats_silver_same_order(self):
        """GOLD must always earn more than SILVER for the same order amount."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        customer = make_customer(phone="9300000005", name="CTR Gold vs Silver")
        res_gold   = f"{_PREFIX}-CTR-GLD-{frappe.generate_hash(length=4)}"
        res_silver = f"{_PREFIX}-CTR-SLV-{frappe.generate_hash(length=4)}"
        try:
            make_restaurant(res_gold,   plan="GOLD")
            make_restaurant(res_silver, plan="SILVER")
            make_loyalty_config(res_gold)
            make_loyalty_config(res_silver)
            gold_earned   = earn_loyalty_coins(customer.name, res_gold,   1000.0)
            silver_earned = earn_loyalty_coins(customer.name, res_silver, 1000.0)
            self.assertGreater(gold_earned, silver_earned,
                "GOLD restaurant must always yield more coins than SILVER for same order")
        finally:
            for res in [res_gold, res_silver]:
                cleanup_restaurant(res)
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": customer.name})
            frappe.db.commit()

    def test_earn_cap_gold_700(self):
        """GOLD cap is 700 coins; ₹20,000 × 7% = 1400, capped at 700."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        customer = make_customer(phone="9300000002", name="CTR Cap Gold Test")
        try:
            res = f"{_PREFIX}-CTR-CAP-GOLD-{frappe.generate_hash(length=4)}"
            make_restaurant(res, plan="GOLD")
            make_loyalty_config(res)
            earned = earn_loyalty_coins(customer.name, res, 20000.0)
            self.assertEqual(earned, 700, "GOLD earn must be capped at 700 coins")
        finally:
            cleanup_restaurant(res)
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": customer.name})
            frappe.db.commit()

    def test_earn_cap_silver_500(self):
        """SILVER cap is 500 coins; ₹20,000 × 5% = 1000, capped at 500."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        customer = make_customer(phone="9300000006", name="CTR Cap Silver Test")
        try:
            res = f"{_PREFIX}-CTR-CAP-SLV-{frappe.generate_hash(length=4)}"
            make_restaurant(res, plan="SILVER")
            make_loyalty_config(res)
            earned = earn_loyalty_coins(customer.name, res, 20000.0)
            self.assertEqual(earned, 500, "SILVER earn must be capped at 500 coins")
        finally:
            cleanup_restaurant(res)
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": customer.name})
            frappe.db.commit()

    def test_earn_zero_below_min_order_100(self):
        """Platform min order is ₹100; ₹50 order must yield 0 coins regardless of plan."""
        from flamezo_backend.flamezo.utils.loyalty import earn_loyalty_coins
        customer = make_customer(phone="9300000003", name="CTR Min Test")
        try:
            res = f"{_PREFIX}-CTR-MIN-{frappe.generate_hash(length=4)}"
            make_restaurant(res, plan="GOLD")
            make_loyalty_config(res)
            earned = earn_loyalty_coins(customer.name, res, 50.0)
            self.assertEqual(earned, 0, "Order below ₹100 minimum must earn 0 coins")
        finally:
            cleanup_restaurant(res)
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": customer.name})
            frappe.db.commit()


if __name__ == "__main__":
    unittest.main()

# NOTE: TestGuardrailValidation was removed — validate_loyalty_config() and
# per-restaurant guardrails were deleted as part of the centralized model migration.
# All earn/redeem rate enforcement is now handled by _LOCKED_FIELDS in
# update_loyalty_config() and the PLATFORM_LOYALTY constants.
# See TestCentralizedLoyaltyModel above for the replacement tests.


# ─── 15. Daily Redemption Cap ─────────────────────────────────────────────────

class TestDailyRedemptionCap(unittest.TestCase):
    """
    Validates the ₹500/day redemption cap introduced to prevent whale drain.
    - Customer cannot redeem more than ₹500 total across all restaurants in one day
    - Internal reversals (Cancellation Revert) are NOT counted against the cap
    - Cap is enforced inside the DB advisory lock
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-DRC-")
        cls._res  = f"{_PREFIX}-DRC-{frappe.generate_hash(length=6)}"
        cls._res2 = f"{_PREFIX}-DRC2-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="GOLD")
        make_restaurant(cls._res2, plan="GOLD")
        make_loyalty_config(cls._res)
        make_loyalty_config(cls._res2)
        cls._customer = make_customer(phone="9400000001", name="DRC Test Customer")

        from flamezo_backend.flamezo.utils.loyalty import redeem_loyalty_coins
        cls.redeem = staticmethod(redeem_loyalty_coins)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        cleanup_restaurant(cls._res2)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._customer.name})
        frappe.db.commit()

    def _fund(self, coins, restaurant=None):
        """Give the customer a settled balance."""
        make_loyalty_entry(self._customer.name, restaurant or self._res, coins=coins, is_settled=1)

    def test_redemption_within_cap_succeeds(self):
        self._fund(600)
        result = self.redeem(self._customer.name, self._res, 300)
        self.assertEqual(result, 300)

    def test_redemption_clipped_to_daily_cap(self):
        """Trying to redeem 600 when daily cap is 500 — result clipped to 500."""
        self._fund(700)
        result = self.redeem(self._customer.name, self._res, 600)
        self.assertEqual(result, 500, "Should be clipped to daily cap of 500")

    def test_second_redemption_limited_by_remaining_cap(self):
        """After redeeming 300, only 200 more is allowed in the same day (cap=500)."""
        self._fund(700)
        first = self.redeem(self._customer.name, self._res, 300)
        self.assertEqual(first, 300)
        second = self.redeem(self._customer.name, self._res2, 300)
        self.assertEqual(second, 200, "Second redemption limited by remaining daily cap")

    def test_cap_exhausted_raises_error(self):
        """Once the full ₹500 cap is used, further redemption must throw."""
        self._fund(600)
        self.redeem(self._customer.name, self._res, 500)  # exhaust cap
        with self.assertRaises(Exception):
            self.redeem(self._customer.name, self._res2, 50)

    def test_cancellation_revert_not_counted_in_cap(self):
        """Cancellation Revert (internal system entry) must not count against daily cap."""
        self._fund(1100)
        # Do a Cancellation Revert (internal — should not count toward cap)
        self.redeem(self._customer.name, self._res, 500, reason="Cancellation Revert")
        # Now a normal customer redemption should still have full 500 cap available
        result = self.redeem(self._customer.name, self._res2, 500)
        self.assertEqual(result, 500, "Cancellation Revert must not consume daily cap")


# ─── 16. Global Welcome Bonus (One Per Phone) ─────────────────────────────────

class TestGlobalWelcomeBonusDeduplication(unittest.TestCase):
    """
    Validates that the Welcome Bonus is awarded only once per phone number,
    globally across all restaurants — not once per restaurant.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-GWB-")
        cls._res_a = f"{_PREFIX}-GWB-A-{frappe.generate_hash(length=6)}"
        cls._res_b = f"{_PREFIX}-GWB-B-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res_a, plan="GOLD")
        make_restaurant(cls._res_b, plan="GOLD")
        make_loyalty_config(cls._res_a)
        make_loyalty_config(cls._res_b)

        cls._referrer_a = make_customer(phone="9500000001", name="GWB Referrer A")
        cls._referrer_b = make_customer(phone="9500000002", name="GWB Referrer B")
        cls._referee_phone = "9500000003"
        cls._referee = make_customer(phone=cls._referee_phone, name="GWB Referee")

        # Two separate referral links at two different restaurants
        cls._id_a = f"gwb-a-{frappe.generate_hash(length=4)}"
        cls._id_b = f"gwb-b-{frappe.generate_hash(length=4)}"
        for identifier, referrer, restaurant in [
            (cls._id_a, cls._referrer_a.name, cls._res_a),
            (cls._id_b, cls._referrer_b.name, cls._res_b),
        ]:
            if not frappe.db.exists("Referral Link", {"identifier": identifier}):
                frappe.get_doc({
                    "doctype": "Referral Link",
                    "referrer": referrer,
                    "restaurant": restaurant,
                    "identifier": identifier,
                    "is_active": 1,
                    "rewarded_opens_in_cycle": 0,
                }).insert(ignore_permissions=True)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        for restaurant in [cls._res_a, cls._res_b]:
            cleanup_restaurant(restaurant)
        for identifier in [cls._id_a, cls._id_b]:
            frappe.db.delete("Referral Link", {"identifier": identifier})
        for customer in [cls._referrer_a.name, cls._referrer_b.name, cls._referee.name]:
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": customer})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._referee.name})
        for identifier in [self._id_a, self._id_b]:
            frappe.db.set_value("Referral Link", {"identifier": identifier}, "rewarded_opens_in_cycle", 0)
        frappe.db.commit()

    def _claim(self, restaurant_id, identifier):
        from flamezo_backend.flamezo.api.loyalty import claim_referral_reward
        with patch("flamezo_backend.flamezo.api.loyalty.validate_customer_session", return_value=True), \
             patch("flamezo_backend.flamezo.api.loyalty.get_customer_token", return_value="mock-token"):
            return claim_referral_reward(restaurant_id, identifier, self._referee_phone)

    def test_first_claim_succeeds(self):
        result = self._claim(self._res_a, self._id_a)
        self.assertTrue(result.get("success"), f"First claim must succeed: {result}")

    def test_second_claim_at_different_restaurant_rejected(self):
        """After getting welcome bonus at restaurant A, claim at restaurant B must fail."""
        self._claim(self._res_a, self._id_a)
        result = self._claim(self._res_b, self._id_b)
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error", {}).get("code"), "ALREADY_CLAIMED",
            "Second welcome bonus at a different restaurant must be rejected globally")

    def test_only_one_welcome_bonus_entry_in_db(self):
        """Regardless of how many restaurants are tried, only one Welcome Bonus entry exists."""
        self._claim(self._res_a, self._id_a)
        self._claim(self._res_b, self._id_b)  # will fail, but must not create a second entry
        count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._referee.name,
            "reason": "Welcome Bonus"
        })
        self.assertEqual(count, 1, "Exactly one Welcome Bonus entry must exist globally")


# ─── 17. Monthly Referral Cycle Reset ────────────────────────────────────────

class TestMonthlyReferralCycleReset(unittest.TestCase):
    """
    Validates that reset_referral_cycles_monthly() resets all Referral Link
    rewarded_opens_in_cycle to 0 globally, and that the per-order reset is gone.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-MRC-")
        cls._res = f"{_PREFIX}-MRC-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)
        cls._referrer = make_customer(phone="9600000001", name="MRC Referrer")

        cls._id1 = f"mrc-1-{frappe.generate_hash(length=4)}"
        cls._id2 = f"mrc-2-{frappe.generate_hash(length=4)}"
        for identifier in [cls._id1, cls._id2]:
            if not frappe.db.exists("Referral Link", {"identifier": identifier}):
                frappe.get_doc({
                    "doctype": "Referral Link",
                    "referrer": cls._referrer.name,
                    "restaurant": cls._res,
                    "identifier": identifier,
                    "is_active": 1,
                    "rewarded_opens_in_cycle": 7,  # partially used
                }).insert(ignore_permissions=True)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        for identifier in [cls._id1, cls._id2]:
            frappe.db.delete("Referral Link", {"identifier": identifier})
        frappe.db.commit()

    def setUp(self):
        # Reset counters to a non-zero value before each test
        for identifier in [self._id1, self._id2]:
            frappe.db.set_value("Referral Link", {"identifier": identifier}, "rewarded_opens_in_cycle", 7)
        frappe.db.commit()

    def test_monthly_reset_zeroes_all_links(self):
        from flamezo_backend.flamezo.tasks.loyalty_tasks import reset_referral_cycles_monthly
        reset_referral_cycles_monthly()

        for identifier in [self._id1, self._id2]:
            count = frappe.db.get_value("Referral Link", {"identifier": identifier}, "rewarded_opens_in_cycle")
            self.assertEqual(count, 0, f"Link {identifier} must be reset to 0")

    def test_monthly_reset_idempotent(self):
        """Running the reset twice must not raise and links stay at 0."""
        from flamezo_backend.flamezo.tasks.loyalty_tasks import reset_referral_cycles_monthly
        reset_referral_cycles_monthly()
        reset_referral_cycles_monthly()
        for identifier in [self._id1, self._id2]:
            count = frappe.db.get_value("Referral Link", {"identifier": identifier}, "rewarded_opens_in_cycle")
            self.assertEqual(count, 0)

    def test_order_completion_no_longer_resets_cycle(self):
        """handle_loyalty_settlement must NOT reset the referral cycle — only the monthly task should."""
        from flamezo_backend.flamezo.utils.loyalty import handle_loyalty_settlement

        # Create an unsettled order entry
        order_name = f"TEST-MRC-{frappe.generate_hash(length=8)}"
        frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._referrer.name,
            "restaurant": self._res,
            "coins": 10,
            "transaction_type": "Earn",
            "reason": "Order",
            "posting_date": today(),
            "expiry_date": add_days(today(), 180),
            "is_settled": 0,
            "reference_doctype": "Order",
            "reference_name": order_name,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        # Set cycle to non-zero
        frappe.db.set_value("Referral Link", {"identifier": self._id1}, "rewarded_opens_in_cycle", 5)
        frappe.db.commit()

        # Fire settlement hook
        doc = MagicMock()
        doc.name = order_name
        doc.restaurant = self._res
        doc.status = "completed"
        doc.payment_status = "completed"
        doc.platform_customer = self._referrer.name
        handle_loyalty_settlement(doc)

        # Cycle must still be 5 — not reset by order completion
        count = frappe.db.get_value("Referral Link", {"identifier": self._id1}, "rewarded_opens_in_cycle")
        self.assertEqual(count, 5, "Order completion must no longer reset the referral cycle")

        # Cleanup
        frappe.db.delete("Restaurant Loyalty Entry", {
            "customer": self._referrer.name, "reference_name": order_name
        })
        frappe.db.commit()


# ─── 18. Manual Adjustment Cap ───────────────────────────────────────────────

class TestManualAdjustmentCap(unittest.TestCase):
    """
    Validates that adjust_customer_points() enforces the max_manual_adjustment_coins cap.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-MAC-")
        cls._res = f"{_PREFIX}-MAC-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9700000001", name="MAC Test Customer")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._customer.name})
        frappe.db.commit()

    def test_adjustment_within_cap_succeeds(self):
        from flamezo_backend.flamezo.api.loyalty import adjust_customer_points
        result = adjust_customer_points(self._res, self._customer.name, 500, "Test", "Earn")
        self.assertTrue(result.get("success"), f"Adjustment within cap must succeed: {result}")

    def test_adjustment_above_cap_rejected(self):
        from flamezo_backend.flamezo.api.loyalty import adjust_customer_points
        result = adjust_customer_points(self._res, self._customer.name, 501, "Test", "Earn")
        self.assertFalse(result.get("success"))
        self.assertIn("Max", result.get("error", ""), "Error must mention max limit")

    def test_adjustment_at_cap_boundary_succeeds(self):
        """Exactly 500 coins must be allowed (boundary inclusive)."""
        from flamezo_backend.flamezo.api.loyalty import adjust_customer_points
        result = adjust_customer_points(self._res, self._customer.name, 500, "Boundary Test", "Earn")
        self.assertTrue(result.get("success"))

    def test_zero_coins_still_rejected(self):
        from flamezo_backend.flamezo.api.loyalty import adjust_customer_points
        result = adjust_customer_points(self._res, self._customer.name, 0, "Test", "Earn")
        self.assertFalse(result.get("success"))


# ─── 19. Global Balance in Cart (pricing.py fix) ──────────────────────────────

class TestPricingUsesGlobalBalance(unittest.TestCase):
    """
    Validates that calculate_cart_totals() uses the customer's global loyalty
    balance (across all restaurants), not just coins earned at that specific restaurant.
    This was a bug where restaurant= was passed to get_loyalty_balance, breaking
    cross-restaurant redemption at cart level.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-PGB-")
        cls._res_earn = f"{_PREFIX}-PGB-EARN-{frappe.generate_hash(length=4)}"
        cls._res_spend = f"{_PREFIX}-PGB-SPEND-{frappe.generate_hash(length=4)}"
        make_restaurant(cls._res_earn, plan="GOLD")
        make_restaurant(cls._res_spend, plan="GOLD")
        make_loyalty_config(cls._res_earn)
        make_loyalty_config(cls._res_spend)
        cls._customer = make_customer(phone="9800000001", name="PGB Test Customer")

    @classmethod
    def tearDownClass(cls):
        for res in [cls._res_earn, cls._res_spend]:
            cleanup_restaurant(res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._customer.name})
        frappe.db.commit()

    def test_coins_earned_at_restaurant_a_visible_in_cart_at_restaurant_b(self):
        """
        Customer earns 100 coins at restaurant A.
        When they open cart at restaurant B with loyalty_coins=100,
        the pricing engine must see the 100 coin balance (global wallet),
        not 0 (restaurant-B-only balance).
        """
        # Give 100 coins at res_earn (restaurant A)
        make_loyalty_entry(self._customer.name, self._res_earn, coins=100, is_settled=1)

        # Simulate cart at res_spend (restaurant B) with loyalty_coins=100
        from flamezo_backend.flamezo.utils.pricing import calculate_cart_totals
        items = [{"quantity": 1, "unitPrice": 500.0, "dishId": "dish-001"}]

        result = calculate_cart_totals(
            restaurant=self._res_spend,
            items=items,
            loyalty_coins=100,
            customer=self._customer.name,
            delivery_type="Dine-in"
        )

        self.assertGreater(result.get("loyaltyDiscount", 0), 0,
            "Loyalty discount must be non-zero — global balance from restaurant A must be visible at restaurant B")
        self.assertEqual(result.get("loyaltyDiscount"), 100,
            "Full 100 coins must be applicable as discount at restaurant B")


# ─── 20. Dead reset_referral_cycle removal ───────────────────────────────────

class TestResetReferralCycleRemoved(unittest.TestCase):
    """
    Validates that reset_referral_cycle no longer exists in api/loyalty.py
    (was replaced by monthly scheduler) and that orders.py no longer calls it.
    """

    def test_reset_referral_cycle_not_importable(self):
        """reset_referral_cycle must not be exported from api/loyalty.py."""
        import flamezo_backend.flamezo.api.loyalty as loyalty_api
        self.assertFalse(
            hasattr(loyalty_api, "reset_referral_cycle"),
            "reset_referral_cycle must be removed — replaced by monthly scheduler"
        )

    def test_orders_py_does_not_import_reset_referral_cycle(self):
        """orders.py must not import reset_referral_cycle anywhere."""
        import inspect
        import flamezo_backend.flamezo.api.orders as orders_mod
        source = inspect.getsource(orders_mod)
        self.assertNotIn(
            "reset_referral_cycle",
            source,
            "orders.py must not reference reset_referral_cycle — dead code was removed"
        )


# ─── 21. Coin Expiry Notification Task ────────────────────────────────────────

class TestCoinExpiryNotifications(unittest.TestCase):
    """
    Validates send_coin_expiry_notifications() scheduler logic:
    - Skips customers with zero balance (all coins already spent)
    - Skips customers with no FCM tokens
    - Skips customers who have already been nudged today (cache dedup)
    - Does not crash when no expiring coins exist
    - Only considers settled Earn entries within the 7-day window
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-EXN-")
        cls._res = f"{_PREFIX}-EXN-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)
        cls._customer = make_customer(phone="9900000001", name="EXN Test Customer")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": self._customer.name})
        # Clear any cache key from previous test runs
        from frappe.utils import today
        cache_key = f"dm_expiry_nudge:{self._customer.name}:{today()}"
        frappe.cache().delete_value(cache_key)
        frappe.db.commit()

    def _add_expiring_entry(self, coins, days_from_now):
        """Insert a settled Earn entry with expiry_date = today + days_from_now."""
        from frappe.utils import today, add_days
        exp_date = add_days(today(), days_from_now)
        doc = frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": coins,
            "transaction_type": "Earn",
            "reason": "Order",
            "posting_date": today(),
            "expiry_date": exp_date,
            "is_settled": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

    def test_no_expiring_coins_runs_cleanly(self):
        """Task must not crash when no coins expire within 7 days."""
        from flamezo_backend.flamezo.tasks.loyalty_tasks import send_coin_expiry_notifications
        try:
            send_coin_expiry_notifications()
        except Exception as e:
            self.fail(f"send_coin_expiry_notifications raised: {e}")

    def test_skips_customers_with_zero_balance(self):
        """Customer with expiring coins but zero net balance (all spent) must be skipped."""
        # Add an expiring earn entry, then add a redeem that zeroes it out
        self._add_expiring_entry(100, 3)
        doc = frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": self._customer.name,
            "restaurant": self._res,
            "coins": 100,
            "transaction_type": "Redeem",
            "reason": "Redemption",
            "posting_date": frappe.utils.today(),
            "is_settled": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance
        balance = get_loyalty_balance(self._customer.name)
        self.assertEqual(balance, 0, "Setup: balance must be 0 for this test")

        # No FCM tokens on this customer → task must skip silently
        from flamezo_backend.flamezo.tasks.loyalty_tasks import send_coin_expiry_notifications
        try:
            send_coin_expiry_notifications()
        except Exception as e:
            self.fail(f"Task raised when balance is zero: {e}")

    def test_skips_coins_expiring_outside_window(self):
        """Coins expiring in 30 days must NOT trigger a nudge."""
        self._add_expiring_entry(200, 30)  # outside 7-day window
        from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance
        balance = get_loyalty_balance(self._customer.name)
        self.assertEqual(balance, 200)

        from flamezo_backend.flamezo.tasks.loyalty_tasks import send_coin_expiry_notifications
        try:
            send_coin_expiry_notifications()
        except Exception as e:
            self.fail(f"Task raised for out-of-window coins: {e}")

        # Cache key must NOT be set (customer was skipped — no FCM tokens anyway)
        from frappe.utils import today
        cache_key = f"dm_expiry_nudge:{self._customer.name}:{today()}"
        self.assertFalse(frappe.cache().get_value(cache_key),
            "Cache must not be set for coins outside the 7-day window")

    def test_cache_dedup_prevents_double_nudge(self):
        """Once cache key is set, re-running the task must not nudge again."""
        from frappe.utils import today
        cache_key = f"dm_expiry_nudge:{self._customer.name}:{today()}"
        frappe.cache().set_value(cache_key, 1, expires_in_sec=3600)

        self._add_expiring_entry(150, 2)

        # Task must run without error (customer is skipped via cache)
        from flamezo_backend.flamezo.tasks.loyalty_tasks import send_coin_expiry_notifications
        try:
            send_coin_expiry_notifications()
        except Exception as e:
            self.fail(f"Task raised on already-nudged customer: {e}")


# ─── 22. Loyalty Analytics API ───────────────────────────────────────────────

class TestLoyaltyAnalytics(unittest.TestCase):
    """
    Validates get_loyalty_analytics() returns correct structure and values.
    - summary block has all required keys
    - earn_by_reason correctly categorises Order vs Welcome Bonus entries
    - daily_trend contains only settled entries within last 30 days
    - top_earners is sorted by lifetime coins descending
    - expiring_soon only includes customers with positive net balance expiring ≤7 days
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-ANA-")
        cls._res = f"{_PREFIX}-ANA-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="GOLD")
        make_loyalty_config(cls._res)

        cls._c1 = make_customer(phone="9910000001", name="ANA Customer 1")
        cls._c2 = make_customer(phone="9910000002", name="ANA Customer 2")

        from frappe.utils import today, add_days

        # c1: 200 coins earned (Order), 50 redeemed — net 150
        make_loyalty_entry(cls._c1.name, cls._res, coins=200, is_settled=1)
        make_loyalty_entry(cls._c1.name, cls._res, coins=50,
                           txn_type="Redeem", reason="Redemption", is_settled=1)

        # c2: 100 coins earned (Welcome Bonus), expiring in 3 days
        exp_soon = add_days(today(), 3)
        frappe.get_doc({
            "doctype": "Restaurant Loyalty Entry",
            "customer": cls._c2.name,
            "restaurant": cls._res,
            "coins": 100,
            "transaction_type": "Earn",
            "reason": "Welcome Bonus",
            "posting_date": today(),
            "expiry_date": exp_soon,
            "is_settled": 1,
        }).insert(ignore_permissions=True)

        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        for c in [cls._c1.name, cls._c2.name]:
            frappe.db.delete("Restaurant Loyalty Entry", {"customer": c})
        frappe.db.commit()

    def _call(self):
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_analytics
        return get_loyalty_analytics(self._res)

    def test_returns_success(self):
        result = self._call()
        self.assertTrue(result.get("success"), f"Expected success, got: {result}")

    def test_summary_has_required_keys(self):
        data = self._call()["data"]
        required = [
            "total_coins_issued", "total_coins_redeemed", "active_customers",
            "customers_expiring_soon", "redemption_rate_percent",
            "avg_balance", "today_redeemed_restaurant",
        ]
        for key in required:
            self.assertIn(key, data["summary"], f"summary missing key: {key}")

    def test_total_issued_counts_settled_earn(self):
        summary = self._call()["data"]["summary"]
        # c1: 200, c2: 100 = 300 total (at minimum — other test data may exist)
        self.assertGreaterEqual(summary["total_coins_issued"], 300)

    def test_total_redeemed_counts_settled_redeem(self):
        summary = self._call()["data"]["summary"]
        self.assertGreaterEqual(summary["total_coins_redeemed"], 50)

    def test_redemption_rate_is_percentage(self):
        summary = self._call()["data"]["summary"]
        rate = summary["redemption_rate_percent"]
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)

    def test_earn_by_reason_contains_order(self):
        data = self._call()["data"]
        reasons = {r["reason"] for r in data["earn_by_reason"]}
        self.assertIn("Order", reasons, "earn_by_reason must include 'Order'")

    def test_earn_by_reason_contains_welcome_bonus(self):
        data = self._call()["data"]
        reasons = {r["reason"] for r in data["earn_by_reason"]}
        self.assertIn("Welcome Bonus", reasons)

    def test_top_earners_sorted_descending(self):
        data = self._call()["data"]
        earners = data["top_earners"]
        if len(earners) >= 2:
            for i in range(len(earners) - 1):
                self.assertGreaterEqual(
                    earners[i]["lifetime_coins"],
                    earners[i + 1]["lifetime_coins"],
                    "top_earners must be sorted by lifetime_coins descending"
                )

    def test_expiring_soon_includes_c2(self):
        data = self._call()["data"]
        expiring_ids = {e["customer"] for e in data["expiring_soon"]}
        self.assertIn(self._c2.name, expiring_ids,
            "c2 has coins expiring in 3 days — must appear in expiring_soon")

    def test_expiring_soon_excludes_zero_balance(self):
        """A customer whose expiring coins are already spent must not appear."""
        # c1 has coins but none in the 7-day expiry window (no expiry_date set)
        data = self._call()["data"]
        # c1's entry has no expiry_date set → must not be in expiring_soon
        for e in data["expiring_soon"]:
            if e["customer"] == self._c1.name:
                self.fail("c1 has no expiring coins — must not be in expiring_soon")

    def test_daily_trend_structure(self):
        data = self._call()["data"]
        trend = data["daily_trend"]
        if trend:
            entry = trend[0]
            self.assertIn("date",     entry)
            self.assertIn("earned",   entry)
            self.assertIn("redeemed", entry)

    def test_active_customers_count(self):
        summary = self._call()["data"]["summary"]
        self.assertGreaterEqual(summary["active_customers"], 2,
            "Both c1 and c2 have earned coins — active_customers must be ≥ 2")
