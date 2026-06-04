# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Patch: Remove the ₹399 monthly floor / minimum guarantee from the model.

Background
----------
The single-tier GOLD model previously charged a ₹399/mo minimum: if a
restaurant's success share for the period fell short of the floor, the
shortfall was deducted from its coin wallet every 30 days (nightly
`process_daily_subscription_floors` task). That floor has been removed —
restaurants now pay only a success share on the orders they actually process.

The charging task and its scheduler entry have already been retired in code
(now a no-op). This patch zeroes out the stored floor values so existing
restaurants reflect the new "no floor" state, regardless of what the old
migration set:

  1. Restaurant.monthly_minimum      -> 0   (every restaurant)
  2. Restaurant.enable_floor_recovery -> 0  (every restaurant)
  3. Flamezo Settings.gold_monthly_fee / gold_monthly_floor_legacy -> 0

This only ever REDUCES what a restaurant could be charged (floor -> 0), so it
is safe and idempotent. It does not touch platform_fee_percent (success share).
"""

import frappe


def execute():
    # 1 & 2 — zero the per-restaurant floor + disable floor recovery for all.
    #         Raw SQL keeps this fast and avoids Restaurant.validate hooks.
    frappe.db.sql(
        """
        UPDATE `tabRestaurant`
        SET monthly_minimum = 0,
            enable_floor_recovery = 0
        WHERE COALESCE(monthly_minimum, 0) != 0
           OR COALESCE(enable_floor_recovery, 0) != 0
        """
    )

    # 3 — zero the platform-level floor defaults in Flamezo Settings (Single).
    try:
        if frappe.db.exists("DocType", "Flamezo Settings"):
            frappe.db.set_single_value("Flamezo Settings", "gold_monthly_fee", 0)
            frappe.db.set_single_value("Flamezo Settings", "gold_monthly_floor_legacy", 0)
    except Exception as e:
        # Settings may not be installed on every site — never fail the migrate.
        frappe.log_error(
            f"remove_monthly_floor_2026: settings update skipped: {str(e)}"[:140],
            "Billing Patch Info",
        )

    frappe.db.commit()
