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
def list_restaurants(active_only=True, city=None, limit=50):
	"""
	GET /api/method/flamezo_backend.flamezo.api.restaurant.list_restaurants
	Returns full restaurant cards for the consumer Discover page.

	Parameters:
	- active_only (optional, default: true)
	- city (optional): filter by city name (case-insensitive)
	- limit (optional, default: 50)
	"""
	try:
		from frappe.utils import getdate, now_datetime
		import datetime

		filters = {}
		if active_only:
			filters["is_active"] = 1
		if city:
			filters["city"] = ["like", f"%{city}%"]

		restaurants = frappe.get_all(
			"Restaurant",
			filters=filters,
			fields=[
				"name", "restaurant_id", "restaurant_name", "is_active",
				"logo", "city", "address", "latitude", "longitude",
				"plan_type", "onboarding_date",
			],
			order_by="restaurant_name",
			limit=int(limit),
		)

		if not restaurants:
			return {"success": True, "data": {"restaurants": []}}

		restaurant_names = [r["name"] for r in restaurants]

		# --- Bulk fetch Restaurant Config (tagline, description) ---
		configs = frappe.get_all(
			"Restaurant Config",
			filters={"restaurant": ["in", restaurant_names]},
			fields=["restaurant", "tagline", "subtitle", "description"],
		)
		config_map = {c["restaurant"]: c for c in configs}

		# --- Bulk fetch Gallery photos (up to 6 per restaurant) ---
		gallery_items = frappe.get_all(
			"Restaurant Gallery Item",
			filters={"restaurant": ["in", restaurant_names], "is_selected": 1},
			fields=["restaurant", "url"],
			order_by="sort_order asc",
		)
		photos_map = {}
		for item in gallery_items:
			photos_map.setdefault(item["restaurant"], [])
			if len(photos_map[item["restaurant"]]) < 6:
				photos_map[item["restaurant"]].append(item["url"])

		# --- Bulk count active coupons per restaurant ---
		coupon_counts_raw = frappe.db.sql(
			"""
			SELECT restaurant, COUNT(*) AS cnt
			FROM `tabCoupon`
			WHERE restaurant IN ({placeholders}) AND is_active = 1
			GROUP BY restaurant
			""".format(placeholders=", ".join(["%s"] * len(restaurant_names))),
			tuple(restaurant_names),
			as_dict=True,
		)
		coupon_map = {row["restaurant"]: row["cnt"] for row in coupon_counts_raw}

		# --- Derive isNew: onboarded within last 90 days ---
		ninety_days_ago = (now_datetime() - datetime.timedelta(days=90)).date()

		result = []
		for r in restaurants:
			doc_name = r["name"]
			cfg = config_map.get(doc_name, {})

			primary_color = "#B7410E"
			tagline = cfg.get("tagline") or cfg.get("subtitle") or cfg.get("description") or ""
			cuisine_type = cfg.get("subtitle") or cfg.get("description") or "Restaurant"

			onboarding_date = r.get("onboarding_date")
			is_new = False
			if onboarding_date:
				try:
					is_new = getdate(onboarding_date) >= ninety_days_ago
				except Exception:
					is_new = False

			result.append({
				"restaurant_id": r["restaurant_id"],
				"restaurant_name": r["restaurant_name"],
				"is_active": bool(r["is_active"]),
				"logo": r.get("logo") or "",
				"photos": photos_map.get(doc_name, []),
				"city": r.get("city") or "",
				"address": r.get("address") or "",
				"latitude": r.get("latitude") or 0,
				"longitude": r.get("longitude") or 0,
				"plan_type": r.get("plan_type") or "GOLD",
				"primaryColor": primary_color,
				"tagline": tagline,
				"cuisine_type": cuisine_type,
				"active_offers_count": coupon_map.get(doc_name, 0),
				"isNew": is_new,
				# rating/review_count/openTime are not stored in Frappe —
				# frontend falls back to Google Places or surat_outlets.json
				"rating": None,
				"review_count": None,
				"openTime": None,
			})

		return {
			"success": True,
			"data": {
				"restaurants": result
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

@frappe.whitelist(allow_guest=True)
def get_restaurant_detail(restaurant_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.restaurant.get_restaurant_detail

	Consumer-facing full outlet detail. Replaces the bundled SQLite lookup.
	Returns everything the outlet detail screen needs in one call — cached 5 min.

	Response:
	  id, restaurant_name, logo, outlet_type, address, city, lat, lng,
	  phone, whatsapp, instagram_url, description, tagline,
	  rating, review_count, cuisines[], price_range, amenities_mask, hours_json,
	  is_featured, is_open_now, active_offers_count,
	  photos[] (first 4 gallery items),
	  enable_dine_in, enable_loyalty,
	  google_review_url, enable_table_booking
	"""
	import json
	import math
	from frappe.utils import flt, cint, today

	if not restaurant_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "restaurant_id is required"}}

	try:
		# Cache 5 minutes — busted when merchant edits their profile
		cache_key = f"flamezo:outlet_detail:{restaurant_id}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return json.loads(cached)

		# Resolve internal name from restaurant_id field OR direct name
		rest_name = frappe.db.get_value("Restaurant", {"restaurant_id": restaurant_id}, "name")
		if not rest_name:
			rest_name = frappe.db.get_value("Restaurant", restaurant_id, "name")
		if not rest_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}

		# Single row fetch — all discovery fields + ops fields
		r = frappe.db.get_value(
			"Restaurant",
			rest_name,
			[
				"name", "restaurant_name", "logo", "outlet_type",
				"address", "city", "state", "zip_code",
				"latitude", "longitude",
				"contact_phone", "whatsapp_number", "instagram_url",
				"description", "google_map_url",
				"is_featured", "rating", "review_count",
				"cuisines", "price_range", "amenities_mask", "hours_json",
				"enable_dine_in", "enable_loyalty",
			],
			as_dict=True,
		)
		if not r:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}

		# Fetch social links + table booking flag from Restaurant Config (single query)
		cfg = frappe.db.get_value(
			"Restaurant Config",
			{"restaurant": rest_name},
			["google_review_link", "enable_table_booking", "tagline"],
			as_dict=True,
		) or {}

		# Gallery: first 4 selected photos
		photos = frappe.get_all(
			"Restaurant Gallery Item",
			filters={"restaurant": rest_name, "is_selected": 1},
			fields=["url", "media_type as type", "title"],
			order_by="sort_order asc",
			limit=4,
		)

		# Active offers count (single SQL, no N+1)
		today_str = today()
		offers_row = frappe.db.sql(
			"""
			SELECT COUNT(*) FROM `tabCoupon`
			WHERE restaurant = %s AND is_active = 1
			  AND (valid_from IS NULL OR valid_from <= %s)
			  AND (valid_until IS NULL OR valid_until >= %s)
			""",
			(rest_name, today_str, today_str),
		)
		active_offers_count = offers_row[0][0] if offers_row else 0

		# Open-now computation (reuse helper from flamezo.py)
		hours_raw = r.get("hours_json") or ""

		def _is_open_now_inline(hours_json_str):
			if not hours_json_str:
				return None
			try:
				import pytz
				from datetime import datetime
				tz = pytz.timezone("Asia/Kolkata")
				now = datetime.now(tz)
				day_key = now.strftime("%a").lower()
				hours = json.loads(hours_json_str) if isinstance(hours_json_str, str) else hours_json_str
				slot = (hours.get(day_key) or "").strip()
				if not slot or slot.lower() in ("closed", ""):
					return False
				if "open 24" in slot.lower() or "24 hours" in slot.lower():
					return True
				parts = slot.replace("–", "-").split("-")
				if len(parts) != 2:
					return None
				def _parse(s):
					s = s.strip().upper()
					fmt = "%I:%M %p" if ":" in s else "%I %p"
					return datetime.strptime(s, fmt).replace(
						year=now.year, month=now.month, day=now.day, tzinfo=tz
					)
				open_t, close_t = _parse(parts[0]), _parse(parts[1])
				if close_t < open_t:
					return now >= open_t or now <= close_t
				return open_t <= now <= close_t
			except Exception:
				return None

		full_address = " ".join(filter(None, [
			r.get("address"), r.get("city"), r.get("state"), r.get("zip_code")
		]))

		data = {
			"id": r["name"],
			"restaurant_id": restaurant_id,
			"restaurant_name": r["restaurant_name"],
			"logo": r.get("logo") or "",
			"outlet_type": r.get("outlet_type") or "dining",
			"address": r.get("address") or "",
			"full_address": full_address,
			"city": r.get("city") or "",
			"state": r.get("state") or "",
			"zip_code": r.get("zip_code") or "",
			"latitude": flt(r.get("latitude") or 0) or None,
			"longitude": flt(r.get("longitude") or 0) or None,
			"google_map_url": r.get("google_map_url") or "",
			"phone": r.get("contact_phone") or "",
			"whatsapp": r.get("whatsapp_number") or "",
			"instagram_url": r.get("instagram_url") or "",
			"description": r.get("description") or "",
			"tagline": cfg.get("tagline") or "",
			"is_featured": bool(r.get("is_featured")),
			"rating": flt(r.get("rating") or 0) or None,
			"review_count": cint(r.get("review_count") or 0),
			"cuisines": [c.strip() for c in (r.get("cuisines") or "").split(",") if c.strip()],
			"price_range": r.get("price_range") or "",
			"amenities_mask": cint(r.get("amenities_mask") or 0),
			"hours_json": json.loads(hours_raw) if hours_raw else {},
			"is_open_now": _is_open_now_inline(hours_raw),
			"active_offers_count": active_offers_count,
			"photos": [{"url": p.get("url", ""), "type": p.get("type", "Image"), "title": p.get("title", "")} for p in photos],
			"enable_dine_in": bool(r.get("enable_dine_in", 1)),
			"enable_loyalty": bool(r.get("enable_loyalty", 0)),
			"enable_table_booking": bool(cfg.get("enable_table_booking", 1)),
			"google_review_url": cfg.get("google_review_link") or "",
		}

		response = {"success": True, "data": data}
		frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=300)
		return response

	except Exception as e:
		frappe.log_error(f"Error in get_restaurant_detail: {str(e)}")
		return {"success": False, "error": {"code": "DETAIL_FETCH_ERROR", "message": str(e)}}


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
