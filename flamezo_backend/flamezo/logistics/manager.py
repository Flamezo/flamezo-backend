import frappe
from frappe.utils import flt, cint

class LogisticsManager:
    def __init__(self, outlet_name):
        self.restaurant = frappe.get_doc("Restaurant", outlet_name)
        self.settings = frappe.get_single("Flamezo Settings")
        self.provider = None

    @property
    def is_self_delivery(self):
        return True

    def get_quote(self, order_details):
        """Gets a quote for self-managed delivery."""
        return {
            "success": True,
            "courier_fee": 0,
            "markup": 0,
            "platform_fee": 0,
            "delivery_fee": 0,
            "eta_mins": 30,
            "provider": "Self"
        }

    def book_delivery(self, order):
        """
        Books a self-managed delivery. No coins are deducted.
        """
        delivery_charge = flt(order.delivery_fee or 0)
        return {
            "success": True,
            "delivery_id": f"SELF-{order.name}",
            "status": "ACCEPTED",
            "tracking_url": None,
            "delivery_fee": delivery_charge,
            "logistics_platform_fee": 0,
            "provider": "Self",
            "note": "Self delivery — managed by outlet's own rider."
        }

    def cancel_delivery(self, delivery_id):
        return {"success": True, "message": "Self delivery cancelled."}

    def track_delivery(self, delivery_id):
        return {"success": True, "status": "Self-Managed", "message": "Self delivery is managed locally."}

    def verify_webhook(self, provider_name, data, signature):
        return False
