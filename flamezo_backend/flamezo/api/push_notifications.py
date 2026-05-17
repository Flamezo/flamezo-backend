# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Web Push Notifications via Firebase Cloud Messaging (FCM) HTTP v1.
Cost: ZERO — FCM is free forever. No per-message charges.

Architecture:
  - Customer browsers subscribe → endpoint stored on tabCustomer (push_endpoint JSON)
  - Merchant (dashboard) browsers subscribe → endpoints stored on tabRestaurant Config
  - When order status changes → frappe.enqueue this module's send_* helpers
  - FCM HTTP v1 bearer token is obtained via Google service-account OAuth2 (cached 55 min)

Setup (one-time, Flamezo admin):
  1. Create a Firebase project at console.firebase.google.com
  2. Generate a service account key JSON (Project Settings → Service Accounts)
  3. Store the JSON content in site_config.json under key "fcm_service_account_json"
  4. The VAPID public key (for the web push subscription) lives in site_config.json
     under "fcm_vapid_public_key"
"""

import frappe
import json
import time
from frappe.utils import cstr

# ─────────────────────────────────────────────────────────────────────────────
# FCM token helpers
# ─────────────────────────────────────────────────────────────────────────────

_FCM_TOKEN_CACHE = {"token": None, "expires_at": 0}


def _get_fcm_access_token():
    """
    Returns a short-lived Google OAuth2 bearer token for FCM HTTP v1.
    Token is cached in memory (valid for ~55 min).
    Requires: google-auth library (pip install google-auth)
    """
    global _FCM_TOKEN_CACHE

    if _FCM_TOKEN_CACHE["token"] and time.time() < _FCM_TOKEN_CACHE["expires_at"]:
        return _FCM_TOKEN_CACHE["token"]

    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests

        sa_json = frappe.conf.get("fcm_service_account_json")
        if not sa_json:
            frappe.log_error("FCM service account JSON not configured in site_config.json", "Push Notifications")
            return None

        # Resolve JSON content if it's a filename
        import os
        if isinstance(sa_json, str) and not sa_json.startswith("{"):
            # It's a filename path (relative to site directory)
            try:
                path = frappe.get_site_path(sa_json)
                if os.path.exists(path):
                    with open(path, "r") as f:
                        sa_info = json.load(f)
                else:
                    frappe.log_error(f"FCM service account file not found: {path}", "Push Notifications")
                    return None
            except Exception as fe:
                frappe.log_error(f"Failed to read FCM service account file: {str(fe)}", "Push Notifications")
                return None
        elif isinstance(sa_json, str):
            sa_info = json.loads(sa_json)
        else:
            sa_info = sa_json

        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)

        _FCM_TOKEN_CACHE["token"] = credentials.token
        _FCM_TOKEN_CACHE["expires_at"] = time.time() + 3300  # 55 min

        return credentials.token
    except Exception as e:
        frappe.log_error(f"Failed to get FCM access token: {str(e)}", "Push Notifications")
        return None


def _get_fcm_project_id():
    sa_json = frappe.conf.get("fcm_service_account_json")
    if not sa_json:
        return None

    import os
    if isinstance(sa_json, str) and not sa_json.startswith("{"):
        try:
            path = frappe.get_site_path(sa_json)
            if os.path.exists(path):
                with open(path, "r") as f:
                    sa_info = json.load(f)
                    return sa_info.get("project_id")
        except Exception:
            pass
        return None

    if isinstance(sa_json, str):
        try:
            sa_info = json.loads(sa_json)
            return sa_info.get("project_id")
        except Exception:
            return None
    
    return sa_json.get("project_id") if sa_json else None


def _send_fcm_message(fcm_token: str, title: str, body: str, data: dict = None, icon: str = None):
    """
    Sends a single FCM message to one device/browser subscription token.
    Returns True on success.
    """
    try:
        import requests as http_requests

        access_token = _get_fcm_access_token()
        project_id = _get_fcm_project_id()

        if not access_token or not project_id:
            return False

        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "message": {
                "token": fcm_token,
                "notification": {
                    "title": title,
                    "body": body,
                },
                "webpush": {
                    "notification": {
                        "title": title,
                        "body": body,
                        "icon": icon or "/assets/flamezo_backend/logo-192.png",
                        "badge": "/assets/flamezo_backend/badge-72.png",
                        "requireInteraction": False,
                        "silent": False,
                    },
                    "fcm_options": {
                        "link": "/"
                    }
                },
                "data": {k: cstr(v) for k, v in (data or {}).items()}
            }
        }

        resp = http_requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            return True

        # Token expired/unregistered → remove it
        if resp.status_code in (404, 410):
            return "unregistered"

        frappe.log_error(
            f"FCM send failed [{resp.status_code}]: {resp.text[:500]}",
            "Push Notifications"
        )
        return False
    except Exception as e:
        frappe.log_error(f"FCM send exception: {str(e)}", "Push Notifications")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Subscription management (whitelisted — called from browser)
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def save_customer_subscription(restaurant_id, fcm_token, customer_phone=None):
    """
    Saves a customer's FCM token so we can push order status updates to them.
    Called from ONO menu after browser grants notification permission.
    """
    try:
        if not fcm_token:
            return {"success": False, "error": "No FCM token provided"}

        restaurant_id = restaurant_id.lower() if restaurant_id else restaurant_id

        if customer_phone:
            from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone
            normalized = normalize_phone(str(customer_phone))

            # Find or create customer record
            customer = frappe.db.get_value("Customer", {"normalized_phone": normalized}, "name")
            if customer:
                # Store token on Customer doc — push_fcm_tokens is a JSON list field
                existing_raw = frappe.db.get_value("Customer", customer, "push_fcm_tokens") or "[]"
                try:
                    tokens = json.loads(existing_raw)
                except Exception:
                    tokens = []

                if fcm_token not in tokens:
                    tokens.append(fcm_token)
                    # Keep max 5 tokens per customer (multiple devices)
                    tokens = tokens[-5:]
                    frappe.db.set_value("Customer", customer, "push_fcm_tokens", json.dumps(tokens))
                    frappe.db.commit()

        # Also store anonymously keyed by the token itself in a cache table
        # Use frappe.cache() for ephemeral storage (no extra doctype needed)
        frappe.cache().set_value(
            f"push_token:{restaurant_id}:{fcm_token[:32]}",
            fcm_token,
            expires_in_sec=30 * 24 * 3600  # 30 days
        )

        return {"success": True}
    except Exception as e:
        frappe.log_error(f"Error saving customer push subscription: {str(e)}", "Push Notifications")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def save_merchant_subscription(restaurant_id, fcm_token):
    """
    Saves a merchant's FCM token so new order alerts reach the dashboard even when
    the browser tab is in the background.
    Called from the merchant dashboard after notification permission is granted.
    """
    try:
        if not fcm_token:
            return {"success": False, "error": "No FCM token provided"}

        restaurant_id = restaurant_id.lower() if restaurant_id else restaurant_id

        config = frappe.db.get_value(
            "Restaurant Config",
            {"restaurant": restaurant_id},
            ["name", "merchant_push_tokens"],
            as_dict=True
        )

        if not config:
            return {"success": False, "error": "Restaurant config not found"}

        existing_raw = config.get("merchant_push_tokens") or "[]"
        try:
            tokens = json.loads(existing_raw)
        except Exception:
            tokens = []

        if fcm_token not in tokens:
            tokens.append(fcm_token)
            tokens = tokens[-10:]  # Max 10 devices per restaurant
            frappe.db.set_value(
                "Restaurant Config",
                config.name,
                "merchant_push_tokens",
                json.dumps(tokens)
            )
            frappe.db.commit()

        return {"success": True}
    except Exception as e:
        frappe.log_error(f"Error saving merchant push subscription: {str(e)}", "Push Notifications")
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def remove_customer_subscription(fcm_token, restaurant_id=None, customer_phone=None):
    """
    Removes a customer FCM token (on unsubscribe or token rotation).
    """
    try:
        if customer_phone:
            from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone
            normalized = normalize_phone(str(customer_phone))
            customer = frappe.db.get_value("Customer", {"normalized_phone": normalized}, "name")
            if customer:
                existing_raw = frappe.db.get_value("Customer", customer, "push_fcm_tokens") or "[]"
                try:
                    tokens = json.loads(existing_raw)
                except Exception:
                    tokens = []
                tokens = [t for t in tokens if t != fcm_token]
                frappe.db.set_value("Customer", customer, "push_fcm_tokens", json.dumps(tokens))
                frappe.db.commit()

        return {"success": True}
    except Exception as e:
        frappe.log_error(f"Error removing push subscription: {str(e)}", "Push Notifications")
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Internal senders — called from doc events / order_status.py
# ─────────────────────────────────────────────────────────────────────────────

def send_order_status_push_to_customer(order_name: str):
    """
    Enqueued background job. Sends a push to the customer when their order
    status changes. 100% free via FCM. 
    """
    try:
        order = frappe.get_doc("Order", order_name)

        # Human-readable status messages (Indian-friendly language)
        STATUS_MESSAGES = {
            "confirmed": ("✅ Order Confirmed!", "Your order #{num} has been confirmed and is being prepared."),
            "preparing": ("👨‍🍳 Being Prepared", "Your order #{num} is in the kitchen — almost ready!"),
            "ready": ("🍽️ Order Ready!", "Your order #{num} is ready. Come pick it up!"),
            "delivered": ("✨ Delivered!", "Your order #{num} has been delivered. Enjoy your meal!"),
            "billed": ("✨ Done!", "Your order #{num} has been completed. Thank you for dining with us!"),
            "cancelled": ("❌ Order Cancelled", "Your order #{num} was cancelled. Contact us if this was unexpected."),
        }

        status_key = (order.status or "").lower()
        if status_key not in STATUS_MESSAGES:
            return  # Don't push for intermediate/internal statuses

        order_num = order.order_number or order.name[-6:]
        title, body_tpl = STATUS_MESSAGES[status_key]
        body = body_tpl.replace("{num}", str(order_num))

        # Collect customer tokens
        tokens_to_try = []

        if order.platform_customer:
            raw = frappe.db.get_value("Customer", order.platform_customer, "push_fcm_tokens") or "[]"
            try:
                tokens_to_try.extend(json.loads(raw))
            except Exception:
                pass

        if not tokens_to_try:
            return  # No tokens — nothing to send, no cost incurred

        data = {
            "order_id": order.order_id or order.name,
            "order_number": str(order_num),
            "status": order.status,
            "restaurant_id": order.restaurant,
        }

        stale_tokens = []
        for token in tokens_to_try:
            result = _send_fcm_message(
                fcm_token=token,
                title=title,
                body=body,
                data=data,
                icon="/assets/flamezo_backend/logo-192.png"
            )
            if result == "unregistered":
                stale_tokens.append(token)

        # Clean up stale tokens
        if stale_tokens and order.platform_customer:
            raw = frappe.db.get_value("Customer", order.platform_customer, "push_fcm_tokens") or "[]"
            try:
                tokens = [t for t in json.loads(raw) if t not in stale_tokens]
                frappe.db.set_value(
                    "Customer",
                    order.platform_customer,
                    "push_fcm_tokens",
                    json.dumps(tokens)
                )
                frappe.db.commit()
            except Exception:
                pass

    except Exception as e:
        frappe.log_error(f"Error in send_order_status_push_to_customer: {str(e)}", "Push Notifications")


def send_new_order_push_to_merchant(order_name: str):
    """
    Enqueued background job. Sends a push to ALL merchant devices when a new
    order is placed. Ensures the merchant never misses an order even when the
    dashboard tab is in the background. 100% free via FCM.
    """
    try:
        order = frappe.get_doc("Order", order_name)
        restaurant_id = order.restaurant

        # Fetch merchant tokens from Restaurant Config
        config = frappe.db.get_value(
            "Restaurant Config",
            {"restaurant": restaurant_id},
            "merchant_push_tokens"
        )

        if not config:
            return

        try:
            tokens = json.loads(config)
        except Exception:
            return

        if not tokens:
            return

        order_num = order.order_number or order.name[-6:]
        order_type_label = {
            "dine_in": "Dine-in",
            "delivery": "Delivery",
            "takeaway": "Takeaway"
        }.get(order.order_type, "Order")

        title = f"🔔 New {order_type_label} Order #{order_num}"
        body_parts = []
        if order.customer_name:
            body_parts.append(order.customer_name)
        if order.table_number:
            body_parts.append(f"Table {order.table_number}")
        body_parts.append(f"₹{int(order.total or 0)}")
        body = " • ".join(body_parts)

        data = {
            "type": "new_order",
            "order_id": order.order_id or order.name,
            "order_number": str(order_num),
            "restaurant_id": restaurant_id,
        }

        stale_tokens = []
        for token in tokens:
            result = _send_fcm_message(
                fcm_token=token,
                title=title,
                body=body,
                data=data,
                icon="/assets/flamezo_backend/logo-192.png"
            )
            if result == "unregistered":
                stale_tokens.append(token)

        # Clean up stale tokens from config
        if stale_tokens:
            config_name = frappe.db.get_value(
                "Restaurant Config",
                {"restaurant": restaurant_id},
                "name"
            )
            if config_name:
                clean_tokens = [t for t in tokens if t not in stale_tokens]
                frappe.db.set_value(
                    "Restaurant Config",
                    config_name,
                    "merchant_push_tokens",
                    json.dumps(clean_tokens)
                )
                frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"Error in send_new_order_push_to_merchant: {str(e)}", "Push Notifications")


@frappe.whitelist(allow_guest=True)
def get_vapid_public_key():
    """Returns the VAPID/FCM public key for the browser to use when subscribing."""
    key = frappe.conf.get("fcm_vapid_public_key", "")
    return {"success": True, "vapid_key": key}
