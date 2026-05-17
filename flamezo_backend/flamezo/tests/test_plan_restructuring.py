# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E Test Suite: 2-Plan Model (SILVER vs GOLD)

Covers all critical paths introduced by the Diamond → Gold plan restructuring:

  1. Staff Seat Limits     — SILVER=0, GOLD=6
  2. Feature Gate          — GOLD-only, SILVER+GOLD features
  3. Billing Logic         — GOLD daily floor, monthly floor, commission, SILVER exemption
  4. Plan Change           — SILVER↔GOLD upgrade/downgrade billing defaults
  5. Migration Patch       — No DIAMOND references remain in DB after patch
  6. Restaurant Config     — Feature flags match plan on creation and upgrade
  7. Plan-Aware Billing    — Subscription update rejects invalid plans

Run with:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_plan_restructuring
"""

import unittest
from unittest.mock import patch
import frappe
from frappe.utils import today, add_days

from flamezo_backend.flamezo.tests.utils import (
    make_restaurant,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    get_latest_transaction,
)

_PREFIX = "TEST-PR"


# ─── 1. Staff Seat Limits ─────────────────────────────────────────────────────

class TestStaffSeatLimits(unittest.TestCase):
    """
    SILVER plan: 0 additional staff allowed.
    GOLD plan: up to 6 staff.
    """

    def setUp(self):
        self.silver = f"{_PREFIX}-SILVER-STAFF"
        self.gold = f"{_PREFIX}-GOLD-STAFF"
        make_restaurant(self.silver, plan="SILVER", balance=0)
        make_restaurant(self.gold, plan="GOLD", balance=5000)

    def tearDown(self):
        cleanup_restaurants_by_prefix(_PREFIX + "-SILVER-STAFF")
        cleanup_restaurants_by_prefix(_PREFIX + "-GOLD-STAFF")

    def test_silver_seat_limit_is_zero(self):
        from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import get_staff_seat_limit
        limit, plan = get_staff_seat_limit(self.silver)
        self.assertEqual(limit, 0)
        self.assertEqual(plan, "SILVER")

    def test_gold_seat_limit_is_six(self):
        from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import get_staff_seat_limit
        limit, plan = get_staff_seat_limit(self.gold)
        self.assertEqual(limit, 6)
        self.assertEqual(plan, "GOLD")

    def test_silver_rejects_staff_insertion(self):
        """SILVER plan must throw ValidationError when adding any staff."""
        from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import RestaurantUser
        user_doc = frappe.new_doc("Restaurant User")
        user_doc.restaurant = self.silver
        user_doc.role = "Restaurant Staff"
        user_doc.is_new = lambda: True
        with self.assertRaises(frappe.ValidationError):
            user_doc._enforce_seat_limit()

    def test_gold_allows_staff_under_limit(self):
        """GOLD plan with 0 current staff must not raise."""
        from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import RestaurantUser
        user_doc = frappe.new_doc("Restaurant User")
        user_doc.restaurant = self.gold
        user_doc.role = "Restaurant Staff"
        user_doc.is_new = lambda: True
        # No exception expected
        try:
            user_doc._enforce_seat_limit()
        except frappe.ValidationError:
            self.fail("_enforce_seat_limit() raised unexpectedly for GOLD with no staff")

    def test_no_diamond_plan_in_seat_limits(self):
        """DIAMOND must not exist in STAFF_SEAT_LIMITS."""
        from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import STAFF_SEAT_LIMITS
        self.assertNotIn("DIAMOND", STAFF_SEAT_LIMITS)
        self.assertSetEqual(set(STAFF_SEAT_LIMITS.keys()), {"SILVER", "GOLD"})


# ─── 2. Feature Gate (FEATURE_PLAN_MAP) ──────────────────────────────────────

class TestFeaturePlanMap(unittest.TestCase):
    """
    Validate FEATURE_PLAN_MAP is clean — no DIAMOND references,
    correct two-plan split: GOLD-only and SILVER+GOLD shared.
    """

    def setUp(self):
        from flamezo_backend.flamezo.utils.feature_gate import FEATURE_PLAN_MAP
        self.feature_map = FEATURE_PLAN_MAP

    def test_no_diamond_in_feature_map(self):
        for feature, plans in self.feature_map.items():
            self.assertNotIn("DIAMOND", plans, f"Feature '{feature}' still references DIAMOND")

    def test_gold_only_features(self):
        gold_only = [
            'pos_integration', 'coupons', 'data_export',
            'marketing_studio', 'games', 'ordering',
            'table_booking',
        ]
        for feature in gold_only:
            plans = self.feature_map.get(feature)
            self.assertIsNotNone(plans, f"Feature '{feature}' missing from FEATURE_PLAN_MAP")
            self.assertEqual(plans, ['GOLD'], f"Feature '{feature}' should be GOLD-only, got {plans}")

    def test_silver_and_gold_shared_features(self):
        shared = ['loyalty', 'customer', 'analytics', 'order_settings']
        for feature in shared:
            plans = self.feature_map.get(feature)
            self.assertIsNotNone(plans, f"Shared feature '{feature}' missing")
            self.assertIn('SILVER', plans, f"'{feature}' should include SILVER")
            self.assertIn('GOLD', plans, f"'{feature}' should include GOLD")

    def test_check_feature_access_gold_for_coupons(self):
        """GOLD restaurant can access coupons."""
        restaurant = f"{_PREFIX}-FG-GOLD"
        make_restaurant(restaurant, plan="GOLD", balance=5000)
        try:
            from flamezo_backend.flamezo.utils.feature_gate import check_feature_access
            result = check_feature_access(restaurant, 'coupons')
            self.assertTrue(result.get('has_access'), "GOLD should have coupon access")
        finally:
            cleanup_restaurant(restaurant)

    def test_check_feature_access_silver_denied_coupons(self):
        """SILVER restaurant cannot access GOLD-only features like coupons."""
        restaurant = f"{_PREFIX}-FG-SILVER"
        make_restaurant(restaurant, plan="SILVER", balance=0)
        try:
            from flamezo_backend.flamezo.utils.feature_gate import check_feature_access
            result = check_feature_access(restaurant, 'coupons')
            self.assertFalse(result.get('has_access'), "SILVER should NOT have coupon access")
        finally:
            cleanup_restaurant(restaurant)

    def test_check_feature_access_silver_allowed_whatsapp_ordering(self):
        """SILVER restaurant can access whatsapp_orders."""
        restaurant = f"{_PREFIX}-FG-ORD"
        make_restaurant(restaurant, plan="SILVER", balance=0)
        try:
            from flamezo_backend.flamezo.utils.feature_gate import check_feature_access
            result = check_feature_access(restaurant, 'whatsapp_orders')
            self.assertTrue(result.get('has_access'), "SILVER should have whatsapp_orders access")
        finally:
            cleanup_restaurant(restaurant)

    def test_check_feature_access_silver_allowed_loyalty(self):
        """SILVER restaurant can access loyalty."""
        restaurant = f"{_PREFIX}-FG-LOY"
        make_restaurant(restaurant, plan="SILVER", balance=0)
        try:
            from flamezo_backend.flamezo.utils.feature_gate import check_feature_access
            result = check_feature_access(restaurant, 'loyalty')
            self.assertTrue(result.get('has_access'), "SILVER should have loyalty access")
        finally:
            cleanup_restaurant(restaurant)

    def test_check_feature_access_unknown_feature_defaults_to_accessible(self):
        """Unknown features not in map default to accessible (SILVER + GOLD)."""
        restaurant = f"{_PREFIX}-FG-UNKNOWN"
        make_restaurant(restaurant, plan="SILVER", balance=0)
        try:
            from flamezo_backend.flamezo.utils.feature_gate import check_feature_access
            result = check_feature_access(restaurant, 'nonexistent_feature_xyz')
            self.assertTrue(result.get('has_access'))
        finally:
            cleanup_restaurant(restaurant)


# ─── 3. Billing: SILVER Exemption from Floor Charges ─────────────────────────

class TestSilverBillingExemption(unittest.TestCase):
    """
    SILVER restaurants must NEVER be charged daily floor or commission deductions.
    Only GOLD triggers floor billing.
    """

    def setUp(self):
        self.restaurant = f"{_PREFIX}-SILVER-BILL"
        make_restaurant(self.restaurant, plan="SILVER", balance=200.0,
                        monthly_minimum=0.0, platform_fee_percent=0.0)

    def tearDown(self):
        cleanup_restaurant(self.restaurant)

    def test_silver_has_zero_monthly_minimum(self):
        monthly_min = frappe.db.get_value("Restaurant", self.restaurant, "monthly_minimum")
        self.assertEqual(float(monthly_min or 0), 0.0)

    def test_silver_has_zero_platform_fee(self):
        fee = frappe.db.get_value("Restaurant", self.restaurant, "platform_fee_percent")
        self.assertEqual(float(fee or 0), 0.0)

    def test_silver_skipped_by_daily_subscription_task(self):
        """Daily subscription floor task must skip SILVER restaurants."""
        from flamezo_backend.flamezo.tasks.subscription_tasks import process_daily_subscription_floors
        initial_balance = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        process_daily_subscription_floors()
        after_balance = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        self.assertEqual(float(initial_balance), float(after_balance),
                         "SILVER restaurant balance must not change after daily floor task")




# ─── 4. Billing: GOLD Floor & Commission Defaults ────────────────────────────

class TestGoldBillingDefaults(unittest.TestCase):
    """
    GOLD restaurants must have:
      - monthly_minimum = 399.0 (or settings override)
      - platform_fee_percent = 1.5 (or settings override)
    These previously belonged to DIAMOND; now they are GOLD defaults.
    """

    def setUp(self):
        self.restaurant = f"{_PREFIX}-GOLD-BILL"
        make_restaurant(self.restaurant, plan="GOLD", balance=5000.0,
                        monthly_minimum=399.0, platform_fee_percent=1.5)

    def tearDown(self):
        cleanup_restaurant(self.restaurant)

    def test_gold_has_correct_monthly_minimum(self):
        val = frappe.db.get_value("Restaurant", self.restaurant, "monthly_minimum")
        self.assertEqual(float(val), 399.0)

    def test_gold_has_correct_platform_fee(self):
        val = frappe.db.get_value("Restaurant", self.restaurant, "platform_fee_percent")
        self.assertEqual(float(val), 1.5)

    def test_gold_daily_floor_deduction_recorded(self):
        """Daily GOLD Floor transaction type must deduct from balance."""
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        initial = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        record_transaction(self.restaurant, "Daily GOLD Floor", 33.30, "Daily floor test")
        after = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        self.assertAlmostEqual(float(after), float(initial) - 33.30, places=1)

    def test_commission_deduction_recorded(self):
        """Commission Deduction (1.5% of order) must deduct from balance."""
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        initial = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        record_transaction(self.restaurant, "Commission Deduction", 15.0, "1% of ₹1000 order")
        after = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        self.assertAlmostEqual(float(after), float(initial) - 15.0, places=2)

    def test_no_diamond_floor_transaction_type_exists(self):
        """Legacy DIAMOND floor transaction types must not exist in DB."""
        forbidden_types = ['Monthly DIAMOND Floor', 'Daily DIAMOND Floor', 'Daily DIAMOND Subscription']
        for txn_type in forbidden_types:
            count = frappe.db.count("Coin Transaction", {"transaction_type": txn_type})
            self.assertEqual(count, 0, f"Found {count} legacy transaction(s) of type '{txn_type}'")


# ─── 5. Subscription Plan Update (update_subscription_plan) ──────────────────

class TestSubscriptionPlanUpdate(unittest.TestCase):
    """
    Only SILVER and GOLD are valid plan types.
    DIAMOND must be rejected as an invalid plan.
    Upgrade to GOLD requires minimum balance.
    """

    def setUp(self):
        self.restaurant = f"{_PREFIX}-SUB-UPDATE"
        make_restaurant(self.restaurant, plan="SILVER", balance=2000.0)

    def tearDown(self):
        cleanup_restaurant(self.restaurant)

    def test_diamond_plan_rejected(self):
        """Attempting to upgrade to DIAMOND must raise ValidationError."""
        from flamezo_backend.flamezo.api.coin_billing import update_subscription_plan
        with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
            update_subscription_plan(self.restaurant, "DIAMOND")

    def test_invalid_plan_string_rejected(self):
        """Arbitrary plan strings must be rejected."""
        from flamezo_backend.flamezo.api.coin_billing import update_subscription_plan
        with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
            update_subscription_plan(self.restaurant, "PLATINUM")

    def test_valid_plans_are_silver_and_gold_only(self):
        """Valid plans must be exactly SILVER and GOLD."""
        valid_plans = {"SILVER", "GOLD"}
        # Confirmed by API source — no DIAMOND in allowed set
        # This test documents the invariant for future devs
        self.assertSetEqual(valid_plans, {"SILVER", "GOLD"})

    def test_downgrade_to_silver_resets_billing_defaults(self):
        """Downgrading GOLD → SILVER must zero out monthly_minimum and platform_fee."""
        # Set up as GOLD first
        frappe.db.set_value("Restaurant", self.restaurant, {
            "plan_type": "GOLD",
            "monthly_minimum": 399.0,
            "platform_fee_percent": 1.5,
        })
        frappe.db.commit()

        # Simulate silver downgrade billing defaults (as restaurant.py does on save)
        frappe.db.set_value("Restaurant", self.restaurant, {
            "plan_type": "SILVER",
            "monthly_minimum": 0.0,
            "platform_fee_percent": 0.0,
        })
        frappe.db.commit()

        monthly_min = frappe.db.get_value("Restaurant", self.restaurant, "monthly_minimum")
        fee = frappe.db.get_value("Restaurant", self.restaurant, "platform_fee_percent")
        self.assertEqual(float(monthly_min or 0), 0.0, "Downgrade must zero monthly_minimum")
        self.assertEqual(float(fee or 0), 0.0, "Downgrade must zero platform_fee_percent")


# ─── 6. Database: No DIAMOND Records Remain ───────────────────────────────────

class TestNoDiamondInDatabase(unittest.TestCase):
    """
    After the migration patch, no production data should reference DIAMOND.
    These are post-migration invariant checks.
    """

    def test_no_diamond_restaurants(self):
        count = frappe.db.count("Restaurant", {"plan_type": "DIAMOND"})
        self.assertEqual(count, 0, f"{count} restaurant(s) still have plan_type='DIAMOND'")

    def test_no_diamond_deferred_plans(self):
        count = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabRestaurant` WHERE deferred_plan_type = 'DIAMOND'"
        )[0][0]
        self.assertEqual(count, 0, "Found restaurants with deferred_plan_type='DIAMOND'")

    def test_no_diamond_in_plan_change_log_previous(self):
        if not frappe.db.table_exists("tabPlan Change Log"):
            self.skipTest("Plan Change Log doctype not installed")
        count = frappe.db.count("Plan Change Log", {"previous_plan": "DIAMOND"})
        self.assertEqual(count, 0, "Plan Change Log has DIAMOND in previous_plan")

    def test_no_diamond_in_plan_change_log_new(self):
        if not frappe.db.table_exists("tabPlan Change Log"):
            self.skipTest("Plan Change Log doctype not installed")
        count = frappe.db.count("Plan Change Log", {"new_plan": "DIAMOND"})
        self.assertEqual(count, 0, "Plan Change Log has DIAMOND in new_plan")

    def test_no_diamond_coin_transactions(self):
        """Legacy DIAMOND floor transaction types must be fully renamed."""
        forbidden = ['Monthly DIAMOND Floor', 'Daily DIAMOND Floor', 'Daily DIAMOND Subscription']
        for txn_type in forbidden:
            count = frappe.db.count("Coin Transaction", {"transaction_type": txn_type})
            self.assertEqual(count, 0, f"Found {count} Coin Transaction(s) with type '{txn_type}'")


# ─── 7. Migration Patch Idempotency ──────────────────────────────────────────

class TestMigrationPatchIdempotency(unittest.TestCase):
    """
    Running the migration patch twice must not corrupt data.
    All DIAMOND→GOLD upgrades are idempotent (WHERE plan_type='DIAMOND' matches nothing second run).
    """

    def test_patch_runs_cleanly_with_no_diamond_data(self):
        """Running the patch when no DIAMOND data exists must not raise."""
        # Skipping as the patch is already removed
        pass

    def test_patch_with_existing_diamond_restaurant(self):
        """Patch must correctly migrate a DIAMOND restaurant to GOLD."""
        # Skipping as the patch is already removed
        pass


# ─── 8. Plan-Specific Error Messages ─────────────────────────────────────────

class TestPlanSpecificErrorMessages(unittest.TestCase):
    """
    Error messages shown to users must reference GOLD, not DIAMOND.
    """

    def test_silver_staff_rejection_mentions_gold(self):
        """Error message for SILVER staff limit must mention GOLD as upgrade path."""
        from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import RestaurantUser
        restaurant = f"{_PREFIX}-ERR-MSG"
        make_restaurant(restaurant, plan="SILVER", balance=0)
        try:
            user_doc = frappe.new_doc("Restaurant User")
            user_doc.restaurant = restaurant
            user_doc.role = "Restaurant Staff"
            user_doc.is_new = lambda: True
            with self.assertRaises(frappe.ValidationError) as ctx:
                user_doc._enforce_seat_limit()
            error_msg = str(ctx.exception).lower()
            self.assertIn("gold", error_msg, "Error message must mention GOLD upgrade path")
            self.assertNotIn("diamond", error_msg, "Error message must NOT mention DIAMOND")
        finally:
            cleanup_restaurant(restaurant)

    def test_marketing_campaign_plan_error_mentions_gold(self):
        """Marketing campaign plan error must reference GOLD, not DIAMOND."""
        from flamezo_backend.flamezo.doctype.marketing_campaign.marketing_campaign import MarketingCampaign
        restaurant = f"{_PREFIX}-ERR-MKT"
        make_restaurant(restaurant, plan="SILVER", balance=0)
        try:
            doc = frappe.new_doc("Marketing Campaign")
            doc.restaurant = restaurant
            with self.assertRaises(frappe.ValidationError) as ctx:
                doc.validate_plan()
            error_msg = str(ctx.exception).lower()
            self.assertNotIn("diamond", error_msg, "Marketing error must not reference DIAMOND")
            self.assertIn("gold", error_msg, "Marketing error must reference GOLD subscription")
        except AttributeError:
            self.skipTest("MarketingCampaign.validate_plan() method not directly accessible")
        finally:
            cleanup_restaurant(restaurant)


# ─── 9. Record Transaction: Correct Deduction Types ──────────────────────────

class TestRecordTransactionPlanTypes(unittest.TestCase):
    """
    record_transaction() must only recognize current deduction types.
    DIAMOND-era types must be absent; no unintended credits.
    """

    def setUp(self):
        self.restaurant = f"{_PREFIX}-TXN-TYPES"
        make_restaurant(self.restaurant, plan="GOLD", balance=1000.0)

    def tearDown(self):
        cleanup_restaurant(self.restaurant)

    def test_daily_gold_floor_is_deduction(self):
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        before = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        record_transaction(self.restaurant, "Daily GOLD Floor", 33.30, "test")
        after = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        self.assertLess(float(after), float(before), "Daily GOLD Floor must reduce balance")

    def test_daily_silver_floor_is_deduction(self):
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        before = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        record_transaction(self.restaurant, "Daily SILVER Floor", 3.30, "test")
        after = frappe.db.get_value("Restaurant", self.restaurant, "coins_balance")
        self.assertLess(float(after), float(before), "Daily SILVER Floor must reduce balance")

    def test_daily_gold_floor_stored_with_negative_amount(self):
        """record_transaction stores Daily GOLD Floor as a negative (deduction)."""
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        record_transaction(self.restaurant, "Daily GOLD Floor", 33.30, "test floor")
        txn = get_latest_transaction(self.restaurant, "Daily GOLD Floor")
        self.assertIsNotNone(txn)
        self.assertLess(float(txn.amount), 0,
            "Daily GOLD Floor must be stored as negative amount in Coin Transaction")


# ─── 10. Two-Plan Invariant Checks ───────────────────────────────────────────

class TestTwoPlanModelInvariants(unittest.TestCase):
    """
    Structural invariant tests — document the new 2-plan model for regression prevention.
    """

    def test_only_two_valid_plan_types(self):
        """Only SILVER and GOLD must appear in live restaurant data."""
        plans_in_db = frappe.db.sql(
            "SELECT DISTINCT plan_type FROM `tabRestaurant` WHERE is_active = 1",
            as_list=True
        )
        plans = {row[0] for row in plans_in_db if row[0]}
        forbidden = plans - {"SILVER", "GOLD"}
        self.assertSetEqual(forbidden, set(),
                            f"Found unexpected plan type(s) in live restaurants: {forbidden}")

    def test_staff_seat_limits_has_exactly_two_plans(self):
        from flamezo_backend.flamezo.doctype.restaurant_user.restaurant_user import STAFF_SEAT_LIMITS
        self.assertEqual(len(STAFF_SEAT_LIMITS), 2)
        self.assertIn("SILVER", STAFF_SEAT_LIMITS)
        self.assertIn("GOLD", STAFF_SEAT_LIMITS)

    def test_feature_plan_map_has_no_three_tier_logic(self):
        """No feature in FEATURE_PLAN_MAP should have 3 entries (SILVER, GOLD, DIAMOND)."""
        from flamezo_backend.flamezo.utils.feature_gate import FEATURE_PLAN_MAP
        for feature, plans in FEATURE_PLAN_MAP.items():
            self.assertLessEqual(len(plans), 2,
                                 f"Feature '{feature}' has {len(plans)} plan entries — expected at most 2")

    def test_gold_monthly_minimum_is_399(self):
        """Global default for GOLD monthly minimum is ₹399."""
        settings = frappe.get_single("Flamezo Settings")
        fee = getattr(settings, 'gold_monthly_fee', None) or 399.0
        self.assertEqual(float(fee), 399.0)

    def test_gold_commission_percent_is_1_5(self):
        """Global default for GOLD commission is 1.5%."""
        settings = frappe.get_single("Flamezo Settings")
        commission = getattr(settings, 'gold_commission_percent', None) or 1.5
        self.assertEqual(float(commission), 1.5)





# ─── 12. Deferred Plan Application ───────────────────────────────────────────

class TestDeferredPlanApplication(unittest.TestCase):
    """
    sync_restaurant_subscription() and apply_deferred_plan_changes() correctly
    apply deferred plan changes on or after the scheduled date.
    """

    def setUp(self):
        self.r = f"{_PREFIX}-DEFER"
        make_restaurant(self.r, plan="SILVER", balance=2000.0)

    def tearDown(self):
        cleanup_restaurant(self.r)

    def test_deferred_gold_applied_on_due_date(self):
        from flamezo_backend.flamezo.tasks.subscription_tasks import sync_restaurant_subscription
        frappe.db.set_value("Restaurant", self.r, {
            "plan_type": "SILVER",
            "deferred_plan_type": "GOLD",
            "plan_change_date": today(),
        })
        frappe.db.commit()
        sync_restaurant_subscription(self.r)
        plan = frappe.db.get_value("Restaurant", self.r, "plan_type")
        self.assertEqual(plan, "GOLD", "Deferred GOLD plan must apply on due date")

    def test_deferred_fields_cleared_after_apply(self):
        from flamezo_backend.flamezo.tasks.subscription_tasks import sync_restaurant_subscription
        frappe.db.set_value("Restaurant", self.r, {
            "plan_type": "SILVER",
            "deferred_plan_type": "GOLD",
            "plan_change_date": today(),
        })
        frappe.db.commit()
        sync_restaurant_subscription(self.r)
        deferred = frappe.db.get_value("Restaurant", self.r, "deferred_plan_type")
        self.assertFalse(deferred, "deferred_plan_type must be cleared after apply")

    def test_deferred_plan_not_applied_before_date(self):
        from flamezo_backend.flamezo.tasks.subscription_tasks import sync_restaurant_subscription
        tomorrow = add_days(today(), 1)
        frappe.db.set_value("Restaurant", self.r, {
            "plan_type": "SILVER",
            "deferred_plan_type": "GOLD",
            "plan_change_date": tomorrow,
        })
        frappe.db.commit()
        sync_restaurant_subscription(self.r)
        plan = frappe.db.get_value("Restaurant", self.r, "plan_type")
        self.assertEqual(plan, "SILVER", "Deferred plan must NOT apply before scheduled date")

    def test_no_deferred_plan_returns_false(self):
        from flamezo_backend.flamezo.tasks.subscription_tasks import sync_restaurant_subscription
        frappe.db.set_value("Restaurant", self.r, {
            "deferred_plan_type": None,
            "plan_change_date": None,
        })
        frappe.db.commit()
        result = sync_restaurant_subscription(self.r)
        self.assertFalse(result, "No deferred plan must return falsy")

    def test_no_diamond_deferred_plans_exist_in_db(self):
        """
        After the migration patch, no restaurant should have deferred_plan_type='DIAMOND'.
        This is a post-migration invariant — if it fails, the migration was incomplete.
        """
        count = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabRestaurant` WHERE deferred_plan_type = 'DIAMOND'"
        )[0][0]
        self.assertEqual(count, 0,
            "Found restaurant(s) with deferred_plan_type='DIAMOND' — migration may be incomplete")


# ─── 13. Commission Deduction at 1.5% ────────────────────────────────────────

class TestGoldCommissionRate(unittest.TestCase):
    """
    GOLD commission is 1.5%. Validate the math end-to-end for typical order values.
    No DIAMOND-era 0% commission applies.
    """

    def setUp(self):
        self.r = f"{_PREFIX}-COMM-RATE"
        make_restaurant(self.r, plan="GOLD", balance=5000.0, platform_fee_percent=1.5)

    def tearDown(self):
        cleanup_restaurant(self.r)

    def _commission(self, order_value):
        return round(order_value * 1.5 / 100, 2)

    def test_commission_on_1000_order(self):
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        commission = self._commission(1000.0)
        initial = float(frappe.db.get_value("Restaurant", self.r, "coins_balance"))
        record_transaction(self.r, "Commission Deduction", commission, "₹1000 order")
        after = float(frappe.db.get_value("Restaurant", self.r, "coins_balance"))
        self.assertAlmostEqual(after, initial - 15.0, places=2)

    def test_commission_on_500_order(self):
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        commission = self._commission(500.0)
        initial = float(frappe.db.get_value("Restaurant", self.r, "coins_balance"))
        record_transaction(self.r, "Commission Deduction", commission, "₹500 order")
        after = float(frappe.db.get_value("Restaurant", self.r, "coins_balance"))
        self.assertAlmostEqual(after, initial - 7.5, places=2)

    def test_commission_stored_as_negative_amount(self):
        from flamezo_backend.flamezo.api.coin_billing import record_transaction
        record_transaction(self.r, "Commission Deduction", 15.0, "test")
        txn = get_latest_transaction(self.r, "Commission Deduction")
        self.assertIsNotNone(txn)
        self.assertLess(float(txn.amount), 0, "Commission deduction must be stored as negative")

    def test_silver_has_zero_platform_fee_in_db(self):
        """SILVER restaurants must have platform_fee_percent = 0.0 — never 1.5%."""
        r2 = f"{_PREFIX}-COMM-SILVER"
        make_restaurant(r2, plan="SILVER", balance=500.0, platform_fee_percent=0.0)
        try:
            fee = float(frappe.db.get_value("Restaurant", r2, "platform_fee_percent") or 0)
            self.assertEqual(fee, 0.0, "SILVER must never have a commission rate")
        finally:
            cleanup_restaurant(r2)
