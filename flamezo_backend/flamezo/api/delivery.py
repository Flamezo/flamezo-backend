# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.logistics.manager import LogisticsManager

@frappe.whitelist()
def get_delivery_quote(order_id):
    """Whitelisted API to get a dynamic delivery estimate for an order"""
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)
        
        manager = LogisticsManager(order.restaurant)
        return manager.get_quote({
            "address": order.delivery_address,
            "latitude": order.delivery_latitude,
            "longitude": order.delivery_longitude,
            "phone": order.customer_phone,
            "name": order.customer_name,
            "items": order.get("order_items"),
            "total": order.total
        })
    except Exception as e:
        return {"success": False, "error": str(e)}

def _push_delivery_update(order_name, fields):
    """
    Push a delivery status change to both:
    1. Administrator room (merchant dashboard)
    2. Customer-specific channel (ONO menu in-progress page)
    """
    payload = {"order_id": order_name, **fields}
    frappe.publish_realtime("order_update", payload, user="Administrator")
    frappe.publish_realtime(f"delivery_update_{order_name}", payload)


@frappe.whitelist()
def assign_delivery(order_id, delivery_mode, partner_name=None, rider_name=None, rider_phone=None, eta=None):
    """Entry point for all delivery assignments (Manual only)"""
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)

        order.db_set({
            "delivery_partner": "manual",
            "delivery_status": "assigned",
            "delivery_rider_name": rider_name,
            "delivery_rider_phone": rider_phone,
            "delivery_eta": eta,
        })
        frappe.db.commit()
        # Push realtime update so customer in-progress page refreshes instantly
        _push_delivery_update(order.name, {
            "delivery_status": "assigned",
            "rider_name": rider_name or "",
            "rider_phone": rider_phone or "",
            "tracking_url": "",
        })
        return {"success": True, "message": _("Manual delivery assigned")}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Delivery Assignment Error"))
        return {"success": False, "error": str(e)}

@frappe.whitelist()
def cancel_delivery(order_id, delivery_id=None):
    """Entry point for delivery cancellations"""
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)

        order.db_set({
            "delivery_id": None,
            "delivery_status": "cancelled",
            "delivery_rider_name": None,
            "delivery_rider_phone": None,
            "delivery_tracking_url": None,
        })
        return {"success": True}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Delivery Cancellation Error"))
        return {"success": False, "error": str(e)}

@frappe.whitelist()
def sync_delivery_status(order_id):
    """
    Manually poll the logistics provider for the latest status.
    For manual delivery, this is a no-op.
    """
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)
        return {"success": True, "status": order.delivery_status or "assigned"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Delivery Sync Error"))
        return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
def handle_unified_webhook():
    """Universal gateway for all logistics webhooks (disabled)"""
    return {"status": True, "message": "Webhook Processed"}


@frappe.whitelist()
def update_delivery_info(order_id, rider_name=None, rider_phone=None, eta=None):
    """
    Update rider details after self-delivery assignment without cancelling and re-assigning.
    Pushes a realtime event so the customer in-progress page refreshes instantly.
    """
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)

        update_fields = {}
        if rider_name is not None:
            update_fields["delivery_rider_name"] = rider_name
        if rider_phone is not None:
            update_fields["delivery_rider_phone"] = rider_phone
        if eta is not None:
            update_fields["delivery_eta"] = eta

        if not update_fields:
            return {"success": True, "message": _("Nothing to update")}

        order.db_set(update_fields)
        frappe.db.commit()
        _push_delivery_update(order.name, {
            "delivery_status": order.delivery_status or "",
            "rider_name": rider_name if rider_name is not None else (order.delivery_rider_name or ""),
            "rider_phone": rider_phone if rider_phone is not None else (order.delivery_rider_phone or ""),
            "tracking_url": order.delivery_tracking_url or "",
        })
        return {"success": True, "message": _("Rider info updated")}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Update Delivery Info Error"))
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def mark_self_delivery_status(order_id, new_status):
    """
    Progress self / manual delivery:
      assigned → DISPATCHED → DELIVERED (auto-completes order)
    Pushes realtime to both merchant dashboard and customer in-progress page.
    """
    ALLOWED = {"DISPATCHED", "DELIVERED"}
    if new_status not in ALLOWED:
        return {"success": False, "error": _("Invalid status. Must be DISPATCHED or DELIVERED.")}

    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)

        if order.status in ["completed", "cancelled"]:
            return {"success": False, "error": _("Order is already completed or cancelled")}

        update_fields = {"delivery_status": new_status}
        if new_status == "DELIVERED":
            update_fields["status"] = "completed"

        order.db_set(update_fields)
        frappe.db.commit()
        _push_delivery_update(order.name, {
            "delivery_status": new_status,
            "rider_name": order.delivery_rider_name or "",
            "rider_phone": order.delivery_rider_phone or "",
            "tracking_url": "",
        })
        return {"success": True, "message": _(f"Delivery marked as {new_status.title()}")}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Mark Self Delivery Status Error"))
        return {"success": False, "error": str(e)}
