# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Consumer-facing Table Booking API — a LEAD HANDOFF, not a reservation.

No table is ever held and no availability/capacity check happens at
creation. Placing a "booking" here just alerts the outlet over WhatsApp
that a customer intends to visit (name, phone, party size, date, preferred
time, notes) — the outlet manages their own floor exactly like a phone
call or walk-in, with zero obligation and zero no-show risk, since nothing
was ever promised to the customer as confirmed. See dispatch_table_booking
_whatsapp() in utils/table_booking_whatsapp.py for the actual alert.

The `status` field (pending/confirmed/rejected/...) still exists for the
outlet's own record-keeping in their dashboard (Bookings.tsx) — it is
deliberately never surfaced to the customer as a promise ("confirmed"
there means "the outlet marked this as noted," not "your table is held").

Endpoints:
  - create_table_booking   — let an outlet know you're coming
  - get_my_table_bookings  — list all bookings by this phone (paginated)
  - cancel_table_booking   — let the outlet know your plans changed
  - get_table_booking_detail — single booking detail
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, today, getdate

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_phone(phone):
    if not phone:
        frappe.throw(_("phone is required"), frappe.AuthenticationError)
    return phone.strip()


def _require_session(phone):
    """Every endpoint here touches personal booking data — a client-supplied
    phone alone is not identity. Without this, anyone who knows/guesses a
    phone number could create bookings as that person, or read/cancel their
    real ones (same class of bug found and fixed in crowd.py/clubs.py)."""
    if not has_active_customer_session(phone):
        frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
    return phone


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
        "outlet_id": b.restaurant_id or "",
        "outlet_name": b.restaurant_name or "",
        "outlet_city": b.city or "",
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
def create_table_booking(phone, outlet_id, date, time_slot, number_of_diners,
                         customer_name=None, notes=None):
    """
    POST .../table_booking_consumer.create_table_booking

    Lets an outlet know a customer intends to visit — NOT a reservation, no
    table is held. The outlet gets an instant WhatsApp alert; the customer
    gets told "the outlet's been notified," never "confirmed."

    - phone: customer phone (required, must have an active verified session)
    - outlet_id: outlet name/ID (required)
    - date: intended visit date YYYY-MM-DD (required)
    - time_slot: free-text preferred time, e.g. "Tonight, around 8" (required)
    - number_of_diners: integer (required)
    - customer_name: display name (optional, defaults to phone)
    - notes: anything else the outlet should know (optional)
    """
    phone = _require_phone(phone)
    _require_session(phone)

    if not outlet_id:
        frappe.throw(_("outlet_id is required"))
    if not date:
        frappe.throw(_("date is required"))
    if not time_slot:
        frappe.throw(_("time_slot is required"))
    if not number_of_diners or int(number_of_diners) < 1:
        frappe.throw(_("number_of_diners must be at least 1"))

    # Validate outlet exists and accepts bookings
    outlet = frappe.db.get_value(
        "Outlet",
        outlet_id,
        ["name", "restaurant_name", "city", "is_active"],
        as_dict=True,
    )
    if not outlet:
        frappe.throw(_("Outlet not found"), frappe.DoesNotExistError)
    if not outlet.is_active:
        frappe.throw(_("Outlet is not accepting bookings"))

    # Reject past dates
    try:
        booking_date = getdate(date)
    except Exception:
        frappe.throw(_("Invalid date format. Use YYYY-MM-DD"))

    if booking_date < getdate(today()):
        frappe.throw(_("Booking date cannot be in the past"))

    doc = frappe.get_doc({
        "doctype": "Table Booking",
        "restaurant": outlet_id,
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

    # Best-effort, enqueued — the WhatsApp alert to the outlet must never
    # block or fail the customer's request, same convention as order alerts
    # (order_whatsapp.py::dispatch_order_whatsapp).
    frappe.enqueue(
        "flamezo_backend.flamezo.utils.table_booking_whatsapp.dispatch_table_booking_whatsapp",
        queue="short",
        booking_name=doc.name,
    )
    # Same for the customer-facing confirmation — the in-app screen already
    # tells them "they've been notified", this is a best-effort extra nudge.
    frappe.enqueue(
        "flamezo_backend.flamezo.utils.table_booking_whatsapp.dispatch_table_booking_customer_confirmation",
        queue="short",
        booking_name=doc.name,
    )

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
    _require_session(phone)
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
        LEFT JOIN `tabOutlet` r ON r.name = tb.restaurant
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
    _require_session(phone)
    if not booking_id:
        frappe.throw(_("booking_id is required"))

    rows = frappe.db.sql(
        """
        SELECT tb.name, tb.booking_number, tb.restaurant, tb.date, tb.time_slot,
               tb.number_of_diners, tb.status, tb.notes, tb.customer_name, tb.customer_phone,
               tb.confirmed_at, tb.rejected_at, tb.rejection_reason, tb.cancelled_at, tb.creation,
               r.restaurant_id, r.restaurant_name, r.city
        FROM `tabTable Booking` tb
        LEFT JOIN `tabOutlet` r ON r.name = tb.restaurant
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

    Lets the outlet know a customer's plans changed. Since nothing was ever
    held, this is a courtesy notice, not the release of a resource — still
    worth telling the outlet so they don't wonder if the customer's coming.
    Only the booking's owner phone can cancel.
    """
    phone = _require_phone(phone)
    _require_session(phone)
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
