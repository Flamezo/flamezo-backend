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
	"""Fast fetch of primary_color from Restaurant Config."""
	return frappe.db.get_value(
		"Restaurant Config",
		{"restaurant": restaurant_name},
		"primary_color"
	) or "#DB782F"


def _get_active_offers_count(restaurant_name):
	"""Count currently active coupons with a minimum order amount for a restaurant."""
	today_date = getdate(today())
	try:
		rows = frappe.db.get_list(
			"Coupon",
			filters={
				"restaurant": restaurant_name,
				"is_active": 1,
			},
			fields=["valid_from", "valid_until"],
			ignore_permissions=True,
		)
		count = 0
		for r in rows:
			raw_from = r.get("valid_from")
			raw_until = r.get("valid_until")
			if raw_from and getdate(raw_from) > today_date:
				continue
			if raw_until and getdate(raw_until) < today_date:
				continue
			count += 1
		return count
	except Exception:
		return 0


# ── 1. Discovery — All Restaurants ───────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_all_restaurants(latitude=None, longitude=None, search=None, city=None, page=1, limit=30):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_all_restaurants

	Returns all active FLAMEZO-enrolled restaurants for the discovery feed.
	Sorted by distance if lat/lon provided, else by onboarding date desc.

	Parameters:
	- latitude (float, optional): User's latitude for distance sorting
	- longitude (float, optional): User's longitude for distance sorting
	- search (str, optional): Name/cuisine/city filter
	- city (str, optional): City filter
	- page (int): Page number (default 1)
	- limit (int): Results per page (default 30, max 100)
	"""
	try:
		page = cint(page) or 1
		limit = min(cint(limit) or 30, 100)
		offset = (page - 1) * limit

		# Cache key — include location bucket for distance sorting (rounded to 0.1 deg ~11km)
		lat_bucket = round(flt(latitude), 1) if latitude else None
		lon_bucket = round(flt(longitude), 1) if longitude else None
		cache_key = f"flamezo:restaurants:{lat_bucket}:{lon_bucket}:{search or ''}:{city or ''}:{page}:{limit}"

		if frappe.session.user == "Guest":
			cached = frappe.cache().get_value(cache_key)
			if cached:
				return json.loads(cached)

		# Build filters
		filters: dict = {"is_active": 1}
		if city:
			filters["city"] = ["like", f"%{city}%"]

		fields = [
			"name", "restaurant_name", "logo", "latitude", "longitude",
			"city", "plan_type", "onboarding_date",
			"description",
		]

		# Search across name, cuisine, city
		if search:
			restaurants = frappe.get_all(
				"Restaurant",
				filters={**filters, "restaurant_name": ["like", f"%{search}%"]},
				fields=fields,
				order_by="onboarding_date desc",
				limit=limit,
				start=offset,
			)
			if not restaurants:
				restaurants = frappe.get_all(
					"Restaurant",
					filters={**filters, "city": ["like", f"%{search}%"]},
					fields=fields,
					order_by="onboarding_date desc",
					limit=limit,
					start=offset,
				)
		else:
			restaurants = frappe.get_all(
				"Restaurant",
				filters=filters,
				fields=fields,
				order_by="onboarding_date desc",
				limit=limit * 3 if latitude else limit,  # Fetch extra for distance re-sort
				start=0 if latitude else offset,
			)

		# Enrich each restaurant
		user_lat = flt(latitude) if latitude else None
		user_lon = flt(longitude) if longitude else None

		enriched = []
		for r in restaurants:
			# Get branding primary color (single fast query per restaurant)
			primary_color = _get_restaurant_primary_color(r.name)

			# Get logo URL — use existing logo field or media asset
			logo_url = r.logo or ""

			# Distance
			distance_km = None
			if user_lat and user_lon and r.latitude and r.longitude:
				distance_km = round(_haversine_km(user_lat, user_lon, flt(r.latitude), flt(r.longitude)), 1)

			# Active offers count
			active_offers = _get_active_offers_count(r.name)

			enriched.append({
				"name": r.name,
				"restaurant_name": r.restaurant_name,
				"logo": logo_url,
				"latitude": r.latitude,
				"longitude": r.longitude,
				"city": r.city or "",
				"plan_type": r.plan_type or "SILVER",
				"primaryColor": primary_color,
				"tagline": r.description or "",
				"distance_km": distance_km,
				"active_offers_count": active_offers,
			})

		# Sort by distance if coords provided, then paginate
		if user_lat and user_lon:
			enriched.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 99999)
			enriched = enriched[offset: offset + limit]

		total = frappe.db.count("Restaurant", filters=filters)

		response = {
			"success": True,
			"data": {
				"restaurants": enriched,
				"page": page,
				"limit": limit,
				"total": total,
				"has_more": (offset + limit) < total,
			}
		}

		if frappe.session.user == "Guest":
			frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=120)

		return response

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_all_restaurants: {str(e)}")
		return {"success": False, "error": {"code": "DISCOVERY_ERROR", "message": str(e)}}


# ── 2. Cross-Restaurant Offers Feed ──────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_cross_restaurant_offers(city=None, page=1, limit=30):
	"""
	GET /api/method/flamezo_backend.flamezo.api.flamezo.get_cross_restaurant_offers

	Returns active coupons/offers across all GOLD-plan FLAMEZO restaurants.
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

		# Get all active GOLD restaurants (only GOLD has offers feature)
		restaurant_filters: dict = {"is_active": 1, "plan_type": "GOLD"}
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

		# Referral code — use customer name as referral code if not set
		raw_referral = frappe.db.get_value("Customer", customer.name, "referral_code")
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
def register_flamezo_member(phone, full_name=None, city=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.flamezo.register_flamezo_member

	Creates or updates a Customer record for FLAMEZO.
	Called after successful OTP verification to enrich the profile.

	Parameters:
	- phone (str, required): Verified phone number
	- full_name (str, optional): Customer's name
	- city (str, optional): Home city for discovery personalization
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

		if update_fields:
			frappe.db.set_value("Customer", customer.name, update_fields)
			frappe.db.commit()

		# Return current member state
		balance = get_loyalty_balance(customer.name)
		tier = get_loyalty_tier(customer.name)
		raw_referral = frappe.db.get_value("Customer", customer.name, "referral_code")
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

		restaurant = frappe.db.get_value(
			"Restaurant",
			{"restaurant_id": restaurant_id},
			["name", "restaurant_name", "logo", "city", "plan_type", "is_active", "latitude", "longitude"],
			as_dict=True,
		)

		if not restaurant:
			# Try by name
			restaurant = frappe.db.get_value(
				"Restaurant",
				{"name": restaurant_id},
				["name", "restaurant_name", "logo", "city", "plan_type", "is_active", "latitude", "longitude"],
				as_dict=True,
			)

		if not restaurant:
			return {"success": False, "error": {"code": "RESTAURANT_NOT_FOUND", "message": "Restaurant not found"}}

		if not restaurant.is_active:
			return {"success": False, "error": {"code": "RESTAURANT_INACTIVE", "message": "Restaurant is currently inactive"}}

		config = frappe.db.get_value(
			"Restaurant Config",
			{"restaurant": restaurant.name},
			["restaurant_name", "tagline", "primary_color", "default_theme"],
			as_dict=True,
		) or {}

		active_offers = _get_active_offers_count(restaurant.name)

		response = {
			"success": True,
			"data": {
				"id": restaurant.name,
				"restaurant_name": config.get("restaurant_name") or restaurant.restaurant_name,
				"tagline": config.get("tagline") or "",
				"logo": restaurant.logo or "",
				"city": restaurant.city or "",
				"plan_type": restaurant.plan_type or "SILVER",
				"primary_color": config.get("primary_color") or "#DB782F",
				"default_theme": config.get("default_theme") or "dark",
				"latitude": restaurant.latitude,
				"longitude": restaurant.longitude,
				"active_offers_count": active_offers,
				"is_gold": restaurant.plan_type == "GOLD",
			}
		}

		frappe.cache().set_value(cache_key, json.dumps(response), expires_in_sec=300)
		return response

	except Exception as e:
		frappe.log_error(f"Error in flamezo.get_restaurant_summary: {str(e)}")
		return {"success": False, "error": {"code": "SUMMARY_FETCH_ERROR", "message": str(e)}}
