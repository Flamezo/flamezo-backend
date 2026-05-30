import frappe
import requests
import json
from frappe.utils import now_datetime
from flamezo_backend.flamezo.pos.base import POSProvider
from flamezo_backend.flamezo.utils.common import safe_log_error

# Staging vs Production endpoint selection.
# Set petpooja_env = "production" in site_config.json to switch to prod URLs.
# Petpooja uses DIFFERENT base domains for order APIs vs menu APIs in staging.
# Docs: save_order → 47pfzh5sf2, menu fetch → qle1yy2ydc
_STAGING_MENU_BASE  = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1"
_STAGING_ORDER_BASE = "https://47pfzh5sf2.execute-api.ap-southeast-1.amazonaws.com/V1"
_PROD_BASE          = "https://prod.petpooja.com/V1"  # placeholder — update when Petpooja provides prod URL

def _menu_base_url():
    env = frappe.conf.get("petpooja_env", "staging")
    return _PROD_BASE if env == "production" else _STAGING_MENU_BASE

def _order_base_url():
    env = frappe.conf.get("petpooja_env", "staging")
    return _PROD_BASE if env == "production" else _STAGING_ORDER_BASE

class PetpoojaProvider(POSProvider):
    def __init__(self, restaurant_doc):
        super().__init__(restaurant_doc)
        order_base = _order_base_url()
        menu_base  = _menu_base_url()
        self.save_order_url   = f"{order_base}/save_order"
        self.fetch_menu_url   = f"{menu_base}/mapped_restaurant_menus"
        self.update_order_url = f"{order_base}/update_order_status"
        self.rider_url        = f"{order_base}/rider_status_update"

    def sync_menu(self):
        """Petpooja is push-based; we also support active pull via mapped_restaurant_menus."""
        return self.pull_menu()

    def pull_menu(self):
        """
        Petpooja's fetch menu API is deprecated (confirmed by Malvi Vaghela, May 2026).
        Menu sync is push-only: Petpooja pushes to our Menu Sharing Endpoint on every change.
        The "Sync Menu Now" button in the dashboard should instruct the user to trigger
        a manual push from their Petpooja tablet (Menu Management → Push Menu).
        """
        if not self.restaurant.get("pos_menu_sync_enabled", 1):
            return {"status": "skipped", "message": "Menu sync is disabled for this restaurant"}

        return {
            "status": "info",
            "message": "Petpooja uses push-based menu sync. To refresh your menu, go to your Petpooja dashboard → Menu Management → Push Menu. Your menu will update automatically."
        }

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
                self.save_order_url,
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
            
            # Map Petpooja status to Flamezo status
            new_status = self.map_status(petpooja_status)
            if not new_status:
                safe_log_error("Petpooja Sync Warning", f"Received unknown Petpooja status: {petpooja_status} for order {client_order_id}")
                return

            # Status Transition Safety: Don't move backwards
            # Must match Order doctype status options exactly
            status_priority = {
                "pending_verification": 0,
                "Accepted": 1,
                "confirmed": 1,
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
            from flamezo_backend.flamezo.api.realtime import notify_order_update
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
        Skipped if the restaurant has disabled menu sync (pos_menu_sync_enabled = 0).
        """
        if not self.restaurant.get("pos_menu_sync_enabled", 1):
            frappe.logger().info(f"Menu sync skipped for {self.restaurant.name} — sync disabled by restaurant")
            return {"status": "skipped", "message": "Menu sync is disabled for this restaurant"}

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

            # Persist CGST/SGST taxids from the menu payload so _format_order can reference them
            taxes = data.get("taxes", [])
            for t in taxes:
                tname = (t.get("taxname") or "").upper()
                if tname == "CGST":
                    self.restaurant.db_set("pos_cgst_taxid", str(t.get("taxid", "2201")))
                elif tname == "SGST":
                    self.restaurant.db_set("pos_sgst_taxid", str(t.get("taxid", "2202")))

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
        Map Petpooja status codes to Flamezo statuses (Unified Engine)
        """
        from flamezo_backend.flamezo.pos.base import FlamezoOrderStatus
        
        # Per Petpooja docs: -1=Cancelled, 1/2/3=Accepted, 4=Dispatched, 5=Food Ready, 10=Delivered
        mapping = {
            "1": FlamezoOrderStatus.ACCEPTED,
            "2": FlamezoOrderStatus.ACCEPTED,
            "3": FlamezoOrderStatus.ACCEPTED,
            "4": FlamezoOrderStatus.DISPATCHED,
            "5": FlamezoOrderStatus.READY,
            "10": FlamezoOrderStatus.DELIVERED,
            "-1": FlamezoOrderStatus.CANCELLED
        }
        return mapping.get(str(provider_status))

    def _format_order(self, order_doc):
        """
        Map Flamezo Order to Petpooja 'Save Order' 2026 schema.
        Uses the correct nested structure: orderinfo → OrderInfo → { Restaurant, Customer, Order, OrderItem, Tax }
        Supports: Dine-In (D), Takeaway (P), Delivery (H)
        """
        from frappe.utils import get_url, get_datetime
        from flamezo_backend.flamezo.utils.addon_group_helpers import deserialize_addon_selections

        callback_url = get_url("/api/method/flamezo_backend.flamezo.api.pos.petpooja_callback")

        # ── Tax setup ──
        order_subtotal = float(order_doc.subtotal or 0) or 1
        order_cgst = float(order_doc.cgst or 0)
        order_sgst = float(order_doc.sgst or 0)
        tax_rate_half = float(order_doc.tax_percent or 0) / 2

        cgst_taxid = frappe.db.get_value("Restaurant", self.restaurant.name, "pos_cgst_taxid") or "2201"
        sgst_taxid = frappe.db.get_value("Restaurant", self.restaurant.name, "pos_sgst_taxid") or "2202"

        # ── Build order items ──
        order_items = []
        for item in order_doc.order_items:
            item_subtotal = float(item.unit_price or 0) * int(item.quantity or 1)
            weight = item_subtotal / order_subtotal if order_subtotal else 1
            item_cgst_amt = round(order_cgst * weight, 2)
            item_sgst_amt = round(order_sgst * weight, 2)

            item_tax = []
            if tax_rate_half > 0:
                item_tax = [
                    {"id": cgst_taxid, "name": "CGST", "tax_percentage": str(tax_rate_half), "amount": str(item_cgst_amt)},
                    {"id": sgst_taxid, "name": "SGST", "tax_percentage": str(tax_rate_half), "amount": str(item_sgst_amt)},
                ]

            petpooja_item_id = frappe.db.get_value("Menu Product", item.product, "pos_id") or item.product

            # Parse addon/variation from customizations — supports v2 (addon groups) and legacy
            addon_details = []
            variation_name = ""
            variation_id = ""
            if item.customizations:
                try:
                    version, cust = deserialize_addon_selections(item.customizations)
                    if version == 2:
                        # v2 addon group format — has POS IDs
                        for group in cust.get("groups", []):
                            if group.get("group_type") == "variation":
                                for sel in group.get("selected_items", []):
                                    variation_name = sel.get("item_name", "")
                                    variation_id = sel.get("pos_addon_item_id", "")
                            else:
                                for sel in group.get("selected_items", []):
                                    addon_details.append({
                                        "id": sel.get("pos_addon_item_id") or sel.get("item_id", ""),
                                        "name": sel.get("item_name", ""),
                                        "group_name": group.get("group_name", ""),
                                        "price": str(sel.get("price", 0)),
                                        "group_id": group.get("pos_addon_group_id") or "",
                                        "quantity": "1"
                                    })
                    else:
                        # Legacy format
                        variation = cust.get("variation") or {}
                        variation_name = str(variation.get("name", ""))
                        variation_id = str(variation.get("id", ""))
                        for addon in (cust.get("addons") or []):
                            addon_details.append({
                                "id": str(addon.get("id", "")),
                                "name": str(addon.get("name", "")),
                                "group_name": str(addon.get("group_name", "")),
                                "price": str(addon.get("price", "0")),
                                "group_id": str(addon.get("group_id", "")),
                                "quantity": str(addon.get("quantity", 1))
                            })
                except Exception:
                    pass

            order_items.append({
                "id": str(petpooja_item_id),
                "name": item.product_name,
                "tax_inclusive": False,
                "gst_liability": "restaurant",
                "item_tax": item_tax,
                "item_discount": "",
                "price": str(item.unit_price),
                "final_price": str(item.total_price),
                "quantity": str(item.quantity),
                "description": "",
                "variation_name": variation_name,
                "variation_id": str(variation_id) if variation_id else "",
                "AddonItem": {
                    "details": addon_details
                }
            })

        # ── Order type, payment, timestamps ──
        order_type = {"dine_in": "D", "takeaway": "P", "delivery": "H"}.get(order_doc.order_type, "P")

        full_address = order_doc.delivery_address or ""
        if order_doc.delivery_landmark:
            full_address += f" (Landmark: {order_doc.delivery_landmark})"

        pm = (order_doc.payment_method or "").lower()
        payment_type = "CARD" if pm == "card" else ("ONLINE" if pm in ("online", "upi", "wallet") else "COD")

        creation_dt = get_datetime(order_doc.creation)
        order_date = creation_dt.strftime("%Y-%m-%d")
        order_time = creation_dt.strftime("%H:%M:%S")
        created_on = creation_dt.strftime("%Y-%m-%d %H:%M:%S")
        tax_percent = str(order_doc.tax_percent or 0)

        # ── Order-level tax (Tax.details array) ──
        tax_details = []
        if order_cgst > 0:
            tax_details.append({
                "id": cgst_taxid, "title": "CGST", "type": "P",
                "price": str(tax_rate_half), "tax": str(round(order_cgst, 2)),
                "restaurant_liable_amt": str(round(order_cgst, 2))
            })
        if order_sgst > 0:
            tax_details.append({
                "id": sgst_taxid, "title": "SGST", "type": "P",
                "price": str(tax_rate_half), "tax": str(round(order_sgst, 2)),
                "restaurant_liable_amt": str(round(order_sgst, 2))
            })

        discount_total = str(round(float(order_doc.discount or 0) + float(order_doc.loyalty_discount or 0), 2))

        # ── Build payload in Petpooja's actual nested structure ──
        payload = {
            "app_key": self.settings["app_key"],
            "app_secret": self.settings["app_secret"],
            "access_token": self.settings["access_token"],
            "orderinfo": {
                "OrderInfo": {
                    "Restaurant": {
                        "details": {
                            "res_name": self.restaurant.restaurant_name or self.restaurant.name,
                            "address": self.restaurant.address or "",
                            "contact_information": self.restaurant.contact_number or "",
                            "restID": self.settings["merchant_id"]
                        }
                    },
                    "Customer": {
                        "details": {
                            "email": order_doc.customer_email or "",
                            "name": order_doc.customer_name or "Guest",
                            "address": full_address,
                            "phone": order_doc.customer_phone or "",
                            "latitude": str(order_doc.delivery_latitude) if getattr(order_doc, "delivery_latitude", None) else "",
                            "longitude": str(order_doc.delivery_longitude) if getattr(order_doc, "delivery_longitude", None) else ""
                        }
                    },
                    "Order": {
                        "details": {
                            "orderID": order_doc.name,
                            "preorder_date": order_date,
                            "preorder_time": order_time,
                            "service_charge": "0",
                            "sc_tax_amount": "0",
                            "delivery_charges": str(order_doc.delivery_fee or 0),
                            "dc_tax_percentage": tax_percent if order_doc.delivery_fee else "0",
                            "dc_tax_amount": "0",
                            "dc_gst_details": [],
                            "packing_charges": str(order_doc.packaging_fee or 0),
                            "pc_tax_amount": "0",
                            "pc_tax_percentage": tax_percent if order_doc.packaging_fee else "0",
                            "pc_gst_details": [],
                            "order_type": order_type,
                            "ondc_bap": "",
                            "advanced_order": "N",
                            "urgent_order": False,
                            "urgent_time": 0,
                            "payment_type": payment_type,
                            "table_no": str(order_doc.table_number) if order_type == "D" and order_doc.table_number else "",
                            "no_of_persons": "0",
                            "discount_total": discount_total,
                            "tax_total": str(round(float(order_doc.tax or 0), 2)),
                            "discount_type": "F",
                            "total": str(order_doc.total),
                            "description": order_doc.delivery_instructions or "",
                            "created_on": created_on,
                            "enable_delivery": 1,
                            "min_prep_time": 20,
                            "callback_url": callback_url
                        }
                    },
                    "OrderItem": {
                        "details": order_items
                    },
                    "Tax": {
                        "details": tax_details
                    }
                },
                "udid": "",
                "device_type": "Web"
            }
        }

        return payload
