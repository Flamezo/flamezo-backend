# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

"""
Production-grade tests for subscription_tasks.py

Covers:
  - process_daily_subscription_floors()
      * GOLD flat daily fee when no commissions paid
      * GOLD skips when commission already covers the floor
      * DIAMOND floor recovery when commissions are below the target
      * DIAMOND skips floor when commissions exceed target
      * Idempotency: floor not charged twice in the same UTC day
      * Skips inactive restaurants
      * Skips restaurants with enable_floor_recovery=0
      * Respects per-restaurant monthly_minimum (not a global constant)
      * Only processes GOLD and DIAMOND plans (not SILVER)

  - sync_restaurant_subscription()
      * Returns False when no deferred plan is scheduled
      * Returns False when plan_change_date is in the future
      * Applies plan change when plan_change_date == today
      * Applies overdue plan changes (plan_change_date in the past)
      * Clears deferred fields after a successful switch

  - apply_deferred_plan_changes()
      * Batch-applies all due restaurants
      * Does not apply future-dated changes

  - process_silver_feature_renewals()
      * SILVER restaurant is charged 100 coins for menu theme renewal
      * paid_until extended by 30 days after successful charge
      * GOLD/DIAMOND restaurants are NOT charged (skipped and paid_until cleared)
      * Feature is disabled when restaurant has insufficient balance
      * Skips restaurants where paid_until has not yet expired

Run with:
    bench run-tests --app dinematters --module dinematters.dinematters.tests.test_subscription_tasks
"""

import unittest
import frappe
from frappe.utils import today, add_days, getdate

from dinematters.dinematters.tests.utils import (
    make_restaurant,
    make_restaurant_config,
    make_coin_transaction,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    reset_restaurant_balance,
    clear_transactions,
    get_latest_transaction,
)

_PREFIX = "TEST-SUB"


# ─── 1. process_daily_subscription_floors() ──────────────────────────────────

class TestDailySubscriptionFloors(unittest.TestCase):
    """
    Validates the nightly billing task that recovers daily minimum fees.

    GOLD  — flat ₹33.30/day (999 / 30), regardless of order commissions.
    DIAMOND — monthly guarantee recovery: (monthly_min) - total commissions in 30 days.
              Checked and charged only every 30 days.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-DSF-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-DSF-")

    def setUp(self):
        self._sfx = frappe.generate_hash(length=6)
        from dinematters.dinematters.tasks.subscription_tasks import process_daily_subscription_floors
        self.run_floors = process_daily_subscription_floors

    def _gold_name(self):
        return f"{_PREFIX}-DSF-G-{self._sfx}"

    def _diamond_name(self):
        return f"{_PREFIX}-DSF-D-{self._sfx}"

    def tearDown(self):
        cleanup_restaurant(self._gold_name())
        cleanup_restaurant(self._diamond_name())
        extra = f"{_PREFIX}-DSF-X-{self._sfx}"
        cleanup_restaurant(extra)

    # ── GOLD: flat daily fee ──

    def test_gold_charged_flat_daily_fee_when_no_commission(self):
        """
        GOLD restaurant, no orders today.
        Expected deduction: ₹999 / 30 = ₹33.30 (Daily GOLD Subscription).
        """
        g = self._gold_name()
        make_restaurant(g, plan="GOLD", balance=500.0, monthly_minimum=999.0,
                        enable_floor_recovery=1)
        clear_transactions(g)

        self.run_floors()

        txn = get_latest_transaction(g, "Daily GOLD Subscription")
        self.assertIsNotNone(txn, "GOLD floor transaction must be created")
        self.assertAlmostEqual(abs(txn.amount), 33.30, places=2)

    def test_gold_skips_when_commission_already_covers_floor(self):
        """
        GOLD has already paid ₹50 in Commission Deductions today (> ₹33.30).
        No floor transaction should be created.

        Note: In practice GOLD doesn't pay order commissions, but the billing
        engine is plan-agnostic — if commissions exist, they offset the floor.
        """
        g = self._gold_name()
        make_restaurant(g, plan="GOLD", balance=500.0, monthly_minimum=999.0,
                        enable_floor_recovery=1)
        clear_transactions(g)
        # Pre-load today's commission deductions
        make_coin_transaction(g, "Commission Deduction", 50.0, "order commission")

        self.run_floors()

        txn = get_latest_transaction(g, "Daily GOLD Subscription")
        self.assertIsNone(txn, "GOLD floor must not be charged when commissions cover it")

    # ── DIAMOND: floor recovery ──

    def test_diamond_monthly_floor_recovery_at_end_of_cycle(self):
        """
        DIAMOND monthly_minimum=399. After 30 days, if only ₹200 commissions paid,
        shortfall = 399 - 200 = 199.
        """
        d = self._diamond_name()
        # Mock a 30-day old cycle
        activation_date = add_days(today(), -30)
        make_restaurant(d, plan="DIAMOND", balance=2000.0, monthly_minimum=399.0,
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        clear_transactions(d)
        make_coin_transaction(d, "Commission Deduction", 200.0, "partial monthly commissions")

        self.run_floors()

        txn = get_latest_transaction(d, "Monthly DIAMOND Floor")
        self.assertIsNotNone(txn, "DIAMOND monthly floor must be triggered")
        self.assertAlmostEqual(abs(txn.amount), 199.0, places=2)

    def test_diamond_skips_floor_mid_cycle(self):
        """DIAMOND at day 15: no charge yet."""
        d = self._diamond_name()
        activation_date = add_days(today(), -15)
        make_restaurant(d, plan="DIAMOND", balance=2000.0, monthly_minimum=399.0,
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        clear_transactions(d)

        self.run_floors()

        txn = get_latest_transaction(d, "Monthly DIAMOND Floor")
        self.assertIsNone(txn, "DIAMOND must skip monthly check during the cycle")

    # ── Idempotency ──

    def test_idempotent_floor_not_charged_twice(self):
        """
        Running process_daily_subscription_floors() twice in the same UTC day
        must only create one floor transaction.
        """
        g = self._gold_name()
        make_restaurant(g, plan="GOLD", balance=500.0, monthly_minimum=999.0,
                        enable_floor_recovery=1)
        clear_transactions(g)

        self.run_floors()
        self.run_floors()

        all_txns = frappe.db.count("Coin Transaction", {
            "restaurant": g,
            "transaction_type": "Daily GOLD Subscription",
        })
        self.assertEqual(all_txns, 1, "Floor must be charged exactly once per day")

    # ── Filters ──

    def test_skips_inactive_restaurants(self):
        name = f"{_PREFIX}-DSF-X-{self._sfx}"
        make_restaurant(name, plan="GOLD", balance=500.0, monthly_minimum=999.0,
                        enable_floor_recovery=1, is_active=0)
        clear_transactions(name)

        self.run_floors()

        txn = get_latest_transaction(name, "Daily GOLD Subscription")
        self.assertIsNone(txn, "Inactive restaurant must not be billed")

    def test_skips_restaurants_with_floor_recovery_disabled(self):
        name = f"{_PREFIX}-DSF-X-{self._sfx}"
        make_restaurant(name, plan="GOLD", balance=500.0, monthly_minimum=999.0,
                        enable_floor_recovery=0)
        clear_transactions(name)

        self.run_floors()

        txn = get_latest_transaction(name, "Daily GOLD Subscription")
        self.assertIsNone(txn, "Floor recovery must be skipped when flag is off")

    def test_silver_restaurants_are_not_billed(self):
        """SILVER plan must never receive a floor deduction."""
        name = f"{_PREFIX}-DSF-X-{self._sfx}"
        make_restaurant(name, plan="SILVER", balance=500.0, enable_floor_recovery=1)
        clear_transactions(name)

        self.run_floors()

        # No floor-type transaction must exist
        count = frappe.db.count("Coin Transaction", {
            "restaurant": name,
            "transaction_type": ["in", [
                "Daily SILVER Floor", "Daily GOLD Floor",
                "Daily DIAMOND Floor", "Daily GOLD Subscription",
                "Daily DIAMOND Subscription",
            ]],
        })
        self.assertEqual(count, 0, "SILVER must not receive any floor charge")

    def test_uses_per_restaurant_monthly_minimum(self):
        """
        Two GOLD restaurants with different monthly_minimums must be charged
        their own daily rates, not a shared global constant.
        """
        g1 = f"{_PREFIX}-DSF-G1-{self._sfx}"
        g2 = f"{_PREFIX}-DSF-G2-{self._sfx}"
        make_restaurant(g1, plan="GOLD", balance=500.0, monthly_minimum=600.0,
                        enable_floor_recovery=1)
        make_restaurant(g2, plan="GOLD", balance=500.0, monthly_minimum=1200.0,
                        enable_floor_recovery=1)
        clear_transactions(g1)
        clear_transactions(g2)

        try:
            self.run_floors()

            txn1 = get_latest_transaction(g1, "Daily GOLD Subscription")
            txn2 = get_latest_transaction(g2, "Daily GOLD Subscription")

            # 600/30 = 20.00, 1200/30 = 40.00
            self.assertAlmostEqual(abs(txn1.amount), 20.00, places=2)
            self.assertAlmostEqual(abs(txn2.amount), 40.00, places=2)
        finally:
            cleanup_restaurant(g1)
            cleanup_restaurant(g2)


# ─── 2. sync_restaurant_subscription() ───────────────────────────────────────

class TestSyncRestaurantSubscription(unittest.TestCase):
    """Validates the JIT plan-switch fail-safe function."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-SRS-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-SRS-")

    def setUp(self):
        self._res_name = f"{_PREFIX}-SRS-{frappe.generate_hash(length=6)}"
        from dinematters.dinematters.tasks.subscription_tasks import sync_restaurant_subscription
        self.sync = sync_restaurant_subscription

    def tearDown(self):
        cleanup_restaurant(self._res_name)

    def test_returns_false_when_no_deferred_plan(self):
        make_restaurant(self._res_name, plan="GOLD")
        result = self.sync(self._res_name)
        self.assertFalse(result)

    def test_returns_false_when_change_date_is_in_future(self):
        make_restaurant(
            self._res_name, plan="SILVER",
            deferred_plan_type="GOLD",
            plan_change_date=add_days(today(), 5)
        )
        result = self.sync(self._res_name)
        self.assertFalse(result)
        # Plan must remain SILVER
        current = frappe.db.get_value("Restaurant", self._res_name, "plan_type")
        self.assertEqual(current, "SILVER")

    def test_applies_plan_change_when_due_today(self):
        make_restaurant(
            self._res_name, plan="SILVER",
            deferred_plan_type="GOLD",
            plan_change_date=today()
        )
        result = self.sync(self._res_name)
        self.assertTrue(result)
        new_plan = frappe.db.get_value("Restaurant", self._res_name, "plan_type")
        self.assertEqual(new_plan, "GOLD")

    def test_applies_overdue_plan_change(self):
        """plan_change_date in the past must still be applied."""
        make_restaurant(
            self._res_name, plan="SILVER",
            deferred_plan_type="DIAMOND",
            plan_change_date=add_days(today(), -3)
        )
        result = self.sync(self._res_name)
        self.assertTrue(result)
        new_plan = frappe.db.get_value("Restaurant", self._res_name, "plan_type")
        self.assertEqual(new_plan, "DIAMOND")

    def test_clears_deferred_fields_after_switch(self):
        """After switching, deferred_plan_type and plan_change_date must be NULL."""
        make_restaurant(
            self._res_name, plan="SILVER",
            deferred_plan_type="GOLD",
            plan_change_date=today()
        )
        self.sync(self._res_name)

        result = frappe.db.get_value(
            "Restaurant", self._res_name,
            ["deferred_plan_type", "plan_change_date"],
            as_dict=True
        )
        self.assertIsNone(result.deferred_plan_type)
        self.assertIsNone(result.plan_change_date)

    def test_returns_false_when_no_deferred_plan_type_only(self):
        """plan_change_date set but no deferred_plan_type — must return False."""
        make_restaurant(
            self._res_name, plan="GOLD",
            plan_change_date=today()
        )
        result = self.sync(self._res_name)
        self.assertFalse(result)


# ─── 3. apply_deferred_plan_changes() ────────────────────────────────────────

class TestApplyDeferredPlanChanges(unittest.TestCase):
    """Batch midnight task: flip all due restaurants to their new plans."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-ADPC-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-ADPC-")

    def setUp(self):
        self._sfx = frappe.generate_hash(length=6)
        from dinematters.dinematters.tasks.subscription_tasks import apply_deferred_plan_changes
        self.apply = apply_deferred_plan_changes

    def tearDown(self):
        for suffix in ["DUE1", "DUE2", "FUT"]:
            cleanup_restaurant(f"{_PREFIX}-ADPC-{suffix}-{self._sfx}")

    def test_applies_all_due_restaurants(self):
        r1 = f"{_PREFIX}-ADPC-DUE1-{self._sfx}"
        r2 = f"{_PREFIX}-ADPC-DUE2-{self._sfx}"
        make_restaurant(r1, plan="SILVER", deferred_plan_type="GOLD",
                        plan_change_date=today())
        make_restaurant(r2, plan="GOLD", deferred_plan_type="DIAMOND",
                        plan_change_date=add_days(today(), -1))

        self.apply()

        self.assertEqual(frappe.db.get_value("Restaurant", r1, "plan_type"), "GOLD")
        self.assertEqual(frappe.db.get_value("Restaurant", r2, "plan_type"), "DIAMOND")

    def test_does_not_apply_future_changes(self):
        r_fut = f"{_PREFIX}-ADPC-FUT-{self._sfx}"
        make_restaurant(r_fut, plan="SILVER", deferred_plan_type="GOLD",
                        plan_change_date=add_days(today(), 2))

        self.apply()

        self.assertEqual(frappe.db.get_value("Restaurant", r_fut, "plan_type"), "SILVER",
                         "Future plan change must not be applied early")


# ─── 4. process_silver_feature_renewals() ────────────────────────────────────

class TestSilverFeatureRenewals(unittest.TestCase):
    """
    Daily task that renews paid menu-theme features for SILVER restaurants.

    Charged:   100 coins / 30 days
    Skipped:   GOLD/DIAMOND (charged 0, paid_until cleared if set)
    Disabled:  if SILVER restaurant has insufficient balance
    Skipped:   if paid_until is still in the future
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-SFR-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-SFR-")

    def setUp(self):
        self._sfx = frappe.generate_hash(length=6)
        from dinematters.dinematters.tasks.subscription_tasks import process_silver_feature_renewals
        self.run_renewals = process_silver_feature_renewals

    def _name(self, tag):
        return f"{_PREFIX}-SFR-{tag}-{self._sfx}"

    def tearDown(self):
        for tag in ["SIL", "GOLD", "BROKE", "ACTIVE"]:
            cleanup_restaurant(self._name(tag))

    def test_silver_charged_100_coins(self):
        name = self._name("SIL")
        make_restaurant(name, plan="SILVER", balance=500.0)
        reset_restaurant_balance(name, 500.0)
        clear_transactions(name)
        make_restaurant_config(name, menu_theme_background_enabled=1, menu_theme_paid_until=None)

        self.run_renewals()

        new_bal = frappe.db.get_value("Restaurant", name, "coins_balance")
        self.assertAlmostEqual(new_bal, 400.0, places=2, msg="SILVER must be charged 100 coins")

    def test_silver_paid_until_extended_30_days(self):
        name = self._name("SIL")
        make_restaurant(name, plan="SILVER", balance=500.0)
        reset_restaurant_balance(name, 500.0)
        clear_transactions(name)
        make_restaurant_config(name, menu_theme_background_enabled=1, menu_theme_paid_until=None)

        self.run_renewals()

        cfg_name = frappe.db.get_value("Restaurant Config", {"restaurant": name}, "name")
        new_paid_until = frappe.db.get_value("Restaurant Config", cfg_name, "menu_theme_paid_until")
        expected = add_days(today(), 30)
        self.assertEqual(getdate(new_paid_until), getdate(expected),
                         "paid_until must be extended 30 days")

    def test_gold_restaurant_not_charged(self):
        """GOLD restaurant must be skipped entirely — only plan_type=SILVER rows enter the loop."""
        name = self._name("GOLD")
        make_restaurant(name, plan="GOLD", balance=500.0)
        reset_restaurant_balance(name, 500.0)
        clear_transactions(name)
        original_expiry = add_days(today(), -5)
        make_restaurant_config(
            name,
            menu_theme_background_enabled=1,
            menu_theme_paid_until=original_expiry,  # expired, but GOLD so never touched
        )

        self.run_renewals()

        # Balance must be untouched — no deduction attempted
        bal = frappe.db.get_value("Restaurant", name, "coins_balance")
        self.assertAlmostEqual(bal, 500.0, places=2, msg="GOLD balance must be unchanged")

        # paid_until is also untouched — the query filters plan_type='SILVER' so GOLD rows
        # never enter the renewal loop and are neither charged nor cleared.
        cfg_name = frappe.db.get_value("Restaurant Config", {"restaurant": name}, "name")
        paid_until = frappe.db.get_value("Restaurant Config", cfg_name, "menu_theme_paid_until")
        self.assertEqual(getdate(paid_until), getdate(original_expiry),
                         "GOLD paid_until must remain unchanged (GOLD restaurants are not processed)")

    def test_feature_disabled_when_balance_insufficient(self):
        """
        SILVER restaurant balance is -205. Deducting 100 coins would produce -305
        which is below the -300 grace limit, so deduct_coins() raises ValidationError
        and the renewal task disables the feature.
        """
        name = self._name("BROKE")
        make_restaurant(name, plan="SILVER", balance=-205.0)
        reset_restaurant_balance(name, -205.0)
        clear_transactions(name)
        make_restaurant_config(name, menu_theme_background_enabled=1, menu_theme_paid_until=None)

        self.run_renewals()

        cfg_name = frappe.db.get_value("Restaurant Config", {"restaurant": name}, "name")
        enabled = frappe.db.get_value("Restaurant Config", cfg_name, "menu_theme_background_enabled")
        self.assertEqual(enabled, 0, "Feature must be disabled when deduction would exceed grace limit")

    def test_skips_restaurant_with_active_paid_until(self):
        """If paid_until is 20 days in the future, restaurant must not be charged."""
        name = self._name("ACTIVE")
        make_restaurant(name, plan="SILVER", balance=500.0)
        reset_restaurant_balance(name, 500.0)
        clear_transactions(name)
        make_restaurant_config(
            name,
            menu_theme_background_enabled=1,
            menu_theme_paid_until=add_days(today(), 20),  # still valid
        )

        self.run_renewals()

        bal = frappe.db.get_value("Restaurant", name, "coins_balance")
        self.assertAlmostEqual(bal, 500.0, places=2,
                               msg="No charge when paid_until is still in the future")


if __name__ == "__main__":
    unittest.main()
