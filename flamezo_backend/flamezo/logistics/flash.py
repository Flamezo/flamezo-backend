import frappe
import requests
from .base import LogisticsProvider

# Production-confirmed base URLs from Flash Open API (2025) v1.3
FLASH_PRODUCTION_URL = "https://open-api.flash.uengage.in"
FLASH_STAGING_URL = "https://riderapi-staging.uengage.in"


class FlashProvider(LogisticsProvider):
    def __init__(self, settings=None):
        self.settings = settings or frappe.get_single("Flamezo Settings")
        self.is_production = getattr(self.settings, "flash_mode", "Sandbox") == "Production"
        self.base_url = FLASH_PRODUCTION_URL if self.is_production else FLASH_STAGING_URL
        self.access_token = self.settings.get_password("flash_access_token")

    def get_headers(self):
        return {
            "access-token": self.access_token,
            "Content-Type": "application/json",
        }

    def verify_webhook(self, data, signature):
        """
        Verifies authenticity of incoming Flash webhooks.
        Flash uses a configurable Header Key + Value pair set in the uEngage dashboard.
        Both key and value are stored in Flamezo Settings as flash_webhook_header_key
        and flash_webhook_header_value.
        """
        header_key = getattr(self.settings, "flash_webhook_header_key", None)
        if not header_key:
            # No auth configured — accept all (log a warning)
            frappe.log_error("Flash webhook received but no Header Key configured in settings.", "Flash Webhook Auth Warning")
            return True

        expected_value = self.settings.get_password("flash_webhook_header_value")
        received_value = signature  # Caller passes the value from request headers
        return received_value == expected_value

    # ------------------------------------------------------------------
    # SERVICEABILITY CHECK  (POST /getServiceability)
    # ------------------------------------------------------------------
    def calculate_quote(self, restaurant, order_details):
        """
        Checks if a drop location is serviceable and returns the delivery charge.
        Spec: store_id (snake_case) + pickupDetails + dropDetails
        """
        if not self.access_token:
            return {"success": False, "error": "Flash Access Token is missing in Flamezo Settings"}

        store_id = getattr(self.settings, "flash_store_id", None)
        if not store_id:
            return {"success": False, "error": "Flash Store ID not configured in Flamezo Settings"}

        # Validate coordinates
        drop_lat = order_details.get("latitude")
        drop_lng = order_details.get("longitude")
        if not drop_lat or not drop_lng:
            return {"success": False, "error": "Drop location coordinates missing"}

        pickup_lat = getattr(restaurant, "latitude", None)
        pickup_lng = getattr(restaurant, "longitude", None)
        if not pickup_lat or not pickup_lng:
            return {"success": False, "error": "Restaurant coordinates not configured"}

        # Exact payload per Flash API v1.3 spec
        payload = {
            "store_id": str(store_id),
            "pickupDetails": {
                "latitude": str(pickup_lat),
                "longitude": str(pickup_lng),
            },
            "dropDetails": {
                "latitude": str(drop_lat),
                "longitude": str(drop_lng),
            },
        }

        try:
            response = requests.post(
                f"{self.base_url}/getServiceability",
                json=payload,
                headers=self.get_headers(),
                timeout=30,
            )
            res_data = response.json()

            # Validate BOTH serviceability flags per spec
            serviceability = res_data.get("serviceability", {})
            rider_ok = serviceability.get("riderServiceAble", False)
            location_ok = serviceability.get("locationServiceAble", False)

            if response.status_code == 200 and str(res_data.get("status")) == "200" and rider_ok and location_ok:
                payouts = res_data.get("payouts", {})
                return {
                    "success": True,
                    "delivery_fee": float(payouts.get("total") or 0),
                    "eta_mins": 30,  # Flash does not return ETA at serviceability stage
                    "currency": "INR",
                    "provider": "Flash",
                }
            else:
                # Extract human-readable reason
                payout_msg = res_data.get("payouts", {}).get("message", "")
                error_msg = payout_msg or f"Not serviceable (rider={rider_ok}, location={location_ok})"
                return {"success": False, "error": error_msg}

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Flash Serviceability Error")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # CREATE TASK  (POST /createTask)
    # ------------------------------------------------------------------
    def create_order(self, restaurant, order):
        """
        Creates a delivery task on Flash.
        All field names are matched exactly to Flash API v1.3 spec.
        """
        if not self.access_token:
            return {"success": False, "error": "Flash Access Token is missing in Flamezo Settings"}

        store_id = getattr(self.settings, "flash_store_id", None)
        if not store_id:
            return {"success": False, "error": "Flash Store ID not configured in Flamezo Settings"}

        # Guard: delivery coordinates must be real (non-zero)
        drop_lat = getattr(order, "delivery_latitude", None)
        drop_lng = getattr(order, "delivery_longitude", None)
        try:
            if not drop_lat or not drop_lng or float(drop_lat) == 0.0 or float(drop_lng) == 0.0:
                frappe.log_error(
                    f"Order {order.name} missing delivery coordinates (lat={drop_lat}, lng={drop_lng}).",
                    "Flash Create Task — Missing Coordinates"
                )
                return {"success": False, "error": "Delivery location coordinates are missing. Customer must re-select their address on the map."}
        except (TypeError, ValueError):
            return {"success": False, "error": f"Invalid delivery coordinates: lat={drop_lat}, lng={drop_lng}"}

        # Guard: restaurant must have coordinates
        if not getattr(restaurant, "latitude", None) or not getattr(restaurant, "longitude", None):
            return {"success": False, "error": "Restaurant lat/lng not configured — update restaurant record first"}

        # Determine order source
        order_source = "pos" if getattr(order, "order_source", "") == "pos" else "website"

        # Determine paid status  — spec uses string "true" / "false"
        is_paid = getattr(order, "payment_status", "") == "completed"
        paid_str = "true" if is_paid else "false"


        # Build order items in Flash spec format: id, name, quantity, price
        items = []
        for item in order.get("order_items"):
            items.append({
                "id": str(item.product or item.name),
                "name": str(getattr(item, "product_name", None) or item.product or "Item"),
                "quantity": int(item.quantity or 1),
                "price": float(item.unit_price or 0),
            })

        payload = {
            "storeId": str(store_id),  # camelCase for createTask per spec
            "order_details": {
                "order_total": float(order.total),
                "paid": paid_str,
                "vendor_order_id": str(order.name),          # Required — shown to rider
                "order_source": order_source,                  # Required
                "customer_orderId": str(order.name),           # Optional — same for simplicity
            },
            "pickup_details": {
                "name": restaurant.restaurant_name,            # Required
                "contact_number": str(restaurant.owner_phone or ""),
                "latitude": float(restaurant.latitude),
                "longitude": float(restaurant.longitude),
                "address": str(restaurant.address or ""),
                "city": str(restaurant.city or ""),
                "state": str(getattr(restaurant, "state", "") or ""),
            },
            "drop_details": {
                "name": str(order.customer_name or "Customer"),
                "contact_number": str(order.customer_phone or ""),
                "latitude": float(order.delivery_latitude),
                "longitude": float(order.delivery_longitude),
                "address": str(order.delivery_address or ""),
                "city": str(getattr(order, "delivery_city", None) or restaurant.city or ""),
                "State": str(getattr(order, "delivery_state", None) or getattr(restaurant, "state", "") or ""),
            },
            "order_items": items,
            # NOTE: callback_url is configured in the uEngage Dashboard > Configuration,
            # NOT passed per request. Do not include it here.
        }

        try:
            response = requests.post(
                f"{self.base_url}/createTask",
                json=payload,
                headers=self.get_headers(),
                timeout=30,
            )
            res_data = response.json()

            if response.status_code == 200 and res_data.get("status") is True:
                return {
                    "success": True,
                    "delivery_id": res_data.get("taskId"),
                    "vendor_order_id": res_data.get("vendor_order_id"),
                    "status": res_data.get("Status_code") or "ACCEPTED",
                    "tracking_url": None,  # Provided later via webhook (ALLOTTED stage)
                    "delivery_fee": float(order.delivery_fee or 0),
                }
            else:
                err = res_data.get("message") or f"Task creation failed (status={res_data.get('Status_code')})"
                frappe.log_error(
                    f"Flash createTask failed for {order.name}: {err}\nPayload: {payload}\nResponse: {res_data}",
                    "Flash Create Task Error",
                )
                return {"success": False, "error": err}

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Flash Create Task Exception")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # CANCEL TASK  (POST /cancelTask)
    # ------------------------------------------------------------------
    def cancel_order(self, delivery_id):
        if not self.access_token:
            return {"success": False, "error": "Missing Flash access token"}

        store_id = getattr(self.settings, "flash_store_id", None)
        try:
            response = requests.post(
                f"{self.base_url}/cancelTask",
                json={"storeId": str(store_id), "taskId": str(delivery_id)},
                headers=self.get_headers(),
                timeout=30,
            )
            res_data = response.json()
            return {
                "success": res_data.get("status") is True,
                "status_code": res_data.get("status_code"),
                "message": res_data.get("message"),
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Flash Cancel Task Exception")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # TRACK TASK  (POST /trackTaskStatus)
    # ------------------------------------------------------------------
    def track_order(self, delivery_id):
        if not self.access_token:
            return {"success": False, "error": "Missing Flash access token"}

        store_id = getattr(self.settings, "flash_store_id", None)
        try:
            response = requests.post(
                f"{self.base_url}/trackTaskStatus",
                json={"storeId": str(store_id), "taskId": str(delivery_id)},
                headers=self.get_headers(),
                timeout=30,
            )
            res_data = response.json()

            if response.status_code == 200 and res_data.get("status") is True:
                data = res_data.get("data", {})
                lat = data.get("latitude")
                lng = data.get("longitude")
                return {
                    "success": True,
                    "status": res_data.get("status_code"),          # e.g. ALLOTTED, DISPATCHED
                    "rider_name": data.get("rider_name"),
                    "rider_phone": data.get("rider_contact"),
                    "tracking_url": data.get("tracking_url"),
                    "partner_name": data.get("partner_name"),
                    "rto_reason": data.get("rto_reason"),
                    "lat": float(lat) if lat else None,
                    "lng": float(lng) if lng else None,
                }
            else:
                return {
                    "success": False,
                    "error": res_data.get("message") or "Tracking failed",
                }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Flash Track Task Exception")
            return {"success": False, "error": str(e)}
