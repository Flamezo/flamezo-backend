# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Outlet lookup and information
"""

import frappe
from frappe import _
from frappe.utils import get_url, cint
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api, get_restaurant_context
from flamezo_backend.flamezo.utils.outlet_media import batch_resolve_outlet_media


@frappe.whitelist(allow_guest=True)
def get_outlet_id(outlet_name):
	"""
	GET /api/method/flamezo_backend.flamezo.api.outlet.get_outlet_id
	Get outlet_id from outlet_name

	Parameters:
	- outlet_name (required): The outlet name to lookup

	Returns:
	{
		"success": true,
		"data": {
			"outlet_id": "the-gallery-cafe",
			"outlet_name": "The Gallery Cafe",
			"is_active": true
		}
	}
	"""
	try:
		if not outlet_name:
			return {
				"success": False,
				"error": {
					"code": "VALIDATION_ERROR",
					"message": "outlet_name is required"
				}
			}

		# Try to find outlet by outlet_name (exact match first)
		outlet = frappe.db.get_value(
			"Outlet",
			{"restaurant_name": outlet_name},
			["name", "restaurant_id", "restaurant_name", "is_active"],
			as_dict=True
		)

		# If not found, try case-insensitive search
		if not outlet:
			outlets = frappe.get_all(
				"Outlet",
				filters={"restaurant_name": ["like", f"%{outlet_name}%"]},
				fields=["name", "restaurant_id", "restaurant_name", "is_active"],
				limit=1
			)
			if outlets:
				outlet = outlets[0]

		if not outlet:
			return {
				"success": False,
				"error": {
					"code": "OUTLET_NOT_FOUND",
					"message": f"Outlet '{outlet_name}' not found"
				}
			}

		return {
			"success": True,
			"data": {
				"outlet_id": outlet.restaurant_id,
				"outlet_name": outlet.restaurant_name,
				"is_active": bool(outlet.is_active)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_outlet_id: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "RESTAURANT_LOOKUP_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_outlet_info(outlet_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.outlet.get_outlet_info
	Get full outlet information by outlet_id

	Parameters:
	- outlet_id (required): The outlet identifier

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
		outlet = validate_restaurant_for_api(outlet_id)
		outlet_context = get_restaurant_context(outlet_id)

		if not outlet_context:
			return {
				"success": False,
				"error": {
					"code": "OUTLET_NOT_FOUND",
					"message": f"Outlet {outlet_id} not found"
				}
			}

		return {
			"success": True,
			"data": outlet_context
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
		frappe.log_error(f"Error in get_outlet_info: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "RESTAURANT_FETCH_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist(allow_guest=True)
def get_outlet_tables(outlet_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.outlet.get_outlet_tables
	Get available tables for an outlet

	Parameters:
	- outlet_id (required): The outlet identifier

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
		outlet = validate_restaurant_for_api(outlet_id)

		# Get number of tables from outlet
		tables_count = frappe.db.get_value("Outlet", outlet, "tables")

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
				"code": "OUTLET_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
				"message": str(e)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_outlet_tables: {str(e)}")
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
	GET /api/method/flamezo_backend.flamezo.api.outlet.list_restaurants
	Returns full outlet cards for the consumer Discover page.

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

		outlets = frappe.get_all(
			"Outlet",
			filters=filters,
			fields=[
				"name", "restaurant_id", "restaurant_name", "is_active",
				"logo", "city", "address", "latitude", "longitude",
				"plan_type", "onboarding_date",
			],
			order_by="restaurant_name",
			limit=int(limit),
		)

		if not outlets:
			return {"success": True, "data": {"restaurants": []}}

		outlet_names = [r["name"] for r in outlets]

		# --- Bulk fetch Restaurant Config (tagline, description) ---
		configs = frappe.get_all(
			"Restaurant Config",
			filters={"restaurant": ["in", outlet_names]},
			fields=["restaurant", "tagline", "subtitle", "description"],
		)
		config_map = {c["restaurant"]: c for c in configs}

		# --- Bulk fetch Gallery photos (up to 6 per outlet) ---
		gallery_items = frappe.get_all(
			"Restaurant Gallery Item",
			filters={"restaurant": ["in", outlet_names], "is_selected": 1},
			fields=["restaurant", "url"],
			order_by="sort_order asc",
		)
		photos_map = {}
		for item in gallery_items:
			photos_map.setdefault(item["restaurant"], [])
			if len(photos_map[item["restaurant"]]) < 6:
				photos_map[item["restaurant"]].append(item["url"])

		# --- Bulk count active coupons per outlet ---
		coupon_counts_raw = frappe.db.sql(
			"""
			SELECT restaurant, COUNT(*) AS cnt
			FROM `tabCoupon`
			WHERE restaurant IN ({placeholders}) AND is_active = 1
			GROUP BY restaurant
			""".format(placeholders=", ".join(["%s"] * len(outlet_names))),
			tuple(outlet_names),
			as_dict=True,
		)
		coupon_map = {row["restaurant"]: row["cnt"] for row in coupon_counts_raw}

		# --- Derive isNew: onboarded within last 90 days ---
		ninety_days_ago = (now_datetime() - datetime.timedelta(days=90)).date()

		result = []
		for r in outlets:
			doc_name = r["name"]
			cfg = config_map.get(doc_name, {})

			primary_color = "#B7410E"
			tagline = cfg.get("tagline") or cfg.get("subtitle") or cfg.get("description") or ""
			cuisine_type = cfg.get("subtitle") or cfg.get("description") or "Outlet"

			onboarding_date = r.get("onboarding_date")
			is_new = False
			if onboarding_date:
				try:
					is_new = getdate(onboarding_date) >= ninety_days_ago
				except Exception:
					is_new = False

			result.append({
				"outlet_id": r["restaurant_id"],
				"outlet_name": r["restaurant_name"],
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
def get_outlet_gallery(outlet_id):
	"""
	Get selected gallery items for an outlet (max 25)
	"""
	try:
		outlet = validate_restaurant_for_api(outlet_id)

		items = frappe.get_all(
			"Restaurant Gallery Item",
			filters={
				"restaurant": outlet,
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
		frappe.log_error(f"Error in get_outlet_gallery: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "GALLERY_FETCH_ERROR",
				"message": str(e)
			}
		}

# ── Amenity bitmask decode ────────────────────────────────────────────────
# Mirrors the Flutter app's `Amenity` class + `kAmenityDisplayOrder` +
# `amenityHighlights()` (outlet_detail.dart) bit-for-bit. Keeping this table
# server-side means the client never re-implements the bit-position
# contract — a single source of truth instead of two copies that could
# silently drift out of sync.
_AMENITY_FLAGS = [
	("dineIn", 1 << 0, "Dine-in"),
	("takeout", 1 << 1, "Takeout"),
	("delivery", 1 << 2, "Delivery"),
	("reservable", 1 << 3, "Reservations"),
	("outdoorSeating", 1 << 4, "Outdoor seating"),
	("breakfast", 1 << 5, "Breakfast"),
	("lunch", 1 << 6, "Lunch"),
	("dinner", 1 << 7, "Dinner"),
	("brunch", 1 << 8, "Brunch"),
	("veg", 1 << 9, "Pure veg"),
	("coffee", 1 << 10, "Coffee"),
	("cocktails", 1 << 11, "Cocktails"),
	("dessert", 1 << 12, "Dessert"),
	("liveMusic", 1 << 13, "Live music"),
	("kids", 1 << 14, "Kid-friendly"),
	("groups", 1 << 15, "Good for groups"),
	("sports", 1 << 16, "Sports screening"),
	("restroom", 1 << 17, "Restroom"),
	("creditCard", 1 << 18, "Credit cards"),
	("debitCard", 1 << 19, "Debit cards"),
	("upiNfc", 1 << 20, "UPI / NFC"),
	("cashOnly", 1 << 21, "Cash only"),
	("parkingFree", 1 << 22, "Free parking"),
	("parkingPaid", 1 << 23, "Paid parking"),
	("parkingValet", 1 << 24, "Valet parking"),
	("parkingStreet", 1 << 25, "Street parking"),
]
_AMENITY_BY_KEY = {key: (flag, label) for key, flag, label in _AMENITY_FLAGS}

# "Most-asked-about first" display order for the full Facilities grid —
# mirrors `kAmenityDisplayOrder` exactly (NOT the same as bit-declaration
# order above, which is just the canonical flag/label source of truth).
_DISPLAY_KEY_ORDER = [
	"dineIn", "takeout", "delivery", "reservable", "outdoorSeating", "veg",
	"breakfast", "lunch", "dinner", "brunch", "coffee", "cocktails", "dessert",
	"liveMusic", "kids", "groups", "sports", "upiNfc", "creditCard", "debitCard",
	"cashOnly", "parkingValet", "parkingFree", "parkingPaid", "parkingStreet",
	"restroom",
]

# Curated "WHAT YOU'LL LOVE" priority order — mirrors `amenityHighlights()`
# exactly (max 4 shown, in this priority order). Labels here intentionally
# differ from `labels` above for 3 flags (groups/upiNfc/reservable) — the
# highlight strip uses friendlier wording than the full facilities grid,
# matching the Dart source exactly rather than reusing `_AMENITY_BY_KEY`.
_HIGHLIGHT_ORDER = [
	("outdoorSeating", "Outdoor seating"),
	("liveMusic", "Live music"),
	("parkingValet", "Valet parking"),
	("veg", "Pure veg"),
	("groups", "Great for groups"),
	("kids", "Kid-friendly"),
	("upiNfc", "UPI accepted"),
	("reservable", "Takes reservations"),
]


def _decode_amenities(mask):
	"""Full facility grid, in the same display order as kAmenityDisplayOrder."""
	mask = cint(mask or 0)
	out = []
	for key in _DISPLAY_KEY_ORDER:
		flag, label = _AMENITY_BY_KEY[key]
		if mask & flag:
			out.append({"key": key, "label": label})
	return out


def _decode_amenity_highlights(mask):
	"""Curated max-4 subset for the Offers tab's highlight strip."""
	mask = cint(mask or 0)
	out = []
	for key, label in _HIGHLIGHT_ORDER:
		flag, _ = _AMENITY_BY_KEY[key]
		if mask & flag:
			out.append({"key": key, "label": label})
		if len(out) >= 4:
			break
	return out


@frappe.whitelist(allow_guest=True)
def get_outlet_detail(outlet_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.outlet.get_outlet_detail

	Consumer-facing full outlet detail. Replaces the bundled SQLite lookup.
	Returns everything the outlet detail screen needs in one call — cached 5 min.

	Response:
	  id, outlet_name, logo, outlet_type, address, city, lat, lng,
	  phone, whatsapp, instagram_url, description, tagline,
	  rating, review_count, cuisines[], price_range, amenities_mask, hours_json,
	  is_featured, is_open_now, active_offers_count,
	  photos[] (first 12 gallery items),
	  enable_dine_in, enable_loyalty,
	  google_review_url, enable_table_booking
	"""
	import json
	import math
	from frappe.utils import flt, cint, today

	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}

	try:
		# Cache 5 minutes — busted when merchant edits their profile
		cache_key = f"flamezo:outlet_detail:{outlet_id}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return json.loads(cached)

		# Resolve internal name from restaurant_id field OR direct name
		rest_name = frappe.db.get_value("Outlet", {"restaurant_id": outlet_id}, "name")
		if not rest_name:
			rest_name = frappe.db.get_value("Outlet", outlet_id, "name")
		if not rest_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Outlet not found"}}

		# Single row fetch — all discovery fields + ops fields
		r = frappe.db.get_value(
			"Outlet",
			rest_name,
			[
				"name", "restaurant_name", "logo", "outlet_type",
				"address", "city", "state", "zip_code",
				"latitude", "longitude",
				"contact_phone", "whatsapp_number", "instagram_url",
				"description", "google_map_url",
				"is_featured", "rating", "review_count",
				"cuisines", "price_range", "amenities_mask", "hours_json",
				"enable_dine_in", "enable_loyalty", "google_review_url",
			],
			as_dict=True,
		)
		if not r:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Outlet not found"}}

		# Fetch social links + table booking flag from Restaurant Config (single query)
		cfg = frappe.db.get_value(
			"Restaurant Config",
			{"restaurant": rest_name},
			["google_review_link", "enable_table_booking", "tagline"],
			as_dict=True,
		) or {}

		# Gallery: first 12 selected photos, falling back to food/product photos
		# then logo if the merchant hasn't curated a showcase — same batched
		# resolver the discovery feed uses (see utils/outlet_media.py). Was
		# capped at 4 (far below the discovery card's 6 and the dedicated
		# gallery viewer's 25) — the detail page's HeroCollage widget was
		# already built to handle a scrollable N-image collage, it just
		# never got fed more than 4. Same priority order either way
		# (curated gallery -> food photos -> logo), just a higher cap.
		photos = batch_resolve_outlet_media(
			[rest_name], limit_per_outlet=12, logos={rest_name: r.get("logo") or ""}
		).get(rest_name, [])

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
			"outlet_id": outlet_id,
			"outlet_name": r["restaurant_name"],
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
			"amenities": _decode_amenities(r.get("amenities_mask")),
			"amenity_highlights": _decode_amenity_highlights(r.get("amenities_mask")),
			"hours_json": json.loads(hours_raw) if hours_raw else {},
			"is_open_now": _is_open_now_inline(hours_raw),
			"active_offers_count": active_offers_count,
			"photos": [{"url": p.get("url", ""), "type": p.get("type", "Image"), "title": p.get("title", "")} for p in photos],
			"enable_dine_in": bool(r.get("enable_dine_in", 1)),
			"enable_loyalty": bool(r.get("enable_loyalty", 0)),
			"enable_table_booking": bool(cfg.get("enable_table_booking", 1)),
			"google_review_url": r.get("google_review_url") or cfg.get("google_review_link") or "",
		}

		response = {"success": True, "data": data}
		frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=300)
		return response

	except Exception as e:
		frappe.log_error(f"Error in get_outlet_detail: {str(e)}")
		return {"success": False, "error": {"code": "DETAIL_FETCH_ERROR", "message": str(e)}}


_BEVERAGE_KW = ("beverage", "drink", "juice", "coffee", "tea", "shake", "mocktail",
	"cocktail", "smoothie", "soda", "water", "lassi", "latte", "cappuccino",
	"espresso", "mojito", "boba", "cooler", "soft drink", "hot drink", "brew")
_COMBO_KW = ("combo", "package", "thali", "meal", "platter", "feast", "family",
	"set menu", "hamper", "bundle")


def _menu_section(*texts):
	"""Auto-distribute a menu image into Combos / Beverages / Food by the item's
	category + name. Combo wins first (it contains both food & drink), then
	beverage keywords, else it's Food."""
	blob = " ".join(t for t in texts if t).lower()
	if any(k in blob for k in _COMBO_KW):
		return "Combos"
	if any(k in blob for k in _BEVERAGE_KW):
		return "Beverages"
	return "Food"


@frappe.whitelist()
def get_outlet_media_pool(outlet_id):
	"""
	Collect all media used by the outlet across the app
	"""
	try:
		outlet = validate_restaurant_for_api(outlet_id)
		media_pool = []
		seen_urls = set()

		# 0. Restaurant Branding
		outlet_doc = frappe.get_doc("Outlet", outlet)

		# Industry-aware label for the "products" media folder — food outlets see
		# "Food Images", fashion sees "Products & Catalogue", etc.
		outlet_type = outlet_doc.get("outlet_type") or "dining"
		MEDIA_LABELS = {
			"dining": "Food Images",
			"cafe": "Food Images",
			"wellness": "Products & Services",
			"fitness": "Classes & Services",
			"sports_court": "Facilities",
			"sports_venue": "Facilities",
			"fashion": "Products & Catalogue",
		}
		product_label = MEDIA_LABELS.get(outlet_type, "Products & Catalogue")

		# Restaurant.logo is the single source of truth for the outlet's logo
		# (Restaurant Config.logo was removed — see
		# onboarding.backfill_restaurant_logo_from_config for the one-time migration).
		branding_logo = outlet_doc.get("logo")

		if branding_logo:
			media_pool.append({
				"url": branding_logo,
				"type": "image",
				"source_title": "Outlet Logo",
				"source_type": "Branding",
				"category": "Branding"
			})
			seen_urls.add(branding_logo)

		# 1. Menu Product Media
		# The override column / section doctype only exist after `bench migrate`;
		# degrade gracefully (auto-sort only) until then instead of erroring out.
		_has_sec = frappe.db.has_column("Media Asset", "menu_section")
		_sec_sel = ", ma.menu_section as section_override" if _has_sec else ""
		_sec_join = "LEFT JOIN `tabMedia Asset` ma ON pm.media_asset = ma.name" if _has_sec else ""
		product_media = frappe.db.sql(f"""
			SELECT pm.media_url as url, pm.media_type as type, p.product_name as source_title,
			       'Menu Product' as source_type, pm.media_asset as media_asset,
			       p.name as product_name, p.category_name as subcategory{_sec_sel}
			FROM `tabProduct Media` pm
			JOIN `tabMenu Product` p ON pm.parent = p.name
			{_sec_join}
			WHERE p.restaurant = %s
		""", (outlet,), as_dict=1)

		# Dish photos are deliberately listed in TWO folders, not moved between
		# them: the products folder stays the merchant's familiar home for
		# catalogue media, while Menu Images shows the same photos split into
		# sections by the outlet's own Menu Categories (Food, Beverages,
		# Desserts...). Same underlying image — two ways in.
		for m in product_media:
			if m.url and m.url not in seen_urls:
				m['subcategory'] = m.get('subcategory') or "Uncategorised"
				# Merchant override wins; else auto-sort into Food / Beverages / Combos.
				m['menu_section'] = m.get('section_override') or _menu_section(m.get('subcategory'), m.get('source_title'))
				m['category'] = product_label
				media_pool.append(m)
				media_pool.append({**m, "category": "Menu Images"})
				seen_urls.add(m.url)

		# 1b. AI-generated images (enhanced_image_url) — surface every generated
		#     photo so the merchant can pick which go into the active showcase.
		ai_generated = frappe.get_all(
			"AI Image Generation",
			filters={"restaurant": outlet, "enhanced_image_url": ["is", "set"]},
			fields=["enhanced_image_url as url", "owner_name as source_title"],
			order_by="creation desc",
		)
		for a in ai_generated:
			if a.url and a.url not in seen_urls:
				media_pool.append({
					"url": a.url,
					"type": "image",
					"source_title": a.source_title or "AI Generated",
					"source_type": "AI Generated",
					"category": product_label,
					"subcategory": "AI Generated",
				})
				seen_urls.add(a.url)

		# 1c. Catalogue Item Media (non-food outlets — fashion, wellness, etc.)
		catalogue_media = frappe.db.sql("""
			SELECT cim.media_url as url, cim.media_type as type, ci.item_name as source_title,
			       'Catalogue' as source_type, cc.category_name as subcategory
			FROM `tabCatalogue Item Media` cim
			JOIN `tabCatalogue Item` ci ON cim.parent = ci.name
			LEFT JOIN `tabCatalogue Category` cc ON ci.category = cc.name
			WHERE ci.restaurant = %s
		""", (outlet,), as_dict=1)
		for c in catalogue_media:
			if c.url and c.url not in seen_urls:
				c['category'] = product_label
				c['subcategory'] = c.get('subcategory') or "Uncategorised"
				media_pool.append(c)
				seen_urls.add(c.url)

		# NOTE: the scanned menu-card photos (Menu Image Item) are deliberately NOT
		# in this pool. They are extractor input, not showable assets — the rows
		# render broken in the dashboard and are not something a merchant would
		# publish. Menu Images shows the parsed dish photos instead.

		# 2. Events
		events = frappe.get_all(
			"Event",
			filters={"restaurant": outlet, "image_src": ["is", "set"]},
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
			filters={"restaurant": outlet},
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

		# Merchant-created (possibly empty) Menu Images sections, so a folder the
		# merchant added shows even before any image is moved into it.
		custom_sections = []
		if frappe.db.exists("DocType", "Outlet Media Section"):
			custom_sections = [
				r.section_name for r in frappe.get_all(
					"Outlet Media Section",
					filters={"restaurant": outlet, "section_kind": "menu"},
					fields=["section_name"],
					order_by="creation asc",
				)
			]

		return {
			"success": True,
			"data": {
				"media": media_pool,
				"product_category_label": product_label,
				"outlet_type": outlet_type,
				"custom_menu_sections": custom_sections
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_outlet_media_pool: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "MEDIA_POOL_ERROR",
				"message": str(e)
			}
		}


@frappe.whitelist()
def add_menu_section(outlet_id, section_name):
	"""Create a (possibly empty) custom Menu Images section for this outlet."""
	outlet = validate_restaurant_for_api(outlet_id)
	name = (section_name or "").strip()
	if not name:
		return {"success": False, "error": {"code": "BAD_NAME", "message": "Section name required"}}
	if not frappe.db.exists("Outlet Media Section", {"restaurant": outlet, "section_name": name, "section_kind": "menu"}):
		frappe.get_doc({
			"doctype": "Outlet Media Section",
			"restaurant": outlet,
			"section_name": name,
			"section_kind": "menu",
		}).insert(ignore_permissions=True)
		frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def delete_menu_section(outlet_id, section_name):
	"""Remove a custom section; images assigned to it fall back to auto-sort."""
	outlet = validate_restaurant_for_api(outlet_id)
	for r in frappe.get_all("Outlet Media Section", filters={"restaurant": outlet, "section_name": section_name, "section_kind": "menu"}):
		frappe.delete_doc("Outlet Media Section", r.name, ignore_permissions=True)
	for r in frappe.get_all("Media Asset", filters={"restaurant": outlet, "menu_section": section_name}):
		frappe.db.set_value("Media Asset", r.name, "menu_section", None)
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def move_media_to_section(outlet_id, media_asset_id, section_name):
	"""Assign a menu image to a section (override the auto-sort). Empty = back to auto."""
	outlet = validate_restaurant_for_api(outlet_id)
	asset_restaurant = frappe.db.get_value("Media Asset", media_asset_id, "restaurant")
	if not asset_restaurant:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Image not found"}}
	# The asset must actually belong to the outlet the caller is authorized
	# for — without this check, any dashboard user could pass any other
	# outlet's media_asset_id and reassign its menu section.
	if asset_restaurant != outlet:
		return {"success": False, "error": {"code": "FORBIDDEN", "message": "Image does not belong to this outlet"}}
	frappe.db.set_value("Media Asset", media_asset_id, "menu_section", (section_name or "").strip() or None)
	frappe.db.commit()
	return {"success": True}
