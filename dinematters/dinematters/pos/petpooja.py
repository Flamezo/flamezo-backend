import frappe
import requests
import json
from frappe.utils import now_datetime
from dinematters.dinematters.pos.base import POSProvider
from dinematters.dinematters.utils.common import safe_log_error

class PetpoojaProvider(POSProvider):
    def __init__(self, restaurant_doc):
        super().__init__(restaurant_doc)
        self.api_url = "https://developerapi.petpooja.com/v1/" # Staging: https://sandbox.petpooja.com/v1/

    def sync_menu(self):
        """
        Petpooja usually pushes the menu to us.
        We provide pull_menu as the standardized way to trigger this.
        """
        return self.pull_menu()

    def pull_menu(self):
        """
        Fetch menu from Petpooja (Pull strategy)
        """
        # In actual Petpooja implementation, this often requires hitting /get_menus
        # For now, we provide the template for the 'Price Override' sync logic
        safe_log_error("Petpooja Sync", f"Pull Menu triggered for {self.restaurant.name}")
        
        # This would be the mapping logic once response is received:
        # 1. Resolve Category
        # 2. Sync Product (Boss Logic: Override Price)
        
        return {"status": "success", "message": "Pull Menu initiated for Petpooja."}

    def push_order(self, order_doc):
        """
        Push order to Petpooja 'Save Order' API
        """
        if not self.settings["app_key"] or not self.settings["app_secret"] or not self.settings["access_token"] or not self.settings["merchant_id"]:
            return {"status": "error", "message": "Missing Petpooja credentials (App Key, Secret, or Access Token)"}

        # Format order for Petpooja
        payload = self._format_order(order_doc)
        
        headers = {
            "Content-Type": "application/json"
        }

        try:
            # Petpooja 'Save Order' endpoint
            response = requests.post(
                f"{self.api_url}save_order",
                headers=headers,
                data=json.dumps(payload),
                timeout=15
            )
            response.raise_for_status()
            result = response.json()

            if str(result.get("success")) == "1":
                return {"status": "success", "pos_order_id": result.get("orderID")}
            else:
                return {"status": "error", "message": result.get("message", "Unknown Petpooja error")}

        except Exception as e:
            safe_log_error("Petpooja Order Push Error", frappe.get_traceback())
            return {"status": "error", "message": str(e)}

    def handle_callback(self, data):
        # Route by payload type
        if "inStock" in data:
            return self.handle_item_stock_update(data)
        if "store_status" in data:
            return self.handle_store_status_update(data)
        if "categories" in data or "items" in data:
            return self.handle_menu_push(data)
        if "rider_data" in data or data.get("status") in ["rider-assigned", "rider-arrived", "pickedup", "delivered"]:
            # Note: delivered status might overlap with order status, but rider_data is the identifier
            return self.handle_rider_update(data)

        petpooja_status = str(data.get("status"))
        client_order_id = data.get("clientorderID") or data.get("orderID")
        pos_order_id = data.get("orderID") if data.get("clientorderID") else data.get("petpooja_order_id") # Adjust if Petpooja sends their ID differently
        app_key = data.get("app_key")

        # Production Security: Validate App Key if provided
        if app_key and app_key != self.settings.get("app_key"):
            safe_log_error("Petpooja Webhook Auth Error", f"Petpooja callback invalid app_key: {app_key}")
            return

        if not client_order_id:
            safe_log_error("Petpooja Webhook Error", f"Petpooja callback missing order identifiers: {json.dumps(data)}")
            return

        try:
            order = frappe.get_doc("Order", client_order_id)
            
            # Map Petpooja status to DineMatters status
            new_status = self.map_status(petpooja_status)
            if not new_status:
                safe_log_error("Petpooja Sync Warning", f"Received unknown Petpooja status: {petpooja_status} for order {client_order_id}")
                return

            # Status Transition Safety: Don't move backwards
            status_priority = {
                "pending": 0,
                "Accepted": 1,
                "preparing": 2,
                "ready": 3,
                "Dispatched": 4,
                "delivered": 5,
                "cancelled": -1
            }

            current_priority = status_priority.get(order.status, 0)
            new_priority = status_priority.get(new_status, 0)

            if new_status == "cancelled":
                # Cancellation is always valid unless already delivered
                if order.status == "delivered":
                    return 
            elif new_priority <= current_priority:
                # Ignore status updates that are older or the same as current
                return

            # Update Order
            order.db_set("status", new_status)
            order.db_set("pos_sync_status", f"Petpooja: {petpooja_status}")
            
            # Real-time update for Merchant and Customer
            from dinematters.dinematters.api.realtime import notify_order_update
            notify_order_update(order)

            # Log for production audit
            frappe.logger().info(f"Petpooja Sync: Order {order.name} status updated to {new_status} (Petpooja: {petpooja_status})")

        except frappe.DoesNotExistError:
            safe_log_error("Petpooja Webhook Error", f"Petpooja callback for non-existent order: {client_order_id}")
        except Exception as e:
            safe_log_error("Petpooja Sync Error", f"Error handling Petpooja status callback: {str(e)}\n{frappe.get_traceback()}")

    def handle_menu_push(self, data):
        """
        Handle Menu Push from Petpooja (Production Implementation)
        Ensures Categories and Products are synced with correct pricing.
        """
        frappe.logger().info(f"Petpooja Menu Push received for restaurant {self.restaurant.name}")
        
        try:
            # 1. Process Categories
            categories = data.get("categories", [])
            for cat in categories:
                self._sync_category(cat)

            # 2. Process Items (Products)
            items = data.get("items", [])
            for item in items:
                self._sync_product(item)

            self.restaurant.db_set("pos_last_sync_at", now_datetime())
            self.restaurant.db_set("pos_sync_status", "Success: Menu Pushed")
            
            return {"status": "success", "message": "Menu synced successfully"}

        except Exception as e:
            safe_log_error("Petpooja Menu Sync Error", frappe.get_traceback())
            return {"status": "error", "message": str(e)}

    def _sync_category(self, cat_data):
        """Sync single category from Petpooja data"""
        cat_id = cat_data.get("categoryid")
        cat_name = cat_data.get("categoryname")
        
        if not cat_id or not cat_name:
            return

        # Check if exists or create
        cat = frappe.get_all("Menu Category", filters={"pos_id": cat_id, "restaurant": self.restaurant.name}, limit=1)
        if cat:
            doc = frappe.get_doc("Menu Category", cat[0].name)
            doc.category_name = cat_name
            doc.status = "Active" if cat_data.get("categorystatus") == "1" else "Inactive"
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.new_doc("Menu Category")
            doc.restaurant = self.restaurant.name
            doc.category_name = cat_name
            doc.pos_id = cat_id
            doc.status = "Active" if cat_data.get("categorystatus") == "1" else "Inactive"
            doc.insert(ignore_permissions=True)

    def _sync_product(self, item_data):
        """Sync single product from Petpooja data"""
        item_id = item_data.get("itemid")
        item_name = item_data.get("itemname")
        cat_id = item_data.get("categoryid")
        
        if not item_id or not item_name:
            return

        # Find Category
        cat = frappe.get_all("Menu Category", filters={"pos_id": cat_id, "restaurant": self.restaurant.name}, limit=1)
        cat_name = cat[0].name if cat else None

        # Check if exists or create
        prod = frappe.get_all("Menu Product", filters={"pos_id": item_id, "restaurant": self.restaurant.name}, limit=1)
        
        status = "Active" if str(item_data.get("itemstatus")) == "1" else "Inactive"
        price = float(item_data.get("itemprice", 0))
        is_veg = 1 if str(item_data.get("itemvegetarian")) == "1" else 0
        nutrition = item_data.get("nutrition", {})
        calories = nutrition.get("kcal") or nutrition.get("calories")

        if prod:
            doc = frappe.get_doc("Menu Product", prod[0].name)
            doc.product_name = item_name
            doc.category = cat_name
            doc.price = price
            doc.status = status
            doc.is_vegetarian = is_veg
            if calories:
                doc.calories = calories
            doc.description = item_data.get("itemdescription", "")[:140]
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.new_doc("Menu Product")
            doc.restaurant = self.restaurant.name
            doc.product_name = item_name
            doc.category = cat_name
            doc.price = price
            doc.pos_id = item_id
            doc.status = status
            doc.is_vegetarian = is_veg
            if calories:
                doc.calories = calories
            doc.description = item_data.get("itemdescription", "")[:140]
            doc.insert(ignore_permissions=True)

    def handle_item_stock_update(self, data):
        """Handle item/addon stock updates from Petpooja"""
        in_stock = data.get("inStock")
        item_ids = data.get("itemID", []) # This can be a list or a single string depending on Petpooja version
        
        if isinstance(item_ids, str):
            item_ids = [item_ids]
        
        status = "Active" if in_stock else "Inactive"
        
        for p_id in item_ids:
            prod = frappe.get_all("Menu Product", filters={"pos_id": p_id, "restaurant": self.restaurant.name}, limit=1)
            if prod:
                frappe.db.set_value("Menu Product", prod[0].name, "status", status)
                
        return {"status": "success", "message": "Stock status updated"}

    def handle_store_status_update(self, data):
        """Handle store open/close status from Petpooja"""
        store_status = str(data.get("store_status")) # "1" or "0"
        
        is_open = (store_status == "1")
        self.restaurant.db_set("pos_store_status", "Open" if is_open else "Closed")
        
        return {"status": "success", "message": f"Store status updated to {'Open' if is_open else 'Closed'}"}

    def handle_rider_update(self, data):
        """Handle rider information updates from Petpooja"""
        client_order_id = data.get("order_id") # Documentation says order_id is client order id here
        rider_data = data.get("rider_data", {})
        
        if not client_order_id:
            return {"status": "error", "message": "Missing order_id"}
            
        try:
            order = frappe.get_doc("Order", client_order_id)
            if rider_data.get("rider_name"):
                order.db_set("delivery_rider_name", rider_data.get("rider_name"))
            if rider_data.get("rider_phone"):
                order.db_set("delivery_rider_phone", rider_data.get("rider_phone"))
            
            # Optionally update custom delivery status
            # order.db_set("delivery_status", data.get("status"))
            
            return {"status": "success", "message": "Rider info updated"}
        except Exception as e:
            safe_log_error("Petpooja Rider Update Error", frappe.get_traceback())
            return {"status": "error", "message": str(e)}

    def map_status(self, provider_status):
        """
        Map Petpooja status codes to Dinematters statuses (Unified Engine)
        """
        from dinematters.dinematters.pos.base import DineMattersOrderStatus
        
        mapping = {
            "1": DineMattersOrderStatus.ACCEPTED,
            "2": DineMattersOrderStatus.PREPARING,
            "3": DineMattersOrderStatus.READY,
            "4": DineMattersOrderStatus.DISPATCHED,
            "5": DineMattersOrderStatus.DELIVERED,
            "10": DineMattersOrderStatus.DELIVERED,
            "-1": DineMattersOrderStatus.CANCELLED
        }
        return mapping.get(str(provider_status))

    def _format_order(self, order_doc):
        """
        Map Dinematters Order to Petpooja 'Save Order' 2026 schema
        Supports: Dine-In (1), Takeaway (2), Delivery (3)
        """
        # Generate Callback URL for Petpooja updates
        from frappe.utils import get_url
        callback_url = get_url("/api/method/dinematters.dinematters.api.pos.petpooja_callback")

        order_items = []
        for item in order_doc.order_items:
            # Map item taxes if available
            item_tax = []
            if getattr(item, 'tax_percent', None):
                item_tax.append({
                    "id": "1", # Generic Tax ID
                    "title": "GST",
                    "type": "percentage",
                    "price": str(item.tax_amount) if hasattr(item, 'tax_amount') else "0",
                    "tax_percentage": str(item.tax_percent)
                })

            order_items.append({
                "id": item.product,
                "name": item.product_name,
                "quantity": str(item.quantity),
                "price": str(item.price),
                "total": str(item.total_price),
                "discount": "0",
                "tax_inclusive": "1" if getattr(item, 'is_tax_inclusive', 0) else "0",
                "item_tax": item_tax,
                "addonItem": [] # Placeholder for now, can be expanded if Customizations exist
            })

        # Determine Order Type
        # 1: Dine-In, 2: Takeaway, 3: Delivery
        order_type_map = {
            "dine_in": "1",
            "takeaway": "2",
            "delivery": "3"
        }
        order_type = order_type_map.get(order_doc.order_type, "2")

        # Construct Address for Delivery
        full_address = order_doc.delivery_address or ""
        if order_doc.delivery_landmark:
            full_address += f" (Landmark: {order_doc.delivery_landmark})"

        # 2025/2026 Tax percentages
        tax_percent = str(order_doc.tax_percent or 0)

        # Base payload with authentication
        payload = {
            "app_key": self.settings["app_key"],
            "app_secret": self.settings["app_secret"],
            "access_token": self.settings["access_token"],
            "restID": self.settings["merchant_id"],
            "res_name": self.restaurant.restaurant_name or self.restaurant.name,
            "address": self.restaurant.address or "",
            "Contact_information": self.restaurant.contact_number or "",
            "device_type": "Web",
            "order": {
                "customer": {
                    "name": order_doc.customer_name or "Guest",
                    "phone": order_doc.customer_phone or "",
                    "email": order_doc.customer_email or "",
                    "address": full_address,
                    "city": order_doc.delivery_city or "",
                    "zip": order_doc.delivery_zip_code or ""
                },
                "order": {
                    "orderID": order_doc.name,
                    "order_number": order_doc.order_number,
                    "order_date": order_doc.creation.strftime("%Y-%m-%d %H:%M:%S"),
                    "order_type": order_type,
                    "subtotal": str(order_doc.subtotal),
                    "tax": str(order_doc.tax),
                    "total": str(order_doc.total),
                    "payment_type": "1" if order_doc.payment_method == "online" else "0",
                    "discount": str(order_doc.discount or 0.0),
                    "instructions": order_doc.delivery_instructions or "",
                    "callback_url": callback_url,
                    "urgent_order": "0", # Per user requirement
                    "urgent_time": "",
                    "dc_tax_percentage": tax_percent if order_doc.delivery_fee else "0",
                    "pc_tax_percentage": tax_percent if order_doc.packaging_fee else "0"
                },
                "orderItem": order_items,
                "tax": [], # Order level taxes if any summary needed
                "discount": []
            }
        }

        # Add table info if dine-in
        if order_type == "1" and order_doc.table_number:
            payload["order"]["order"]["table_no"] = str(order_doc.table_number)

        return payload
