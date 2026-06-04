# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Patch: Migrate every legacy SILVER restaurant to the new single-tier GOLD model.

Background
----------
As of May 2026 Flamezo runs a single-tier platform model: free onboarding, full
feature access, no monthly floor, success share on online orders. The legacy
SILVER tier had ordering + loyalty only and ran with several Restaurant Config
feature flags forced to 0 (table booking, offers, coupons, etc.) plus several
Home Features hidden.

This patch:
  1. Flips plan_type from SILVER to GOLD for every restaurant.
  2. Initializes monthly_minimum / platform_fee_percent if they are missing,
     using values from Flamezo Settings.
  3. Re-enables the transactional feature flags on every restaurant's
     Restaurant Config row (only when currently 0 — owner choices left alone).
  4. Re-enables previously-hidden Home Feature rows (book-table, offers-events,
     dine-play) that were 0 due to the old plan gate.
  5. Records a Plan Change Log entry per restaurant.

The patch uses raw SQL (or db.set_value) to avoid the admin-only role check in
Restaurant.validate_plan_change().
"""

import json

import frappe


_DEFAULT_FLOOR = 0.0  # Monthly floor removed from the model
_DEFAULT_COMMISSION = 1.5
_CONFIG_FEATURE_FIELDS = (
    "enable_table_booking",
    "enable_banquet_booking",
    "enable_events",
    "enable_offers",
    "enable_coupons",
    "enable_experience_lounge",
)
_HOME_FEATURE_IDS = ("book-table", "offers-events", "dine-play")


def _settings_floor() -> float:
    val = frappe.db.get_single_value("Flamezo Settings", "gold_monthly_fee")
    return float(val) if val is not None else _DEFAULT_FLOOR


def _settings_commission() -> float:
    val = frappe.db.get_single_value("Flamezo Settings", "gold_commission_percent")
    return float(val) if val is not None else _DEFAULT_COMMISSION


def execute():
    silver_restaurants = frappe.get_all(
        "Restaurant",
        filters={"plan_type": "SILVER"},
        fields=["name", "monthly_minimum", "platform_fee_percent"],
    )

    if not silver_restaurants:
        frappe.logger().info("migrate_silver_to_gold_2026: no SILVER restaurants found, nothing to do")
        return

    now = frappe.utils.now()
    floor = _settings_floor()
    commission = _settings_commission()

    migrated = 0
    config_flips = 0
    feature_flips = 0
    errors = 0

    for res in silver_restaurants:
        try:
            updates = {
                "plan_type": "GOLD",
                "plan_activated_on": now,
                "plan_changed_by": "Administrator",
                "plan_change_reason": "Auto-migration (May 2026 new business model: single GOLD tier)",
            }
            if not res.monthly_minimum:
                updates["monthly_minimum"] = floor
            if res.platform_fee_percent is None or float(res.platform_fee_percent) == 0:
                updates["platform_fee_percent"] = commission

            # Bypass validate_plan_change() role guard.
            frappe.db.set_value("Restaurant", res.name, updates, update_modified=True)

            # Append a plan_change_history JSON entry (best-effort).
            try:
                raw_history = frappe.db.get_value("Restaurant", res.name, "plan_change_history") or "[]"
                history = json.loads(raw_history) if isinstance(raw_history, str) else (raw_history or [])
                if not isinstance(history, list):
                    history = []
                history.append({
                    "date": now,
                    "from": "SILVER",
                    "to": "GOLD",
                    "by": "Administrator",
                    "reason": updates["plan_change_reason"],
                })
                frappe.db.set_value(
                    "Restaurant",
                    res.name,
                    "plan_change_history",
                    json.dumps(history),
                    update_modified=False,
                )
            except Exception as hist_err:
                frappe.logger().warning(
                    f"migrate_silver_to_gold_2026: plan_change_history write failed for {res.name}: {hist_err}"
                )

            # Write the Plan Change Log doc separately so reports still work.
            try:
                frappe.get_doc({
                    "doctype": "Plan Change Log",
                    "restaurant": res.name,
                    "previous_plan": "SILVER",
                    "new_plan": "GOLD",
                    "changed_by": "Administrator",
                    "changed_on": now,
                    "change_reason": updates["plan_change_reason"],
                    "ip_address": "Migration Script",
                }).insert(ignore_permissions=True)
            except Exception as log_err:
                frappe.logger().warning(
                    f"migrate_silver_to_gold_2026: Plan Change Log insert failed for {res.name}: {log_err}"
                )

            # Re-enable transactional flags on the restaurant's config — but only
            # if currently OFF, so we don't trample an owner who intentionally
            # disabled a feature post-migration.
            config_name = frappe.db.get_value("Restaurant Config", {"restaurant": res.name}, "name")
            if config_name:
                for field in _CONFIG_FEATURE_FIELDS:
                    current = frappe.db.get_value("Restaurant Config", config_name, field)
                    if not current:
                        frappe.db.set_value("Restaurant Config", config_name, field, 1, update_modified=False)
                        config_flips += 1

            # Re-enable previously-disabled Home Features for this restaurant.
            for feature_id in _HOME_FEATURE_IDS:
                feature_row = frappe.db.get_value(
                    "Home Feature",
                    {"restaurant": res.name, "feature_id": feature_id},
                    ["name", "is_enabled"],
                    as_dict=True,
                )
                if feature_row and not feature_row.is_enabled:
                    frappe.db.set_value("Home Feature", feature_row.name, "is_enabled", 1, update_modified=False)
                    feature_flips += 1

            migrated += 1
        except Exception as e:
            errors += 1
            frappe.logger().error(f"migrate_silver_to_gold_2026: failed for {res.name}: {e}")
            continue

    frappe.db.commit()

    summary = (
        f"migrate_silver_to_gold_2026: migrated={migrated} "
        f"config_feature_flips={config_flips} home_feature_flips={feature_flips} errors={errors}"
    )
    frappe.logger().info(summary)
    print("✅", summary)
