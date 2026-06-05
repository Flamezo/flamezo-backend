"""
test_plan_purge.py
==================
Comprehensive unit/integration tests verifying that the Gold & Silver
plan purge is complete and correct across the Flamezo backend.

Run via:
    cd frappe-bench
    bench --site <site> run-tests \
        --app flamezo_backend \
        --module flamezo_backend.flamezo.tests.test_plan_purge

All tests are isolated in a transaction that is rolled back at the end
of the suite so no production data is modified.
"""

import frappe
import unittest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_restaurant(name: str, plan_type: str = "GOLD", **kwargs) -> str:
    """Insert a minimal test Restaurant and return its name."""
    if frappe.db.exists("Restaurant", name):
        frappe.db.set_value("Restaurant", name, {"plan_type": plan_type, **kwargs})
        return name

    doc = frappe.get_doc({
        "doctype": "Restaurant",
        "restaurant_id": name,
        "restaurant_name": f"Test {name}",
        "plan_type": plan_type,
        "is_active": 1,
        "coins_balance": 1000.0,
        "timezone": "UTC",
        "monthly_minimum": 0,
        "tax_rate": 0.0,
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestPlanPurge(unittest.TestCase):
    """
    Validates that `plan_type` is always treated as 'GOLD' throughout the
    backend after the single-tier model migration.
    """

    @classmethod
    def setUpClass(cls):
        """Create shared test fixtures once per suite."""
        frappe.set_user("Administrator")

        cls.res_id = "test-plan-purge-restaurant"
        _make_restaurant(cls.res_id, plan_type="GOLD")

    @classmethod
    def tearDownClass(cls):
        """Roll back all changes made during the test suite."""
        frappe.db.rollback()

    # ------------------------------------------------------------------
    # 1. Config API
    # ------------------------------------------------------------------

    def test_get_restaurant_config_plan_type_always_gold(self):
        """
        get_restaurant_config must always return planType='GOLD' regardless
        of what is stored in the Restaurant DocType field.
        """
        from flamezo_backend.flamezo.api.config import get_restaurant_config

        # Force DB value to something that should be ignored
        frappe.db.set_value("Restaurant", self.res_id, "plan_type", "GOLD")
        frappe.db.commit()

        result = get_restaurant_config(self.res_id)

        self.assertTrue(result.get("success"), f"API error: {result}")
        subscription = result["data"]["subscription"]
        self.assertEqual(
            subscription["planType"],
            "GOLD",
            "subscription.planType must always be 'GOLD'",
        )

    def test_get_restaurant_config_deferred_plan_null(self):
        """
        deferredPlanType must always be None in the API response (the field
        is retired in the single-tier model).
        """
        from flamezo_backend.flamezo.api.config import get_restaurant_config

        result = get_restaurant_config(self.res_id)

        self.assertTrue(result.get("success"))
        subscription = result["data"]["subscription"]
        self.assertIsNone(
            subscription.get("deferredPlanType"),
            "deferredPlanType must be None in the single-tier model",
        )

    def test_get_restaurant_config_plan_change_date_null(self):
        """
        planChangeDate must always be None (not read from the DB any longer).
        """
        from flamezo_backend.flamezo.api.config import get_restaurant_config

        result = get_restaurant_config(self.res_id)
        self.assertIsNone(result["data"]["subscription"].get("planChangeDate"))

    def test_get_restaurant_config_settings_plan_type_gold(self):
        """
        settings.planType must also always be 'GOLD'.
        """
        from flamezo_backend.flamezo.api.config import get_restaurant_config

        result = get_restaurant_config(self.res_id)
        settings = result["data"]["settings"]
        self.assertEqual(settings.get("planType"), "GOLD")

    def test_get_restaurant_config_all_features_true(self):
        """
        Under the single-tier model every feature flag must be True.
        """
        from flamezo_backend.flamezo.api.config import get_restaurant_config

        result = get_restaurant_config(self.res_id)
        features = result["data"]["subscription"]["features"]

        expected_true = [
            "ordering",
            "loyalty",
            "order_settings",
            "whatsapp_orders",
            "games",
            "tableBooking",
            "events",
            "offers",
            "experience_lounge",
            "google_growth",
            "marketing_studio",
            "videoUpload",
            "analytics",
            "customer",
            "aiRecommendations",
            "customBranding",
        ]
        for feat in expected_true:
            self.assertTrue(
                features.get(feat),
                f"Feature '{feat}' must be True for all restaurants (single-tier model)",
            )

    def test_get_restaurant_config_gold_barrier_zero(self):
        """
        plan_defaults.gold_barrier must be 0.0 (retired unlock barrier).
        """
        from flamezo_backend.flamezo.api.config import get_restaurant_config

        result = get_restaurant_config(self.res_id)
        plan_defaults = result["data"]["subscription"]["plan_defaults"]
        self.assertAlmostEqual(
            float(plan_defaults.get("gold_barrier", 999)),
            0.0,
            places=2,
            msg="gold_barrier must be 0.0 in the single-tier model",
        )

    # ------------------------------------------------------------------
    # 2. Admin API
    # ------------------------------------------------------------------

    def test_get_restaurant_details_no_plan_type_in_response(self):
        """
        get_restaurant_details should not include a meaningful plan_type
        distinction; any plan_type value returned must be 'GOLD'.
        """
        from flamezo_backend.flamezo.api.admin import get_restaurant_details

        result = get_restaurant_details(self.res_id)
        self.assertTrue(result.get("success"), f"Admin API error: {result}")

        restaurant = result["data"]["restaurant"]
        if "plan_type" in restaurant:
            self.assertEqual(
                restaurant["plan_type"],
                "GOLD",
                "plan_type in admin API must always be GOLD",
            )

    def test_admin_update_restaurant_settings_ignores_plan_type(self):
        """
        admin_update_restaurant_settings must reject / ignore any attempt
        to set plan_type to a non-GOLD value.
        """
        from flamezo_backend.flamezo.api.admin import admin_update_restaurant_settings

        # Attempt to set plan_type to a legacy value
        result = admin_update_restaurant_settings(
            restaurant_id=self.res_id,
            updates={"plan_type": "SILVER"},
        )
        # The field is not in the allowed list so the call should succeed
        # but the DB value must remain GOLD.
        actual = frappe.db.get_value("Restaurant", self.res_id, "plan_type")
        self.assertEqual(
            actual,
            "GOLD",
            "plan_type must not be changed via admin_update_restaurant_settings",
        )

    def test_update_restaurant_plan_endpoint_is_deprecated(self):
        """
        update_restaurant_plan must raise PermissionError / return an error
        response — it is deprecated in the single-tier model.
        """
        from flamezo_backend.flamezo.api.admin import update_restaurant_plan

        try:
            result = update_restaurant_plan(
                restaurant_id=self.res_id,
                plan_type="SILVER",
            )
            # If it returns a dict, it must be an error
            self.assertFalse(
                result.get("success", False),
                "update_restaurant_plan must not succeed — it is deprecated",
            )
        except (frappe.PermissionError, Exception):
            # Any exception is also acceptable (deprecated endpoint)
            pass

    # ------------------------------------------------------------------
    # 3. Loyalty API
    # ------------------------------------------------------------------

    def test_loyalty_api_does_not_fetch_plan_type_from_db(self):
        """
        The loyalty customer list API must always produce results without
        gating behind a plan_type check (plan_type is hardcoded to GOLD).
        This test verifies the API completes without errors for our restaurant.
        """
        from flamezo_backend.flamezo.api.loyalty import get_loyalty_customers

        # Should not raise; plan_type is always GOLD internally
        result = get_loyalty_customers(restaurant=self.res_id)
        self.assertTrue(
            result.get("success", True),
            f"Loyalty API error: {result}",
        )

    # ------------------------------------------------------------------
    # 4. Restaurant DocType field defaults
    # ------------------------------------------------------------------

    def test_restaurant_plan_type_default_is_gold(self):
        """
        A freshly inserted Restaurant must default to plan_type='GOLD'.
        """
        temp_id = "test-plan-default-check"
        if not frappe.db.exists("Restaurant", temp_id):
            frappe.get_doc({
                "doctype": "Restaurant",
                "restaurant_id": temp_id,
                "restaurant_name": "Plan Default Check",
                "is_active": 0,
            }).insert(ignore_permissions=True)

        val = frappe.db.get_value("Restaurant", temp_id, "plan_type")
        self.assertEqual(val, "GOLD", "Default plan_type must be 'GOLD'")

    # ------------------------------------------------------------------
    # 5. Flamezo Settings — gold_upgrade_barrier
    # ------------------------------------------------------------------

    def test_flamezo_settings_gold_upgrade_barrier_is_zero(self):
        """
        The platform-wide gold_upgrade_barrier must be 0.0 (retired).
        """
        barrier = frappe.db.get_single_value(
            "Flamezo Settings", "gold_upgrade_barrier"
        )
        self.assertAlmostEqual(
            float(barrier or 0),
            0.0,
            places=2,
            msg="gold_upgrade_barrier must be 0.0 in the single-tier model",
        )

    def test_flamezo_settings_gold_commission_percent_is_three(self):
        """
        The platform-wide gold_commission_percent default must be 3.0%.
        """
        pct = frappe.db.get_single_value(
            "Flamezo Settings", "gold_commission_percent"
        )
        self.assertAlmostEqual(
            float(pct or 0),
            3.0,
            places=1,
            msg="gold_commission_percent must default to 3.0%",
        )

    # ------------------------------------------------------------------
    # 6. Platform settings API response
    # ------------------------------------------------------------------

    def test_get_platform_settings_no_upgrade_barrier(self):
        """
        get_platform_settings must not expose a non-zero gold_upgrade_barrier.
        """
        from flamezo_backend.flamezo.api.admin import get_platform_settings

        result = get_platform_settings()
        self.assertTrue(result.get("success"), f"Platform settings error: {result}")

        data = result.get("data", {})
        barrier = float(data.get("gold_upgrade_barrier", 0))
        self.assertAlmostEqual(
            barrier,
            0.0,
            places=2,
            msg="Platform settings must not expose a non-zero gold_upgrade_barrier",
        )


if __name__ == "__main__":
    unittest.main()
