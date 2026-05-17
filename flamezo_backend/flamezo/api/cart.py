# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

"""
API endpoints for Cart operations
Matches format from BACKEND_API_DOCUMENTATION.md
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, get_datetime_str
from flamezo_backend.flamezo.utils.api_helpers import (
	validate_restaurant_for_api, 
	validate_product_belongs_to_restaurant,
	get_product_from_id
)
from flamezo_backend.flamezo.utils.customization_helpers import load_product_customizations, validate_customizations
from flamezo_backend.flamezo.utils.currency_helpers import get_restaurant_currency_info
import json
import random
import string
from datetime import datetime
from collections import defaultdict

# Handled by customization_helpers


@frappe.whitelist(allow_guest=True)
def add_to_cart(restaurant_id, dish_id, quantity=1, customizations=None, session_id=None, table_number=None, latitude=None, longitude=None):
	"""
	POST /api/v1/cart/add
	Add item to cart
	Requires restaurant_id for SaaS multi-tenancy
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Get user or use session_id
		user = frappe.session.user if frappe.session.user != "Guest" else None
		if not user and not session_id:
			session_id = frappe.session.get("session_id") or generate_session_id()
		
		# Resolve product name if it's a slug/ID
		actual_dish_id = get_product_from_id(dish_id, restaurant)
		
		# Validate product exists
		if not actual_dish_id:
			return {
				"success": False,
				"error": {
					"code": "PRODUCT_NOT_FOUND",
					"message": f"Product {dish_id} not found"
				}
			}
		
		# Use actual document name for operations
		dish_id = actual_dish_id
		product = frappe.get_doc("Menu Product", dish_id)
		
		# Load customization options (nested child table)
		load_product_customizations(product)
		
		# Validate product belongs to restaurant
		if product.restaurant != restaurant:
			return {
				"success": False,
				"error": {
					"code": "PRODUCT_NOT_FOUND",
					"message": f"Product {dish_id} not found for restaurant {restaurant_id}"
				}
			}
		
		if not product.is_active:
			return {
				"success": False,
				"error": {
					"code": "PRODUCT_NOT_ACTIVE",
					"message": f"Product {dish_id} is not active"
				}
			}
		
		# Parse and Validate customizations
		if isinstance(customizations, str):
			customizations = json.loads(customizations) if customizations else {}
		customizations = customizations or {}
		
		# Validate required customizations
		validate_customizations(product, customizations)
		
		# Calculate unit price (base + customizations)
		unit_price = flt(product.price)
		
		# Add customization prices
		if customizations and product.customization_questions:
			for question in product.customization_questions:
				question_id = question.question_id
				if question_id in customizations:
					selected_options = customizations[question_id]
					if isinstance(selected_options, str):
						selected_options = [selected_options]
					
					for option_id in selected_options:
						# Find option in question
						for option in question.options:
							if option.option_id == option_id:
								unit_price += flt(option.price) or 0
								break
		
		# Check if identical item exists in cart (for same restaurant)
		existing_entry = find_existing_cart_entry(user, session_id, restaurant, dish_id, customizations)
		
		if existing_entry:
			# Update quantity
			entry_doc = frappe.get_doc("Cart Entry", existing_entry)
			new_quantity = cint(quantity) + entry_doc.quantity
			entry_doc.quantity = new_quantity
			entry_doc.total_price = unit_price * new_quantity
			
			# Update table_number if provided
			if table_number:
				parsed_table_number = parse_table_number_from_qr(table_number, restaurant_id)
				entry_doc.table_number = parsed_table_number
			
			entry_doc.save(ignore_permissions=True)
			entry_id = entry_doc.entry_id
		else:
			# Create new entry
			# Use the product slug (product_id) for the entryId to ensure frontend match
			entry_id = generate_entry_id(product.product_id or dish_id)
			# Parse table_number from QR code if provided
			parsed_table_number = None
			if table_number:
				parsed_table_number = parse_table_number_from_qr(table_number, restaurant_id)
			
			entry_doc = frappe.get_doc({
				"doctype": "Cart Entry",
				"entry_id": entry_id,
				"restaurant": restaurant,
				"user": user,
				"session_id": session_id,
				"product": dish_id,
				"quantity": cint(quantity),
				"customizations": json.dumps(customizations) if customizations else None,
				"unit_price": unit_price,
				"total_price": unit_price * cint(quantity),
				"table_number": parsed_table_number
			})
			entry_doc.insert(ignore_permissions=True)
		
		# Get cart summary (for this restaurant)
		cart_summary = get_cart_summary(user, session_id, restaurant, latitude=latitude, longitude=longitude)
		
		cart_item_data = {
					"entryId": entry_id,
					"dishId": product.product_id,
					"quantity": cint(quantity) if not existing_entry else entry_doc.quantity,
					"customizations": customizations,
					"unitPrice": unit_price,
					"totalPrice": entry_doc.total_price
		}
		
		# Add tableNumber if available
		if parsed_table_number:
			cart_item_data["tableNumber"] = parsed_table_number
		elif existing_entry and entry_doc.table_number:
			cart_item_data["tableNumber"] = entry_doc.table_number
		
		return {
			"success": True,
			"data": {
				"cartItem": cart_item_data,
				"cart": cart_summary
			}
		}
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		return {
			"success": False,
			"error": {
				"code": "RESTAURANT_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
				"message": str(e)
			}
		}
	except Exception as e:
		frappe.log_error("Error in add_to_cart", str(e))
		return {
			"success": False,
			"error": {
				"code": "CART_ADD_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_cart(restaurant_id, session_id=None, coupon_code=None, loyalty_coins=0, order_type=None, latitude=None, longitude=None):
	"""
	GET /api/v1/cart
	Get current cart with detailed pricing Breakdown
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		user = frappe.session.user if frappe.session.user != "Guest" else None
		if not user and not session_id:
			session_id = frappe.session.get("session_id")
		
		filters = {"restaurant": restaurant}
		if user: filters["user"] = user
		elif session_id: filters["session_id"] = session_id
		
		# Get cart entries
		entries = frappe.get_all("Cart Entry", fields=["*"], filters=filters, order_by="creation desc")
		
		# Format cart items
		items = []
		if entries:
			product_names = [e.product for e in entries]
			from flamezo_backend.flamezo.api.products import format_products_for_listing
			products = frappe.get_all("Menu Product", filters={"name": ["in", product_names]}, fields=[
				"name as docname",
				"product_id as id",
				"product_name as name",
				"price",
				"original_price",
				"category_name as category",
				"product_type as type",
				"description",
				"is_vegetarian",
				"calories",
				"estimated_time as estimatedTime",
				"serving_size as servingSize",
				"has_no_media",
				"main_category as mainCategory",
				"display_order",
				"is_active",
				"recommendations",
				"seo_slug"
			])
			formatted_products = format_products_for_listing(products)
			product_map = {p.get("docname"): p for p in formatted_products}
			
			for entry in entries:
				if entry.product not in product_map: continue
				dish = product_map[entry.product]
				customizations = json.loads(entry.customizations) if entry.customizations else {}
				
				items.append({
					"entryId": entry.entry_id,
					"dishId": dish.get("id"),
					"dish": dish,
					"quantity": entry.quantity,
					"customizations": customizations,
					"unitPrice": flt(entry.unit_price),
					"totalPrice": flt(entry.total_price)
				})
		
		# Use the NEW pricing engine for the summary
		from flamezo_backend.flamezo.utils.pricing import calculate_cart_totals
		
		# Find customer if possible (for loyalty and coupon limits)
		customer_id = None
		if user:
			from flamezo_backend.flamezo.utils.customer_helpers import get_platform_customer_from_user
			customer_id = get_platform_customer_from_user(user)

		summary = calculate_cart_totals(
			restaurant=restaurant,
			items=items,
			coupon_code=coupon_code,
			loyalty_coins=flt(loyalty_coins),
			customer=customer_id,
			delivery_type=order_type.capitalize() if order_type else None,
			latitude=latitude,
			longitude=longitude
		)
		
		return {
			"success": True,
			"data": {
				"items": items,
				"summary": summary
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_cart: {str(e)}")
		return {"success": False, "error": {"code": "CART_FETCH_ERROR", "message": str(e)}}



@frappe.whitelist(allow_guest=True)
def update_cart_item(restaurant_id, entry_id, quantity):
	"""
	PATCH /api/v1/cart/items/:entryId
	Update cart item quantity
	Requires restaurant_id for SaaS multi-tenancy
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		if not frappe.db.exists("Cart Entry", entry_id):
			return {
				"success": False,
				"error": {
					"code": "CART_ITEM_NOT_FOUND",
					"message": f"Cart item {entry_id} not found"
				}
			}
		
		entry_doc = frappe.get_doc("Cart Entry", entry_id)
		
		# Validate entry belongs to restaurant
		if entry_doc.restaurant != restaurant:
			return {
				"success": False,
				"error": {
					"code": "CART_ITEM_NOT_FOUND",
					"message": f"Cart item {entry_id} not found for restaurant {restaurant_id}"
				}
			}
		
		entry_doc.quantity = cint(quantity)
		entry_doc.total_price = entry_doc.unit_price * cint(quantity)
		entry_doc.save(ignore_permissions=True)
		
		return {
			"success": True,
			"message": "Cart item updated"
		}
	except Exception as e:
		frappe.log_error(f"Error in update_cart_item: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "CART_UPDATE_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def remove_cart_item(restaurant_id, entry_id):
	"""
	DELETE /api/v1/cart/items/:entryId
	Remove item from cart
	Requires restaurant_id for SaaS multi-tenancy
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		if not frappe.db.exists("Cart Entry", entry_id):
			return {
				"success": False,
				"error": {
					"code": "CART_ITEM_NOT_FOUND",
					"message": f"Cart item {entry_id} not found"
				}
			}
		
		entry_doc = frappe.get_doc("Cart Entry", entry_id)
		
		# Validate entry belongs to restaurant
		if entry_doc.restaurant != restaurant:
			return {
				"success": False,
				"error": {
					"code": "CART_ITEM_NOT_FOUND",
					"message": f"Cart item {entry_id} not found for restaurant {restaurant_id}"
				}
			}
		
		# Use db.delete to avoid Redis Queue dependency
		frappe.db.delete("Cart Entry", {"entry_id": entry_id})
		frappe.db.commit()
		
		return {
			"success": True,
			"message": "Item removed from cart"
		}
	except Exception as e:
		frappe.log_error(f"Error in remove_cart_item: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "CART_REMOVE_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def clear_cart(restaurant_id, session_id=None):
	"""
	DELETE /api/v1/cart
	Clear entire cart for restaurant
	Requires restaurant_id for SaaS multi-tenancy
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		user = frappe.session.user if frappe.session.user != "Guest" else None
		if not user and not session_id:
			session_id = frappe.session.get("session_id")
		
		filters = {"restaurant": restaurant}
		if user:
			filters["user"] = user
		elif session_id:
			filters["session_id"] = session_id
		
		entries = frappe.get_all("Cart Entry", filters=filters)
		entry_ids = [entry.name for entry in entries]
		if entry_ids:
			frappe.db.delete("Cart Entry", {"name": ["in", entry_ids]})
			frappe.db.commit()
		
		return {
			"success": True,
			"message": "Cart cleared"
		}
	except Exception as e:
		frappe.log_error(f"Error in clear_cart: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "CART_CLEAR_ERROR",
				"message": str(e)
			}
		}


# Helper functions

# Handled by customization_helpers


def find_existing_cart_entry(user, session_id, restaurant, dish_id, customizations):
	"""Find existing cart entry with same product, restaurant, and customizations"""
	filters = {"product": dish_id, "restaurant": restaurant}
	if user:
		filters["user"] = user
	elif session_id:
		filters["session_id"] = session_id
	
	entries = frappe.get_all("Cart Entry", filters=filters, fields=["name", "customizations"])
	
	for entry in entries:
		entry_customizations = json.loads(entry.customizations) if entry.customizations else {}
		
		# Compare customizations (simple dict comparison)
		if customizations == entry_customizations:
			return entry.name
	
	return None


def generate_entry_id(dish_id):
	"""
	Generate unique entry ID: {dishId}-{timestamp}-{random}
	dish_id should be the SEO slug (product_id) for frontend consistency.
	"""
	timestamp = int(datetime.now().timestamp())
	random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
	return f"{dish_id}-{timestamp}-{random_str}"


def generate_session_id():
	"""Generate session ID for guest users"""
	return ''.join(random.choices(string.ascii_letters + string.digits, k=32))


def get_cart_summary(user, session_id, restaurant, coupon_code=None, loyalty_coins=0, order_type=None, latitude=None, longitude=None):
	"""Calculate cart summary using centralized pricing engine."""
	filters = {"restaurant": restaurant}
	if user: filters["user"] = user
	elif session_id: filters["session_id"] = session_id
	
	entries = frappe.get_all("Cart Entry", fields=["total_price", "unit_price", "quantity", "product"], filters=filters)
	
	# Prepare items for pricing utility
	items = []
	for entry in entries:
		# Map back to slug (product_id) for pricing engine and frontend consistency
		product_data = frappe.db.get_value("Menu Product", entry.product, ["product_id", "product_name"], as_dict=True)
		slug_id = product_data.get("product_id") if product_data else entry.product
		
		items.append({
			"quantity": entry.quantity,
			"unitPrice": entry.unit_price,
			"dishId": slug_id
		})
	
	# Use the pricing engine
	from flamezo_backend.flamezo.utils.pricing import calculate_cart_totals
	
	# Find customer if possible
	customer_id = None
	if user:
		from flamezo_backend.flamezo.utils.customer_helpers import get_platform_customer_from_user
		customer_id = get_platform_customer_from_user(user)

	return calculate_cart_totals(
		restaurant=restaurant,
		items=items,
		coupon_code=coupon_code,
		loyalty_coins=loyalty_coins,
		customer=customer_id,
		delivery_type=order_type.capitalize() if order_type else None,
		latitude=latitude,
		longitude=longitude
	)



def cint(value):
	"""Convert to integer"""
	from frappe.utils import cint as frappe_cint
	return frappe_cint(value)


def parse_table_number_from_qr(qr_data, restaurant_id):
	"""
	Parse table number from QR code data.
	QR code format: restaurant-id/table-number  OR  base_url/restaurant-id/table-number

	Security rule: if the QR data contains a restaurant-id segment that does NOT match
	the current restaurant, we reject it entirely — we must NOT fall through to the
	plain-number parser, as that would allow cross-restaurant table spoofing.

	Returns table number (int > 0) or None if invalid.
	"""
	try:
		if not qr_data:
			return None

		# Check if QR data matches URL format (contains slashes)
		if "/" in qr_data:
			parts = qr_data.split("/")
			# Handle full URL: base_url/restaurant-id/table-number
			# Handle short format: restaurant-id/table-number
			if len(parts) >= 2:
				# restaurant_id is the second-to-last, table is the last
				qr_restaurant_id = parts[-2]
				table_num_str = parts[-1]

				# If this segment looks like a restaurant slug (not a domain/protocol)
				# match it against the current restaurant.
				# A domain part will contain "." or be "http:"; restaurant IDs won't.
				if "." not in qr_restaurant_id and qr_restaurant_id not in ("http:", "https:", ""):
					if qr_restaurant_id != restaurant_id:
						# Explicitly wrong restaurant — reject, do NOT fall through
						return None
					table_number = cint(table_num_str)
					if table_number > 0:
						return table_number
					return None

		# If format is a plain number (no slashes or unrecognised URL), parse directly
		table_number = cint(qr_data)
		if table_number > 0:
			return table_number

		return None
	except Exception as e:
		frappe.log_error("QR Table Number Parse Error", str(e))
		return None


@frappe.whitelist(allow_guest=True)
def parse_qr_code(qr_data):
	"""
	API endpoint to parse QR code and return table information
	POST /api/method/flamezo_backend.flamezo.api.cart.parse_qr_code
	"""
	try:
		if not qr_data:
			return {
				"success": False,
				"error": {
					"code": "INVALID_QR_CODE",
					"message": "QR code data is required"
				}
			}
		
		# Parse QR code format: base_url/restaurant-id/table-number or restaurant-id/table-number (backward compatibility)
		if "/" not in qr_data:
			return {
				"success": False,
				"error": {
					"code": "INVALID_QR_FORMAT",
					"message": "Invalid QR code format. Expected: base_url/restaurant-id/table-number or restaurant-id/table-number"
				}
			}
		
		parts = qr_data.split("/")
		
		# Handle new format: base_url/restaurant-id/table-number (e.g., https://app.flamezo_backend.com/restaurant-id/1)
		# Or old format: restaurant-id/table-number (backward compatibility)
		if len(parts) >= 3:
			# New format with base URL: extract restaurant_id and table_number from last two parts
			restaurant_id = parts[-2]  # Second to last part
			table_number = cint(parts[-1])  # Last part
		elif len(parts) == 2:
			# Old format: restaurant-id/table-number (backward compatibility)
			restaurant_id = parts[0]
			table_number = cint(parts[1])
		else:
			return {
				"success": False,
				"error": {
					"code": "INVALID_QR_FORMAT",
					"message": "Invalid QR code format. Expected: base_url/restaurant-id/table-number or restaurant-id/table-number"
				}
			}
		
		# Validate table number: must be a positive integer
		if table_number <= 0:
			return {
				"success": False,
				"error": {
					"code": "INVALID_TABLE_NUMBER",
					"message": f"Table number must be a positive integer (got {table_number})"
				}
			}

		# Validate restaurant exists
		if not frappe.db.exists("Restaurant", {"restaurant_id": restaurant_id}):
			return {
				"success": False,
				"error": {
					"code": "RESTAURANT_NOT_FOUND",
					"message": f"Restaurant {restaurant_id} not found"
				}
			}

		# Validate table number is within restaurant's range
		restaurant = frappe.get_doc("Restaurant", {"restaurant_id": restaurant_id})
		if not restaurant.tables or table_number > restaurant.tables:
			return {
				"success": False,
				"error": {
					"code": "INVALID_TABLE_NUMBER",
					"message": f"Table number {table_number} is invalid for this restaurant (max: {restaurant.tables or 0})"
				}
			}
		
		return {
			"success": True,
			"data": {
				"restaurantId": restaurant_id,
				"tableNumber": table_number,
				"qrData": qr_data
			}
		}
	except Exception as e:
		frappe.log_error(f"Error parsing QR code: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "QR_PARSE_ERROR",
				"message": str(e)
			}
		}

