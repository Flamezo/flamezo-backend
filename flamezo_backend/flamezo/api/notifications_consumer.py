# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Consumer Notification API.

Endpoints:
  - get_my_notifications   — paginated list for a phone
  - mark_notifications_read — bulk mark read
  - get_notification_count  — unread count (for badge)
  - create_notification    — internal helper (called by other APIs)
"""

import frappe
from frappe import _
from frappe.utils import now_datetime


# ── internal helper (not an HTTP endpoint) ────────────────────────────────────

def create_notification(customer_phone, title, body, notification_type="general",
                        reference_doctype=None, reference_name=None,
                        image_url=None, deep_link=None):
    """
    Create a Flamezo Notification for a customer.
    Called internally by order/booking/crowd APIs when state changes.
    """
    if not customer_phone or not title:
        return None
    try:
        doc = frappe.get_doc({
            "doctype": "Flamezo Notification",
            "customer_phone": customer_phone,
            "notification_type": notification_type,
            "title": title,
            "body": body or "",
            "image_url": image_url or "",
            "reference_doctype": reference_doctype or "",
            "reference_name": reference_name or "",
            "deep_link": deep_link or "",
            "is_read": 0,
            "is_actioned": 0,
        })
        doc.insert(ignore_permissions=True)
        # Invalidate unread count cache
        frappe.cache().delete_value(f"notif:count:{customer_phone}")
        return doc.name
    except Exception as e:
        frappe.log_error(f"create_notification failed: {e}")
        return None


# ── consumer endpoints ────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


def _format_notif(n):
    return {
        "id": n.name,
        "type": n.notification_type,
        "title": n.title,
        "body": n.body or "",
        "image_url": n.image_url or "",
        "is_read": bool(n.is_read),
        "is_actioned": bool(n.is_actioned),
        "reference_doctype": n.reference_doctype or "",
        "reference_name": n.reference_name or "",
        "deep_link": n.deep_link or "",
        "created_at": str(n.creation) if n.creation else "",
    }


@frappe.whitelist(allow_guest=True)
def get_my_notifications(phone, page=1, limit=30, unread_only=False):
    """
    GET .../notifications_consumer.get_my_notifications

    Returns paginated notifications for a phone, newest first.
    unread_only=True filters to unread only.
    """
    phone = _require_phone(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    filters = {"customer_phone": phone}
    if str(unread_only).lower() in ("1", "true"):
        filters["is_read"] = 0

    rows = frappe.get_all(
        "Flamezo Notification",
        filters=filters,
        fields=[
            "name", "notification_type", "title", "body", "image_url",
            "is_read", "is_actioned", "reference_doctype", "reference_name",
            "deep_link", "creation",
        ],
        order_by="creation desc",
        limit=limit + 1,
        start=offset,
    )

    has_more = len(rows) > limit
    items = rows[:limit]

    return {
        "success": True,
        "data": {
            "notifications": [_format_notif(n) for n in items],
            "page": page,
            "has_more": has_more,
        }
    }


@frappe.whitelist(allow_guest=True)
def get_notification_count(phone):
    """
    GET .../notifications_consumer.get_notification_count

    Returns unread notification count for badge display.
    Cached for 60s per phone.
    """
    phone = _require_phone(phone)
    cache_key = f"notif:count:{phone}"
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return {"success": True, "data": {"unread_count": cached}}

    count = frappe.db.count("Flamezo Notification", {"customer_phone": phone, "is_read": 0})
    frappe.cache().set_value(cache_key, count, expires_in_sec=60)
    return {"success": True, "data": {"unread_count": count}}


@frappe.whitelist(allow_guest=True)
def mark_notifications_read(phone, notification_ids=None):
    """
    POST .../notifications_consumer.mark_notifications_read

    Marks specific notifications as read.
    If notification_ids is None or empty, marks ALL as read (mark-all-read).
    notification_ids: comma-separated string or list.
    """
    phone = _require_phone(phone)

    if notification_ids:
        if isinstance(notification_ids, str):
            ids = [i.strip() for i in notification_ids.split(",") if i.strip()]
        else:
            ids = list(notification_ids)

        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            frappe.db.sql(
                f"UPDATE `tabFlamezo Notification` SET is_read=1, modified=%s WHERE name IN ({placeholders}) AND customer_phone=%s",
                [now_datetime()] + ids + [phone],
            )
    else:
        # Mark all unread as read
        frappe.db.sql(
            "UPDATE `tabFlamezo Notification` SET is_read=1, modified=%s WHERE customer_phone=%s AND is_read=0",
            [now_datetime(), phone],
        )

    frappe.db.commit()
    frappe.cache().delete_value(f"notif:count:{phone}")
    return {"success": True}


@frappe.whitelist(allow_guest=True)
def mark_notification_actioned(phone, notification_id):
    """
    POST .../notifications_consumer.mark_notification_actioned

    Marks a notification as actioned (user tapped the CTA).
    Also marks it as read.
    """
    phone = _require_phone(phone)
    if not notification_id:
        frappe.throw(_("notification_id is required"))

    notif = frappe.db.get_value(
        "Flamezo Notification",
        notification_id,
        ["name", "customer_phone"],
        as_dict=True,
    )
    if not notif:
        frappe.throw(_("Notification not found"), frappe.DoesNotExistError)
    if notif.customer_phone != phone:
        frappe.throw(_("Access denied"), frappe.PermissionError)

    frappe.db.set_value("Flamezo Notification", notification_id, {
        "is_read": 1,
        "is_actioned": 1,
    })
    frappe.db.commit()
    frappe.cache().delete_value(f"notif:count:{phone}")
    return {"success": True}
