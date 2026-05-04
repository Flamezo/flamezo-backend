# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

"""
Production-grade tests for coin_billing.py

Covers:
  - get_bonus_units()          — pure math, no DB
  - record_transaction()       — atomic balance updates, sign convention, fail_below guard, suspension
  - check_and_trigger_auto_recharge() — all branch coverage
  - _credit_autopay_coins()    — idempotency
  - deduct_coins()             — grace limit enforcement
  - update_subscription_plan() — barrier checks, Tomorrow Rule
  - initialize_free_coins()    — idempotent signup bonus
  - process_referral_bonus()   — first-purchase trigger, double-dip prevention

Run with:
    bench run-tests --app dinematters --module dinematters.dinematters.tests.test_coin_billing
"""

import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.utils import add_days, getdate

from dinematters.dinematters.tests.utils import (
    make_restaurant,
    make_coin_transaction,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    reset_restaurant_balance,
    clear_transactions,
    get_latest_transaction,
)

# All test restaurants share this prefix for safe bulk cleanup
_PREFIX = "TEST-CB"


# ─── 1. Pure unit tests: get_bonus_units() ───────────────────────────────────

class TestGetBonusUnits(unittest.TestCase):
    """
    No DB interaction required.
    Validates bonus tier math including boundary values.
    """

    def setUp(self):
        from dinematters.dinematters.api.coin_billing import get_bonus_units
        self.get_bonus_units = get_bonus_units

    # Below 999 — no bonus
    def test_zero_amount_no_bonus(self):
        self.assertEqual(self.get_bonus_units(0), 0)

    def test_below_999_no_bonus(self):
        self.assertEqual(self.get_bonus_units(500), 0)

    def test_998_no_bonus(self):
        self.assertEqual(self.get_bonus_units(998), 0)

    # 999 — mini-bonus (+₹1)
    def test_exactly_999_gets_mini_bonus(self):
        self.assertEqual(self.get_bonus_units(999), 1.0)

    # 1000 — above mini threshold, below tier 1; no bonus
    def test_exactly_1000_no_bonus(self):
        self.assertEqual(self.get_bonus_units(1000), 0)

    def test_2998_no_bonus(self):
        self.assertEqual(self.get_bonus_units(2998), 0)

    # Tier 1: 2999–4998 → 10% bonus
    def test_tier1_lower_boundary_2999(self):
        bonus = self.get_bonus_units(2999)
        self.assertAlmostEqual(bonus, 2999 * 0.10, places=2)

    def test_tier1_midpoint_3500(self):
        bonus = self.get_bonus_units(3500)
        self.assertAlmostEqual(bonus, 350.0, places=2)

    def test_tier1_upper_boundary_4998(self):
        bonus = self.get_bonus_units(4998)
        self.assertAlmostEqual(bonus, 4998 * 0.10, places=2)

    # Tier 2: >= 4999 → 20% bonus
    def test_tier2_lower_boundary_4999(self):
        bonus = self.get_bonus_units(4999)
        self.assertAlmostEqual(bonus, 4999 * 0.20, places=2)

    def test_tier2_round_5000(self):
        bonus = self.get_bonus_units(5000)
        self.assertAlmostEqual(bonus, 1000.0, places=2)

    def test_tier2_large_amount(self):
        bonus = self.get_bonus_units(10000)
        self.assertAlmostEqual(bonus, 2000.0, places=2)


# ─── 2. Integration tests: record_transaction() ──────────────────────────────

class TestRecordTransaction(unittest.TestCase):
    """
    Tests atomic balance updates, correct sign convention on the Coin Transaction
    document, the fail_below guard, and suspension triggering.

    All fixtures use unique restaurant names and are explicitly deleted in tearDown
    because record_transaction() calls frappe.db.commit() internally.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-RT-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-RT-")

    def setUp(self):
        self._res_name = f"{_PREFIX}-RT-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res_name, plan="GOLD", balance=1000.0)
        # Restaurant creation hooks may auto-grant free coins — reset to a known state.
        reset_restaurant_balance(self._res_name, 1000.0)
        clear_transactions(self._res_name)
        from dinematters.dinematters.api.coin_billing import record_transaction
        self.record_transaction = record_transaction

    def tearDown(self):
        cleanup_restaurant(self._res_name)

    # ── balance arithmetic ──

    def test_purchase_increases_balance(self):
        new_bal = self.record_transaction(
            self._res_name, "Purchase", 200.0, "top-up"
        )
        self.assertAlmostEqual(new_bal, 1200.0, places=2)
        self.assertAlmostEqual(
            frappe.db.get_value("Restaurant", self._res_name, "coins_balance"),
            1200.0, places=2
        )

    def test_free_coins_increases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Free Coins", 60.0)
        self.assertAlmostEqual(new_bal, 1060.0, places=2)

    def test_refund_increases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Refund", 50.0)
        self.assertAlmostEqual(new_bal, 1050.0, places=2)

    def test_autopay_recharge_increases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Autopay Recharge", 500.0)
        self.assertAlmostEqual(new_bal, 1500.0, places=2)

    def test_ai_deduction_decreases_balance(self):
        new_bal = self.record_transaction(self._res_name, "AI Deduction", 30.0)
        self.assertAlmostEqual(new_bal, 970.0, places=2)

    def test_commission_deduction_decreases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Commission Deduction", 45.0)
        self.assertAlmostEqual(new_bal, 955.0, places=2)

    def test_daily_gold_subscription_decreases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Daily GOLD Subscription", 33.30)
        self.assertAlmostEqual(new_bal, 966.70, places=2)

    def test_daily_diamond_floor_decreases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Daily DIAMOND Floor", 43.30)
        self.assertAlmostEqual(new_bal, 956.70, places=2)

    def test_delivery_fee_decreases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Delivery Fee", 25.0)
        self.assertAlmostEqual(new_bal, 975.0, places=2)

    def test_admin_adjustment_positive_increases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Admin Adjustment", 100.0)
        self.assertAlmostEqual(new_bal, 1100.0, places=2)

    def test_admin_adjustment_negative_decreases_balance(self):
        new_bal = self.record_transaction(self._res_name, "Admin Adjustment", -200.0)
        self.assertAlmostEqual(new_bal, 800.0, places=2)

    # ── Coin Transaction document sign convention ──

    def test_deduction_creates_negative_amount_in_doc(self):
        self.record_transaction(self._res_name, "AI Deduction", 10.0, "sign test")
        txn = get_latest_transaction(self._res_name, "AI Deduction")
        self.assertIsNotNone(txn)
        self.assertLess(txn.amount, 0, "Deduction transaction amount must be negative")

    def test_credit_creates_positive_amount_in_doc(self):
        self.record_transaction(self._res_name, "Purchase", 10.0, "sign test")
        txn = get_latest_transaction(self._res_name, "Purchase")
        self.assertIsNotNone(txn)
        self.assertGreater(txn.amount, 0, "Credit transaction amount must be positive")

    def test_balance_after_matches_new_balance(self):
        new_bal = self.record_transaction(self._res_name, "Purchase", 100.0)
        txn = get_latest_transaction(self._res_name, "Purchase")
        self.assertAlmostEqual(txn.balance_after, new_bal, places=2)

    # ── fail_below guard ──

    def test_fail_below_raises_when_balance_would_go_under_limit(self):
        """Restaurant has ₹1000. Deducting ₹900 with fail_below=200 should raise."""
        reset_restaurant_balance(self._res_name, 1000.0)
        with self.assertRaises(frappe.ValidationError):
            self.record_transaction(
                self._res_name, "AI Deduction", 900.0,
                fail_below=200.0
            )

    def test_fail_below_succeeds_when_balance_stays_above_limit(self):
        """Deducting ₹100 with fail_below=200 and balance=1000 should succeed."""
        reset_restaurant_balance(self._res_name, 1000.0)
        new_bal = self.record_transaction(
            self._res_name, "AI Deduction", 100.0,
            fail_below=200.0
        )
        self.assertAlmostEqual(new_bal, 900.0, places=2)

    def test_fail_below_none_never_raises(self):
        """When fail_below is None, any deduction is allowed."""
        reset_restaurant_balance(self._res_name, 10.0)
        new_bal = self.record_transaction(
            self._res_name, "AI Deduction", 500.0,
            fail_below=None
        )
        self.assertAlmostEqual(new_bal, -490.0, places=2)

    # ── suspension at -₹300 ──

    def test_suspension_triggered_when_balance_drops_below_negative_300(self):
        """
        When new_balance < -300 after a deduction, suspend_restaurant_billing() must be called.
        We patch the method on the Restaurant doc to verify the call.
        """
        reset_restaurant_balance(self._res_name, 100.0)
        with patch.object(
            frappe.get_doc("Restaurant", self._res_name).__class__,
            "suspend_restaurant_billing",
            return_value=None
        ) as mock_suspend:
            self.record_transaction(self._res_name, "AI Deduction", 500.0)
            mock_suspend.assert_called_once()

    def test_suspension_not_triggered_when_balance_stays_above_negative_100(self):
        """If new balance is -99, suspension must NOT be triggered."""
        reset_restaurant_balance(self._res_name, 1.0)
        with patch.object(
            frappe.get_doc("Restaurant", self._res_name).__class__,
            "suspend_restaurant_billing",
            return_value=None
        ) as mock_suspend:
            self.record_transaction(self._res_name, "AI Deduction", 99.0)
            mock_suspend.assert_not_called()

    # ── auto-recharge trigger ──

    @patch("dinematters.dinematters.api.coin_billing.check_and_trigger_auto_recharge")
    def test_auto_recharge_checked_after_deduction(self, mock_check):
        """check_and_trigger_auto_recharge must be called after each deduction."""
        self.record_transaction(self._res_name, "AI Deduction", 10.0)
        mock_check.assert_called_once_with(self._res_name, unittest.mock.ANY)

    @patch("dinematters.dinematters.api.coin_billing.check_and_trigger_auto_recharge")
    def test_auto_recharge_not_checked_after_credit(self, mock_check):
        """check_and_trigger_auto_recharge must NOT be called after a credit."""
        self.record_transaction(self._res_name, "Purchase", 10.0)
        mock_check.assert_not_called()


# ─── 3. check_and_trigger_auto_recharge() ────────────────────────────────────

class TestCheckAndTriggerAutoRecharge(unittest.TestCase):
    """
    Validates all branches of the auto-recharge guard logic.
    frappe.enqueue is patched to prevent real background jobs.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-AR-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-AR-")

    def setUp(self):
        self._res_name = f"{_PREFIX}-AR-{frappe.generate_hash(length=6)}"
        from dinematters.dinematters.api.coin_billing import check_and_trigger_auto_recharge
        self.check = check_and_trigger_auto_recharge

    def tearDown(self):
        cleanup_restaurant(self._res_name)

    @patch("frappe.enqueue")
    def test_skips_if_auto_recharge_disabled(self, mock_enqueue):
        make_restaurant(self._res_name, balance=50.0, auto_recharge_enabled=0,
                        auto_recharge_threshold=200.0)
        self.check(self._res_name, 50.0)
        mock_enqueue.assert_not_called()

    @patch("frappe.enqueue")
    def test_skips_if_balance_above_threshold(self, mock_enqueue):
        """Balance (500) is above threshold (200) — no recharge needed."""
        make_restaurant(self._res_name, balance=500.0,
                        auto_recharge_enabled=1, auto_recharge_threshold=200.0)
        self.check(self._res_name, 500.0)
        mock_enqueue.assert_not_called()

    @patch("frappe.enqueue")
    def test_enqueues_when_balance_below_threshold(self, mock_enqueue):
        """Balance (100) is below threshold (200) — should enqueue recharge."""
        make_restaurant(self._res_name, balance=100.0,
                        auto_recharge_enabled=1, auto_recharge_threshold=200.0,
                        auto_recharge_amount=1000.0, daily_auto_recharge_count=0.0)
        self.check(self._res_name, 100.0)
        mock_enqueue.assert_called_once()
        enqueue_call_kwargs = mock_enqueue.call_args[0][0]
        self.assertIn("trigger_auto_recharge", enqueue_call_kwargs)

    @patch("frappe.enqueue")
    def test_skips_if_daily_limit_would_be_exceeded(self, mock_enqueue):
        """
        daily_auto_recharge_count is already 4500.
        Recharge amount 1000 would push it to 5500 > AUTO_RECHARGE_DAILY_LIMIT (5000).
        """
        make_restaurant(self._res_name, balance=50.0,
                        auto_recharge_enabled=1, auto_recharge_threshold=200.0,
                        auto_recharge_amount=1000.0, daily_auto_recharge_count=4500.0,
                        last_auto_recharge_date=frappe.utils.today())
        self.check(self._res_name, 50.0)
        mock_enqueue.assert_not_called()

    @patch("frappe.enqueue")
    def test_resets_daily_count_on_new_day(self, mock_enqueue):
        """
        If last_auto_recharge_date is yesterday, the counter resets to 0 and
        recharge should be allowed even if count was high.
        """
        yesterday = add_days(frappe.utils.today(), -1)
        make_restaurant(self._res_name, balance=50.0,
                        auto_recharge_enabled=1, auto_recharge_threshold=200.0,
                        auto_recharge_amount=1000.0, daily_auto_recharge_count=4900.0,
                        last_auto_recharge_date=yesterday)
        self.check(self._res_name, 50.0)
        mock_enqueue.assert_called_once()


# ─── 4. _credit_autopay_coins() idempotency ──────────────────────────────────

class TestCreditAutoPayCoinsIdempotency(unittest.TestCase):
    """
    _credit_autopay_coins() must be a no-op if a Coin Transaction with the
    same restaurant + payment_id + type "Autopay Recharge" already exists.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-CAP-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-CAP-")

    def setUp(self):
        self._res_name = f"{_PREFIX}-CAP-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res_name, balance=500.0)
        # Reset after creation hook auto-grants may fire
        reset_restaurant_balance(self._res_name, 500.0)
        clear_transactions(self._res_name)
        from dinematters.dinematters.api.coin_billing import _credit_autopay_coins
        self._credit_autopay_coins = _credit_autopay_coins

    def tearDown(self):
        cleanup_restaurant(self._res_name)

    def test_credits_on_first_call(self):
        self._credit_autopay_coins(self._res_name, 1000.0, "pay_unique_111", 200.0)
        new_bal = frappe.db.get_value("Restaurant", self._res_name, "coins_balance")
        self.assertAlmostEqual(new_bal, 1500.0, places=2)

    def test_idempotent_on_duplicate_payment_id(self):
        """Second call with same payment_id must not credit again."""
        self._credit_autopay_coins(self._res_name, 1000.0, "pay_dup_222", 200.0)
        balance_after_first = frappe.db.get_value("Restaurant", self._res_name, "coins_balance")

        self._credit_autopay_coins(self._res_name, 1000.0, "pay_dup_222", 200.0)
        balance_after_second = frappe.db.get_value("Restaurant", self._res_name, "coins_balance")

        self.assertAlmostEqual(balance_after_first, balance_after_second, places=2,
                               msg="Duplicate payment_id must not credit twice")

    def test_different_payment_ids_both_credited(self):
        """Two distinct payment IDs must both result in credits."""
        self._credit_autopay_coins(self._res_name, 500.0, "pay_A", 200.0)
        self._credit_autopay_coins(self._res_name, 500.0, "pay_B", 200.0)
        final_bal = frappe.db.get_value("Restaurant", self._res_name, "coins_balance")
        self.assertAlmostEqual(final_bal, 1500.0, places=2)


# ─── 5. deduct_coins() grace limit ───────────────────────────────────────────

class TestDeductCoins(unittest.TestCase):
    """
    deduct_coins() enforces a fail_below of -100 (the grace limit).
    Below that, the deduction must raise ValidationError.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-DC-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-DC-")

    def setUp(self):
        self._res_name = f"{_PREFIX}-DC-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res_name, balance=0.0)
        reset_restaurant_balance(self._res_name, 0.0)
        clear_transactions(self._res_name)
        from dinematters.dinematters.api.coin_billing import deduct_coins
        self.deduct_coins = deduct_coins

    def tearDown(self):
        cleanup_restaurant(self._res_name)

    def test_deduction_succeeds_within_grace_limit(self):
        """Balance 0 → deduct 99 → new balance -99 (still above -100 grace limit)."""
        reset_restaurant_balance(self._res_name, 0.0)
        new_bal = self.deduct_coins(
            restaurant=self._res_name,
            amount=99.0,
            type="AI Deduction",
            description="within grace"
        )
        self.assertAlmostEqual(new_bal, -99.0, places=2)

    def test_deduction_succeeds_exactly_at_grace_limit(self):
        """Balance 0 → deduct 100 → new balance exactly -100 (boundary, allowed)."""
        reset_restaurant_balance(self._res_name, 0.0)
        new_bal = self.deduct_coins(
            restaurant=self._res_name,
            amount=100.0,
            type="AI Deduction",
            description="at grace boundary"
        )
        self.assertAlmostEqual(new_bal, -100.0, places=2)

    def test_deduction_fails_beyond_grace_limit(self):
        """Balance 0 → deduct 101 → would be -101 < -100 → ValidationError."""
        reset_restaurant_balance(self._res_name, 0.0)
        with self.assertRaises(frappe.ValidationError):
            self.deduct_coins(
                restaurant=self._res_name,
                amount=101.0,
                type="AI Deduction",
                description="beyond grace"
            )

    def test_deduction_fails_when_already_at_grace_limit(self):
        """Balance already -100 → any further deduction must fail."""
        reset_restaurant_balance(self._res_name, -100.0)
        clear_transactions(self._res_name)
        with self.assertRaises(frappe.ValidationError):
            self.deduct_coins(
                restaurant=self._res_name,
                amount=1.0,
                type="AI Deduction",
                description="already at limit"
            )


# ─── 6. update_subscription_plan() ───────────────────────────────────────────

class TestUpdateSubscriptionPlan(unittest.TestCase):
    """
    Tests the 'Tomorrow Rule' for plan changes and the balance barrier checks
    for GOLD and DIAMOND upgrades.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-USP-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-USP-")

    def setUp(self):
        self._res_name = f"{_PREFIX}-USP-{frappe.generate_hash(length=6)}"
        from dinematters.dinematters.api.coin_billing import update_subscription_plan
        self.update_subscription_plan = update_subscription_plan

    def tearDown(self):
        cleanup_restaurant(self._res_name)

    def test_invalid_plan_type_raises(self):
        make_restaurant(self._res_name, plan="SILVER", balance=5000.0)
        with self.assertRaises(frappe.exceptions.ValidationError):
            self.update_subscription_plan(self._res_name, "PLATINUM")

    def test_same_plan_returns_success_without_change(self):
        make_restaurant(self._res_name, plan="GOLD", balance=5000.0)
        result = self.update_subscription_plan(self._res_name, "GOLD")
        self.assertTrue(result["success"])
        self.assertFalse(result.get("deferred", False))

    def test_gold_upgrade_fails_when_balance_below_minimum(self):
        """GOLD requires balance >= monthly_minimum (default 999). Balance 500 must fail."""
        make_restaurant(self._res_name, plan="SILVER", balance=500.0, monthly_minimum=999.0)
        with self.assertRaises(frappe.ValidationError):
            self.update_subscription_plan(self._res_name, "GOLD")

    def test_gold_upgrade_succeeds_when_balance_meets_minimum(self):
        make_restaurant(self._res_name, plan="SILVER", balance=1000.0, monthly_minimum=999.0)
        result = self.update_subscription_plan(self._res_name, "GOLD")
        self.assertTrue(result["success"])
        self.assertTrue(result["deferred"])
        self.assertEqual(result["plan_type"], "GOLD")

    def test_diamond_upgrade_fails_when_balance_below_barrier(self):
        """DIAMOND requires balance >= diamond_upgrade_barrier (default 1299). Balance 500 must fail."""
        make_restaurant(self._res_name, plan="SILVER", balance=500.0)
        with self.assertRaises(frappe.ValidationError):
            self.update_subscription_plan(self._res_name, "DIAMOND")

    def test_diamond_upgrade_succeeds_when_balance_meets_barrier(self):
        make_restaurant(self._res_name, plan="SILVER", balance=2000.0)
        result = self.update_subscription_plan(self._res_name, "DIAMOND")
        self.assertTrue(result["success"])
        self.assertTrue(result["deferred"])
        self.assertEqual(result["plan_type"], "DIAMOND")

    def test_plan_change_deferred_to_tomorrow(self):
        """effective_date must be tomorrow, plan_type must NOT change immediately."""
        make_restaurant(self._res_name, plan="SILVER", balance=2000.0)
        result = self.update_subscription_plan(self._res_name, "GOLD")
        tomorrow = add_days(getdate(), 1)

        # Check deferred fields in DB
        res = frappe.db.get_value(
            "Restaurant", self._res_name,
            ["deferred_plan_type", "plan_change_date", "plan_type"],
            as_dict=True
        )
        self.assertEqual(res.deferred_plan_type, "GOLD")
        self.assertEqual(getdate(res.plan_change_date), tomorrow)
        # Current plan must remain SILVER until midnight
        self.assertEqual(res.plan_type, "SILVER")

    def test_downgrade_silver_no_balance_check(self):
        """Downgrading to SILVER must always succeed regardless of balance."""
        make_restaurant(self._res_name, plan="GOLD", balance=0.0)
        result = self.update_subscription_plan(self._res_name, "SILVER")
        self.assertTrue(result["success"])


# ─── 7. initialize_free_coins() ──────────────────────────────────────────────

class TestInitializeFreeCoins(unittest.TestCase):
    """Signup bonus: 60 coins, granted exactly once per restaurant."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-IFC-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-IFC-")

    def setUp(self):
        self._res_name = f"{_PREFIX}-IFC-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res_name, balance=0.0)
        # Clear the auto-hook free coins so initialize_free_coins() sees a clean slate
        reset_restaurant_balance(self._res_name, 0.0)
        clear_transactions(self._res_name)
        from dinematters.dinematters.api.coin_billing import initialize_free_coins
        self.initialize_free_coins = initialize_free_coins

    def tearDown(self):
        cleanup_restaurant(self._res_name)

    def test_grants_60_coins_on_first_call(self):
        result = self.initialize_free_coins(self._res_name)
        self.assertTrue(result)
        new_bal = frappe.db.get_value("Restaurant", self._res_name, "coins_balance")
        self.assertAlmostEqual(new_bal, 60.0, places=2)

    def test_idempotent_no_double_grant(self):
        self.initialize_free_coins(self._res_name)
        result_second = self.initialize_free_coins(self._res_name)
        self.assertFalse(result_second)
        # Balance must still be exactly 60 (not 120)
        new_bal = frappe.db.get_value("Restaurant", self._res_name, "coins_balance")
        self.assertAlmostEqual(new_bal, 60.0, places=2)

    def test_skips_if_legacy_ai_credit_exists(self):
        """
        If an AI Credit Transaction 'Free Credits' exists, initialize_free_coins
        must not grant coins (avoids double-dipping during legacy migration).
        """
        frappe.get_doc({
            "doctype": "AI Credit Transaction",
            "restaurant": self._res_name,
            "transaction_type": "Free Credits",
            "credits": 30,
            "balance_after": 30,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        granted = self.initialize_free_coins(self._res_name)
        self.assertFalse(granted)
        # Clean up AI Credit Transaction
        frappe.db.delete("AI Credit Transaction", {"restaurant": self._res_name})
        frappe.db.commit()


# ─── 8. process_referral_bonus() ─────────────────────────────────────────────

class TestProcessReferralBonus(unittest.TestCase):
    """
    Referral bonus (₹500 to each party) fires only on the referee's first
    purchase of ₹1000+, and is idempotent against double-fire.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-RB-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-RB-")

    def setUp(self):
        self._referrer = f"{_PREFIX}-RB-REF-{frappe.generate_hash(length=6)}"
        self._referee = f"{_PREFIX}-RB-NEW-{frappe.generate_hash(length=6)}"

        make_restaurant(self._referrer, balance=500.0)
        make_restaurant(
            self._referee, balance=0.0,
            referred_by_restaurant=self._referrer
        )
        # Reset both after creation hooks may auto-grant free coins
        reset_restaurant_balance(self._referrer, 500.0)
        clear_transactions(self._referrer)
        reset_restaurant_balance(self._referee, 0.0)
        clear_transactions(self._referee)
        from dinematters.dinematters.api.coin_billing import process_referral_bonus
        self.process_referral_bonus = process_referral_bonus

    def tearDown(self):
        cleanup_restaurant(self._referrer)
        cleanup_restaurant(self._referee)

    def test_no_referrer_skips_silently(self):
        # A restaurant with no referred_by_restaurant
        solo_res = f"{_PREFIX}-RB-SOLO-{frappe.generate_hash(length=6)}"
        make_restaurant(solo_res, balance=0.0)
        reset_restaurant_balance(solo_res, 0.0)
        clear_transactions(solo_res)
        try:
            bal_before = frappe.db.get_value("Restaurant", solo_res, "coins_balance")
            self.process_referral_bonus(solo_res)  # must not raise
            bal_after = frappe.db.get_value("Restaurant", solo_res, "coins_balance")
            # No bonus must be granted — balance unchanged
            self.assertAlmostEqual(bal_after, bal_before, places=2)
        finally:
            cleanup_restaurant(solo_res)

    def test_first_purchase_grants_500_to_both_parties(self):
        """
        After the referee's first Purchase transaction, both the referee
        and the referrer must receive ₹500 Free Coins.
        """
        # Simulate the first Purchase being already recorded (txn_count will be 1)
        make_coin_transaction(self._referee, "Purchase", 1000.0, "First recharge")
        referrer_bal_before = frappe.db.get_value("Restaurant", self._referrer, "coins_balance")
        referee_bal_before = frappe.db.get_value("Restaurant", self._referee, "coins_balance")

        self.process_referral_bonus(self._referee)

        referrer_bal_after = frappe.db.get_value("Restaurant", self._referrer, "coins_balance")
        referee_bal_after = frappe.db.get_value("Restaurant", self._referee, "coins_balance")

        self.assertAlmostEqual(referrer_bal_after - referrer_bal_before, 500.0, places=2,
                               msg="Referrer must receive ₹500 bonus")
        self.assertAlmostEqual(referee_bal_after - referee_bal_before, 500.0, places=2,
                               msg="Referee must receive ₹500 bonus")

    def test_second_purchase_does_not_grant_bonus(self):
        """If txn_count > 1, no bonus should be granted."""
        make_coin_transaction(self._referee, "Purchase", 1000.0, "First recharge")
        make_coin_transaction(self._referee, "Purchase", 500.0, "Second recharge")

        referrer_bal_before = frappe.db.get_value("Restaurant", self._referrer, "coins_balance")
        self.process_referral_bonus(self._referee)
        referrer_bal_after = frappe.db.get_value("Restaurant", self._referrer, "coins_balance")

        self.assertAlmostEqual(referrer_bal_after, referrer_bal_before, places=2,
                               msg="No bonus should be granted for second purchase")

    def test_existing_bonus_not_double_granted(self):
        """Idempotency: if 'Referral Bonus' Free Coins already exist, do not grant again."""
        make_coin_transaction(self._referee, "Purchase", 1000.0, "First recharge")
        self.process_referral_bonus(self._referee)  # grants bonus

        referrer_bal_mid = frappe.db.get_value("Restaurant", self._referrer, "coins_balance")
        referee_bal_mid = frappe.db.get_value("Restaurant", self._referee, "coins_balance")

        # Second call — must be a no-op
        self.process_referral_bonus(self._referee)

        self.assertAlmostEqual(
            frappe.db.get_value("Restaurant", self._referrer, "coins_balance"),
            referrer_bal_mid, places=2,
            msg="Referrer bonus must not be granted twice"
        )
        self.assertAlmostEqual(
            frappe.db.get_value("Restaurant", self._referee, "coins_balance"),
            referee_bal_mid, places=2,
            msg="Referee bonus must not be granted twice"
        )


if __name__ == "__main__":
    unittest.main()
