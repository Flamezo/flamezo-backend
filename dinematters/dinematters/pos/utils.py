import frappe
from dinematters.dinematters.pos.base import get_pos_provider
from dinematters.dinematters.utils.common import safe_log_error

def handle_order_update(doc, method):
    """
    Hook for Order DocType on_update.
    Check if order status has changed to a 'pushable' status.
    """
    if not doc.status:
        return

    # Check if the order has already been pushed to the POS
    if doc.get("is_pushed_to_pos"):
        return

    # Check if the status was changed in this update
    db_status = frappe.db.get_value("Order", doc.name, "status")
    
    pushable_statuses = ["Accepted", "confirmed", "Auto Accepted"]
    
    if doc.status in pushable_statuses and db_status != doc.status:
        # Enqueue the push to avoid slowing down the main process
        frappe.enqueue(
            "dinematters.dinematters.pos.utils.push_order_to_pos_job",
            order_name=doc.name,
            now=frappe.flags.in_test
        )

def push_order_to_pos_job(order_name):
    """
    Background job to push order to POS
    """
    try:
        # Check again if already pushed (double-check for race conditions)
        if frappe.db.get_value("Order", order_name, "is_pushed_to_pos"):
            return

        order = frappe.get_doc("Order", order_name)
        restaurant = frappe.get_doc("Restaurant", order.restaurant)
        
        provider = get_pos_provider(restaurant)
        if not provider:
            return

        result = provider.push_order(order)
        
        if result.get("status") == "success":
            pos_id = result.get("pos_order_id")
            # Update order flag and ID using db_set to avoid triggering on_update again
            frappe.db.set_value("Order", order_name, {
                "is_pushed_to_pos": 1,
                "pos_order_id": pos_id,
                "idempotency_key": f"pushed_{frappe.utils.now()}"
            }, update_modified=False)
            
            # Log success
            safe_log_error("POS Push Success", f"Order {order_name} pushed to {restaurant.pos_provider}. POS ID: {pos_id}")
        else:
            # Log failure for retry
            safe_log_error("POS Push Failure", f"Failed to push order {order_name} to {restaurant.pos_provider}: {result.get('message')}")
            
    except Exception as e:
        safe_log_error("POS Push Job Error", frappe.get_traceback())
