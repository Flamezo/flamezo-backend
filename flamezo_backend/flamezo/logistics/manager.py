import frappe
from frappe.utils import flt, cint

class LogisticsManager:
    def __init__(self, restaurant_name):
        self.restaurant = frappe.get_doc("Restaurant", restaurant_name)
        self.settings = frappe.get_single("Flamezo Settings")
        self.provider = None

    @property
    def is_self_delivery(self):
        return True

    def get_quote(self, order_details):
        """
        Gets a quote for self-managed delivery calculated by distance.
        Formula: default_delivery_fee (base) + (distance * delivery_charge_per_km)
        """
        lat = order_details.get("latitude")
        lng = order_details.get("longitude")
        
        road_distance = 0.0
        if lat is not None and lng is not None and self.restaurant.latitude is not None and self.restaurant.longitude is not None:
            from flamezo_backend.flamezo.utils.geoutils import calculate_distance, get_osrm_road_distance, estimate_road_distance
            try:
                road_distance = get_osrm_road_distance(self.restaurant.latitude, self.restaurant.longitude, lat, lng)
                if road_distance is None:
                    straight_dist = calculate_distance(self.restaurant.latitude, self.restaurant.longitude, lat, lng)
                    road_distance = round(estimate_road_distance(straight_dist), 2)
            except Exception:
                road_distance = 0.0

        base_fee = flt(self.restaurant.default_delivery_fee or 0)
        charge_per_km = flt(self.restaurant.delivery_charge_per_km or 0)
        delivery_fee = base_fee + flt(road_distance * charge_per_km)

        return {
            "success": True,
            "courier_fee": 0,
            "markup": delivery_fee, 
            "platform_fee": 0,          
            "delivery_fee": delivery_fee, 
            "eta_mins": self.restaurant.estimated_prep_time or 30,
            "provider": "Self"
        }

    def book_delivery(self, order):
        """
        Books a self-managed delivery. No coins are deducted.
        """
        delivery_charge = flt(order.delivery_fee or self.restaurant.default_delivery_fee or 0)
        return {
            "success": True,
            "delivery_id": f"SELF-{order.name}",
            "status": "ACCEPTED",
            "tracking_url": None,
            "delivery_fee": delivery_charge,
            "logistics_platform_fee": 0,
            "provider": "Self",
            "note": "Self delivery — managed by restaurant's own rider."
        }

    def cancel_delivery(self, delivery_id):
        return {"success": True, "message": "Self delivery cancelled."}

    def track_delivery(self, delivery_id):
        return {"success": True, "status": "Self-Managed", "message": "Self delivery is managed locally."}

    def verify_webhook(self, provider_name, data, signature):
        return False
