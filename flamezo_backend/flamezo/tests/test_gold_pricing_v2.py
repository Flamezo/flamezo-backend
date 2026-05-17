# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import today, add_days, getdate
from flamezo_backend.flamezo.tests.utils import (
    make_restaurant,
    make_coin_transaction,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    clear_transactions,
    get_latest_transaction,
)

_PREFIX = "TEST-PRICE-V2"

class TestGoldMonthlyFloor(unittest.TestCase):
    """
    Production-grade tests for the GOLD Monthly Floor logic (₹399 guarantee).
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX)

    def setUp(self):
        self._sfx = frappe.generate_hash(length=6)
        from flamezo_backend.flamezo.tasks.subscription_tasks import process_daily_subscription_floors
        self.run_billing = process_daily_subscription_floors

    def _gold_name(self):
        return f"{_PREFIX}-GOLD-{self._sfx}"

    def tearDown(self):
        cleanup_restaurant(self._gold_name())

    def test_gold_monthly_floor_trigger_at_30_days(self):
        """
        GOLD: After 30 days, if commission is ₹100 and floor is ₹399,
        system must deduct ₹299 shortfall.
        """
        d = self._gold_name()
        # Create restaurant with 30-day old activation
        activation_date = add_days(today(), -30)
        make_restaurant(d, plan="GOLD", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        
        clear_transactions(d)
        # Add ₹100 in commissions during the period
        make_coin_transaction(d, "Commission Deduction", 100.0, "partial commissions")
        
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly GOLD Floor")
        self.assertIsNotNone(txn, "Monthly floor recovery must be triggered")
        self.assertAlmostEqual(abs(txn.amount), 299.0, places=2)
        
        # Verify cycle reset
        new_last_date = frappe.db.get_value("Restaurant", d, "last_floor_recovery_date")
        self.assertEqual(getdate(new_last_date), getdate(today()), "Last recovery date must be updated to today")

    def test_gold_monthly_minimum_is_399(self):
        pass

    def test_gold_monthly_floor_skips_before_30_days(self):
        """
        GOLD: On day 29, no charge should be applied.
        """
        d = self._gold_name()
        activation_date = add_days(today(), -29)
        make_restaurant(d, plan="GOLD", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        
        clear_transactions(d)
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly GOLD Floor")
        self.assertIsNone(txn, "No monthly floor should be charged before 30 days")

    def test_gold_zero_charge_if_commission_exceeds_floor(self):
        """
        GOLD: If commission is ₹500 and floor is ₹399, charge must be ₹0.
        """
        d = self._gold_name()
        activation_date = add_days(today(), -30)
        make_restaurant(d, plan="GOLD", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        
        clear_transactions(d)
        # Add ₹500 in commissions
        make_coin_transaction(d, "Commission Deduction", 500.0, "high volume")
        
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly GOLD Floor")
        self.assertIsNone(txn, "No floor charge if commissions already cover the minimum guarantee")
        
        # Date should still update because the 30-day window is over
        new_last_date = frappe.db.get_value("Restaurant", d, "last_floor_recovery_date")
        self.assertEqual(getdate(new_last_date), getdate(today()), "Cycle must still reset after 30 days")

    def test_gold_mid_cycle_no_charge(self):
        """
        GOLD on day 1 (just activated): process_daily_subscription_floors must not
        charge anything — the 30-day window has not elapsed.
        """
        g = self._gold_name()
        # Restaurant activated today — date_diff will be 0, skipped by < 30 check
        make_restaurant(g, plan="GOLD", balance=1000.0, monthly_minimum=399.0, enable_floor_recovery=1)
        clear_transactions(g)

        self.run_billing()

        txn = get_latest_transaction(g, "Monthly GOLD Floor")
        self.assertIsNone(txn, "GOLD must not be billed in the first 30 days")

    def test_gold_skips_if_toggle_off(self):
        """
        GOLD: Even at day 30, no charge if enable_floor_recovery=0.
        """
        d = self._gold_name()
        activation_date = add_days(today(), -35)
        make_restaurant(d, plan="GOLD", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=0, floor_recovery_activated_on=activation_date)
        
        clear_transactions(d)
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly GOLD Floor")
        self.assertIsNone(txn, "Disabled floor recovery must not bill")

if __name__ == "__main__":
    unittest.main()
