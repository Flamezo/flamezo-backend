# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import requests
import json
import hmac
import hashlib
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
    """Entry point for all delivery assignments (Manual or Integrated)"""
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)

        if delivery_mode == "manual":
            order.db_set({
                "delivery_partner": partner_name or "manual",
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

        if delivery_mode == "auto" or partner_name in ["borzo", "flash"]:
            # If partner_name is not provided, use the restaurant's preferred one
            manager = LogisticsManager(order.restaurant)
            res = manager.book_delivery(order)
            
            if res.get("success"):
                order.db_set({
                    "delivery_partner": partner_name or manager.restaurant.preferred_logistics_provider or "flash",
                    "delivery_id": res.get("delivery_id"),
                    "delivery_status": res.get("status"),
                    "delivery_tracking_url": res.get("tracking_url"),
                    "delivery_fee": res.get("delivery_fee"),
                    "logistics_platform_fee": res.get("logistics_platform_fee")
                })
                frappe.db.commit()
                _push_delivery_update(order.name, {
                    "delivery_status": res.get("status") or "",
                    "rider_name": "",
                    "rider_phone": "",
                    "tracking_url": res.get("tracking_url") or "",
                })
                return res
            else:
                return {"success": False, "error": res.get("error")}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Delivery Assignment Error"))
        return {"success": False, "error": str(e)}

@frappe.whitelist()
def cancel_delivery(order_id, delivery_id=None):
    """Entry point for delivery cancellations"""
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)

        if order.delivery_partner in ["borzo", "flash"] and delivery_id:
            manager = LogisticsManager(order.restaurant)
            manager.cancel_delivery(delivery_id)

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
    Useful as a fallback if webhooks are delayed.
    """
    try:
        order = frappe.get_doc("Order", order_id)
        validate_restaurant_for_api(order.restaurant, frappe.session.user)
        
        if not order.delivery_id:
            return {"success": False, "error": _("No delivery assigned to this order")}
            
        manager = LogisticsManager(order.restaurant)
        res = manager.track_delivery(order.delivery_id)
        
        if res.get("success"):
            update_data = {"delivery_status": res.get("status")}
            if res.get("rider_name"): update_data["delivery_rider_name"] = res.get("rider_name")
            if res.get("rider_phone"): update_data["delivery_rider_phone"] = res.get("rider_phone")
            if res.get("tracking_url"): update_data["delivery_tracking_url"] = res.get("tracking_url")
            if res.get("lat") and res.get("lng"):
                update_data["rider_latitude"] = res.get("lat")
                update_data["rider_longitude"] = res.get("lng")
                update_data["rider_last_updated"] = frappe.utils.now_datetime()
                
            order.db_set(update_data)
            frappe.db.commit()
            _push_delivery_update(order_id, {
                "delivery_status": res.get("status") or "",
                "rider_name": res.get("rider_name") or "",
                "rider_phone": res.get("rider_phone") or "",
                "tracking_url": res.get("tracking_url") or "",
            })
            return res
        else:
            return {"success": False, "error": res.get("error")}
            
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Delivery Sync Error"))
        return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
def handle_unified_webhook():
    """Universal gateway for all logistics webhooks (Flash, Borzo, etc)"""
    try:
        # Frappe merges URL query params (?provider=flash) into frappe.form_dict for
        # whitelisted POST calls — frappe.request.args is often empty in this context.
        provider_name = (
            frappe.form_dict.get("provider")
            or frappe.request.args.get("provider")
            or ""
        ).lower().strip()
        raw_body = frappe.request.get_data()
        
        # ── Flash webhook authentication ───────────────────────────────────────
        # NOTE: We do NOT use the "Authorization" header here because Frappe's
        # global validate_auth() middleware intercepts it and raises AuthenticationError.
        # The uEngage dashboard lets you set any custom header key — we use X-Flash-Token
        # (or whatever key is configured in Flamezo Settings > flash_webhook_header_key).
        if provider_name == "flash":
            settings = frappe.get_single("Flamezo Settings")
            header_key = getattr(settings, "flash_webhook_header_key", None)
            if header_key:
                expected_value = settings.get_password("flash_webhook_header_value") or ""
                # Try exact key, then lowercase, then stripped
                received_value = (
                    frappe.request.headers.get(header_key)
                    or frappe.request.headers.get(header_key.lower())
                    or frappe.request.headers.get(header_key.replace(" ", "-"))
                    or ""
                )
                if expected_value and received_value != expected_value:
                    frappe.response.http_status_code = 401
                    return {"error": "Unauthorized", "message": "Authentication is required."}

        # Determine order from payload based on provider
        data = json.loads(raw_body.decode('utf-8'))
        delivery_id = None
        status = None
        tracking_url = None
        lat = lng = None
        rider_name = rider_phone = None

        if provider_name == "borzo":
            # Borzo payload structure
            borzo_order = data.get("order", {})
            delivery_id = str(borzo_order.get("order_id"))
            status = borzo_order.get("status_description") or borzo_order.get("status")
            courier = borzo_order.get("courier", {})
            rider_name = courier.get("name")
            rider_phone = courier.get("phone")
            lat = flt(courier.get("latitude"))
            lng = flt(courier.get("longitude"))
        
        elif provider_name == "flash":
            # uEngage Flash payload structure (Callback API spec)
            flash_data = data.get("data", {})
            delivery_id = flash_data.get("taskId")
            status = data.get("status_code")  # e.g. DISPATCHED, DELIVERED, ALLOTTED
            rider_name = flash_data.get("rider_name")
            rider_phone = flash_data.get("rider_contact")
            tracking_url = flash_data.get("tracking_url")
            lat = flt(flash_data.get("latitude")) if flash_data.get("latitude") else None
            lng = flt(flash_data.get("longitude")) if flash_data.get("longitude") else None

        if not delivery_id:
            return {"status": True, "message": "Webhook Processed"}

        order_name = frappe.db.get_value("Order", {"delivery_id": delivery_id}, "name")
        if not order_name:
            # Flash requires HTTP 200 + specific body even for unknown orders
            return {"status": True, "message": "Webhook Processed"}

        order = frappe.get_doc("Order", order_name)
        
        # Update delivery fields
        update_fields = {}
        if status:
            update_fields["delivery_status"] = status
            # Auto-mark order as completed when delivered
            if status == "DELIVERED" and order.status not in ["completed", "cancelled"]:
                update_fields["status"] = "completed"
        if rider_name:
            update_fields["delivery_rider_name"] = rider_name
        if rider_phone:
            update_fields["delivery_rider_phone"] = rider_phone
        if tracking_url:
            update_fields["delivery_tracking_url"] = tracking_url
        if lat and lng:
            update_fields["rider_latitude"] = lat
            update_fields["rider_longitude"] = lng
            update_fields["rider_last_updated"] = frappe.utils.now_datetime()

        if update_fields:
            order.db_set(update_fields, update_modified=True)

        frappe.db.commit()

        # Push real-time update to:
        # 1. The restaurant dashboard (Administrator room)
        # 2. The specific customer's room (by order_id) so the ONO menu in-progress page updates live
        realtime_payload = {
            "order_id": order_name,
            "delivery_status": status,
            "rider_name": rider_name or "",
            "rider_phone": rider_phone or "",
            "tracking_url": tracking_url or "",
            "rider_lat": str(lat) if lat else "",
            "rider_lng": str(lng) if lng else "",
        }
        frappe.publish_realtime("order_update", realtime_payload, user="Administrator")
        # Customer-facing room: keyed by order_name so the ONO in-progress page can subscribe
        frappe.publish_realtime(f"delivery_update_{order_name}", realtime_payload)

        # Flash requires exactly this response shape
        return {"status": True, "message": "Webhook Processed"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Unified Logistics Webhook Error"))
        # Return 200 to prevent Flash from retrying on our own bugs
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
