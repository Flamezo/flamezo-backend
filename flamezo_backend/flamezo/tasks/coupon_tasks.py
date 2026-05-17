"""
Flamezo Coupon Tasks
Handles scheduled coupon activation and expiry based on valid_from / valid_until.
"""

import frappe
from frappe.utils import today, getdate


def auto_activate_scheduled_coupons():
    """
    Daily task (00:05) — activate coupons whose valid_from is today and are still inactive.
    Merchants can create coupons in advance and let them go live automatically.
    """
    today_date = today()

    # Coupons that should now be active: valid_from <= today, not yet active
    to_activate = frappe.get_all(
        "Coupon",
        filters={
            "is_active": 0,
            "valid_from": ("<=", today_date),
        },
        fields=["name", "code", "restaurant", "valid_until"],
    )

    activated = []
    for coupon in to_activate:
        # Skip if already expired
        if coupon.valid_until and getdate(coupon.valid_until) < getdate(today_date):
            continue
        frappe.db.set_value("Coupon", coupon.name, "is_active", 1)
        activated.append(coupon.code)

    if activated:
        frappe.db.commit()
        frappe.logger().info(f"[coupon_tasks] Auto-activated {len(activated)} coupons: {activated}")

    return activated


def auto_deactivate_expired_coupons():
    """
    Daily task (00:05) — deactivate coupons whose valid_until is in the past.
    Keeps the active list clean without manual effort from the merchant.
    """
    today_date = today()

    to_deactivate = frappe.get_all(
        "Coupon",
        filters={
            "is_active": 1,
            "valid_until": ("<", today_date),
        },
        fields=["name", "code"],
    )

    deactivated = []
    for coupon in to_deactivate:
        frappe.db.set_value("Coupon", coupon.name, "is_active", 0)
        deactivated.append(coupon.code)

    if deactivated:
        frappe.db.commit()
        frappe.logger().info(f"[coupon_tasks] Auto-deactivated {len(deactivated)} expired coupons: {deactivated}")

    return deactivated
