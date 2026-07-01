"""
Flamezo Coupon Tasks
- auto_activate_scheduled_coupons : daily 00:05 — go-live coupons
- auto_deactivate_expired_coupons : daily 00:05 — expire coupons
- send_offer_claim_notification   : short-queue — WhatsApp after PIN claim
"""

import frappe
from frappe.utils import today, getdate, flt


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
        fields=["name", "code", "valid_until"],
    )

    deactivated = []
    for coupon in to_deactivate:
        # Extra safety guard: Do not deactivate if valid_until is null, empty, or zero date
        val = coupon.get("valid_until")
        if not val or str(val) in ("0000-00-00", "None", ""):
            continue
        frappe.db.set_value("Coupon", coupon.name, "is_active", 0)
        deactivated.append(coupon.code)

    if deactivated:
        frappe.db.commit()
        frappe.logger().info(f"[coupon_tasks] Auto-deactivated {len(deactivated)} expired coupons: {deactivated}")

    return deactivated


def sync_coupon_activation_by_timelines():
    """
    Run periodically (every 15 min) to automatically toggle coupons On/Off
    based on their day/time/date timeline constraints, if they are set.
    Coupons with no timelines remain infinitely active (unless manually deactivated).
    """
    today_date = today()
    current_dt = now_datetime()
    current_day = current_dt.strftime("%A").lower()
    current_time = current_dt.time()

    import json
    from datetime import datetime

    coupons = frappe.get_all(
        "Coupon",
        fields=[
            "name", "code", "is_active", "valid_from", "valid_until",
            "valid_days_of_week", "valid_time_start", "valid_time_end"
        ]
    )

    for coupon in coupons:
        has_timeline = False
        is_currently_valid = True

        valid_from = coupon.get("valid_from")
        valid_until = coupon.get("valid_until")
        valid_days = coupon.get("valid_days_of_week")
        time_start = coupon.get("valid_time_start")
        time_end = coupon.get("valid_time_end")

        # 1. Date checks
        if valid_from and str(valid_from) not in ("0000-00-00", "None", ""):
            has_timeline = True
            if getdate(valid_from) > getdate(today_date):
                is_currently_valid = False

        if valid_until and str(valid_until) not in ("0000-00-00", "None", ""):
            has_timeline = True
            if getdate(valid_until) < getdate(today_date):
                is_currently_valid = False

        # 2. Day of week checks
        if valid_days and str(valid_days) not in ("[]", "None", ""):
            has_timeline = True
            try:
                days = json.loads(valid_days) if isinstance(valid_days, str) else list(valid_days)
                days_lower = [d.lower() for d in days]
                if current_day not in days_lower:
                    is_currently_valid = False
            except Exception:
                pass

        # 3. Time of day checks
        if time_start or time_end:
            has_timeline = True
            try:
                if time_start:
                    start = datetime.strptime(str(time_start).split(".")[0], "%H:%M:%S").time()
                    if current_time < start:
                        is_currently_valid = False
                if time_end:
                    end = datetime.strptime(str(time_end).split(".")[0], "%H:%M:%S").time()
                    if current_time > end:
                        is_currently_valid = False
            except Exception:
                pass

        # If it has a timeline, sync the active status
        if has_timeline:
            new_state = 1 if is_currently_valid else 0
            if coupon.is_active != new_state:
                frappe.db.set_value("Coupon", coupon.name, "is_active", new_state)
                frappe.logger().info(
                    f"[coupon_tasks] Timed Coupon {coupon.code} toggled {'ON' if new_state else 'OFF'} by timeline scheduler."
                )

    frappe.db.commit()



# ──────────────────────────────────────────────────────────────────────────────
# WhatsApp notification — fires after a successful PIN claim
# ──────────────────────────────────────────────────────────────────────────────


def send_offer_claim_notification(claim_id):
    """
    Short-queue task enqueued (enqueue_after_commit=True) from claim_offer.
    Sends a WhatsApp message confirming the offer and including the pay-bill link.

    Meta template: offer_claim_pay
    Body params: {{1}} discount label, {{2}} restaurant name, {{3}} coupon code
    Button: dynamic URL suffix → {restaurant_slug}/pay-bill?offer={code}
    """
    try:
        claim = frappe.get_doc("Offer Claim", claim_id)
    except frappe.DoesNotExistError:
        return

    phone = claim.customer_phone or ""
    if not phone:
        phone = frappe.db.get_value("Customer", claim.customer, "phone") or ""
    if not phone:
        return

    restaurant_name = (
        frappe.db.get_value("Restaurant", claim.restaurant, "restaurant_name") or "the restaurant"
    )
    restaurant_slug = (
        frappe.db.get_value("Restaurant", claim.restaurant, "restaurant_id") or claim.restaurant
    )

    coupon_row = frappe.db.get_value(
        "Coupon",
        claim.coupon,
        ["discount_value", "discount_type"],
        as_dict=True,
    ) or {}
    discount_val = flt(coupon_row.get("discount_value") or 0)
    discount_type = (coupon_row.get("discount_type") or "flat").lower()
    if discount_type == "percent":
        discount_label = f"{int(discount_val)}% OFF"
    else:
        discount_label = f"₹{int(discount_val)} flat off"

    from flamezo_backend.flamezo.api.otp import generate_whatsapp_auth_token
    wa_token = generate_whatsapp_auth_token(phone, claim.customer) if claim.customer else ""
    token_suffix = f"&wt={wa_token}" if wa_token else ""
    button_url_suffix = f"{restaurant_slug}/pay-bill?offer={claim.coupon_code}{token_suffix}"

    from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message
    try:
        success, result = send_whatsapp_cloud_message(
            to_phone=phone,
            template_name="offer_claim_pay",
            body_params=[discount_label, restaurant_name, claim.coupon_code],
            button_url_param=button_url_suffix,
        )
        if not success:
            frappe.log_error(f"send_offer_claim_notification({claim_id}): {result}", "Coupon")
    except Exception as e:
        frappe.log_error(f"send_offer_claim_notification({claim_id}): {e}", "Coupon")
