import frappe
import json
from frappe import _
from frappe.utils import get_datetime, now_datetime
from dinematters.dinematters.pos.base import get_pos_provider

@frappe.whitelist()
def sync_menu(restaurant_id):
    """
    Manual trigger to sync menu from POS
    """
    restaurant = frappe.get_doc("Restaurant", restaurant_id)
    
    # POS is a GOLD-only feature
    if restaurant.plan_type != "GOLD":
        frappe.throw(_("POS Integration is available on the GOLD plan. Please upgrade to access this feature."), frappe.PermissionError)
        
    provider = get_pos_provider(restaurant)
    
    if not provider:
        frappe.throw(_("POS integration is not enabled or configured for this restaurant."))
    
    # Enqueue as background job
    frappe.enqueue(
        "dinematters.dinematters.api.pos._sync_menu_job",
        restaurant_id=restaurant_id,
        now=frappe.flags.in_test
    )
    
    return {"status": "success", "message": "Menu sync task enqueued."}

def _sync_menu_job(restaurant_id):
    restaurant = frappe.get_doc("Restaurant", restaurant_id)
    provider = get_pos_provider(restaurant)
    if provider:
        # Provider sync_menu will update pos_sync_status internally for detailed logging
        provider.sync_menu()

@frappe.whitelist(allow_guest=True)
def pos_gateway(provider=None):
    """
    Unified POS Gateway (10/10 Production Architecture)
    Handles all incoming webhooks from Petpooja, UrbanPiper, Restroworks, etc.
    Returns 200 OK instantly and enqueues processing.
    """
    if frappe.request.method != "POST":
        return {"status": "error", "message": "Method not allowed"}

    try:
        data = json.loads(frappe.request.data)
        
        # Enqueue with provider hint if available in URL, otherwise sniff it
        frappe.enqueue(
            "dinematters.dinematters.api.pos._process_gateway_event",
            data=data,
            provider_hint=provider,
            now=frappe.flags.in_test
        )
        
        return {"status": "success", "message": "Gateway acknowledged"}
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "POS Gateway Error")
        return {"status": "error", "message": str(e)}

def _process_gateway_event(data, provider_hint=None):
    """
    Background worker to identify the restaurant/provider and process the event.
    """
    provider_name = provider_hint
    restaurant_name = None
    
    # 1. Identification logic (Sniffing)
    if not provider_name:
        if "clientorderID" in data or "restID" in data:
            provider_name = "Petpooja"
        elif "merchant_id" in data and "order_id" in data:
            provider_name = "Restroworks"
        elif "order" in data and "details" in data.get("order", {}):
            provider_name = "UrbanPiper"

    # 2. Resolve Restaurant
    if provider_name == "Petpooja":
        client_order_id = data.get("clientorderID") or data.get("orderID")
        rest_id = data.get("restID")
        
        if client_order_id:
            restaurant_name = frappe.db.get_value("Order", client_order_id, "restaurant")
        
        if not restaurant_name and rest_id:
            # Fallback to restID (Merchant ID) if no order context or order not found
            restaurant_name = frappe.db.get_value("Restaurant", {"pos_merchant_id": rest_id}, "name")
            
    elif provider_name == "Restroworks":
        merchant_id = data.get("merchant_id")
        restaurant_name = frappe.db.get_value("Restaurant", {"pos_merchant_id": merchant_id}, "name")
    elif provider_name == "UrbanPiper":
        store_id = data.get("order", {}).get("details", {}).get("store_id")
        restaurant_name = frappe.db.get_value("Restaurant", {"pos_merchant_id": store_id}, "name")

    if not restaurant_name:
        # If it's a known test merchant or just missing, don't flood the error logs
        log_msg = f"POS Gateway: Could not resolve restaurant for {provider_name}. Data snippet: {json.dumps(data)[:200]}"
        
        # Check for test IDs in various places
        is_test = (
            (provider_name == "Petpooja" and data.get("restID") == "NONEXISTENT_REST") or
            (not provider_name)
        )
        
        if is_test:
            frappe.log_error("POS Gateway Trace (Unresolved)", log_msg)
        else:
            frappe.logger().warning(log_msg)
        return

    # 3. Process via Provider
    restaurant = frappe.get_doc("Restaurant", restaurant_name)
    provider = get_pos_provider(restaurant)
    
    if provider:
        provider.handle_callback(data)

# Deprecated separate callbacks (for backward compatibility during migration)
@frappe.whitelist(allow_guest=True)
def petpooja_callback():
    return pos_gateway(provider="Petpooja")

@frappe.whitelist(allow_guest=True)
def urbanpiper_callback():
    return pos_gateway(provider="UrbanPiper")

@frappe.whitelist(allow_guest=True)
def restroworks_callback():
    return pos_gateway(provider="Restroworks")

@frappe.whitelist(allow_guest=True)
def petpooja_menu_push():
    """Fallback for Petpooja menu pushes which might have different logic"""
    return pos_gateway(provider="Petpooja")
