# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import today, add_days, getdate
from dinematters.dinematters.tests.utils import (
    make_restaurant,
    make_coin_transaction,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    clear_transactions,
    get_latest_transaction,
)

_PREFIX = "TEST-PRICE-V2"

class TestDiamondMonthlyFloor(unittest.TestCase):
    """
    Production-grade tests for the new Diamond Monthly Floor logic (₹399 guarantee).
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
        from dinematters.dinematters.tasks.subscription_tasks import process_daily_subscription_floors
        self.run_billing = process_daily_subscription_floors

    def _diamond_name(self):
        return f"{_PREFIX}-DIAMOND-{self._sfx}"

    def _gold_name(self):
        return f"{_PREFIX}-GOLD-{self._sfx}"

    def tearDown(self):
        cleanup_restaurant(self._diamond_name())
        cleanup_restaurant(self._gold_name())

    def test_diamond_monthly_floor_trigger_at_30_days(self):
        """
        DIAMOND: After 30 days, if commission is ₹100 and floor is ₹399,
        system must deduct ₹299 shortfall.
        """
        d = self._diamond_name()
        # Create restaurant with 30-day old activation
        activation_date = add_days(today(), -30)
        make_restaurant(d, plan="DIAMOND", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        
        clear_transactions(d)
        # Add ₹100 in commissions during the period
        make_coin_transaction(d, "Commission Deduction", 100.0, "partial commissions")
        
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly DIAMOND Floor")
        self.assertIsNotNone(txn, "Monthly floor recovery must be triggered")
        self.assertAlmostEqual(abs(txn.amount), 299.0, places=2)
        
        # Verify cycle reset
        new_last_date = frappe.db.get_value("Restaurant", d, "last_floor_recovery_date")
        self.assertEqual(getdate(new_last_date), getdate(today()), "Last recovery date must be updated to today")

    def test_diamond_monthly_floor_skips_before_30_days(self):
        """
        DIAMOND: On day 29, no charge should be applied.
        """
        d = self._diamond_name()
        activation_date = add_days(today(), -29)
        make_restaurant(d, plan="DIAMOND", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        
        clear_transactions(d)
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly DIAMOND Floor")
        self.assertIsNone(txn, "No monthly floor should be charged before 30 days")

    def test_diamond_zero_charge_if_commission_exceeds_floor(self):
        """
        DIAMOND: If commission is ₹500 and floor is ₹399, charge must be ₹0.
        """
        d = self._diamond_name()
        activation_date = add_days(today(), -30)
        make_restaurant(d, plan="DIAMOND", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=1, floor_recovery_activated_on=activation_date,
                        last_floor_recovery_date=activation_date)
        
        clear_transactions(d)
        # Add ₹500 in commissions
        make_coin_transaction(d, "Commission Deduction", 500.0, "high volume")
        
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly DIAMOND Floor")
        self.assertIsNone(txn, "No floor charge if commissions already cover the minimum guarantee")
        
        # Date should still update because the 30-day window is over
        new_last_date = frappe.db.get_value("Restaurant", d, "last_floor_recovery_date")
        self.assertEqual(getdate(new_last_date), getdate(today()), "Cycle must still reset after 30 days")

    def test_gold_still_bills_daily(self):
        """
        GOLD: Must continue to bill daily regardless of the Diamond monthly changes.
        """
        g = self._gold_name()
        # Create restaurant activated today
        make_restaurant(g, plan="GOLD", balance=1000.0, monthly_minimum=999.0, enable_floor_recovery=1)
        clear_transactions(g)
        
        self.run_billing()
        
        txn = get_latest_transaction(g, "Daily GOLD Subscription")
        self.assertIsNotNone(txn, "GOLD must still receive daily billing")
        self.assertAlmostEqual(abs(txn.amount), 33.30, places=2)

    def test_diamond_skips_if_toggle_off(self):
        """
        DIAMOND: Even at day 30, no charge if enable_floor_recovery=0.
        """
        d = self._diamond_name()
        activation_date = add_days(today(), -35)
        make_restaurant(d, plan="DIAMOND", balance=1000.0, monthly_minimum=399.0, 
                        enable_floor_recovery=0, floor_recovery_activated_on=activation_date)
        
        clear_transactions(d)
        self.run_billing()
        
        txn = get_latest_transaction(d, "Monthly DIAMOND Floor")
        self.assertIsNone(txn, "Disabled floor recovery must not bill")

if __name__ == "__main__":
    unittest.main()
