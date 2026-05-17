# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API helper functions for restaurant validation and context
"""

import frappe
from frappe import _
from flamezo_backend.flamezo.utils.permissions import validate_restaurant_access, get_user_restaurant_ids
from flamezo_backend.flamezo.utils.currency_helpers import get_restaurant_currency_info

# Common metadata paths and scanner targets that should be ignored early
RESERVED_RESTAURANT_IDS = {
	"robots.txt",
	"favicon.ico",
	"sitemap.xml",
	"ads.txt",
	".well-known",
	"webroot",
	"wp-admin",
	"wp-content",
	"cgi-bin",
	".env",
	"administrator",
	"login",
}


def get_restaurant_from_id(restaurant_id):
	"""Get restaurant name from restaurant_id"""
	if not restaurant_id:
		return None
	
	# Skip checks for suspiciously long IDs (likely bot probes)
	if len(str(restaurant_id)) > 50:
		return None
	
	# Try to get by restaurant_id field first
	restaurant = frappe.db.get_value("Restaurant", {"restaurant_id": restaurant_id}, "name")
	
	# If not found, try by name (for backward compatibility)
	if not restaurant:
		restaurant = frappe.db.get_value("Restaurant", {"name": restaurant_id}, "name")
	
	return restaurant


def validate_restaurant_for_api(restaurant_id, user=None, allow_inactive=False):
	"""
	Validate restaurant for API calls
	Returns restaurant name if valid, raises exception if not
	"""
	if not restaurant_id:
		# Use generic message to prevent log title explosion
		frappe.throw(_("Restaurant not found"), exc=frappe.DoesNotExistError)
	
	# Skip reserved IDs early
	id_clean = str(restaurant_id).lower()
	if any(reserved in id_clean for reserved in RESERVED_RESTAURANT_IDS):
		# Silently return a 404 for known scanners/bots
		frappe.throw(_("Restaurant not found"), exc=frappe.DoesNotExistError)
	
	# Get restaurant name
	restaurant = get_restaurant_from_id(restaurant_id)
	
	if not restaurant:
		frappe.throw(_("Restaurant not found"), exc=frappe.DoesNotExistError)
	
	# Check if restaurant is active
	if not allow_inactive and not frappe.db.get_value("Restaurant", restaurant, "is_active"):
		frappe.throw(
			_("Restaurant {0} is not active").format(restaurant_id),
			exc=frappe.ValidationError
		)
	
	# Validate user access (if user provided)
	if user:
		if not validate_restaurant_access(user, restaurant):
			frappe.throw(
				_("You don't have access to restaurant {0}").format(restaurant_id),
				exc=frappe.PermissionError
			)
	
	return restaurant


def get_restaurant_context(restaurant_id):
	"""Get restaurant context for API responses"""
	restaurant = get_restaurant_from_id(restaurant_id)
	
	if not restaurant:
		return None
	
	restaurant_doc = frappe.get_doc("Restaurant", restaurant)
	
	# Get currency info with symbol
	currency_info = get_restaurant_currency_info(restaurant)
	
	return {
		"id": restaurant_doc.restaurant_id,
		"name": restaurant_doc.restaurant_name,
		"logo": restaurant_doc.logo,
		"address": restaurant_doc.address,
		"city": restaurant_doc.city,
		"state": restaurant_doc.state,
		"zip_code": restaurant_doc.zip_code,
		"country": restaurant_doc.country,
		"tax_rate": restaurant_doc.tax_rate,
		"default_delivery_fee": restaurant_doc.default_delivery_fee,
		"currency": currency_info.get("currency", restaurant_doc.currency or "INR"),
		"currencySymbol": currency_info.get("symbol", "₹"),
		"currencySymbolOnRight": currency_info.get("symbolOnRight", False),
		"timezone": restaurant_doc.timezone,
		"google_map_url": restaurant_doc.google_map_url,
		"plan_type": restaurant_doc.plan_type or "SILVER"
	}



def validate_product_belongs_to_restaurant(product_id, restaurant_id):
	"""Validate that product belongs to restaurant"""
	restaurant = get_restaurant_from_id(restaurant_id)
	
	if not restaurant:
		return False
	
	# Resolve product name if it's a slug/ID
	actual_product = get_product_from_id(product_id, restaurant)
	if not actual_product:
		return False
		
	product_restaurant = frappe.db.get_value("Menu Product", actual_product, "restaurant")
	
	return product_restaurant == restaurant


def get_product_from_id(product_id, restaurant=None):
	"""
	Get Menu Product name (docname) from product_id or slug.
	If restaurant is provided, ensures the product belongs to that restaurant.
	"""
	if not product_id:
		return None
	
	# 1. Try by name directly (hash)
	if frappe.db.exists("Menu Product", product_id):
		# If restaurant provided, verify it belongs
		if restaurant:
			if frappe.db.get_value("Menu Product", product_id, "restaurant") == restaurant:
				return product_id
			# If it's a valid hash but for wrong restaurant, continue to slug check
		else:
			return product_id
		
	# 2. Try by product_id field
	filters = {"product_id": product_id}
	if restaurant:
		filters["restaurant"] = restaurant
	
	name = frappe.db.get_value("Menu Product", filters, "name")
	
	# 3. Try by seo_slug if still not found
	if not name:
		filters = {"seo_slug": product_id}
		if restaurant:
			filters["restaurant"] = restaurant
		name = frappe.db.get_value("Menu Product", filters, "name")
		
	return name


def validate_all_products_belong_to_restaurant(product_ids, restaurant_id):
	"""Validate that all products belong to restaurant"""
	restaurant = get_restaurant_from_id(restaurant_id)
	
	if not restaurant:
		return False
	
	# Get all products
	products = frappe.get_all(
		"Menu Product",
		filters={"name": ["in", product_ids]},
		fields=["name", "restaurant"]
	)
	
	# Check all belong to restaurant
	for product in products:
		if product.restaurant != restaurant:
			return False
	
	return True


def get_restaurant_from_product(product_id):
	"""Get restaurant from product"""
	restaurant = frappe.db.get_value("Menu Product", product_id, "restaurant")
	return restaurant


def get_restaurant_from_category(category_id):
	"""Get restaurant from category"""
	restaurant = frappe.db.get_value("Menu Category", category_id, "restaurant")
	return restaurant


