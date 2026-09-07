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

VALID_NOTIFICATION_TYPES = {
    "order", "booking", "promotion", "loyalty", "crowd", "club", "chat", "general",
}


def _parse_types(types):
    """Comma-separated type filter -> validated list. Unknown names are dropped
    so a bad param can never widen the filter into an unfiltered query."""
    if not types:
        return []
    if isinstance(types, str):
        raw = types.split(",")
    else:
        raw = list(types)
    return [t for t in (str(x).strip().lower() for x in raw) if t in VALID_NOTIFICATION_TYPES]


def _clear_count_cache(phone):
    """Unread counts are cached per type-set, so drop every variant."""
    frappe.cache().delete_value(f"notif:count:{phone}")
    frappe.cache().delete_value(f"notif:count:{phone}:all")
    for t in VALID_NOTIFICATION_TYPES:
        frappe.cache().delete_value(f"notif:count:{phone}:{t}")
    frappe.cache().delete_value(f"notif:count:{phone}:crowd,club")


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
        _clear_count_cache(customer_phone)

        # Best-effort push — a delivery failure must never affect the
        # notification row itself (already durably created above).
        try:
            from flamezo_backend.flamezo.api.push_notifications import push_to_customer
            push_to_customer(
                customer_phone, title, body or "",
                data={
                    "notification_id": doc.name,
                    "type": notification_type,
                    "deep_link": deep_link or "",
                },
            )
        except Exception:
            pass

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
def get_my_notifications(phone, page=1, limit=30, unread_only=False, types=None):
    """
    GET .../notifications_consumer.get_my_notifications

    Returns paginated notifications for a phone, newest first.
    unread_only=True filters to unread only.
    types: optional comma-separated notification_type filter (e.g. "crowd,club")
    so a section-specific inbox (the Crowd/Clubs bell) shows only its own
    notifications instead of the whole account feed.
    """
    phone = _require_phone(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    filters = {"customer_phone": phone}
    if str(unread_only).lower() in ("1", "true"):
        filters["is_read"] = 0
    type_list = _parse_types(types)
    if type_list:
        filters["notification_type"] = ["in", type_list]

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
def get_notification_count(phone, types=None):
    """
    GET .../notifications_consumer.get_notification_count

    Returns unread notification count for badge display.
    Cached for 60s per phone.
    """
    phone = _require_phone(phone)
    type_list = _parse_types(types)
    # Cache per type-set — a filtered badge must not serve the account-wide count.
    suffix = ",".join(type_list) if type_list else "all"
    cache_key = f"notif:count:{phone}:{suffix}"
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return {"success": True, "data": {"unread_count": cached}}

    filters = {"customer_phone": phone, "is_read": 0}
    if type_list:
        filters["notification_type"] = ["in", type_list]
    count = frappe.db.count("Flamezo Notification", filters)
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
    _clear_count_cache(phone)
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
    _clear_count_cache(phone)
    return {"success": True}


@frappe.whitelist(allow_guest=True)
def seed_mock_notifications(phone, count=8):
    """
    POST .../notifications_consumer.seed_mock_notifications

    DEV/QA ONLY — inserts a spread of sample Crowd & Clubs notifications so the
    inbox, unread badge and scroll pagination can be exercised without waiting
    for real joins/likes/comments.

    Refuses to run when developer_mode is off, so it can never be called
    against a production site.
    """
    if not frappe.conf.get("developer_mode"):
        frappe.throw(_("seed_mock_notifications is only available in developer mode"))

    phone = _require_phone(phone)
    count = max(1, min(int(count), 50))

    samples = [
        ("crowd", "New join request", "Aarav asked to join \"Sunday Brunch Crew\".", "/crowd/mock-1"),
        ("crowd", "You're in!", "Your request to join \"Friday Football\" was approved.", "/crowd/mock-2"),
        ("crowd", "Request declined", "Your request to join \"Poker Night\" was declined.", "/crowd/mock-3"),
        ("crowd", "Crowd cancelled", "\"Beach Cleanup\" was cancelled by the organiser.", "/crowd/mock-4"),
        ("club", "New post in Coffee Lovers", "We just dropped a new single-origin pour-over...", "/club/mock-1"),
        ("club", "New like", "Neha and 4 others liked your post", "/club/mock-2"),
        ("club", "New follower", "Rahul started following Coffee Lovers.", "/club/mock-1"),
        ("club", "New comment", "Priya commented: \"Adding this to my list!\"", "/club/mock-2"),
    ]

    created = []
    for i in range(count):
        ntype, title, body, link = samples[i % len(samples)]
        # create_notification returns the new row's name (a str), or None.
        name = create_notification(
            customer_phone=phone,
            title=title,
            body=body,
            notification_type=ntype,
            deep_link=link,
        )
        if name:
            created.append(name)

    return {"success": True, "data": {"created": len(created), "ids": created}}
