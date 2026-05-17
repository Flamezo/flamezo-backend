# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
WhatsApp Shadow Ordering API — GOLD Plan Feature

Captures customer intent-to-order data when the customer redirects to WhatsApp.
Creates a shadow Order record for analytics and CRM purposes.

Design decisions:
  - payment_method = "pay_at_counter"  (restaurant handles payment manually)
  - status         = "confirmed"       (immediately visible in analytics dashboard)
  - payment_status = "pending"         (honest — we don't know if WA message was sent)
  - order_type     = "dine_in"         (GOLD is dine-in only)
  - No loyalty, no coupons, no delivery — GOLD feature boundary strictly enforced here.
  - Fire-and-forget design: any failure is swallowed and logged so the WA redirect
    is NEVER blocked by a backend error.
"""

import frappe
from frappe.utils import flt, cint, now_datetime, add_to_date
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import (
    get_or_create_customer,
    normalize_phone,
)
from flamezo_backend.flamezo.api.coin_billing import deduct_coins
import json
import random
import string


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers (re-use the same ID generation logic as orders.py)
# ──────────────────────────────────────────────────────────────────────────────

def _generate_order_id() -> str:
    """Generate a unique order ID in the same format as create_order."""
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f"WA-{suffix}"


def _generate_order_number() -> str:
    """Generate a compact human-readable order number."""
    digits = ''.join(random.choices(string.digits, k=4))
    return f"WA{digits}"


def _parse_table_number(table_number_raw, restaurant_id: str):
    """
    Parse table number from QR format (restaurant-id/table-number) or plain int.
    Returns None if parsing fails — never raises.
    """
    if table_number_raw is None:
        return None
    try:
        raw = str(table_number_raw).strip()
        if '/' in raw:
            parts = raw.split('/')
            if len(parts) == 2 and parts[0] == restaurant_id:
                return cint(parts[1]) or None
            return None
        val = cint(raw)
        return val if val > 0 else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_whatsapp_orders(
    restaurant_id: str,
    search_query=None,
    status=None,
    from_date=None,
    to_date=None,
    page=1,
    page_length=20
):
    """
    POST /api/method/flamezo_backend.flamezo.api.whatsapp_ordering.get_whatsapp_orders
    Optimized fetching of WhatsApp orders with server-side filtering and pagination.
    """
    try:
        # Validate restaurant Access
        validate_restaurant_for_api(restaurant_id)
        
        # Build base filters
        filters = [
            ["restaurant", "=", restaurant_id],
            ["is_whatsapp_order", "=", 1]
        ]
        
        # 1. Search Query Filter
        if search_query:
            query = f"%{search_query}%"
            filters.append([
                "Order", "name", "like", query, "or",
                "Order", "customer_name", "like", query, "or",
                "Order", "customer_phone", "like", query
            ])

        # 2. Status Filter
        if status and status != 'all':
            filters.append(["status", "=", status])
            
        # 3. Date Filters
        if from_date:
            filters.append(["creation", ">=", f"{from_date} 00:00:00"])
        if to_date:
            filters.append(["creation", "<=", f"{to_date} 23:59:59"])
            
        # Get count for pagination
        total_count = frappe.db.count("Order", filters)
        
        # Handle pagination (page to offset)
        limit_start = (cint(page) - 1) * cint(page_length)
        if limit_start < 0:
            limit_start = 0

        # Fetch data
        orders = frappe.get_all(
            "Order",
            fields=[
                "name", "order_number", "status", "total", 
                "creation", "customer_name", "customer_phone", 
                "table_number", "order_type"
            ],
            filters=filters,
            order_by="creation desc",
            start=limit_start,
            page_length=page_length
        )

        # 4. Check unlock status for each order
        # A lead is unlocked if:
        # - It was created in the last 24 hours (FREE)
        # - OR it has an entry in WhatsApp Lead Unlock for this restaurant
        unlocked_phone_list = frappe.get_all(
            "WhatsApp Lead Unlock",
            filters={"restaurant": restaurant_id},
            pluck="customer_phone"
        )
        
        plan_type = frappe.db.get_value("Restaurant", restaurant_id, "plan_type")
        is_gold = plan_type == "GOLD"
        
        # SILVER leads expire after 3 hours; GOLD leads are always unlocked
        silver_cutoff = add_to_date(now_datetime(), hours=-3)
        
        for order in orders:
            is_recent = order.creation > silver_cutoff
            is_purchased = order.customer_phone in unlocked_phone_list
            order["is_unlocked"] = True if (is_gold or is_recent or is_purchased) else False
        
        return {
            "success": True,
            "data": orders,
            "total_count": total_count,
            "has_more": (cint(limit_start) + cint(page_length)) < total_count
        }
        
    except Exception as e:
        frappe.log_error(f"[WhatsApp Order] Fetch Error: {e}", "WhatsApp Ordering")
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=False)
def unlock_whatsapp_lead(restaurant_id: str, customer_phone: str, order_id=None):
    """
    POST /api/method/flamezo_backend.flamezo.api.whatsapp_ordering.unlock_whatsapp_lead
    Unlocks a WhatsApp lead for 1 coin.
    """
    try:
        validate_restaurant_for_api(restaurant_id)
        
        # 1. Check if already unlocked
        if frappe.db.exists("WhatsApp Lead Unlock", {"restaurant": restaurant_id, "customer_phone": customer_phone}):
            return {"success": True, "message": "Lead already unlocked."}
            
        # 2. Check Plan - Gold users get it for free
        plan_type = frappe.db.get_value("Restaurant", restaurant_id, "plan_type")
        if plan_type == "GOLD":
            return {"success": True, "message": "Lead unlocked (GOLD Plan)."}

        # 3. Deduct 1 coin per lead unlock for non-GOLD (SILVER)
        amount_to_deduct = 1

        # 3. Deduct Coins if applicable
        if amount_to_deduct > 0:
            deduct_coins(
                restaurant=restaurant_id,
                amount=amount_to_deduct,
                type="Lead Unlock",
                description=f"Unlocked WhatsApp lead: {customer_phone}",
                ref_doctype="Order" if order_id else None,
                ref_name=order_id
            )
        
        # 4. Record the unlock
        unlock = frappe.get_doc({
            "doctype": "WhatsApp Lead Unlock",
            "restaurant": restaurant_id,
            "customer_phone": customer_phone,
            "order_reference": order_id,
            "was_free": 0
        })
        unlock.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return {"success": True, "message": "Lead successfully unlocked for 1 Coin."}
        
    except frappe.ValidationError as e:
        # These are usually coin insufficiency errors
        return {"success": False, "error": str(e)}
    except Exception as e:
        frappe.log_error(f"[WhatsApp Lead Unlock] Error: {e}", "WhatsApp Ordering")
        return {"success": False, "error": "Internal error occurred during lead unlock."}


@frappe.whitelist(allow_guest=True)
def log_whatsapp_order(
    restaurant_id: str,
    customer_name: str,
    customer_phone: str,
    items: str,           # JSON array: [{dishId, name, qty, unitPrice, customizations?}]
    subtotal=0,
    tax=0,
    discount=0,
    total=0,
    cgst=0,
    sgst=0,
    tax_percent=0,
    table_number=None,
    order_type=None,
    delivery_address=None,
    delivery_landmark=None,
    delivery_city=None,
    delivery_pin_code=None,
    delivery_house_number=None,
    delivery_instructions=None,
    pickup_time=None,
    packaging_fee=0,
    delivery_fee=0,
):
    """
    POST /api/method/flamezo_backend.flamezo.api.whatsapp_ordering.log_whatsapp_order

    Logs a WhatsApp redirect order as a shadow Order record for analytics.
    Designed to be called fire-and-forget from the frontend.

    Args:
        restaurant_id   : Restaurant identifier
        customer_name   : Guest's name (captured in cart form)
        customer_phone  : Guest's phone number (10-digit India)
        items           : JSON array of order items with name, qty, unitPrice [, customizations]
        table_number    : Table number from QR scan (optional, raw or restaurant-id/table format)

    Returns:
        {"success": True, "data": {"order_id": "WA-XXXXXXXX", "order_number": "WA1234"}}
        or {"success": False, "error": {...}} — frontend ignores both responses.
    """
    try:
        # ── 1. Validate restaurant & plan ────────────────────────────────────
        restaurant = validate_restaurant_for_api(restaurant_id)
        plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type")

        if plan_type not in ["SILVER", "GOLD"]:
            return {
                "success": False,
                "error": {
                    "code": "PLAN_NOT_ELIGIBLE",
                    "message": "WhatsApp ordering is available for SILVER and GOLD plans.",
                },
            }

        # ── 2. Validate and normalise inputs ─────────────────────────────────
        customer_name   = (customer_name or "").strip()[:140]   # Frappe Data limit
        customer_phone  = (customer_phone or "").strip()
        normalized_phone = normalize_phone(customer_phone)

        if not customer_name:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": "Customer name is required."},
            }
        if not normalized_phone or len(normalized_phone) != 10:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": "A valid 10-digit phone number is required."},
            }

        # Parse items JSON (frontend sends stringified JSON)
        if isinstance(items, str):
            items = json.loads(items)
        if not items or not isinstance(items, list) or len(items) == 0:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": "Order must contain at least one item."},
            }

        # ── 3. Get/create platform customer ──────────────────────────────────
        platform_customer = None
        try:
            cust = get_or_create_customer(normalized_phone, customer_name)
            platform_customer = cust.name if cust else None
        except Exception as e:
            # Non-fatal — we still create the order; customer can be linked later
            frappe.log_error(f"[WhatsApp Order] Customer creation failed: {e}", "WhatsApp Ordering")

        # ── 4. Build order items (validate and re-price from DB) ─────────────
        order_items = []
        for item in items:
            dish_id  = item.get("dishId") or item.get("dish_id")
            quantity = cint(item.get("qty") or item.get("quantity") or 1)
            customizations = item.get("customizations") or {}

            if not dish_id:
                continue

            # Validate product belongs to this restaurant
            product = frappe.db.get_value(
                "Menu Product",
                {"name": dish_id, "restaurant": restaurant},
                ["name", "price"],
                as_dict=True,
            )
            if not product:
                # Skip invalid products rather than blocking the whole order
                frappe.log_error(
                    f"[WhatsApp Order] Product {dish_id} not found for restaurant {restaurant}",
                    "WhatsApp Ordering",
                )
                continue

            unit_price = flt(product.price)

            # Add customization pricing if provided
            if customizations:
                try:
                    product_doc = frappe.get_doc("Menu Product", dish_id)
                    from flamezo_backend.flamezo.api.orders import load_customization_options
                    load_customization_options(product_doc)
                    for question in (product_doc.customization_questions or []):
                        qid = question.question_id
                        if qid in customizations:
                            selected = customizations[qid]
                            if isinstance(selected, str):
                                selected = [selected]
                            for opt_id in selected:
                                for opt in (question.options or []):
                                    if opt.option_id == opt_id:
                                        unit_price += flt(opt.price) or 0
                                        break
                except Exception:
                    pass  # Use base price if customization pricing fails

            order_items.append({
                "product":      dish_id,
                "quantity":     quantity,
                "customizations": json.dumps(customizations) if customizations else None,
                "unit_price":   unit_price,
                "total_price":  unit_price * quantity,
            })

        if not order_items:
            return {
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": "No valid order items found."},
            }

        # ── 5. Generate unique IDs ────────────────────────────────────────────
        order_id     = _generate_order_id()
        order_number = _generate_order_number()

        # Ensure uniqueness (extremely rare collision, but be safe)
        attempts = 0
        while frappe.db.exists("Order", {"order_id": order_id}) and attempts < 5:
            order_id = _generate_order_id()
            attempts += 1
        attempts = 0
        while frappe.db.exists("Order", {"order_number": order_number}) and attempts < 5:
            order_number = _generate_order_number()
            attempts += 1

        # ── 6. Parse table number ─────────────────────────────────────────────
        parsed_table = _parse_table_number(table_number, restaurant_id)

        # ── 7. Create the Order document ──────────────────────────────────────
        # The Order.before_save() hook will run calculate_cart_totals which
        # re-prices everything server-side — fully authoritative totals.
        restaurant_doc = frappe.get_doc("Restaurant", restaurant)
        estimated_minutes = cint(restaurant_doc.get("estimated_prep_time", 30) or 30)
        estimated_delivery = add_to_date(now_datetime(), minutes=estimated_minutes)

        order_doc = frappe.get_doc({
            "doctype":          "Order",
            "order_id":         order_id,
            "order_number":     order_number,
            "restaurant":       restaurant,
            "customer_name":    customer_name,
            "customer_phone":   normalized_phone,
            "platform_customer": platform_customer,
            # Map order type from frontend, fallback to dine_in
            "order_type":       order_type or "dine_in",
            "table_number":     parsed_table,
            # Delivery details
            "delivery_address": delivery_address,
            "delivery_landmark": delivery_landmark,
            "delivery_city": delivery_city,
            "delivery_pin_code": delivery_pin_code,
            "delivery_house_number": delivery_house_number,
            "delivery_instructions": delivery_instructions,
            "pickup_time": pickup_time,
            "packaging_fee": flt(packaging_fee),
            "delivery_fee": flt(delivery_fee),
            # Shadow order semantics:
            # - pay_at_counter: restaurant collects payment manually via WhatsApp confirmation
            # - status Pending Verification: signals merchant is waiting for WhatsApp msg
            # - payment_status pending: honest representation — we don't know if WA was sent
            "payment_method":   "pay_at_counter",
            "status":           "pending_verification",
            "payment_status":   "pending",
            "is_whatsapp_order": 1,
            "estimated_delivery": estimated_delivery,
            # Pricing fields passed from the frontend (Shadow totals)
            "subtotal":         flt(subtotal),
            "discount":         flt(discount),
            "tax":              flt(tax),
            "cgst":             flt(cgst),
            "sgst":             flt(sgst),
            "tax_percent":      flt(tax_percent),
            "total":            flt(total),
        })

        for item_data in order_items:
            order_doc.append("order_items", item_data)

        order_doc.insert(ignore_permissions=True)
        
        # ── 8. Trigger real-time merchant notification ───────────────────────
        try:
            from flamezo_backend.flamezo.api.realtime import notify_whatsapp_intent
            notify_whatsapp_intent(order_doc)
        except Exception:
            pass # Never block order logging for notification failures

        frappe.db.commit()

        return {
            "success": True,
            "data": {
                "order_id":     order_doc.order_id,
                "order_number": order_doc.order_number,
                "total":        flt(order_doc.total),
            },
        }

    except Exception as e:
        frappe.log_error(f"[WhatsApp Order] Unhandled error: {e}", "WhatsApp Ordering")
        return {
            "success": False,
            "error": {
                "code":    "INTERNAL_ERROR",
                "message": "Failed to log WhatsApp order. The redirect has been completed.",
            },
        }
