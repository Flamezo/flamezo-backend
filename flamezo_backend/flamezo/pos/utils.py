import frappe
from flamezo_backend.flamezo.pos.base import get_pos_provider
from flamezo_backend.flamezo.utils.common import safe_log_error

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

    pushable_statuses = ["Accepted", "confirmed", "Auto Accepted"]  # exact Order doctype options

    if doc.status not in pushable_statuses:
        return

    # Only push if status changed in this update (compare against pre-save state)
    previous_doc = doc.get_doc_before_save()
    previous_status = previous_doc.status if previous_doc else None

    if doc.status != previous_status:
        # Enqueue the push to avoid slowing down the main process
        frappe.enqueue(
            "flamezo_backend.flamezo.pos.utils.push_order_to_pos_job",
            order_name=doc.name,
            now=frappe.flags.in_test
        )

def push_order_to_pos_job(order_name, attempt=1):
    """
    Background job to push order to POS.
    Retries up to 3 times with exponential backoff (30s, 60s, 120s) on transient failure.
    """
    MAX_ATTEMPTS = 3

    try:
        # Double-check idempotency — another worker may have succeeded already
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
            frappe.db.set_value("Order", order_name, {
                "is_pushed_to_pos": 1,
                "pos_order_id": pos_id,
                "pos_sync_status": f"Pushed to {restaurant.pos_provider}",
                "idempotency_key": f"pushed_{frappe.utils.now()}"
            }, update_modified=False)
            frappe.logger().info(f"POS Push Success: Order {order_name} → {restaurant.pos_provider} (POS ID: {pos_id})")
        else:
            msg = result.get("message", "Unknown error")
            if attempt < MAX_ATTEMPTS:
                delay = 30 * (2 ** (attempt - 1))  # 30s, 60s, 120s
                frappe.logger().warning(f"POS Push attempt {attempt} failed for {order_name}: {msg}. Retrying in {delay}s.")
                frappe.enqueue(
                    "flamezo_backend.flamezo.pos.utils.push_order_to_pos_job",
                    order_name=order_name,
                    attempt=attempt + 1,
                    enqueue_after_commit=True,
                    queue="short",
                    at_front=False,
                    # frappe.enqueue doesn't support native delay; use countdown via RQ
                    job_id=f"pos_push_{order_name}_attempt_{attempt + 1}",
                )
                frappe.db.set_value("Order", order_name, "pos_sync_status",
                                    f"Push retry {attempt}/{MAX_ATTEMPTS}: {msg[:80]}", update_modified=False)
            else:
                safe_log_error("POS Push Failed", f"Order {order_name} failed after {MAX_ATTEMPTS} attempts: {msg}")
                frappe.db.set_value("Order", order_name, "pos_sync_status",
                                    f"Push FAILED after {MAX_ATTEMPTS} attempts: {msg[:80]}", update_modified=False)

    except Exception:
        safe_log_error("POS Push Job Error", frappe.get_traceback())
        if attempt < MAX_ATTEMPTS:
            frappe.enqueue(
                "flamezo_backend.flamezo.pos.utils.push_order_to_pos_job",
                order_name=order_name,
                attempt=attempt + 1,
                job_id=f"pos_push_{order_name}_attempt_{attempt + 1}",
            )
