# Copyright (c) 2026, Flamezo and contributors
"""
Server-side WhatsApp order delivery to restaurants (official Meta Cloud API).

When a restaurant's `order_channel` == "WhatsApp", every placed order is sent to
the restaurant's WhatsApp number using an APPROVED Meta utility template.

Enqueued, idempotent (Order.is_sent_to_whatsapp) and retried — it never blocks or
fails order creation. Petpooja / UrbanPiper POS push is independent of this.
"""

import frappe
from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message
from flamezo_backend.flamezo.utils.common import safe_log_error

MAX_ATTEMPTS = 3


def _money(v):
    try:
        return f"₹{float(v or 0):,.0f}"
    except Exception:
        return f"₹{v}"


def build_order_params(order_doc):
    """
    Build the 5 summary BODY params for the order template. The full itemised bill
    (coupon, loyalty, cashback, taxes, fees) lives on the receipt page linked by the
    template's URL button (flamezo.in/o/<token>).

    Params (in ascending order, as they appear in the template body):
      {{1}} order number
      {{2}} customer name (+ phone)
      {{3}} fulfilment (Dine-in Table N / Takeaway / Delivery + address)
      {{4}} itemised list (single line) + any cooking notes
      {{5}} Total ₹X · Paid online / Collect at counter

    The URL-button param (the receipt token) is supplied by dispatch_order_whatsapp.
    """
    from flamezo_backend.flamezo.api.orders import format_order

    data = format_order(order_doc)

    order_no = data.get("orderNumber") or getattr(order_doc, "order_number", None) or order_doc.name

    cust = data.get("customer") or {}
    cust_name = cust.get("name") or getattr(order_doc, "customer_name", None) or "Guest"
    cust_phone = cust.get("phone") or getattr(order_doc, "customer_phone", None) or ""
    p2 = f"{cust_name} ({cust_phone})" if cust_phone else cust_name

    order_type = data.get("orderType") or getattr(order_doc, "order_type", None) or "dine_in"
    if order_type == "dine_in":
        table = data.get("tableNumber") or getattr(order_doc, "table_number", None)
        p3 = f"Dine-in · Table {table}" if table else "Dine-in"
    elif order_type == "takeaway":
        p3 = "Takeaway"
    else:
        addr = getattr(order_doc, "delivery_address", None) or ""
        p3 = ("Delivery · " + addr).strip(" ·") if addr else "Delivery"

    # {{4}} — itemised list (single line) + cooking notes
    items = data.get("items") or []
    parts = []
    for it in items:
        name = (it.get("dish") or {}).get("name") or "Item"
        qty = it.get("quantity") or 1
        parts.append(f"{qty}× {name}")
    items_line = ", ".join(parts) if parts else "(items)"

    notes = data.get("cookingRequests") or []
    note_strs = []
    for n in notes:
        if isinstance(n, str):
            note_strs.append(n)
        elif isinstance(n, dict):
            note_strs.append(n.get("request") or n.get("note") or n.get("text") or "")
    note_line = ", ".join([x for x in note_strs if x])
    if note_line:
        items_line = f"{items_line} — Note: {note_line}"
    if len(items_line) > 1000:
        items_line = items_line[:990] + "…"

    # {{5}} — total + payment
    pay_method = getattr(order_doc, "payment_method", "") or ""
    paid = "Paid online" if pay_method == "pay_online" else "Collect at counter"
    p5 = f"Total {_money(data.get('total'))} · {paid}"

    # WhatsApp REJECTS template params containing newlines, tabs or 4+ spaces.
    # Collapse every param to a single clean line.
    def _one_line(s):
        return " ".join(str(s).split())

    return [_one_line(order_no), _one_line(p2), _one_line(p3), _one_line(items_line), _one_line(p5)]


def dispatch_order_whatsapp(order_name, attempt=1):
    """Background job: send a placed order to the restaurant's WhatsApp. Idempotent + retried."""
    try:
        if frappe.db.get_value("Order", order_name, "is_sent_to_whatsapp"):
            return  # already sent — idempotent

        order = frappe.get_doc("Order", order_name)
        restaurant = frappe.get_doc("Restaurant", order.restaurant)

        if getattr(restaurant, "order_channel", None) != "WhatsApp":
            return  # restaurant is not on the WhatsApp channel

        # Recipient: explicit override → the setup-wizard WhatsApp number → owner phone.
        to_phone = (
            getattr(restaurant, "order_whatsapp_number", None)
            or frappe.db.get_value("Restaurant Config", {"restaurant": restaurant.name}, "whatsapp_phone_number")
            or getattr(restaurant, "owner_phone", None)
        )
        if not to_phone:
            frappe.db.set_value("Order", order_name, "whatsapp_send_status",
                                "No restaurant WhatsApp number set", update_modified=False)
            return

        settings = frappe.get_single("Flamezo Settings")
        template = getattr(settings, "order_whatsapp_template_name", None) or "order_notification"
        params = build_order_params(order)
        token = getattr(order, "order_view_token", None)

        ok, info = send_whatsapp_cloud_message(
            to_phone, template, params, settings=settings, button_url_param=token,
        )

        if ok:
            frappe.db.set_value("Order", order_name, {
                "is_sent_to_whatsapp": 1,
                "whatsapp_send_status": f"Sent ({info or 'ok'})",
            }, update_modified=False)
            frappe.logger().info(f"WhatsApp order sent: {order_name} → {to_phone}")
        elif attempt < MAX_ATTEMPTS:
            frappe.db.set_value("Order", order_name, "whatsapp_send_status",
                                f"Retry {attempt}/{MAX_ATTEMPTS}: {str(info)[:80]}", update_modified=False)
            frappe.enqueue(
                "flamezo_backend.flamezo.utils.order_whatsapp.dispatch_order_whatsapp",
                order_name=order_name,
                attempt=attempt + 1,
                queue="short",
                job_id=f"wa_order_{order_name}_attempt_{attempt + 1}",
            )
        else:
            frappe.db.set_value("Order", order_name, "whatsapp_send_status",
                                f"FAILED after {MAX_ATTEMPTS}: {str(info)[:80]}", update_modified=False)
            safe_log_error("WhatsApp Order Send Failed", f"Order {order_name}: {info}")

    except Exception:
        safe_log_error("WhatsApp Order Dispatch Error", frappe.get_traceback())


@frappe.whitelist()
def send_test_order_whatsapp(phone):
    """
    Manual verification tool: send a SAMPLE order notification to `phone` using the
    REAL configured template + send path (Flamezo Settings token/phone-id/template +
    the dynamic "View Full Order" button). Auth-required (not allow_guest) to avoid abuse.

    Returns the Meta result so you can confirm delivery from the dashboard/console.
    """
    from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message

    settings = frappe.get_single("Flamezo Settings")
    template = getattr(settings, "order_whatsapp_template_name", None) or "order_notification"

    sample_params = [
        "FL-TEST",                                   # {{1}} order number
        "Test Customer (9876543210)",                # {{2}} customer
        "Dine-in · Table 5",                         # {{3}} fulfilment
        "2× Butter Croissant, 1× Masala Chai",       # {{4}} items
        "Total ₹630 · Paid online",                  # {{5}} total + payment
    ]
    ok, info = send_whatsapp_cloud_message(
        phone, template, sample_params, settings=settings, button_url_param="testtoken123",
    )
    return {"success": bool(ok), "to": phone, "template": template, "result": info}
