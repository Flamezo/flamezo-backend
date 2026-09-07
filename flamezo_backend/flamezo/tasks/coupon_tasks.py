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
        fields=["name", "code", "outlet", "valid_until"],
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
        frappe.db.get_value("Outlet", claim.outlet, "outlet_name") or "the restaurant"
    )
    restaurant_slug = (
        frappe.db.get_value("Outlet", claim.outlet, "outlet_id") or claim.outlet
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
    # claim.customer may be empty; generate_whatsapp_auth_token resolves the
    # Customer by phone as a fallback so the auto-login token is still issued.
    wa_token = generate_whatsapp_auth_token(phone, claim.customer or "")
    token_suffix = f"&wt={wa_token}" if wa_token else ""
    button_url_suffix = f"{restaurant_slug}/pay-bill?offer={claim.coupon_code}{token_suffix}"

    from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message

    # Template name is configurable so an approved-template rename on the Meta
    # side doesn't need a code deploy (the OTP path does the same via
    # site_config.whatsapp_otp_template). Meta rejects an unknown/unapproved
    # name with a 400 and the message silently never arrives.
    template_name = frappe.conf.get("whatsapp_offer_claim_template") or "offer_claim_pay"
    try:
        success, result = send_whatsapp_cloud_message(
            to_phone=phone,
            template_name=template_name,
            body_params=[discount_label, restaurant_name, claim.coupon_code],
            button_url_param=button_url_suffix,
        )
        if not success:
            frappe.log_error(
                f"send_offer_claim_notification({claim_id}) template={template_name} "
                f"phone={phone}: {result}",
                "Coupon WhatsApp Failed",
            )
    except Exception as e:
        frappe.log_error(
            f"send_offer_claim_notification({claim_id}) template={template_name}: {e}",
            "Coupon WhatsApp Failed",
        )
