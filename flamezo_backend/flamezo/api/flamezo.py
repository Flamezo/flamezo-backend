# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
FLAMEZO Consumer App APIs
Aggregated endpoints for the FLAMEZO multi-restaurant super-app.
All endpoints are read-heavy and aggressively cached.
"""

import frappe
from frappe.utils import flt, cint, getdate, today, add_days
from flamezo_backend.flamezo.utils.customer_helpers import (
	normalize_phone,
	get_or_create_customer,
	get_customer_token,
	validate_customer_session,
	get_customer_from_token,
)
from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance, get_loyalty_tier
import json
import math


# ── Helpers ───────────────────────────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2):
	"""Distance in km between two lat/lon points."""
	R = 6371.0
	d_lat = math.radians(lat2 - lat1)
	d_lon = math.radians(lon2 - lon1)
	a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
	return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_restaurant_primary_color(restaurant_name):
	"""Brand color is fixed to the Flamezo copper (no per-restaurant colors)."""
	return "#B7410E"


def _batch_active_offers_count(restaurant_names):
	"""
	Single SQL query — returns {restaurant_name: count} for all given restaurants.
	Groups valid (date-gated) active coupons in one shot; no N+1.
	"""
	if not restaurant_names:
		return {}
	today_str = today()
	placeholders = ",".join(["%s"] * len(restaurant_names))
	rows = frappe.db.sql(
		f"""
		SELECT restaurant, COUNT(*) AS cnt
		FROM `tabCoupon`
		WHERE is_active = 1
		  AND restaurant IN ({placeholders})
		  AND (valid_from IS NULL OR valid_from <= %s)
		  AND (valid_until IS NULL OR valid_until >= %s)
		GROUP BY restaurant
		""",
		restaurant_names + [today_str, today_str],
		as_dict=True,
	)
	return {r.restaurant: r.cnt for r in rows}


def _is_open_now(hours_json_str):
	"""
	Return True if the restaurant is currently open based on its hours_json.
	hours_json format: {"mon": "11 AM – 11 PM", "tue": "Closed", ...}
	"""
	if not hours_json_str:
		return None  # unknown
	try:
		import pytz
		from datetime import datetime
		tz = pytz.timezone("Asia/Kolkata")
		now = datetime.now(tz)
		day_key = now.strftime("%a").lower()  # mon, tue, ...
		hours = json.loads(hours_json_str) if isinstance(hours_json_str, str) else hours_json_str
		slot = (hours.get(day_key) or "").strip()
		if not slot or slot.lower() in ("closed", ""):
			return False
		if "open 24" in slot.lower() or "24 hours" in slot.lower():
			return True
		# Parse "11 AM – 11 PM" or "11:30 AM – 11:30 PM"
		parts = slot.replace("–", "-").split("-")
		if len(parts) != 2:
			return None
		def _parse(s):
			s = s.strip().upper()
			fmt = "%I:%M %p" if ":" in s else "%I %p"
			return datetime.strptime(s, fmt).replace(
				year=now.year, month=now.month, day=now.day,
				tzinfo=tz
			)
		open_t = _parse(parts[0])
		close_t = _parse(parts[1])
		if close_t < open_t:  # midnight rollover
			return now >= open_t or now <= close_t
		return open_t <= now <= close_t
	except Exception:
		return None


_DISCOVERY_FIELDS = [
	"name", "restaurant_name", "logo", "latitude", "longitude",
	"city", "plan_type", "onboarding_date", "description", "outlet_type",
	"contact_phone", "whatsapp_number", "instagram_url",
	"is_featured", "is_signature", "rating", "review_count",
	"cuisines", "price_range", "amenities_mask", "hours_json",
	"total_orders",
]


def _format_restaurant_card(r, user_lat, user_lon, offers_map):
	"""Format a single restaurant record for the discovery feed."""
	distance_km = None
	if user_lat and user_lon and r.get("latitude") and r.get("longitude"):
		distance_km = round(
			_haversine_km(user_lat, user_lon, flt(r["latitude"]), flt(r["longitude"])), 1
		)
	hours_raw = r.get("hours_json") or ""
	return {
		"id": r["name"],
		"restaurant_name": r["restaurant_name"],
		"logo": r.get("logo") or "",
		"latitude": r.get("latitude"),
		"longitude": r.get("longitude"),
		"city": r.get("city") or "",
		"outlet_type": r.get("outlet_type") or "dining",
		"plan_type": r.get("plan_type") or "GOLD",
		"primaryColor": "#B7410E",
		"tagline": r.get("description") or "",
		"phone": r.get("contact_phone") or "",
		"whatsapp": r.get("whatsapp_number") or "",
		"instagram_url": r.get("instagram_url") or "",
		"is_featured": bool(r.get("is_featured")),
		"is_signature": bool(r.get("is_signature")),
		"rating": flt(r.get("rating") or 0) or None,
		"review_count": cint(r.get("review_count") or 0),
		"cuisines": [c.strip() for c in (r.get("cuisines") or "").split(",") if c.strip()],
		"price_range": r.get("price_range") or "",
		"amenities_mask": cint(r.get("amenities_mask") or 0),
		"hours_json": json.loads(hours_raw) if hours_raw else {},
		"is_open_now": _is_open_now(hours_raw),
		"distance_km": distance_km,
		"active_offers_count": offers_map.get(r["name"], 0),
	}


# ── 1. Discovery — All Outlets ────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_all_outlets(
	latitude=None, longitude=None, radius_km=None,
	search=None, city=None,
	outlet_type=None, section=None,
	has_offer=None, open_now=None, is_featured=None, is_signature=None,
	page=1, limit=30,
):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_all_outlets

	Production-grade discovery feed — no N+1, bounding-box geo pre-filter,
	single batch offers-count query.

	Parameters:
	  latitude, longitude (float) — user coords for distance sort + optional radius filter
	  radius_km (float)           — hard geo radius (only works with lat/lon); default none
	  search (str)                — full-text across name, cuisines, description, city
	  city (str)                  — city filter (exact or partial)
	  outlet_type (str)           — comma-separated: "dining", "wellness", "fitness", etc.
	  section (str)               — "featured" | "new" | "popular"
	                                featured  → is_featured=1
	                                new       → ORDER BY onboarding_date DESC (last 60d)
	                                popular   → ORDER BY total_orders DESC
	  has_offer (bool/int)        — only return restaurants with ≥1 active offer
	  open_now (bool/int)         — filter to currently open outlets (requires hours_json)
	  is_featured (bool/int)      — filter to featured outlets
	  page, limit                 — pagination (max 100/page)
	"""
	try:
		page = max(cint(page) or 1, 1)
		limit = min(cint(limit) or 30, 100)
		offset = (page - 1) * limit

		user_lat = flt(latitude) if latitude else None
		user_lon = flt(longitude) if longitude else None
		r_km = flt(radius_km) if radius_km else None

		# ── Cache key ────────────────────────────────────────────────────────────
		lat_b = round(user_lat, 2) if user_lat else None
		lon_b = round(user_lon, 2) if user_lon else None
		cache_key = (
			f"flamezo:disco:{lat_b}:{lon_b}:{r_km}:{search or ''}:{city or ''}:"
			f"{outlet_type or ''}:{section or ''}:{has_offer}:{open_now}:{is_featured}:{is_signature}:{page}:{limit}"
		)
		if frappe.session.user == "Guest":
			cached = frappe.cache().get_value(cache_key)
			if cached:
				return json.loads(cached)

		# ── SQL filters ───────────────────────────────────────────────────────────
		sql_filters = ["r.is_active = 1"]
		params = []

		if city:
			sql_filters.append("r.city LIKE %s")
			params.append(f"%{city}%")

		if outlet_type:
			types = [t.strip() for t in str(outlet_type).split(",") if t.strip()]
			if types:
				phs = ",".join(["%s"] * len(types))
				sql_filters.append(f"r.outlet_type IN ({phs})")
				params.extend(types)

		if cint(is_featured) or section == "featured":
			sql_filters.append("r.is_featured = 1")

		if cint(is_signature):
			sql_filters.append("r.is_signature = 1")

		if section == "new":
			cutoff = add_days(today(), -60)
			sql_filters.append("r.onboarding_date >= %s")
			params.append(str(cutoff))

		# Bounding box pre-filter (fast index scan, Haversine applied after in Python)
		if user_lat and user_lon and r_km:
			lat_delta = r_km / 111.0
			lon_delta = r_km / (111.0 * math.cos(math.radians(user_lat)))
			sql_filters.append("r.latitude  BETWEEN %s AND %s")
			sql_filters.append("r.longitude BETWEEN %s AND %s")
			params += [user_lat - lat_delta, user_lat + lat_delta,
					   user_lon - lon_delta, user_lon + lon_delta]

		# Full-text search across name, cuisines, description, city
		if search:
			sql_filters.append(
				"(r.restaurant_name LIKE %s OR r.cuisines LIKE %s "
				"OR r.description LIKE %s OR r.city LIKE %s)"
			)
			like = f"%{search}%"
			params += [like, like, like, like]

		# ── ORDER BY ─────────────────────────────────────────────────────────────
		if section == "popular":
			order_by = "r.total_orders DESC, r.onboarding_date DESC"
		elif user_lat and user_lon:
			order_by = "r.onboarding_date DESC"  # will re-sort by distance in Python
		else:
			order_by = "r.is_featured DESC, r.onboarding_date DESC"

		where_clause = " AND ".join(sql_filters)

		# Fetch slightly more rows when doing geo sort so paginating by distance works
		fetch_limit = limit * 4 if (user_lat and user_lon) else limit
		fetch_offset = 0 if (user_lat and user_lon) else offset

		fields_csv = ", ".join(f"r.`{f}`" for f in _DISCOVERY_FIELDS)
		sql = f"""
			SELECT {fields_csv}
			FROM `tabRestaurant` r
			WHERE {where_clause}
			ORDER BY {order_by}
			LIMIT {fetch_limit} OFFSET {fetch_offset}
		"""
		restaurants = frappe.db.sql(sql, params, as_dict=True)

		# ── Batch offers count (single query, zero N+1) ───────────────────────────
		rest_names = [r["name"] for r in restaurants]
		offers_map = _batch_active_offers_count(rest_names)

		# ── has_offer filter (post-query, uses the same offers_map) ──────────────
		if cint(has_offer):
			restaurants = [r for r in restaurants if offers_map.get(r["name"], 0) > 0]

		# ── Format cards ──────────────────────────────────────────────────────────
		enriched = [_format_restaurant_card(r, user_lat, user_lon, offers_map) for r in restaurants]

		# ── open_now filter (post-format, uses is_open_now computed per card) ────
		if cint(open_now):
			enriched = [r for r in enriched if r["is_open_now"] is True]

		# ── Distance sort + hard radius + pagination ──────────────────────────────
		if user_lat and user_lon:
			enriched.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 99999)
			if r_km:
				enriched = [x for x in enriched if x["distance_km"] is not None and x["distance_km"] <= r_km]
			total = len(enriched)
			enriched = enriched[offset: offset + limit]
		else:
			# Count without geo (fast)
			count_sql = f"SELECT COUNT(*) FROM `tabRestaurant` r WHERE {where_clause}"
			total = frappe.db.sql(count_sql, params)[0][0]

		response = {
			"success": True,
			"data": {
				"outlets": enriched,
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			},
		}

		if frappe.session.user == "Guest":
			frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=120)

		return response

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_all_outlets: {str(e)}")
		return {"success": False, "error": {"code": "DISCOVERY_ERROR", "message": str(e)}}


# ── 1b. Map Markers — ultra-lightweight ───────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_outlets_for_map(
	city=None,
	sw_lat=None, sw_lng=None, ne_lat=None, ne_lng=None,
	outlet_type=None,
):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_outlets_for_map

	Returns lightweight markers for all active outlets in a bounding box or city.
	Designed for the map-discovery screen — returns ONLY what's needed to render pins.

	Parameters:
	  city                  — city name filter (alternative to bounding box)
	  sw_lat, sw_lng        — south-west corner of the viewport
	  ne_lat, ne_lng        — north-east corner of the viewport
	  outlet_type           — comma-separated outlet types to show

	Response per marker:
	  { id, name, logo, lat, lng, outlet_type, is_featured, active_offers_count }
	"""
	try:
		# ── Cache (5 min per city/bounds/type bucket) ─────────────────────────────
		lat_b = f"{round(flt(sw_lat),2)},{round(flt(ne_lat),2)}" if sw_lat else "none"
		lon_b = f"{round(flt(sw_lng),2)},{round(flt(ne_lng),2)}" if sw_lng else "none"
		cache_key = f"flamezo:map:{city or 'all'}:{lat_b}:{lon_b}:{outlet_type or 'all'}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return json.loads(cached)

		# ── SQL ───────────────────────────────────────────────────────────────────
		sql_filters = ["is_active = 1", "latitude IS NOT NULL", "longitude IS NOT NULL"]
		params = []

		if city:
			sql_filters.append("city LIKE %s")
			params.append(f"%{city}%")

		if sw_lat and sw_lng and ne_lat and ne_lng:
			sql_filters.append("latitude  BETWEEN %s AND %s")
			sql_filters.append("longitude BETWEEN %s AND %s")
			params += [flt(sw_lat), flt(ne_lat), flt(sw_lng), flt(ne_lng)]

		if outlet_type:
			types = [t.strip() for t in str(outlet_type).split(",") if t.strip()]
			if types:
				phs = ",".join(["%s"] * len(types))
				sql_filters.append(f"outlet_type IN ({phs})")
				params.extend(types)

		where = " AND ".join(sql_filters)
		rows = frappe.db.sql(
			f"""
			SELECT name, restaurant_name, logo, latitude, longitude,
			       outlet_type, is_featured
			FROM `tabRestaurant`
			WHERE {where}
			ORDER BY is_featured DESC, onboarding_date DESC
			LIMIT 2000
			""",
			params,
			as_dict=True,
		)

		if not rows:
			result = {"success": True, "data": {"markers": []}}
			frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=300)
			return result

		# Batch offers count in one query
		names = [r["name"] for r in rows]
		offers_map = _batch_active_offers_count(names)

		site_url = frappe.utils.get_url()
		markers = [
			{
				"id": r["name"],
				"name": r["restaurant_name"],
				"logo": (site_url + r["logo"]) if r.get("logo") and r["logo"].startswith("/") else (r.get("logo") or ""),
				"lat": flt(r["latitude"]),
				"lng": flt(r["longitude"]),
				"outlet_type": r.get("outlet_type") or "dining",
				"is_featured": bool(r.get("is_featured")),
				"active_offers_count": offers_map.get(r["name"], 0),
			}
			for r in rows
		]

		result = {"success": True, "data": {"markers": markers, "total": len(markers)}}
		frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=300)
		return result

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_outlets_for_map: {str(e)}")
		return {"success": False, "error": {"code": "MAP_FETCH_ERROR", "message": str(e)}}


# ── 2. Cross-Restaurant Offers Feed ──────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_cross_restaurant_offers(city=None, page=1, limit=30):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_cross_restaurant_offers

	Returns active coupons/offers across all active FLAMEZO restaurants.
	Sorted by discount value desc (best deals first).

	Parameters:
	- city (str, optional): Filter by restaurant city
	- page (int): Page number (default 1)
	- limit (int): Results per page (default 30)
	"""
	try:
		page = cint(page) or 1
		limit = min(cint(limit) or 30, 100)
		offset = (page - 1) * limit

		cache_key = f"flamezo:offers:{city or 'all'}:{page}:{limit}"
		if frappe.session.user == "Guest":
			cached = frappe.cache().get_value(cache_key)
			if cached:
				return json.loads(cached)

		today_date = getdate(today())

		# New model: every onboarded restaurant has the offers feature, so we no
		# longer filter by plan_type. Discovery feed = all active restaurants.
		restaurant_filters: dict = {"is_active": 1}
		if city:
			restaurant_filters["city"] = ["like", f"%{city}%"]

		active_restaurants = frappe.get_all(
			"Restaurant",
			filters=restaurant_filters,
			fields=["name", "restaurant_name", "city", "logo"],
		)
		restaurant_map = {r.name: r for r in active_restaurants}

		if not restaurant_map:
			return {"success": True, "data": {"offers": [], "page": page, "has_more": False}}

		# Fetch all active coupons for these restaurants
		coupons = frappe.db.get_list(
			"Coupon",
			filters={
				"restaurant": ["in", list(restaurant_map.keys())],
				"is_active": 1,
			},
			fields=[
				"name", "code", "description", "discount_type", "discount_value",
				"min_order_amount", "offer_type", "free_item",
				"valid_from", "valid_until", "restaurant",
			],
			ignore_permissions=True,
			order_by="discount_value desc",
		)

		offers = []
		for c in coupons:
			# Date filtering — guard against None before comparison
			raw_from = c.get("valid_from")
			raw_until = c.get("valid_until")
			if raw_from and getdate(raw_from) > today_date:
				continue
			if raw_until and getdate(raw_until) < today_date:
				continue
			v_until = getdate(raw_until) if raw_until else None

			restaurant = restaurant_map.get(c.restaurant)
			if not restaurant:
				continue

			primary_color = _get_restaurant_primary_color(c.restaurant)

			offers.append({
				"name": c.name,
				"code": c.code,
				"description": c.description or f"Use code {c.code} at checkout",
				"discount_type": c.discount_type or "percent",
				"discount_value": flt(c.discount_value),
				"min_order_amount": flt(c.min_order_amount),
				"restaurant_id": c.restaurant,
				"restaurant_name": restaurant.restaurant_name,
				"restaurant_logo": restaurant.logo or "",
				"city": restaurant.city or "",
				"primary_color": primary_color,
				"valid_until": str(v_until) if v_until else None,
			})

		# Paginate
		total = len(offers)
		paginated = offers[offset: offset + limit]

		response = {
			"success": True,
			"data": {
				"offers": paginated,
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			}
		}

		if frappe.session.user == "Guest":
			frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=180)

		return response

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_cross_restaurant_offers: {str(e)}")
		return {"success": False, "error": {"code": "OFFERS_FETCH_ERROR", "message": str(e)}}


# ── 3. FLAMEZO Member Profile ──────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_flamezo_member(phone=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_flamezo_member

	Returns the FLAMEZO unified member profile for the authenticated customer.
	Includes: unified points balance, tier, restaurants visited, referral code.

	Authentication: X-Customer-Token header required (same as loyalty APIs).
	"""
	try:
		# Auth gate — same pattern as loyalty.py
		session_token = get_customer_token()
		if not session_token and not phone:
			return {"success": False, "error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}

		# Resolve phone from token if not provided
		if not phone:
			# Try to get phone from session token
			session = frappe.cache().get_value(f"customer_session:{session_token}")
			if not session:
				return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}
			phone = session.get("phone")

		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}

		# Validate session if token provided
		if session_token and not validate_customer_session(normalized_phone, session_token):
			return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}

		# Get or create customer
		customer = get_or_create_customer(normalized_phone)
		if not customer:
			return {"success": False, "error": {"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"}}

		# Unified balance and tier (global across all restaurants)
		balance = get_loyalty_balance(customer.name)
		tier = get_loyalty_tier(customer.name)

		# Lifetime stats
		lifetime_earned = frappe.db.sql("""
			SELECT COALESCE(SUM(coins), 0) AS total
			FROM `tabRestaurant Loyalty Entry`
			WHERE customer = %s AND transaction_type = 'Earn' AND is_settled = 1
		""", (customer.name,), as_dict=True)[0].total or 0

		lifetime_redeemed = frappe.db.sql("""
			SELECT COALESCE(SUM(coins), 0) AS total
			FROM `tabRestaurant Loyalty Entry`
			WHERE customer = %s AND transaction_type = 'Redeem' AND is_settled = 1
		""", (customer.name,), as_dict=True)[0].total or 0

		# Restaurants visited (distinct)
		visited_restaurants = frappe.db.sql("""
			SELECT COUNT(DISTINCT restaurant) AS count
			FROM `tabRestaurant Loyalty Entry`
			WHERE customer = %s AND transaction_type = 'Earn'
		""", (customer.name,), as_dict=True)[0].count or 0

		# Expiring soon (within 30 days)
		expiring_rows = frappe.get_all(
			"Restaurant Loyalty Entry",
			filters={
				"customer": customer.name,
				"is_settled": 1,
				"transaction_type": "Earn",
				"expiry_date": ["between", [today(), add_days(today(), 30)]],
			},
			fields=["coins"],
		)
		expiring_soon = min(sum(e.coins for e in expiring_rows), flt(balance))

		# Referral code — custom field may not exist on all sites
		raw_referral = (
			frappe.db.get_value("Customer", customer.name, "referral_code")
			if frappe.db.has_column("Customer", "referral_code") else None
		)
		referral_code = raw_referral or (customer.name or "")[:8].upper()

		# Next tier thresholds
		TIER_THRESHOLDS = {"Bronze": 0, "Silver": 500, "Gold": 2000, "Platinum": 5000}
		TIER_ORDER = ["Bronze", "Silver", "Gold", "Platinum"]
		current_idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
		next_tier = TIER_ORDER[current_idx + 1] if current_idx < len(TIER_ORDER) - 1 else None
		next_threshold = TIER_THRESHOLDS.get(next_tier, 0) if next_tier else None
		progress_pct = 0
		if next_threshold:
			current_threshold = TIER_THRESHOLDS.get(tier, 0)
			span = next_threshold - current_threshold
			earned_in_span = max(0, flt(lifetime_earned) - current_threshold)
			progress_pct = min(100, round((earned_in_span / span) * 100)) if span > 0 else 100

		return {
			"success": True,
			"data": {
				"phone": normalized_phone,
				"full_name": customer.customer_name or "",
				"flamezo_points_balance": flt(balance),
				"tier": tier,
				"next_tier": next_tier,
				"tier_progress_pct": progress_pct,
				"next_tier_threshold": next_threshold,
				"lifetime_earned": flt(lifetime_earned),
				"lifetime_redeemed": flt(lifetime_redeemed),
				"expiring_soon": flt(expiring_soon),
				"restaurants_visited": cint(visited_restaurants),
				"referral_code": referral_code,
				"joined_on": str(customer.creation.date()) if customer.creation else None,
			}
		}

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_flamezo_member: {str(e)}")
		return {"success": False, "error": {"code": "MEMBER_FETCH_ERROR", "message": str(e)}}


# ── 4. FLAMEZO Points Ledger ───────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_points_ledger(phone=None, page=1, limit=20):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_points_ledger

	Returns the unified FLAMEZO points transaction history for the customer,
	across ALL restaurants. Same auth pattern as get_flamezo_member.

	Parameters:
	- phone (str): Customer phone (required if no session token context)
	- page (int): Page number (default 1)
	- limit (int): Results per page (default 20, max 50)
	"""
	try:
		page = cint(page) or 1
		limit = min(cint(limit) or 20, 50)
		offset = (page - 1) * limit

		session_token = get_customer_token()
		if not session_token and not phone:
			return {"success": False, "error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}

		# Resolve phone from session if not directly provided
		if not phone:
			session = frappe.cache().get_value(f"customer_session:{session_token}")
			if not session:
				return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}
			phone = session.get("phone")

		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}

		if session_token and not validate_customer_session(normalized_phone, session_token):
			return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}

		customer = get_or_create_customer(normalized_phone)
		if not customer:
			return {"success": False, "error": {"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"}}

		# Fetch ledger entries across all restaurants
		entries = frappe.get_all(
			"Restaurant Loyalty Entry",
			filters={"customer": customer.name},
			fields=[
				"transaction_type", "coins", "reason", "restaurant",
				"reference_doctype", "reference_name",
				"posting_date", "creation", "is_settled", "expiry_date",
			],
			order_by="creation desc",
			limit=limit,
			start=offset,
		)

		# Enrich with restaurant names and compute running balance info
		total_entries = frappe.db.count("Restaurant Loyalty Entry", {"customer": customer.name})
		current_balance = flt(get_loyalty_balance(customer.name))

		formatted_entries = []
		for e in entries:
			restaurant_name = frappe.db.get_value("Restaurant", e.restaurant, "restaurant_name") if e.restaurant else "FLAMEZO"

			# Map type
			if e.transaction_type == "Earn":
				entry_type = "bonus" if "bonus" in (e.reason or "").lower() or "welcome" in (e.reason or "").lower() else "earn"
			elif e.transaction_type == "Redeem":
				entry_type = "redeem"
			else:
				entry_type = "expire"

			formatted_entries.append({
				"restaurant_name": restaurant_name,
				"restaurant_id": e.restaurant or "",
				"points": flt(e.coins),
				"type": entry_type,
				"reason": e.reason or "",
				"is_settled": bool(e.is_settled),
				"posting_date": str(e.posting_date) if e.posting_date else None,
				"timestamp": str(e.creation),
				"order_id": e.reference_name if e.reference_doctype == "Order" else None,
			})

		return {
			"success": True,
			"data": {
				"entries": formatted_entries,
				"page": page,
				"limit": limit,
				"total": total_entries,
				"has_more": (offset + limit) < total_entries,
				"current_balance": current_balance,
			}
		}

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_points_ledger: {str(e)}")
		return {"success": False, "error": {"code": "LEDGER_FETCH_ERROR", "message": str(e)}}


# ── 5. Register FLAMEZO Member ─────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def register_flamezo_member(phone, full_name=None, city=None, email=None, date_of_birth=None, interests=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.flamezo.register_flamezo_member

	Creates or updates a Customer record for FLAMEZO.
	Called after successful OTP verification to enrich the profile.

	Parameters:
	- phone (str, required): Verified phone number
	- full_name (str, optional): Customer's name
	- city (str, optional): Home city for discovery personalization
	- email (str, optional): Customer email address
	- date_of_birth (str, optional): ISO date YYYY-MM-DD
	- interests (str, optional): Comma-separated lifestyle interest tags
	"""
	try:
		session_token = get_customer_token()
		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}

		if session_token and not validate_customer_session(normalized_phone, session_token):
			return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}

		# Get or create customer
		customer = get_or_create_customer(normalized_phone, name=full_name or None)
		if not customer:
			return {"success": False, "error": {"code": "REGISTRATION_FAILED", "message": "Could not create member profile"}}

		# Update optional fields
		update_fields = {}
		if full_name:
			update_fields["customer_name"] = full_name
		if city:
			update_fields["city"] = city
		if email:
			update_fields["email"] = email.strip().lower()
		if date_of_birth:
			try:
				from datetime import datetime
				datetime.strptime(date_of_birth, "%Y-%m-%d")
				if frappe.db.has_column("Customer", "date_of_birth"):
					update_fields["date_of_birth"] = date_of_birth
			except ValueError:
				pass
		if interests is not None:
			if frappe.db.has_column("Customer", "interests"):
				update_fields["interests"] = interests.strip()[:500]

		if update_fields:
			frappe.db.set_value("Customer", customer.name, update_fields)
			frappe.db.commit()

		# Return current member state
		balance = get_loyalty_balance(customer.name)
		tier = get_loyalty_tier(customer.name)
		raw_referral = (
			frappe.db.get_value("Customer", customer.name, "referral_code")
			if frappe.db.has_column("Customer", "referral_code") else None
		)
		referral_code = raw_referral or (customer.name or "")[:8].upper()

		return {
			"success": True,
			"data": {
				"phone": normalized_phone,
				"full_name": frappe.db.get_value("Customer", customer.name, "customer_name") or full_name or "",
				"flamezo_points_balance": flt(balance),
				"tier": tier,
				"referral_code": referral_code,
				"is_new": False,
			}
		}

	except Exception as e:
		frappe.log_error(f"Error in flamezo.register_flamezo_member: {str(e)}")
		return {"success": False, "error": {"code": "REGISTRATION_ERROR", "message": str(e)}}


# ── 6. Quick Restaurant Summary (for link previews / notifications) ───────────

@frappe.whitelist(allow_guest=True)
def get_restaurant_summary(restaurant_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_restaurant_summary

	Lightweight restaurant summary for FLAMEZO link previews, notifications,
	and deep link landing pages. Faster than get_restaurant_config.

	Parameters:
	- restaurant_id (str): Restaurant identifier
	"""
	try:
		cache_key = f"flamezo:restaurant_summary:{restaurant_id}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return json.loads(cached)

		_summary_fields = ["name", "restaurant_name", "logo", "city", "plan_type", "is_active",
			"latitude", "longitude", "outlet_type", "contact_phone", "whatsapp_number", "instagram_url"]

		restaurant = frappe.db.get_value(
			"Restaurant",
			{"restaurant_id": restaurant_id},
			_summary_fields,
			as_dict=True,
		)

		if not restaurant:
			# Try by name
			restaurant = frappe.db.get_value(
				"Restaurant",
				{"name": restaurant_id},
				_summary_fields,
				as_dict=True,
			)

		if not restaurant:
			return {"success": False, "error": {"code": "RESTAURANT_NOT_FOUND", "message": "Restaurant not found"}}

		if not restaurant.is_active:
			return {"success": False, "error": {"code": "RESTAURANT_INACTIVE", "message": "Restaurant is currently inactive"}}

		config = frappe.db.get_value(
			"Restaurant Config",
			{"restaurant": restaurant.name},
			["restaurant_name", "tagline", "default_theme"],
			as_dict=True,
		) or {}

		active_offers = _batch_active_offers_count([restaurant.name]).get(restaurant.name, 0)

		response = {
			"success": True,
			"data": {
				"id": restaurant.name,
				"restaurant_name": config.get("restaurant_name") or restaurant.restaurant_name,
				"tagline": config.get("tagline") or "",
				"logo": restaurant.logo or "",
				"city": restaurant.city or "",
				"plan_type": restaurant.plan_type or "GOLD",
				"outlet_type": restaurant.outlet_type or "dining",
				"contact_phone": restaurant.contact_phone or "",
				"whatsapp_number": restaurant.whatsapp_number or "",
				"instagram_url": restaurant.instagram_url or "",
				"primary_color": "#B7410E",
				"default_theme": config.get("default_theme") or "dark",
				"latitude": restaurant.latitude,
				"longitude": restaurant.longitude,
				"active_offers_count": active_offers,
				"is_gold": True,
			}
		}

		frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=300)
		return response

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_restaurant_summary: {str(e)}")
		return {"success": False, "error": {"code": "SUMMARY_FETCH_ERROR", "message": str(e)}}


# ── 7. Customer Profile Photo Upload ─────────────────────────────────────────

@frappe.whitelist()
def upload_customer_photo():
	"""
	POST /api/method/flamezo_backend.flamezo.api.flamezo.upload_customer_photo

	Multipart upload. Accepts a single file field named 'file'.
	Validates the session token from X-Customer-Token header, saves the
	image to the Customer doctype, and returns the public file URL.
	"""
	try:
		session_token = get_customer_token()
		if not session_token:
			return {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}

		customer_id = get_customer_from_token(session_token)
		if not customer_id:
			return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}

		if "file" not in frappe.request.files:
			return {"success": False, "error": {"code": "NO_FILE", "message": "No file provided"}}

		file = frappe.request.files["file"]
		content_type = file.content_type or ""

		allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
		if content_type not in allowed_types:
			return {"success": False, "error": {"code": "INVALID_TYPE", "message": "Only JPEG, PNG and WebP images are supported"}}

		content = file.read()
		if len(content) > 5 * 1024 * 1024:
			return {"success": False, "error": {"code": "FILE_TOO_LARGE", "message": "Image must be under 5MB"}}

		from frappe.utils.file_manager import save_file

		# The custom X-Customer-Token auth does not create a real Frappe login, so
		# this request runs as the Guest user — which cannot create File docs and
		# would raise PermissionError (surfaced to the app as HTTP 403). We have
		# already validated the customer session above, so elevate to a trusted
		# user for the save only, then restore.
		original_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			frappe.flags.ignore_permissions = True

			file_doc = save_file(
				fname=file.filename or f"avatar_{customer_id}.jpg",
				content=content,
				dt="Customer",
				dn=customer_id,
				decode=False,
				is_private=0,
				folder="Home/Attachments",
			)

			frappe.db.set_value("Customer", customer_id, "image", file_doc.file_url)
			frappe.db.commit()
		finally:
			frappe.flags.ignore_permissions = False
			frappe.set_user(original_user)

		return {"success": True, "file_url": file_doc.file_url}

	except Exception as e:
		frappe.log_error(f"Error in flamezo.upload_customer_photo: {str(e)}")
		return {"success": False, "error": {"code": "UPLOAD_ERROR", "message": str(e)}}


# ── 8. Update Customer Profile ────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def update_profile(phone=None, full_name=None, email=None, date_of_birth=None, interests=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.flamezo.update_profile

	Updates editable fields on the customer record.
	Auth: X-Customer-Token header required.
	Updatable: full_name, email, date_of_birth.
	Phone is immutable (identity anchor).
	"""
	try:
		session_token = get_customer_token()
		if not session_token and not phone:
			return {"success": False, "error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}}

		if not phone:
			session = frappe.cache().get_value(f"customer_session:{session_token}")
			if not session:
				return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}
			phone = session.get("phone")

		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}

		if session_token and not validate_customer_session(normalized_phone, session_token):
			return {"success": False, "error": {"code": "SESSION_INVALID", "message": "Invalid or expired session"}}

		customer = get_or_create_customer(normalized_phone)
		if not customer:
			return {"success": False, "error": {"code": "CUSTOMER_NOT_FOUND", "message": "Customer not found"}}

		updates = {}
		if full_name is not None:
			full_name = full_name.strip()
			if not full_name:
				return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "full_name cannot be empty"}}
			updates["customer_name"] = full_name

		if email is not None:
			email = email.strip().lower()
			if email and "@" not in email:
				return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Invalid email address"}}
			updates["email"] = email

		if date_of_birth is not None:
			try:
				from frappe.utils import getdate as _gd
				dob = _gd(date_of_birth)
				from datetime import date as _date
				if dob > _date.today():
					return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Date of birth cannot be in the future"}}
				updates["date_of_birth"] = str(dob)
			except Exception:
				return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Invalid date_of_birth format (use YYYY-MM-DD)"}}

		if interests is not None:
			# Comma-separated lifestyle interest tags (mirrors register_flamezo_member).
			if frappe.db.has_column("Customer", "interests"):
				updates["interests"] = interests.strip()[:500]

		if not updates:
			return {"success": False, "error": {"code": "NO_FIELDS", "message": "No updatable fields provided"}}

		frappe.db.set_value("Customer", customer.name, updates)
		frappe.db.commit()

		return {
			"success": True,
			"data": {
				"phone": normalized_phone,
				"full_name": updates.get("customer_name", customer.customer_name or ""),
				"email": updates.get("email", customer.email or ""),
				"date_of_birth": updates.get("date_of_birth", str(customer.date_of_birth) if customer.date_of_birth else None),
			}
		}

	except Exception as e:
		frappe.log_error(f"Error in flamezo.update_profile: {str(e)}")
		return {"success": False, "error": {"code": "UPDATE_ERROR", "message": str(e)}}
