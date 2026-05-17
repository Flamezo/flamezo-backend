import frappe
import requests
import json
import hmac
import hashlib
from frappe.utils import flt
from .base import LogisticsProvider

class BorzoProvider(LogisticsProvider):
    def __init__(self, settings=None):
        self.settings = settings or frappe.get_single("Flamezo Settings")
        self.is_production = self.settings.borzo_mode == "Production"
        self.base_url = "https://robot-in.borzodelivery.com/api/business/1.6" if self.is_production else "https://robotapitest-in.borzodelivery.com/api/business/1.6"
        self.api_token = self.settings.get_password("borzo_api_token")
        self.webhook_secret = self.settings.borzo_webhook_token or ""

    def get_headers(self):
        return {
            "X-DV-Auth-Token": self.api_token,
            "Content-Type": "application/json"
        }

    def verify_webhook(self, raw_body, incoming_signature):
        if not self.webhook_secret:
            return True # If no secret, we skip verification but log it in manager
        if not incoming_signature:
            return False
            
        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, incoming_signature)

    def calculate_quote(self, restaurant, order_details):
        if not self.api_token:
            return {"success": False, "error": "Borzo API token is missing"}

        pickup_phone = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant.name}, "whatsapp_phone_number") or restaurant.owner_phone
        
        pickup_point = {
            "address": restaurant.address or f"{restaurant.restaurant_name}, {restaurant.city}",
            "contact_person": {"phone": pickup_phone or "0000000000", "name": restaurant.restaurant_name}
        }
        if restaurant.latitude and restaurant.longitude:
            pickup_point["latitude"] = float(restaurant.latitude)
            pickup_point["longitude"] = float(restaurant.longitude)

        drop_point = {
            "address": order_details.get("address"),
            "contact_person": {"phone": order_details.get("phone") or "0000000000", "name": order_details.get("name") or "Customer"}
        }
        if order_details.get("latitude") and order_details.get("longitude"):
            drop_point["latitude"] = float(order_details.get("latitude"))
            drop_point["longitude"] = float(order_details.get("longitude"))

        item_count = len(order_details.get("items") or [])
        estimated_weight = max(1.0, item_count * 0.5)

        payload = {
            "type": "standard",
            "matter": "Food Delivery Quote",
            "total_weight_kg": estimated_weight,
            "vehicle_type_id": 8, # Motorbike
            "points": [pickup_point, drop_point]
        }

        try:
            response = requests.post(f"{self.base_url}/calculate-order", json=payload, headers=self.get_headers(), timeout=30)
            res_data = response.json()
            if response.status_code == 200 and res_data.get("is_successful"):
                order_res = res_data.get("order", {})
                return {
                    "success": True,
                    "delivery_fee": order_res.get("delivery_fee_amount"),
                    "total_fee": order_res.get("payment_amount"),
                    "currency": order_res.get("currency"),
                    "eta_mins": 45 # Borzo doesn't always provide exact ETA in calculate-order, defaulting to 45
                }
            else:
                errors = res_data.get("errors", ["Calculation failed"])
                return {"success": False, "error": "; ".join(errors) if isinstance(errors, list) else str(errors)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_order(self, restaurant, order):
        if not self.api_token:
            return {"success": False, "error": "Borzo API token is missing"}

        pickup_phone = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant.name}, "whatsapp_phone_number") or restaurant.owner_phone
        
        pickup_point = {
            "address": restaurant.address or f"{restaurant.restaurant_name}, {restaurant.city}",
            "contact_person": {"phone": pickup_phone, "name": restaurant.restaurant_name}
        }
        if restaurant.latitude and restaurant.longitude:
            pickup_point["latitude"] = float(restaurant.latitude)
            pickup_point["longitude"] = float(restaurant.longitude)

        drop_point = {
            "address": order.delivery_address,
            "contact_person": {"phone": order.customer_phone, "name": order.customer_name},
            "commentary": f"Order #{order.order_number or order.name}. {order.delivery_instructions or ''}",
            "apartment_number": order.delivery_house_number or ""
        }
        
        if order.payment_method == "cash":
            drop_point["taking_amount"] = str(order.total)
            drop_point["is_cod_cash_voucher_required"] = True
        
        if order.delivery_latitude and order.delivery_longitude:
            drop_point["latitude"] = float(order.delivery_latitude)
            drop_point["longitude"] = float(order.delivery_longitude)

        item_count = len(order.get("order_items") or [])
        estimated_weight = max(1.0, item_count * 0.5)

        payload = {
            "type": "standard",
            "matter": "Food Delivery",
            "total_weight_kg": estimated_weight,
            "vehicle_type_id": 8,
            "is_client_notification_enabled": True,
            "is_recipient_notification_enabled": True,
            "points": [pickup_point, drop_point],
            "callback_url": frappe.utils.get_url("/api/method/flamezo_backend.flamezo.api.delivery.handle_unified_webhook?provider=borzo")
        }

        try:
            response = requests.post(f"{self.base_url}/create-order", json=payload, headers=self.get_headers(), timeout=30)
            res_data = response.json()
            if response.status_code == 200 and res_data.get("is_successful"):
                order_res = res_data.get("order", {})
                return {
                    "success": True,
                    "delivery_id": str(order_res.get("order_id")),
                    "status": order_res.get("status_description") or order_res.get("status"),
                    "tracking_url": order_res.get("tracking_url"),
                    "delivery_fee": order_res.get("delivery_fee_amount")
                }
            else:
                return {"success": False, "error": str(res_data.get("errors"))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_order(self, delivery_id):
        if not self.api_token: return {"success": False, "error": "Missing API token"}
        try:
            response = requests.post(f"{self.base_url}/cancel-order", json={"order_id": delivery_id}, headers=self.get_headers(), timeout=30)
            res_data = response.json()
            return {"success": res_data.get("is_successful"), "message": str(res_data.get("errors") or "")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def track_order(self, delivery_id):
        if not self.api_token: return {"success": False, "error": "Missing API token"}
        try:
            # Borzo standard lookup
            response = requests.get(f"{self.base_url}/orders?order_id={delivery_id}", headers=self.get_headers(), timeout=30)
            res_data = response.json()
            
            if response.status_code == 200 and res_data.get("is_successful"):
                orders = res_data.get("orders", [])
                if not orders:
                    return {"success": False, "error": "Order not found at provider"}
                
                order_data = orders[0]
                courier = order_data.get("courier", {})
                return {
                    "success": True,
                    "status": order_data.get("status_description") or order_data.get("status"),
                    "rider_name": courier.get("name"),
                    "rider_phone": courier.get("phone"),
                    "tracking_url": order_data.get("tracking_url"),
                    "lat": flt(courier.get("latitude")) if courier.get("latitude") else None,
                    "lng": flt(courier.get("longitude")) if courier.get("longitude") else None
                }
            else:
                return {"success": False, "error": str(res_data.get("errors") or "Tracking failed")}
        except Exception as e:
            return {"success": False, "error": str(e)}
