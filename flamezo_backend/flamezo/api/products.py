# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

"""
API endpoints for Products/Dishes
Matches format from BACKEND_API_DOCUMENTATION.md
"""

import frappe
from frappe import _
from frappe.utils import flt, cint, get_url

from flamezo_backend.flamezo.utils.api_helpers import (
	validate_restaurant_for_api,
	get_product_from_id
)
from flamezo_backend.flamezo.media.utils import get_media_asset_data, bulk_get_media_asset_data
from flamezo_backend.flamezo.utils.currency_helpers import get_restaurant_currency_info
from flamezo_backend.flamezo.utils.customization_helpers import get_customization_options_map, load_product_customizations
from flamezo_backend.flamezo.utils.addon_group_helpers import bulk_load_addon_groups, format_addon_groups_for_api
from flamezo_backend.flamezo.api import dish_attributes as dish_attrs
import json
from collections import defaultdict


def invalidate_product_cache(doc, method=None):
	"""Invalidates caches associated with a Menu Product when updated"""
	import time
	outlet_id = doc.get("outlet") or doc.get("outlet_id")
	if outlet_id:
		frappe.cache().delete_key(f"top_picks:{outlet_id}")
		frappe.cache().delete_key(f"chef_special:{outlet_id}")
		# Bump version keys so all paginated product + category caches become stale
		ts = str(int(time.time()))
		frappe.cache().set_value(f"products_v:{outlet_id}", ts, expires_in_sec=7200)
		frappe.cache().set_value(f"cats_v:{outlet_id}", ts, expires_in_sec=7200)


@frappe.whitelist(allow_guest=True)
def get_top_picks(outlet_id):
	"""
	GET /api/v1/top-picks
	Optimized Top Picks API with Caching and Priority Selection.
	Priority:
	1. Explicit top-picks
	2. Items with media (has_no_media=0)
	3. Newest items (creation desc)
	Stable results (no randomness).
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(outlet_id)

		# Use cache for performance
		cache_key = f"top_picks:{outlet_id}"
		cached_response = frappe.cache().get_value(cache_key)
		if cached_response:
			return json.loads(cached_response)

		# Strict media prioritization: 
		# Only return non-media products if ABSOLUTELY no media products exist for this restaurant.
		has_any_media = frappe.db.exists("Menu Product", {"outlet": restaurant, "is_active": 1, "has_no_media": 0})
		media_filter = " AND has_no_media = 0" if has_any_media else ""
		
		# Single prioritized query for all fallback logic
		# 1. product_type == 'top-picks' gets highest priority (0)
		# 2. Stable order by display_order and creation date
		products = frappe.db.sql(f"""
			SELECT 
				name as docname, product_id as id, product_name as name, price, original_price,
				category_name as category, product_type as type, description, is_vegetarian,
				dietary_attributes,
				calories, estimated_time as estimatedTime, serving_size as servingSize,
				has_no_media, main_category as mainCategory, display_order, is_active,
				recommendations
			FROM `tabMenu Product`
			WHERE
				outlet = %s AND is_active = 1 {media_filter}
			ORDER BY 
				(CASE WHEN product_type = 'top-picks' THEN 0 ELSE 1 END) ASC,
				display_order ASC,
				creation DESC
			LIMIT 10
		""", (restaurant,), as_dict=True)

		# Format products with media only (minimal payload for fast home page)
		formatted_products = format_products_for_listing_minimal(products)
		
		# Get currency info for restaurant
		currency_info = get_restaurant_currency_info(restaurant)
		
		result = {
			"success": True,
			"data": {
				"products": formatted_products,
				"currency": currency_info.get("currency", "INR"),
				"currencySymbol": currency_info.get("symbol", "₹"),
				"currencySymbolOnRight": currency_info.get("symbolOnRight", False)
			}
		}

		# Cache results for 1 hour
		frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=3600)
		
		return result
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		return {
			"success": False,
			"error": {
				"code": "OUTLET_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
				"message": str(e)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_top_picks: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "TOP_PICKS_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_chef_special(outlet_id):
	"""
	GET — Chef's Special list. ALWAYS returns a usable list (min 5 when the menu has
	enough active items): the merchant's explicitly tagged 'chef-special' items first,
	then premium fallback picks of our own so the section is never empty / too short.

	All of this logic lives here (backend) — the frontend just renders the list.
	Fallback priority for the "our own" items:
	  1. tagged chef-special
	  2. NOT top-picks (so Chef's Special doesn't duplicate Top Picks)
	  3. premium feel — higher price first, then display_order, then newest
	Media-prioritized + cached + stable (no randomness).
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)

		cache_key = f"chef_special:{outlet_id}"
		cached_response = frappe.cache().get_value(cache_key)
		if cached_response:
			return json.loads(cached_response)

		# Rank by ACTUAL media (the `has_no_media` flag is unreliable / stale) so the
		# list isn't collapsed to a handful of items. No hard media filter — we still
		# reach the min count even if some items lack media (rendered with a fallback).
		products = frappe.db.sql("""
			SELECT
				name as docname, product_id as id, product_name as name, price, original_price,
				category_name as category, product_type as type, description, is_vegetarian,
				dietary_attributes,
				calories, estimated_time as estimatedTime, serving_size as servingSize,
				has_no_media, main_category as mainCategory, display_order, is_active,
				recommendations
			FROM `tabMenu Product`
			WHERE
				outlet = %s AND is_active = 1
			ORDER BY
				(CASE WHEN product_type = 'chef-special' THEN 0 ELSE 1 END) ASC,
				(CASE WHEN EXISTS (
					SELECT 1 FROM `tabProduct Media` pm WHERE pm.parent = `tabMenu Product`.name
				) THEN 0 ELSE 1 END) ASC,
				(CASE WHEN product_type = 'top-picks' THEN 1 ELSE 0 END) ASC,
				price DESC,
				display_order ASC,
				creation DESC
			LIMIT 8
		""", (restaurant,), as_dict=True)

		formatted_products = format_products_for_listing_minimal(products)
		currency_info = get_restaurant_currency_info(restaurant)

		result = {
			"success": True,
			"data": {
				"products": formatted_products,
				"currency": currency_info.get("currency", "INR"),
				"currencySymbol": currency_info.get("symbol", "₹"),
				"currencySymbolOnRight": currency_info.get("symbolOnRight", False)
			}
		}

		# Cache for 1 hour (same as top picks)
		frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=3600)

		return result
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		return {
			"success": False,
			"error": {
				"code": "OUTLET_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
				"message": str(e)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_chef_special: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "CHEF_SPECIAL_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_products(outlet_id, category=None, type=None, vegetarian=None, search=None, page=1, limit=50, include_inactive=0):
	"""
	GET /api/v1/products
	Get all products/dishes with filters and pagination
	Requires outlet_id for SaaS multi-tenancy
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(outlet_id)

		# ── Redis cache (skip for search queries — unbounded key space) ──
		page = cint(page) or 1
		limit = cint(limit) or 50
		if not search and not cint(include_inactive):
			cache_version = frappe.cache().get_value(f"products_v:{restaurant}") or "0"
			cache_key = (
				f"products_v2:{restaurant}:{cache_version}"
				f":{category or ''}:{type or ''}:{vegetarian if vegetarian is not None else ''}"
				f":p{page}:l{limit}"
			)
			cached = frappe.cache().get_value(cache_key)
			if cached:
				return json.loads(cached)
		else:
			cache_key = None

		# Build filters
		filters = {"outlet": restaurant}
		if not cint(include_inactive):
			filters["is_active"] = 1
		
		if category:
			# Resolve category param (display name or category_id slug) to stable Frappe docnames.
			# Filtering by the `category` Link field (docname) is immune to renames because
			# the docname is a hash that never changes — unlike `category_name` (fetch_from)
			# which Frappe does NOT auto-propagate to existing product records on rename.
			cat_docnames = frappe.get_all(
				"Menu Category",
				filters={"outlet": restaurant, "category_name": category},
				pluck="name"
			)
			if not cat_docnames:
				# Fallback: match by category_id slug (frontend may send either)
				cat_docnames = frappe.get_all(
					"Menu Category",
					filters={"outlet": restaurant, "category_id": category},
					pluck="name"
				)
			if cat_docnames:
				# Include sub-categories so parent selection returns all nested products
				sub_docnames = frappe.get_all(
					"Menu Category",
					filters={"parent_category": ["in", cat_docnames]},
					pluck="name"
				)
				all_docnames = cat_docnames + sub_docnames
				filters["category"] = ["in", all_docnames]
			else:
				filters["category"] = "__no_match__"
		
		if type:
			filters["product_type"] = type
		
		if vegetarian is not None:
			filters["is_vegetarian"] = cint(vegetarian)
		
		# Search filter
		or_filters = {}
		if search:
			or_filters = {
				"product_name": ["like", f"%{search}%"],
				"description": ["like", f"%{search}%"],
				"product_id": ["like", f"%{search}%"]
			}
		
		# Pagination
		start = (page - 1) * limit
		
		# Get products
		products = frappe.get_all(
			"Menu Product",
			fields=[
				"name as docname",
				"product_id as id",
				"product_name as name",
				"price",
				"original_price",
				"category_name as category",
				"product_type as type",
				"description",
				"is_vegetarian",
				"dietary_attributes",
				"calories",
				"estimated_time as estimatedTime",
				"serving_size as servingSize",
				"has_no_media",
				"main_category as mainCategory",
				"display_order",
				"is_active",
				"recommendations",
				"seo_slug"
			],
			filters=filters,
			or_filters=or_filters if or_filters else None,
			limit_start=start,
			limit_page_length=limit,
			order_by="display_order, product_name"
		)
		
		# Get total count for pagination
		if or_filters and search:
			# Use SQL COUNT to avoid fetching all rows just to count
			like = f"%{search}%"
			where_parts = ["`tabMenu Product`.outlet = %s"]
			params = [restaurant]
			if not cint(include_inactive):
				where_parts.append("`tabMenu Product`.is_active = 1")
			if filters.get("category"):
				cat = filters["category"]
				if isinstance(cat, list) and cat[0] == "in":
					placeholders = ",".join(["%s"] * len(cat[1]))
					where_parts.append(f"`tabMenu Product`.category IN ({placeholders})")
					params.extend(cat[1])
				else:
					where_parts.append("`tabMenu Product`.category = %s")
					params.append(cat)
			if type:
				where_parts.append("`tabMenu Product`.product_type = %s")
				params.append(type)
			if vegetarian is not None:
				where_parts.append("`tabMenu Product`.is_vegetarian = %s")
				params.append(cint(vegetarian))
			params += [like, like, like]
			where_clause = " AND ".join(where_parts) + (
				" AND (`tabMenu Product`.product_name LIKE %s"
				" OR `tabMenu Product`.description LIKE %s"
				" OR `tabMenu Product`.product_id LIKE %s)"
			)
			total = frappe.db.sql(
				f"SELECT COUNT(*) FROM `tabMenu Product` WHERE {where_clause}", params
			)[0][0]
		else:
			total = frappe.db.count("Menu Product", filters=filters)

		# Format products with media and customizations using bulk-loaded child tables
		formatted_products = format_products_for_listing(products)

		# Calculate pagination
		total_pages = (total + limit - 1) // limit if limit > 0 else 1

		# Get currency info for restaurant
		currency_info = get_restaurant_currency_info(restaurant)

		result = {
			"success": True,
			"data": {
				"products": formatted_products,
				"pagination": {
					"page": page,
					"limit": limit,
					"total": total,
					"totalPages": total_pages
				},
				"currency": currency_info.get("currency", "INR"),
				"currencySymbol": currency_info.get("symbol", "₹"),
				"currencySymbolOnRight": currency_info.get("symbolOnRight", False)
			}
		}
		if cache_key:
			frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=300)
		return result
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		return {
			"success": False,
			"error": {
				"code": "OUTLET_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
				"message": str(e)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_products: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "PRODUCT_FETCH_ERROR",
				"message": str(e)
			}
		}



def format_products_for_listing(products):
	"""
	Full version of product formatting that includes nested data
	(customizations and recommendations) for the main menu page.
	"""
	if not products:
		return []

	product_names = [product["docname"] for product in products if product.get("docname")]
	media_by_product = get_product_media_map(product_names)

	# Bulk-load all Media Assets + Variants in 2 queries instead of 2×N (eliminates N+1)
	all_media_items = [m for ml in media_by_product.values() for m in ml]
	media_asset_cache = bulk_get_media_asset_data("Product Media", all_media_items)

	questions_by_product, question_names = get_customization_questions_map(product_names)
	options_by_question = get_customization_options_map(question_names)

	# Load addon groups (new system) in bulk
	addon_groups_by_product = bulk_load_addon_groups(product_names)

	formatted_products = []
	for product in products:
		docname = product.get("docname")
		formatted = format_product_from_row(
			product,
			media_by_product.get(docname, []),
			questions_by_product.get(docname, []),
			options_by_question,
			media_asset_cache=media_asset_cache,
		)

		# Attach addon groups (new system)
		product_addon_groups = addon_groups_by_product.get(docname, [])
		if product_addon_groups:
			formatted["addonGroups"] = format_addon_groups_for_api(product_addon_groups)
			formatted["addon_groups"] = formatted["addonGroups"]
			# Set hasCustomizations if either old or new system has data
			formatted["hasCustomizations"] = True
		elif not formatted.get("hasCustomizations"):
			formatted["hasCustomizations"] = False

		formatted_products.append(formatted)

	return formatted_products



def format_products_for_listing_minimal(products):
	"""
	Minimal version of product formatting that excludes heavy nested data
	(customizations and recommendations) for fast home page access.
	"""
	if not products:
		return []

	product_names = [product["docname"] for product in products if product.get("docname")]
	media_by_product = get_product_media_map(product_names)

	# Bulk-load all Media Assets + Variants in 2 queries instead of 2×N (eliminates N+1)
	all_media_items = [m for ml in media_by_product.values() for m in ml]
	media_asset_cache = bulk_get_media_asset_data("Product Media", all_media_items)

	# Fetch which products have customizations (bulk check)
	customization_data = frappe.get_all(
		"Customization Question",
		filters={
			"parent": ["in", product_names],
			"parenttype": "Menu Product",
			"parentfield": "customization_questions"
		},
		fields=["parent"]
	)
	has_customizations_set = {row["parent"] for row in customization_data}

	formatted_products = []
	for product in products:
		formatted_products.append(
			format_product_from_row_minimal(
				product,
				media_by_product.get(product.get("docname"), []),
				product.get("docname") in has_customizations_set,
				media_asset_cache=media_asset_cache,
			)
		)

	return formatted_products


def get_product_media_map(product_names):
	media_by_product = defaultdict(list)
	if not product_names:
		return media_by_product

	media_rows = frappe.get_all(
		"Product Media",
		filters={
			"parent": ["in", product_names],
			"parenttype": "Menu Product",
			"parentfield": "product_media"
		},
		fields=["name", "parent", "media_url", "media_type", "display_order", "alt_text", "caption"],
		order_by="parent asc, display_order asc, idx asc"
	)

	for media_row in media_rows:
		media_by_product[media_row["parent"]].append(media_row)

	return media_by_product


def get_customization_questions_map(product_names):
	questions_by_product = defaultdict(list)
	question_names = []
	if not product_names:
		return questions_by_product, question_names

	question_rows = frappe.get_all(
		"Customization Question",
		filters={
			"parent": ["in", product_names],
			"parenttype": "Menu Product",
			"parentfield": "customization_questions"
		},
		fields=["name", "parent", "question_id", "title", "subtitle", "question_type", "is_required", "display_order"],
		order_by="parent asc, display_order asc, idx asc"
	)

	for question_row in question_rows:
		questions_by_product[question_row["parent"]].append(question_row)
		question_names.append(question_row["name"])

	return questions_by_product, question_names


# Handled by customization_helpers



def format_product_from_row(product_row, media_rows, customization_questions, options_by_question, media_asset_cache=None):
	"""
	Full row formatting including customizations and recommendations.
	"""
	# Start with the same base as minimal
	product = format_product_from_row_minimal(
		product_row,
		media_rows,
		has_customizations=len(customization_questions) > 0,
		media_asset_cache=media_asset_cache,
	)
	
	# Add customizations (Full version)
	if customization_questions:
		questions = []
		for q in customization_questions:
			q_data = {
				"id": q.get("question_id"),
				"question_id": q.get("question_id"),
				"name": q.get("name"),
				"title": q.get("title"),
				"question_type": q.get("question_type"),
				"type": q.get("question_type"),
				"is_required": bool(q.get("is_required")),
				"required": bool(q.get("is_required")),
				"display_order": cint(q.get("display_order")),
				"displayOrder": cint(q.get("display_order"))
			}

			if q.get("subtitle"):
				q_data["subtitle"] = q.get("subtitle")
				
			options = []
			for opt in options_by_question.get(q.get("name"), []):
				opt_data = {
					"id": opt.get("option_id"),
					"option_id": opt.get("option_id"),
					"name": opt.get("name"),
					"label": opt.get("label"),
					"price": flt(opt.get("price")) or 0,
					"display_order": cint(opt.get("display_order")),
					"displayOrder": cint(opt.get("display_order"))
				}

				if opt.get("is_vegetarian") is not None:
					opt_data["isVegetarian"] = bool(opt.get("is_vegetarian"))
					opt_data["is_vegetarian"] = bool(opt.get("is_vegetarian"))
				if opt.get("is_default"):
					opt_data["isDefault"] = True
					opt_data["is_default"] = True
				options.append(opt_data)
			
			q_data["options"] = options
			questions.append(q_data)
		
		if questions:
			product["customizationQuestions"] = questions
			product["customization_questions"] = questions

	# Add recommendations
	recs = product_row.get("recommendations")
	if recs:
		try:
			recommendations = json.loads(recs) if isinstance(recs, str) else recs
			if recommendations and isinstance(recommendations, list):
				ids = [r.get("id") for r in recommendations if isinstance(r, dict) and r.get("id")]
				if ids:
					product["recommendedDishIds"] = ids
					product["recommendedProducts"] = ids
		except Exception:
			pass

	return product



def format_product_from_row_minimal(product_row, media_rows=None, has_customizations=False, media_asset_cache=None):
	"""
	Minimal row formatting excluding customizations and recommendations.
	"""
	product = {
		"id": product_row["id"],
		"name": product_row["name"],
		# No selling price set → show the MRP (original_price) as the price.
		"price": flt(product_row.get("price")) or flt(product_row.get("original_price") or 0),
		"category": product_row.get("category"),
		"description": product_row.get("description") or "",
		"isVegetarian": bool(product_row.get("is_vegetarian")),
		"calories": cint(product_row.get("calories")) or 0,
		"servingSize": product_row.get("servingSize") or "1",
		"displayOrder": cint(product_row.get("display_order")) if product_row.get("display_order") is not None else 0,
		"isActive": bool(product_row.get("is_active")) if product_row.get("is_active") is not None else True,
		"hasCustomizations": has_customizations,
		"docname": product_row.get("docname") or product_row.get("name")
	}

	if product_row.get("original_price"):
		product["originalPrice"] = flt(product_row.get("original_price"))

	attrs = dish_attrs.resolve(product_row.get("dietary_attributes"))
	if attrs:
		product["dietaryAttributes"] = attrs
		product["dietaryAttributeKeys"] = [a["key"] for a in attrs]
		product["cardBadges"] = dish_attrs.card_badges(product_row.get("dietary_attributes"))

	if product_row.get("type"):
		product["type"] = product_row.get("type")

	if product_row.get("estimatedTime"):
		product["estimatedTime"] = cint(product_row.get("estimatedTime"))

	if product_row.get("mainCategory"):
		product["mainCategory"] = product_row.get("mainCategory")

	media = []
	for media_item in media_rows or []:
		if media_asset_cache is not None:
			media_asset_data = media_asset_cache.get(media_item.get("name")) or {
				"url": media_item.get("media_url") or "",
				"blur_placeholder": None,
				"media_id": None,
				"variants": {},
				"srcset": None,
			}
		else:
			media_asset_data = get_media_asset_data(
				"Product Media",
				media_item.get("name"),
				f"product_{media_item.get('media_type') or 'image'}",
				media_item.get("media_url")
			)

		# Ensure URL is absolute if it's a local file
		url = media_asset_data["url"]
		if url and url.startswith("/files/"):
			url = get_url(url)

		if url:
			media_data = {
				"url": url,
				"type": media_item.get("media_type") or "image",
				"blurPlaceholder": media_asset_data.get("blur_placeholder"),
				"variants": media_asset_data.get("variants", {}),
				"srcset": media_asset_data.get("srcset")
			}

			if media_item.get("alt_text"):
				media_data["altText"] = media_item.get("alt_text")
			if media_item.get("caption"):
				media_data["caption"] = media_item.get("caption")
			if media_item.get("display_order"):
				media_data["displayOrder"] = media_item.get("display_order")

			media.append(media_data)

	product["media"] = media
	product["product_media"] = media_rows # Use the original rows for dashboard compatibility
	if not media and product_row.get("has_no_media"):
		product["hasNoMedia"] = True

	return product


@frappe.whitelist(allow_guest=True)
def get_product(outlet_id, product_id):
	"""
	GET /api/v1/products/:productId
	Get single product by ID
	Requires outlet_id for SaaS multi-tenancy
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(outlet_id)
		
		# Resolve product name if it's a slug/ID
		actual_product_id = get_product_from_id(product_id, restaurant)
		
		if not actual_product_id:
			return {
				"success": False,
				"error": {
					"code": "PRODUCT_NOT_FOUND",
					"message": f"Product with ID {product_id} not found"
				}
			}
		
		# Use actual document name for operations
		product_id = actual_product_id
		product_doc = frappe.get_doc("Menu Product", product_id)
		
		# Validate product belongs to restaurant
		if product_doc.outlet != restaurant:
			return {
				"success": False,
				"error": {
					"code": "PRODUCT_NOT_FOUND",
					"message": f"Product {product_id} not found for restaurant {outlet_id}"
				}
			}
		
		if not product_doc.is_active:
			return {
				"success": False,
				"error": {
					"code": "PRODUCT_NOT_ACTIVE",
					"message": f"Product {product_id} is not active"
				}
			}
		
		formatted_product = format_product(product_doc)
		
		# Get currency info for restaurant
		currency_info = get_restaurant_currency_info(restaurant)
		
		return {
			"success": True,
			"data": {
				"product": formatted_product,
				"currency": currency_info.get("currency", "INR"),
				"currencySymbol": currency_info.get("symbol", "₹"),
				"currencySymbolOnRight": currency_info.get("symbolOnRight", False)
			}
		}
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		return {
			"success": False,
			"error": {
				"code": "OUTLET_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
				"message": str(e)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_product: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "PRODUCT_FETCH_ERROR",
				"message": str(e)
			}
		}


def format_product(product_doc):
	"""
	Format a Menu Product document to match API documentation format
	"""
	# Base product data
	product = {
		"id": product_doc.product_id,
		"name": product_doc.product_name,
		# No selling price set → show the MRP (original_price) as the price.
		"price": flt(product_doc.price) or flt(product_doc.original_price or 0),
		"category": product_doc.category_name,
		"description": product_doc.description or "",
		"isVegetarian": bool(product_doc.is_vegetarian),
		"calories": cint(product_doc.calories) or 0,
		"servingSize": product_doc.serving_size or "1",
		"displayOrder": cint(product_doc.display_order) or 0,
		"isActive": bool(product_doc.is_active) if hasattr(product_doc, 'is_active') else True,
		"seo_slug": product_doc.seo_slug
	}

	# Dietary attributes (badges) — always expose keys so the merchant edit form
	# knows what's currently selected, even when the list is empty.
	attr_keys = dish_attrs.parse_keys(product_doc.get("dietary_attributes"))
	product["dietaryAttributeKeys"] = attr_keys
	if attr_keys:
		product["dietaryAttributes"] = dish_attrs.resolve(product_doc.get("dietary_attributes"))
		product["cardBadges"] = dish_attrs.card_badges(product_doc.get("dietary_attributes"))

	# Optional fields
	if product_doc.original_price:
		product["originalPrice"] = flt(product_doc.original_price)
	
	if product_doc.product_type:
		product["type"] = product_doc.product_type
	
	if product_doc.estimated_time:
		product["estimatedTime"] = cint(product_doc.estimated_time)
	
	if product_doc.main_category:
		product["mainCategory"] = product_doc.main_category
	
	# Media - Using centralized Media Asset utility
	media = []
	if product_doc.product_media:
		for media_item in product_doc.product_media:
			# Use centralized utility to get Media Asset data
			media_asset_data = get_media_asset_data(
				"Product Media",
				media_item.name,
				f"product_{media_item.media_type or 'image'}",
				media_item.media_url
			)
			
			if media_asset_data["url"]:
				media_data = {
					"url": media_asset_data["url"],
					"type": media_item.media_type or "image",
					"blurPlaceholder": media_asset_data.get("blur_placeholder"),
					"variants": media_asset_data.get("variants", {}),
					"srcset": media_asset_data.get("srcset")
				}
				
				if media_item.alt_text:
					media_data["altText"] = media_item.alt_text
				if media_item.caption:
					media_data["caption"] = media_item.caption
				if media_item.display_order:
					media_data["displayOrder"] = media_item.display_order
				
				media.append(media_data)
	
	if media:
		product["media"] = media
	elif product_doc.has_no_media:
		product["hasNoMedia"] = True
	
	# Customization Questions - Optimized bulk loading
	if product_doc.customization_questions:
		# Attach options to questions
		load_product_customizations(product_doc)
		
		customization_questions = []
		for question in product_doc.customization_questions:
			question_data = {
				"id": question.question_id,
				"title": question.title,
				"type": question.question_type,
				"required": bool(question.is_required),
				"displayOrder": cint(question.display_order)
			}
			
			if question.subtitle:
				question_data["subtitle"] = question.subtitle
			
			options = []
			for opt in question.get("options", []):
				option_data = {
					"id": opt.option_id,
					"label": opt.label,
					"price": flt(opt.price) or 0,
					"displayOrder": cint(opt.display_order)
				}
				
				if opt.is_vegetarian is not None:
					option_data["isVegetarian"] = bool(opt.is_vegetarian)
				
				if opt.is_default:
					option_data["isDefault"] = True
				
				options.append(option_data)
			
			if options:
				question_data["options"] = options
			
			customization_questions.append(question_data)
		
		if customization_questions:
			product["customizationQuestions"] = customization_questions
	
	# Recommendations
	if hasattr(product_doc, 'recommendations') and product_doc.recommendations:
		try:
			recommendations = (
				json.loads(product_doc.recommendations)
				if isinstance(product_doc.recommendations, str)
				else product_doc.recommendations
			)
			if recommendations and isinstance(recommendations, list):
				# Keep full objects for internal / admin use
				product["recommendations"] = recommendations

				# Frontend contract (see RECOMMENDATIONS_API.md):
				# - recommendedDishIds: primary field, array of dish IDs
				# - recommendedProducts: backward-compatible alias with the same IDs
				ids = [r.get("id") for r in recommendations if isinstance(r, dict) and r.get("id")]
				if ids:
					product["recommendedDishIds"] = ids
					product["recommendedProducts"] = ids
		except Exception:
			# If JSON parsing fails, skip recommendations gracefully
			pass
	
	return product

@frappe.whitelist(allow_guest=True)
def get_product_by_slug(outlet_id, slug):
	"""
	GET /api/method/flamezo_backend.flamezo.api.products.get_product_by_slug
	Get single product by SEO slug
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		
		# Find product by slug
		product = frappe.db.get_value(
			"Menu Product",
			{"outlet": restaurant, "seo_slug": slug, "is_active": 1},
			"name"
		)
		
		if not product:
			return {
				"success": False,
				"error": {
					"code": "PRODUCT_NOT_FOUND",
					"message": f"Product with slug '{slug}' not found"
				}
			}
		
		# Reuse get_product logic
		return get_product(outlet_id, product)
		
	except Exception as e:
		frappe.log_error(f"Error in get_product_by_slug: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "PRODUCT_FETCH_ERROR",
				"message": str(e)
			}
		}

@frappe.whitelist()
def update_product_order(product_orders):
	"""
	POST /api/method/flamezo_backend.flamezo.api.products.update_product_order
	Update the display order for multiple products
	product_orders: list of {"name": "...", "display_order": ...} or JSON string
	"""
	try:
		if isinstance(product_orders, str):
			product_orders = json.loads(product_orders)
			
		for order in product_orders:
			# Use docname (Frappe name) for updating
			frappe.db.set_value("Menu Product", order["name"], "display_order", order["display_order"])
			
		frappe.db.commit()
		
		# Invalidate cache since order changed
		if product_orders:
			# Get restaurant of first product to invalidate cache
			restaurant = frappe.db.get_value("Menu Product", product_orders[0]["name"], "outlet")
			if restaurant:
				frappe.cache().delete_key(f"top_picks:{restaurant}")

		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error in update_product_order: {str(e)}")
		return {"success": False, "error": str(e)}


def _round_price(amount, round_to):
	"""Round `amount` to the nearest multiple of `round_to`. round_to <= 0 means no rounding."""
	amount = flt(amount)
	round_to = flt(round_to)
	if round_to <= 0:
		return round(amount, 2)
	return round(amount / round_to) * round_to


def _apply_price_rule(current, mode, value, direction, round_to):
	"""
	Compute a new price from `current`.
	mode: "flat" (add/subtract ₹value) or "percent" (add/subtract value% of current).
	direction: "increase" or "decrease".
	Result is floored at 0 and rounded to the nearest `round_to`.
	"""
	current = flt(current)
	value = flt(value)
	sign = -1 if direction == "decrease" else 1

	if mode == "percent":
		delta = current * (value / 100.0)
	else:  # flat
		delta = value

	new_price = current + (sign * delta)
	if new_price < 0:
		new_price = 0
	return _round_price(new_price, round_to)


@frappe.whitelist()
def bulk_update_prices(
	outlet_id,
	mode,
	value,
	direction="increase",
	scope="all",
	categories=None,
	product_ids=None,
	round_to=1,
	include_original_price=1,
	dry_run=0,
):
	"""
	POST /api/method/flamezo_backend.flamezo.api.products.bulk_update_prices

	Bulk-adjust the price of many Menu Products at once (e.g. a menu-wide hike
	or a GST %). Update `price`, and optionally `original_price` when it is set.

	mode:      "flat"    -> add/subtract ₹`value` from each price
	           "percent" -> add/subtract `value`% of each price (GST-style)
	direction: "increase" | "decrease"
	scope:     "all"      -> every product in the restaurant
	           "category" -> products whose `category` is in `categories`
	           "selected" -> products whose docname is in `product_ids`
	round_to:  round each result to the nearest multiple (1 = nearest ₹1, 0 = none)
	include_original_price: also adjust original_price when > 0 (preserves discounts)
	dry_run:   if truthy, only return a preview — nothing is written
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id, user=frappe.session.user)

		mode = (mode or "").strip().lower()
		direction = (direction or "increase").strip().lower()
		scope = (scope or "all").strip().lower()
		value = flt(value)
		round_to = flt(round_to)
		include_original_price = cint(include_original_price)
		dry_run = cint(dry_run)

		if mode not in ("flat", "percent"):
			return {"success": False, "error": "mode must be 'flat' or 'percent'"}
		if direction not in ("increase", "decrease"):
			return {"success": False, "error": "direction must be 'increase' or 'decrease'"}
		if value <= 0:
			return {"success": False, "error": "value must be greater than 0"}
		if mode == "percent" and value > 1000:
			return {"success": False, "error": "percent value is unrealistically large"}

		if isinstance(categories, str):
			categories = json.loads(categories) if categories.strip().startswith("[") else [categories]
		if isinstance(product_ids, str):
			product_ids = json.loads(product_ids) if product_ids.strip().startswith("[") else [product_ids]

		filters = {"outlet": restaurant}
		if scope == "category":
			if not categories:
				return {"success": False, "error": "categories are required for scope 'category'"}
			filters["category"] = ["in", categories]
		elif scope == "selected":
			if not product_ids:
				return {"success": False, "error": "product_ids are required for scope 'selected'"}
			filters["name"] = ["in", product_ids]

		rows = frappe.get_all(
			"Menu Product",
			filters=filters,
			fields=["name", "product_name", "price", "original_price"],
		)

		samples = []
		updated = 0
		for row in rows:
			old_price = flt(row.price)
			new_price = _apply_price_rule(old_price, mode, value, direction, round_to)

			new_original = None
			old_original = flt(row.original_price)
			if include_original_price and old_original > 0:
				new_original = _apply_price_rule(old_original, mode, value, direction, round_to)

			# Skip no-op rows (nothing actually changed)
			if new_price == old_price and (new_original is None or new_original == old_original):
				continue

			if len(samples) < 8:
				samples.append({
					"name": row.name,
					"product_name": row.product_name,
					"old_price": old_price,
					"new_price": new_price,
				})

			if not dry_run:
				updates = {"price": new_price}
				if new_original is not None:
					updates["original_price"] = new_original
				frappe.db.set_value("Menu Product", row.name, updates, update_modified=True)

			updated += 1

		if not dry_run and updated:
			frappe.db.commit()
			invalidate_product_cache({"outlet": restaurant})

		return {
			"success": True,
			"dry_run": bool(dry_run),
			"total_matched": len(rows),
			"updated": updated,
			"samples": samples,
		}
	except Exception as e:
		frappe.log_error(f"Error in bulk_update_prices: {str(e)}", "bulk_update_prices")
		return {"success": False, "error": str(e)}

