# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Consumer-facing Dining Table Booking API.

Endpoints:
  - create_table_booking   — book a table at a restaurant
  - get_my_table_bookings  — list all bookings by this phone (paginated)
  - cancel_table_booking   — cancel a pending/confirmed booking
  - get_table_booking_detail — single booking detail
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, today, getdate


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


def _fmt_time(t):
    if t is None:
        return ""
    parts = str(t).split(":")
    if len(parts) >= 2:
        return f"{parts[0].zfill(2)}:{parts[1][:2]}"
    return str(t)[:5]


def _format_booking(b):
    return {
        "id": b.name,
        "booking_number": b.booking_number or b.name,
        "restaurant_id": b.restaurant_id or "",
        "restaurant_name": b.restaurant_name or "",
        "restaurant_city": b.city or "",
        "date": str(b.date) if b.date else "",
        "time_slot": b.time_slot or "",
        "number_of_diners": b.number_of_diners or 0,
        "status": b.status,
        "notes": b.notes or "",
        "customer_name": b.customer_name or "",
        "customer_phone": b.customer_phone or "",
        "confirmed_at": str(b.confirmed_at) if b.confirmed_at else "",
        "rejected_at": str(b.rejected_at) if b.rejected_at else "",
        "rejection_reason": b.rejection_reason or "",
        "cancelled_at": str(b.cancelled_at) if b.cancelled_at else "",
        "created_at": str(b.creation) if b.creation else "",
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def create_table_booking(phone, restaurant_id, date, time_slot, number_of_diners,
                         customer_name=None, notes=None):
    """
    POST .../table_booking_consumer.create_table_booking

    Books a dining table at a restaurant.
    - phone: customer phone (required)
    - restaurant_id: restaurant name/ID (required)
    - date: booking date YYYY-MM-DD (required)
    - time_slot: e.g. "19:00 – 21:00" (required)
    - number_of_diners: integer (required)
    - customer_name: display name (optional, defaults to phone)
    - notes: special requests (optional)
    """
    phone = _require_phone(phone)

    if not restaurant_id:
        frappe.throw(_("restaurant_id is required"))
    if not date:
        frappe.throw(_("date is required"))
    if not time_slot:
        frappe.throw(_("time_slot is required"))
    if not number_of_diners or int(number_of_diners) < 1:
        frappe.throw(_("number_of_diners must be at least 1"))

    # Validate restaurant exists and accepts bookings
    restaurant = frappe.db.get_value(
        "Restaurant",
        restaurant_id,
        ["name", "restaurant_name", "city", "is_active"],
        as_dict=True,
    )
    if not restaurant:
        frappe.throw(_("Restaurant not found"), frappe.DoesNotExistError)
    if not restaurant.is_active:
        frappe.throw(_("Restaurant is not accepting bookings"))

    # Reject past dates
    try:
        booking_date = getdate(date)
    except Exception:
        frappe.throw(_("Invalid date format. Use YYYY-MM-DD"))

    if booking_date < getdate(today()):
        frappe.throw(_("Booking date cannot be in the past"))

    doc = frappe.get_doc({
        "doctype": "Table Booking",
        "restaurant": restaurant_id,
        "customer_phone": phone,
        "customer_name": customer_name or phone,
        "date": date,
        "time_slot": time_slot,
        "number_of_diners": int(number_of_diners),
        "notes": notes or "",
        "status": "pending",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "data": {
            "booking_id": doc.name,
            "booking_number": doc.booking_number or doc.name,
            "status": doc.status,
        }
    }


@frappe.whitelist(allow_guest=True)
def get_my_table_bookings(phone, page=1, limit=20, status=None):
    """
    GET .../table_booking_consumer.get_my_table_bookings

    Returns paginated list of table bookings for a phone.
    Optionally filter by status (Pending, Confirmed, Completed, Cancelled, Rejected).
    """
    phone = _require_phone(phone)
    page = max(1, int(page))
    limit = min(int(limit), 50)
    offset = (page - 1) * limit

    conditions = ["tb.customer_phone = %s"]
    params = [phone]

    if status:
        if isinstance(status, list):
            placeholders = ",".join(["%s"] * len(status))
            conditions.append(f"tb.status IN ({placeholders})")
            params += status
        else:
            conditions.append("tb.status = %s")
            params.append(status)

    where = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT tb.name, tb.booking_number, tb.restaurant, tb.date, tb.time_slot,
               tb.number_of_diners, tb.status, tb.notes, tb.customer_name, tb.customer_phone,
               tb.confirmed_at, tb.rejected_at, tb.rejection_reason, tb.cancelled_at, tb.creation,
               r.restaurant_id, r.restaurant_name, r.city
        FROM `tabTable Booking` tb
        LEFT JOIN `tabRestaurant` r ON r.name = tb.restaurant
        WHERE {where}
        ORDER BY tb.creation DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit + 1, offset],
        as_dict=True,
    )

    has_more = len(rows) > limit
    bookings = rows[:limit]

    return {
        "success": True,
        "data": {
            "bookings": [_format_booking(b) for b in bookings],
            "page": page,
            "has_more": has_more,
        }
    }


@frappe.whitelist(allow_guest=True)
def get_table_booking_detail(booking_id, phone):
    """
    GET .../table_booking_consumer.get_table_booking_detail

    Returns full detail for a single table booking.
    Phone must match booking's customer_phone.
    """
    phone = _require_phone(phone)
    if not booking_id:
        frappe.throw(_("booking_id is required"))

    rows = frappe.db.sql(
        """
        SELECT tb.name, tb.booking_number, tb.restaurant, tb.date, tb.time_slot,
               tb.number_of_diners, tb.status, tb.notes, tb.customer_name, tb.customer_phone,
               tb.confirmed_at, tb.rejected_at, tb.rejection_reason, tb.cancelled_at, tb.creation,
               r.restaurant_id, r.restaurant_name, r.city
        FROM `tabTable Booking` tb
        LEFT JOIN `tabRestaurant` r ON r.name = tb.restaurant
        WHERE tb.name = %s
        """,
        booking_id,
        as_dict=True,
    )
    if not rows:
        frappe.throw(_("Booking not found"), frappe.DoesNotExistError)

    booking = rows[0]
    if booking.customer_phone != phone:
        frappe.throw(_("Access denied"), frappe.PermissionError)

    return {"success": True, "data": {"booking": _format_booking(booking)}}


@frappe.whitelist(allow_guest=True)
def cancel_table_booking(booking_id, phone):
    """
    POST .../table_booking_consumer.cancel_table_booking

    Cancels a Pending or Confirmed booking.
    Only the booking's owner phone can cancel.
    """
    phone = _require_phone(phone)
    if not booking_id:
        frappe.throw(_("booking_id is required"))

    booking = frappe.db.get_value(
        "Table Booking",
        booking_id,
        ["name", "status", "customer_phone"],
        as_dict=True,
    )
    if not booking:
        frappe.throw(_("Booking not found"), frappe.DoesNotExistError)
    if booking.customer_phone != phone:
        frappe.throw(_("Access denied"), frappe.PermissionError)

    cancellable = {"pending", "confirmed"}
    if booking.status not in cancellable:
        frappe.throw(
            _("Cannot cancel a booking with status: {0}").format(booking.status),
            frappe.ValidationError,
        )

    frappe.db.set_value("Table Booking", booking_id, {
        "status": "cancelled",
        "cancelled_at": now_datetime(),
    })
    frappe.db.commit()

    return {"success": True, "data": {"status": "Cancelled"}}
