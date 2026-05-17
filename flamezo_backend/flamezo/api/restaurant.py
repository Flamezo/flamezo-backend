# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Restaurant lookup and information
"""

import frappe
from frappe import _
from frappe.utils import get_url
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api, get_restaurant_context


@frappe.whitelist(allow_guest=True)
def get_restaurant_id(restaurant_name):
	"""
	GET /api/method/flamezo_backend.flamezo.api.restaurant.get_restaurant_id
	Get restaurant_id from restaurant_name
	
	Parameters:
	- restaurant_name (required): The restaurant name to lookup
	
	Returns:
	{
		"success": true,
		"data": {
			"restaurant_id": "the-gallery-cafe",
			"restaurant_name": "The Gallery Cafe",
			"is_active": true
		}
	}
	"""
	try:
		if not restaurant_name:
			return {
				"success": False,
				"error": {
					"code": "VALIDATION_ERROR",
					"message": "restaurant_name is required"
				}
			}
		
		# Try to find restaurant by restaurant_name (exact match first)
		restaurant = frappe.db.get_value(
			"Restaurant",
			{"restaurant_name": restaurant_name},
			["name", "restaurant_id", "restaurant_name", "is_active"],
			as_dict=True
		)
		
		# If not found, try case-insensitive search
		if not restaurant:
			restaurants = frappe.get_all(
				"Restaurant",
				filters={"restaurant_name": ["like", f"%{restaurant_name}%"]},
				fields=["name", "restaurant_id", "restaurant_name", "is_active"],
				limit=1
			)
			if restaurants:
				restaurant = restaurants[0]
		
		if not restaurant:
			return {
				"success": False,
				"error": {
					"code": "RESTAURANT_NOT_FOUND",
					"message": f"Restaurant '{restaurant_name}' not found"
				}
			}
		
		return {
			"success": True,
			"data": {
				"restaurant_id": restaurant.restaurant_id,
				"restaurant_name": restaurant.restaurant_name,
				"is_active": bool(restaurant.is_active)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_restaurant_id: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "RESTAURANT_LOOKUP_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_restaurant_info(restaurant_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.restaurant.get_restaurant_info
	Get full restaurant information by restaurant_id
	
	Parameters:
	- restaurant_id (required): The restaurant identifier
	
	Returns:
	{
		"success": true,
		"data": {
			"id": "the-gallery-cafe",
			"name": "The Gallery Cafe",
			"logo": "...",
			"address": "...",
			...
		}
	}
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		restaurant_context = get_restaurant_context(restaurant_id)
		
		if not restaurant_context:
			return {
				"success": False,
				"error": {
					"code": "RESTAURANT_NOT_FOUND",
					"message": f"Restaurant {restaurant_id} not found"
				}
			}
		
		return {
			"success": True,
			"data": restaurant_context
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
		frappe.log_error(f"Error in get_restaurant_info: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "RESTAURANT_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_restaurant_tables(restaurant_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.restaurant.get_restaurant_tables
	Get available tables for a restaurant
	
	Parameters:
	- restaurant_id (required): The restaurant identifier
	
	Returns:
	{
		"success": true,
		"data": {
			"tables": [
				{"value": 1, "label": "Table 1"},
				{"value": 2, "label": "Table 2"},
				...
			]
		}
	}
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Get number of tables from restaurant
		tables_count = frappe.db.get_value("Restaurant", restaurant, "tables")
		
		if not tables_count or tables_count <= 0:
			return {
				"success": True,
				"data": {
					"tables": []
				}
			}
		
		# Generate table options
		tables = []
		for i in range(1, int(tables_count) + 1):
			tables.append({
				"value": i,
				"label": f"Table {i}"
			})
		
		return {
			"success": True,
			"data": {
				"tables": tables
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
		frappe.log_error(f"Error in get_restaurant_tables: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "TABLES_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def list_restaurants(active_only=True):
	"""
	GET /api/method/flamezo_backend.flamezo.api.restaurant.list_restaurants
	Get list of all restaurants
	
	Parameters:
	- active_only (optional, default: true): Only return active restaurants
	
	Returns:
	{
		"success": true,
		"data": {
			"restaurants": [
				{
					"restaurant_id": "the-gallery-cafe",
					"restaurant_name": "The Gallery Cafe",
					"is_active": true
				}
			]
		}
	}
	"""
	try:
		filters = {}
		if active_only:
			filters["is_active"] = 1
		
		restaurants = frappe.get_all(
			"Restaurant",
			filters=filters,
			fields=["restaurant_id", "restaurant_name", "is_active"],
			order_by="restaurant_name"
		)
		
		return {
			"success": True,
			"data": {
				"restaurants": restaurants
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in list_restaurants: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "RESTAURANT_LIST_ERROR",
				"message": str(e)
			}
		}

@frappe.whitelist(allow_guest=True)
def get_restaurant_gallery(restaurant_id):
	"""
	Get selected gallery items for a restaurant (max 25)
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		items = frappe.get_all(
			"Restaurant Gallery Item",
			filters={
				"restaurant": restaurant,
				"is_selected": 1
			},
			fields=["url", "media_type as type", "title", "sort_order"],
			order_by="sort_order asc",
			limit=25
		)
		
		return {
			"success": True,
			"data": {
				"items": items
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_restaurant_gallery: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "GALLERY_FETCH_ERROR",
				"message": str(e)
			}
		}

@frappe.whitelist()
def get_restaurant_media_pool(restaurant_id):
	"""
	Collect all media used by the restaurant across the app
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		media_pool = []
		seen_urls = set()
		
		# 0. Restaurant Branding
		restaurant_doc = frappe.get_doc("Restaurant", restaurant)
		if restaurant_doc.get("logo"):
			media_pool.append({
				"url": restaurant_doc.logo,
				"type": "image",
				"source_title": "Restaurant Logo",
				"source_type": "Branding",
				"category": "Branding"
			})
			seen_urls.add(restaurant_doc.logo)

		# 1. Menu Product Media
		product_media = frappe.db.sql("""
			SELECT pm.media_url as url, pm.media_type as type, p.product_name as source_title, 'Menu Product' as source_type
			FROM `tabProduct Media` pm
			JOIN `tabMenu Product` p ON pm.parent = p.name
			WHERE p.restaurant = %s
		""", (restaurant,), as_dict=1)
		
		for m in product_media:
			if m.url and m.url not in seen_urls:
				m['category'] = "Food & Menu"
				media_pool.append(m)
				seen_urls.add(m.url)

		# 2. Events
		events = frappe.get_all(
			"Event",
			filters={"restaurant": restaurant, "image_src": ["is", "set"]},
			fields=["image_src as url", "title as source_title"]
		)
		
		for e in events:
			if e.url and e.url not in seen_urls:
				media_pool.append({
					"url": e.url,
					"type": "image",
					"source_title": e.source_title,
					"source_type": "Event",
					"category": "Events"
				})
				seen_urls.add(e.url)

		# 3. Existing Gallery Items (both selected and unselected)
		gallery_items = frappe.get_all(
			"Restaurant Gallery Item",
			filters={"restaurant": restaurant},
			fields=["name", "url", "media_type as type", "title as source_title", "is_selected"]
		)
		
		for g in gallery_items:
			if g.url and g.url not in seen_urls:
				media_pool.append({
					"url": g.url,
					"type": g.type.lower(),
					"source_title": g.source_title,
					"source_type": "Gallery",
					"category": "Gallery Uploads",
					"is_in_gallery": True,
					"is_selected": g.is_selected,
					"gallery_item_name": g.name
				})
				seen_urls.add(g.url)
			elif g.url in seen_urls:
				# Mark as already in gallery if it exists there
				for item in media_pool:
					if item['url'] == g.url:
						item['is_in_gallery'] = True
						item['is_selected'] = g.is_selected
						item['gallery_item_name'] = g.name

		return {
			"success": True,
			"data": {
				"media": media_pool
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_restaurant_media_pool: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "MEDIA_POOL_ERROR",
				"message": str(e)
			}
		}
