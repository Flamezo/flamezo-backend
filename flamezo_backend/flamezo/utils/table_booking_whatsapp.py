# Copyright (c) 2026, Flamezo and contributors
"""
Server-side WhatsApp lead alert to outlets when a customer requests a table
(official Meta Cloud API) — mirrors order_whatsapp.py's dispatch pattern.

This is NOT a reservation confirmation. No table is held, no availability
was checked, nothing is promised to the customer. This message is purely
"a customer wants to visit you" — the outlet handles it like any other
walk-in or phone-in request, at their own discretion.

Enqueued, idempotent (Table Booking.is_sent_to_whatsapp) and retried — it
never blocks or fails booking creation.
"""

import frappe
from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message
from flamezo_backend.flamezo.utils.common import safe_log_error

MAX_ATTEMPTS = 3


def build_table_booking_params(booking_doc, outlet_name):
    """
    4 BODY params for the table-booking lead template:
      {{1}} customer name (+ phone)
      {{2}} party size
      {{3}} date
      {{4}} preferred time + any notes

    WhatsApp rejects params with newlines/tabs/4+ spaces — collapse each to
    a single clean line, same rule as build_order_params.
    """
    def _one_line(s):
        return " ".join(str(s).split())

    cust_name = booking_doc.customer_name or "Guest"
    cust_phone = booking_doc.customer_phone or ""
    p1 = f"{cust_name} ({cust_phone})" if cust_phone else cust_name

    p2 = f"{booking_doc.number_of_diners or 1} guests"
    p3 = str(booking_doc.date) if booking_doc.date else ""

    p4 = booking_doc.time_slot or ""
    if booking_doc.notes:
        p4 = f"{p4} — Note: {booking_doc.notes}" if p4 else f"Note: {booking_doc.notes}"
    if len(p4) > 300:
        p4 = p4[:290] + "…"

    return [_one_line(p1), _one_line(p2), _one_line(p3), _one_line(p4)]


def dispatch_table_booking_whatsapp(booking_name, attempt=1):
    """Background job: alert the outlet a customer wants to visit. Idempotent + retried."""
    try:
        if frappe.db.get_value("Table Booking", booking_name, "is_sent_to_whatsapp"):
            return  # already sent — idempotent

        booking = frappe.get_doc("Table Booking", booking_name)
        restaurant = frappe.get_doc("Restaurant", booking.restaurant)

        # Recipient: explicit override → the setup-wizard WhatsApp number → owner phone.
        # Same fallback chain as order_whatsapp.py — outlets already have this configured.
        to_phone = (
            getattr(restaurant, "order_whatsapp_number", None)
            or frappe.db.get_value("Restaurant Config", {"restaurant": restaurant.name}, "whatsapp_phone_number")
            or getattr(restaurant, "owner_phone", None)
        )
        if not to_phone:
            frappe.db.set_value("Table Booking", booking_name, "whatsapp_send_status",
                                "No outlet WhatsApp number set", update_modified=False)
            return

        settings = frappe.get_single("Flamezo Settings")
        template = getattr(settings, "table_booking_whatsapp_template_name", None)
        if not template:
            frappe.db.set_value("Table Booking", booking_name, "whatsapp_send_status",
                                "No template configured (Flamezo Settings)", update_modified=False)
            return

        params = build_table_booking_params(booking, restaurant.restaurant_name)

        ok, info = send_whatsapp_cloud_message(
            to_phone, template, params, settings=settings,
        )

        if ok:
            frappe.db.set_value("Table Booking", booking_name, {
                "is_sent_to_whatsapp": 1,
                "whatsapp_send_status": f"Sent ({info or 'ok'})",
            }, update_modified=False)
            frappe.logger().info(f"WhatsApp table-booking lead sent: {booking_name} → {to_phone}")
        elif attempt < MAX_ATTEMPTS:
            frappe.db.set_value("Table Booking", booking_name, "whatsapp_send_status",
                                f"Retry {attempt}/{MAX_ATTEMPTS}: {str(info)[:80]}", update_modified=False)
            frappe.enqueue(
                "flamezo_backend.flamezo.utils.table_booking_whatsapp.dispatch_table_booking_whatsapp",
                booking_name=booking_name,
                attempt=attempt + 1,
                queue="short",
                job_id=f"wa_table_booking_{booking_name}_attempt_{attempt + 1}",
            )
        else:
            frappe.db.set_value("Table Booking", booking_name, "whatsapp_send_status",
                                f"FAILED after {MAX_ATTEMPTS}: {str(info)[:80]}", update_modified=False)
            safe_log_error("WhatsApp Table Booking Lead Send Failed", f"Booking {booking_name}: {info}")

    except Exception:
        safe_log_error("WhatsApp Table Booking Lead Dispatch Error", frappe.get_traceback())


@frappe.whitelist()
def send_test_table_booking_whatsapp(phone):
    """
    Manual verification tool: send a SAMPLE table-booking lead alert to `phone`
    using the REAL configured template + send path. Auth-required (not
    allow_guest) to avoid abuse. Returns the Meta result so you can confirm
    delivery/template approval from the console.
    """
    settings = frappe.get_single("Flamezo Settings")
    template = getattr(settings, "table_booking_whatsapp_template_name", None)
    if not template:
        return {"success": False, "error": "table_booking_whatsapp_template_name not set in Flamezo Settings"}

    sample_params = [
        "Test Customer (9876543210)",   # {{1}} customer
        "4 guests",                     # {{2}} party size
        "2026-08-15",                   # {{3}} date
        "Tonight, around 8 — Note: window seat if possible",  # {{4}} time + notes
    ]
    ok, info = send_whatsapp_cloud_message(
        phone, template, sample_params, settings=settings,
    )
    return {"success": bool(ok), "to": phone, "template": template, "result": info}
