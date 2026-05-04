import frappe
import requests
import json
from dinematters.dinematters.pos.base import POSProvider
from dinematters.dinematters.utils.common import safe_log_error

class RestroworksProvider(POSProvider):
    def __init__(self, restaurant_doc):
        super().__init__(restaurant_doc)
        self.api_key = self.settings.get("app_key")
        self.merchant_id = self.settings.get("merchant_id")
        self.base_url = "https://api.posist.co/api/v2"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Merchant-Id": self.merchant_id
        }

    def sync_menu(self):
        """
        Restroworks uses a 'Pull' strategy. We override the push-based sync_menu
        to redirect to pull_menu for consistency in the UI trigger.
        """
        return self.pull_menu()

    def pull_menu(self):
        """
        Fetches the menu from POSist and syncs it to Dinematters.
        Implements the 'Price Override' logic.
        """
        try:
            # In a real scenario, we hit /api/v2/menu
            # For boilerplate, we'll demonstrate the mapping logic
            
            # response = requests.get(f"{self.base_url}/menu", headers=self.headers, timeout=30)
            # data = response.json()
            
            # Using placeholder data for boilerplate demonstration
            data = self._get_mock_menu_data()
            
            synced_count = 0
            for item in data.get("items", []):
                # 1. Resolve Category
                cat_name = item.get("category_name", "Uncategorized")
                category = self._get_or_create_category(cat_name)
                
                # 2. Sync Product (The "Menu Boss" Logic)
                product_name = item.get("item_name")
                price = item.get("price")
                
                product = frappe.db.get_value("Product", 
                    {"product_name": product_name, "restaurant": self.restaurant.name}, 
                    "name"
                )
                
                if product:
                    # Update Price (Override Logic)
                    doc = frappe.get_doc("Product", product)
                    if float(doc.price) != float(price):
                        doc.price = price
                        doc.description = item.get("description") or doc.description
                        doc.save(ignore_permissions=True)
                        frappe.db.commit()
                else:
                    # Create New Product
                    new_prod = frappe.get_doc({
                        "doctype": "Product",
                        "product_name": product_name,
                        "category": category,
                        "restaurant": self.restaurant.name,
                        "price": price,
                        "description": item.get("description"),
                        "is_veg": 1 if item.get("type") == "veg" else 0
                    })
                    new_prod.insert(ignore_permissions=True)
                    frappe.db.commit()
                
                synced_count += 1

            self._log_sync_status("SUCCESS", f"Successfully pulled {synced_count} items from Restroworks (POSist).")
            
            # Real-time notification for UI update
            frappe.publish_realtime(
                event="pos_sync_complete",
                message={
                    "restaurant": self.restaurant.name,
                    "status": "SUCCESS",
                    "items_synced": synced_count
                },
                room=f"restaurant:{self.restaurant.name}"
            )
            return True

        except Exception as e:
            self._log_sync_status("ERROR", f"Pull Sync Failed: {str(e)}")
            safe_log_error("Restroworks Pull Error", frappe.get_traceback())
            return False

    def push_order(self, order_doc):
        """
        Injects a Dinematters order into Restroworks POS.
        """
        try:
            payload = {
                "order_details": {
                    "order_id": order_doc.name,
                    "order_type": "delivery", # Defaulting to delivery for 3rd party
                    "customer_details": {
                        "name": order_doc.customer_name,
                        "mobile": order_doc.customer_phone
                    },
                    "items": [
                        {
                            "item_name": item.product_name,
                            "quantity": item.quantity,
                            "price": item.price
                        } for item in order_doc.items
                    ]
                }
            }
            
            # In production: requests.post(f"{self.base_url}/orders", json=payload, headers=self.headers)
            safe_log_error("Restroworks Order Payload (Mock)", json.dumps(payload))
            return True
            
        except Exception as e:
            safe_log_error("Restroworks Push Order Error", str(e))
            return False

    def handle_callback(self, data):
        """
        Processes real-time status updates from POSist.
        """
        pos_status = data.get("status")
        order_id = data.get("order_id")
        
        dm_status = self.map_status(pos_status)
        
        if order_id and dm_status:
            # Update both the primary status and the sync status
            frappe.db.set_value("Order", order_id, {
                "status": dm_status,
                "pos_sync_status": f"POSist: {pos_status}"
            })
            
            # Publish real-time update
            order = frappe.get_doc("Order", order_id)
            from dinematters.dinematters.api.realtime import notify_order_update
            notify_order_update(order)
            
            return True
        return False

    def map_status(self, raw_status):
        """
        Map Restroworks states to Dinematters statuses (Unified Engine)
        """
        from dinematters.dinematters.pos.base import DineMattersOrderStatus
        
        mapping = {
            "pending": DineMattersOrderStatus.PLACED,
            "confirmed": DineMattersOrderStatus.ACCEPTED,
            "preparing": DineMattersOrderStatus.PREPARING,
            "ready": DineMattersOrderStatus.READY,
            "completed": DineMattersOrderStatus.DELIVERED,
            "cancelled": DineMattersOrderStatus.CANCELLED
        }
        return mapping.get(raw_status.lower(), raw_status)

    def _get_or_create_category(self, cat_name):
        cat = frappe.db.get_value("Category", 
            {"category_name": cat_name, "restaurant": self.restaurant.name}, 
            "name"
        )
        if not cat:
            new_cat = frappe.get_doc({
                "doctype": "Category",
                "category_name": cat_name,
                "restaurant": self.restaurant.name
            })
            new_cat.insert(ignore_permissions=True)
            frappe.db.commit()
            return new_cat.name
        return cat

    def _log_sync_status(self, status, message):
        frappe.db.set_value("Restaurant", self.restaurant.name, {
            "pos_sync_status": f"[{status}] {message}",
            "pos_last_sync_at": frappe.utils.now_datetime()
        })

    def _get_mock_menu_data(self):
        """Return standardized POSist Menu JSON for boilerplate testing"""
        return {
            "items": [
                {
                    "item_name": "Paneer Tikka (Restroworks Sync)",
                    "price": 350.00,
                    "category_name": "Starters",
                    "description": "Succulent paneer cubes marinated in spices and grilled.",
                    "type": "veg"
                },
                {
                    "item_name": "Butter Chicken (Restroworks Sync)",
                    "price": 450.00,
                    "category_name": "Main Course",
                    "description": "The classic Delhi butter chicken.",
                    "type": "non-veg"
                }
            ]
        }
