"""
Flamezo Subscription Billing Tasks
Handles daily floor recovery and deferred plan transitions.
"""

from datetime import date, datetime, time, timedelta

import frappe
import pytz
from frappe.utils import getdate, date_diff, now_datetime
from flamezo_backend.flamezo.api.coin_billing import deduct_coins

def process_daily_subscription_floors():
    """
    Retired — the monthly floor / minimum guarantee was removed from the model.

    Previously this nightly task (23:59) charged GOLD restaurants a ₹399/mo
    minimum: if their success share for the period fell short of the floor, the
    shortfall was deducted from their coin wallet every 30 days.

    Under the current model there is NO monthly minimum or floor — restaurants
    pay only a success share on the orders they actually process. This function
    is kept (as a no-op) so any existing scheduler entries or out-of-tree
    callers continue to import and run without charging anything.
    """
    return

def sync_restaurant_subscription(restaurant):
    """
    Core fail-safe function to flip a restaurant to its new scheduled plan.
    Ensures idempotency and handles plan metadata.
    """
    res_doc = frappe.get_doc("Restaurant", restaurant)
    today = getdate()

    # check if switch is required (deferred plan exists and date is reached/passed)
    if not res_doc.deferred_plan_type or not res_doc.plan_change_date:
        return False

    raw_plan_change = res_doc.plan_change_date
    if not isinstance(raw_plan_change, (str, date, datetime)):
        return False
    plan_change_date = getdate(raw_plan_change)
    if not plan_change_date or not today:
        return False
    if plan_change_date > today:
        return False

    try:
        previous_plan = res_doc.plan_type
        new_plan = res_doc.deferred_plan_type
        
        # Atomically update to avoid race conditions during JIT + scheduler
        frappe.db.set_value("Restaurant", restaurant, {
            "plan_type": new_plan,
            "plan_activated_on": now_datetime(),
            "deferred_plan_type": None,
            "plan_change_date": None
        })
        
        # Log the success for billing audit
        frappe.log_error(f"Subscription Switch Success: {restaurant} moved from {previous_plan} to {new_plan}. (Source: JIT/Scheduler Sync)", "Subscription Info")
        
        # If we have a Config record, ensure it is also sync'd (optional but recommended)
        config_name = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant}, "name")
        if config_name:
            # We don't change config fields yet, but we could trigger a feature re-validation if needed
            pass

        return True
    except Exception as e:
        frappe.log_error(f"Subscription Sync failed for {restaurant}: {str(e)}", "Subscription Error")
        return False

def apply_deferred_plan_changes():
    """
    Midnight task (00:01) to flip restaurants to their new scheduled plans.
    """
    today = getdate()
    
    # 1. Find all restaurants with a plan change scheduled for today or earlier
    pending_res = frappe.get_all("Restaurant", 
        filters={
            "deferred_plan_type": ["is", "set"],
            "plan_change_date": ["<=", today]
        },
        fields=["name"]
    )
    
    for res in pending_res:
        sync_restaurant_subscription(res.name)

    frappe.db.commit()

def process_silver_feature_renewals():
    """
    Retired under the May 2026 single-tier model.

    Previously this task deducted 100 coins / 30 days from SILVER restaurants
    that had Menu Theme Background enabled, treating it as a premium add-on.
    Under the new model every onboarded restaurant is GOLD and the menu theme
    feature is included in the monthly floor — there is nothing to charge.

    The function is kept (as a no-op) so existing scheduler entries in
    hooks.py and any installed sites continue to import successfully. It also
    clears any lingering `menu_theme_paid_until` markers it finds so the
    metadata reflects the new "always included" state.
    """
    try:
        frappe.db.sql(
            """
            UPDATE `tabRestaurant Config`
            SET menu_theme_paid_until = NULL
            WHERE menu_theme_paid_until IS NOT NULL
            """
        )
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            f"process_silver_feature_renewals cleanup skipped: {str(e)}"[:140],
            "Billing Task Info",
        )
