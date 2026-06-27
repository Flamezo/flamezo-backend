# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Coupons
All endpoints require restaurant_id for SaaS multi-tenancy
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, now_datetime, get_datetime, add_to_date
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api, get_restaurant_from_id
from flamezo_backend.flamezo.utils.feature_gate import require_plan
from flamezo_backend.flamezo.utils.customer_helpers import (
	get_customer_token,
	get_customer_from_token,
	has_active_customer_session,
	normalize_phone,
)
import json

DEFAULT_DAILY_CLAIM_LIMIT = 30


def _check_daily_limit(coupon_name, daily_limit):
	"""Return True if the daily claim limit has been reached for this coupon."""
	limit = int(daily_limit) if daily_limit else DEFAULT_DAILY_CLAIM_LIMIT
	if limit <= 0:
		return False
	count = frappe.db.count(
		"Offer Claim",
		filters={"coupon": coupon_name, "claimed_at": [">=", today()]},
	)
	return count >= limit
import csv
import io
from datetime import datetime, timedelta


@frappe.whitelist(allow_guest=True)
def get_coupons(restaurant_id, active_only=True):
	"""
	GET /api/method/flamezo_backend.flamezo.api.coupons.get_coupons
	Get all available coupons for a restaurant
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Build filters
		filters = {"restaurant": restaurant}
		
		if active_only:
			filters["is_active"] = 1
		
		# Get coupons — always fetch active ones; day/time-gated are returned with
		# currentlyRedeemable=False so the customer-facing UI can tease future offers.
		coupons = frappe.get_all(
			"Coupon",
			fields=[
				"name as id",
				"code",
				"discount_value as discount",
				"min_order_amount",
				"discount_type as type",
				"offer_type",
				"category",
				"description",
				"detailed_description",
				"is_active",
				"valid_from",
				"valid_until",
				"valid_days_of_week",
				"valid_time_start",
				"valid_time_end",
				"daily_limit",
			],
			filters=filters,
			order_by="code asc"
		)

		# Batch-fetch today's claim counts for all coupons in one query
		coupon_ids = [c["id"] for c in coupons]
		claimed_today_map = {}
		if coupon_ids:
			rows = frappe.db.sql(
				f"""SELECT coupon, COUNT(*) as cnt FROM `tabOffer Claim`
				WHERE coupon IN ({', '.join(['%s'] * len(coupon_ids))})
				AND claimed_at >= %s
				GROUP BY coupon""",
				tuple(coupon_ids) + (today(),),
				as_dict=True,
			)
			claimed_today_map = {r.coupon: r.cnt for r in rows}

		today_date = today()
		current_dt = now_datetime()
		current_day = current_dt.strftime("%A").lower()
		current_time = current_dt.time()

		formatted_coupons = []

		for coupon in coupons:
			# Skip coupons not yet started or truly expired — they're useless to show.
			valid_from = coupon.get("valid_from")
			valid_until = coupon.get("valid_until")
			if valid_from and getdate(valid_from) > getdate(today_date):
				continue
			if valid_until and getdate(valid_until) < getdate(today_date):
				continue

			# Determine real-time redeemability (day + time gates).
			currently_redeemable = True
			ineligibility_hint = None

			if coupon.get("valid_days_of_week"):
				try:
					raw = coupon["valid_days_of_week"]
					valid_days = json.loads(raw) if isinstance(raw, str) else list(raw)
					valid_days_lower = [d.lower() for d in valid_days]
					if current_day not in valid_days_lower:
						currently_redeemable = False
						day_labels = ", ".join(d.capitalize() for d in valid_days)
						ineligibility_hint = f"Available on {day_labels} only"
				except Exception:
					pass

			if currently_redeemable and (coupon.get("valid_time_start") or coupon.get("valid_time_end")):
				try:
					ts = coupon.get("valid_time_start")
					te = coupon.get("valid_time_end")
					start = datetime.strptime(str(ts).split(".")[0], "%H:%M:%S").time() if ts else None
					end = datetime.strptime(str(te).split(".")[0], "%H:%M:%S").time() if te else None

					def _fmt(t):
						return datetime.strptime(str(t).split(".")[0], "%H:%M:%S").strftime("%-I:%M %p")

					if start and current_time < start:
						currently_redeemable = False
						ineligibility_hint = f"Available from {_fmt(ts)}" + (f" to {_fmt(te)}" if te else "")
					elif end and current_time > end:
						currently_redeemable = False
						ineligibility_hint = f"Available {_fmt(ts) if ts else ''} – {_fmt(te)}"
				except Exception:
					pass

			daily_limit = int(coupon.get("daily_limit") or DEFAULT_DAILY_CLAIM_LIMIT)
			claimed_today = claimed_today_map.get(coupon["id"], 0)
			slots_remaining = max(0, daily_limit - claimed_today) if daily_limit > 0 else None

			coupon_data = {
				"id": str(coupon["id"]),
				"code": coupon["code"],
				"discount": flt(coupon["discount"]),
				"minOrderAmount": flt(coupon.get("min_order_amount", 0)),
				"type": coupon.get("type", "flat"),
				"offerType": coupon.get("offer_type", "coupon"),
				"isActive": bool(coupon.get("is_active", False)),
				"currentlyRedeemable": currently_redeemable,
				"dailyLimit": daily_limit,
				"slotsRemaining": slots_remaining,
				"claimedToday": claimed_today,
			}

			if ineligibility_hint:
				coupon_data["ineligibilityHint"] = ineligibility_hint
			if coupon.get("valid_days_of_week"):
				coupon_data["validDays"] = coupon["valid_days_of_week"]
			if coupon.get("valid_time_start"):
				coupon_data["validTimeStart"] = str(coupon["valid_time_start"])
			if coupon.get("valid_time_end"):
				coupon_data["validTimeEnd"] = str(coupon["valid_time_end"])
			if coupon.get("category"):
				coupon_data["category"] = coupon["category"]
			if coupon.get("description"):
				coupon_data["description"] = coupon["description"]
			if coupon.get("detailed_description"):
				coupon_data["detailedDescription"] = coupon["detailed_description"]
			if coupon.get("valid_from"):
				coupon_data["validFrom"] = str(coupon["valid_from"])
			if coupon.get("valid_until"):
				coupon_data["validUntil"] = str(coupon["valid_until"])

			formatted_coupons.append(coupon_data)
		
		return {
			"success": True,
			"data": {
				"coupons": formatted_coupons
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_coupons: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "COUPON_FETCH_ERROR",
				"message": str(e)
			}
		}


def get_coupon_details(restaurant, coupon_code, cart_total=0, customer_id=None, cart_items=None):
	"""
	Internal helper to validate a coupon and return its details.
	Does NOT use validate_restaurant_for_api (expects restaurant object/id).
	"""
	# Find coupon with all fields
	coupon = frappe.db.get_value(
		"Coupon",
		{"code": coupon_code, "restaurant": restaurant},
		[
			"name", "code", "discount_value", "min_order_amount", "discount_type", 
			"category", "is_active", "valid_from", "valid_until", "max_uses", 
			"usage_count", "max_uses_per_user", "offer_type", "valid_days_of_week",
			"valid_time_start", "valid_time_end", "max_discount_cap",
			"priority", "can_stack"
		],
		as_dict=True
	)
	
	if not coupon:
		return {"success": False, "error_code": "COUPON_NOT_FOUND", "message": f"Coupon code {coupon_code} not found"}
	
	if not coupon.is_active:
		return {"success": False, "error_code": "COUPON_INACTIVE", "message": "Coupon is not active"}
	
	# Check validity dates
	today_date = today()
	if coupon.valid_from and getdate(coupon.valid_from) > getdate(today_date):
		return {"success": False, "error_code": "COUPON_NOT_VALID_YET", "message": "Coupon is not valid yet"}
	
	if coupon.valid_until and getdate(coupon.valid_until) < getdate(today_date):
		return {"success": False, "error_code": "COUPON_EXPIRED", "message": "Coupon has expired"}
	
	# Check minimum order amount
	cart_total = flt(cart_total)
	if coupon.min_order_amount and cart_total < coupon.min_order_amount:
		return {"success": False, "error_code": "MIN_ORDER_NOT_MET", "message": f"Minimum order amount of {coupon.min_order_amount} required"}
	
	# Check max uses
	if coupon.max_uses and coupon.usage_count and coupon.usage_count >= coupon.max_uses:
		return {"success": False, "error_code": "COUPON_LIMIT_REACHED", "message": "Coupon usage limit reached"}
	
	# Check per-customer usage limit
	if coupon.max_uses_per_user and customer_id:
		customer_usage_count = frappe.db.count("Coupon Usage", {"coupon": coupon.name, "customer": customer_id})
		if customer_usage_count >= coupon.max_uses_per_user:
			return {"success": False, "error_code": "CUSTOMER_LIMIT_REACHED", "message": f"You have already used this coupon {customer_usage_count} times"}
	
	# Day/Time checks... (Skipping detail for brevity in this thought, but I'll include them in the code)
	# Check day of week
	if coupon.valid_days_of_week:
		try:
			valid_days = json.loads(coupon.valid_days_of_week) if isinstance(coupon.valid_days_of_week, str) else coupon.valid_days_of_week
			if valid_days and isinstance(valid_days, list):
				current_day = now_datetime().strftime("%A").lower()
				valid_days_lower = [d.lower() for d in valid_days]
				if current_day not in valid_days_lower:
					return {"success": False, "error_code": "INVALID_DAY", "message": f"This offer is only valid on: {', '.join(valid_days)}"}
		except: pass

	# Check time of day
	if coupon.valid_time_start or coupon.valid_time_end:
		current_time = now_datetime().time()
		if coupon.valid_time_start:
			start = datetime.strptime(str(coupon.valid_time_start).split(".")[0], "%H:%M:%S").time()
			if current_time < start:
				return {"success": False, "error_code": "INVALID_TIME", "message": f"This offer is valid from {coupon.valid_time_start}"}
		if coupon.valid_time_end:
			end = datetime.strptime(str(coupon.valid_time_end).split(".")[0], "%H:%M:%S").time()
			if current_time > end:
				return {"success": False, "error_code": "INVALID_TIME", "message": f"This offer is valid until {coupon.valid_time_end}"}



	# Calculate discount amount
	discount_amount = flt(coupon.discount_value)
	if coupon.discount_type == "percent":
		discount_amount = (cart_total * flt(coupon.discount_value)) / 100
		if coupon.max_discount_cap and discount_amount > flt(coupon.max_discount_cap):
			discount_amount = flt(coupon.max_discount_cap)
	
	return {
		"success": True,
		"coupon_name": coupon.name,
		"coupon_code": coupon.code,
		"discount_amount": discount_amount,
		"discount_value": flt(coupon.discount_value),
		"min_order_amount": flt(coupon.min_order_amount or 0),
		"type": coupon.discount_type or "flat",
		"offer_type": coupon.offer_type or "coupon",
		"category": coupon.category or "",
		"description": coupon.description or "",
		"priority": coupon.priority or 0,
		"can_stack": bool(coupon.can_stack)
	}

@frappe.whitelist(allow_guest=True)
def validate_coupon(restaurant_id, coupon_code, cart_total=0, customer_id=None, cart_items=None, phone=None):
	"""API wrapper for get_coupon_details.

	Coupons are a Savings-Corner feature — gated behind verification. Requires
	an X-Customer-Token in headers bound to ``phone``. If the caller doesn't
	pass a phone (legacy callers), we fall back to identifying via the token
	alone, but we still reject if the token is missing/invalid.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		# Verification gate. Two paths:
		#   1. Modern client: passes phone + token → strict phone/token match check.
		#   2. Legacy client: token only → derive identity from token, still requires a valid one.
		token = get_customer_token()
		if phone:
			normalized = normalize_phone(phone)
			if not has_active_customer_session(normalized):
				return {
					"success": False,
					"error": {
						"code": "COUPON_REQUIRES_VERIFICATION",
						"message": "Verify your phone with OTP to use coupons."
					}
				}
		token_customer_id = get_customer_from_token(token)
		if token_customer_id:
			customer_id = token_customer_id
		elif not phone:
			# No token AND no phone — definitely unverified.
			return {
				"success": False,
				"error": {
					"code": "COUPON_REQUIRES_VERIFICATION",
					"message": "Verify your phone with OTP to use coupons."
				}
			}

		result = get_coupon_details(restaurant, coupon_code, cart_total, customer_id, cart_items)
		
		if not result.get("success"):
			return {
				"success": False,
				"error": {
					"code": result.get("error_code"),
					"message": result.get("message")
				}
			}
			
		return {
			"success": True,
			"data": {
				"coupon": {
					"id": result["coupon_name"],
					"code": result["coupon_code"],
					"discount": result["discount_value"],
					"discountAmount": result["discount_amount"],
					"minOrderAmount": result["min_order_amount"],
					"type": result["type"],
					"offerType": result["offer_type"],
					"category": result["category"],
					"description": result["description"],
					"isEligible": True
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in validate_coupon: {str(e)}")
		return {"success": False, "error": {"code": "COUPON_VALIDATION_ERROR", "message": str(e)}}



@frappe.whitelist()
def export_coupons(restaurant_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.coupons.export_coupons
	Export all coupons for a restaurant as a CSV file download.
	Enables multi-outlet replication and backup.
	"""
	restaurant = validate_restaurant_for_api(restaurant_id)

	coupons = frappe.get_all(
		"Coupon",
		filters={"restaurant": restaurant},
		fields=[
			"code", "offer_type", "discount_type", "discount_value", "min_order_amount",
			"max_discount_cap", "description", "detailed_description", "category",
			"priority", "can_stack", "is_active", "valid_from", "valid_until",
			"valid_days_of_week", "valid_time_start", "valid_time_end",
			"max_uses", "max_uses_per_user",
		],
		order_by="code asc",
	)

	columns = [
		"code", "offer_type", "discount_type", "discount_value", "min_order_amount",
		"max_discount_cap", "description", "detailed_description", "category",
		"priority", "can_stack", "is_active", "valid_from", "valid_until",
		"valid_days_of_week", "valid_time_start", "valid_time_end",
		"max_uses", "max_uses_per_user",
	]

	output = io.StringIO()
	writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
	writer.writeheader()
	for coupon in coupons:
		row = {col: (coupon.get(col) or "") for col in columns}
		writer.writerow(row)

	csv_bytes = output.getvalue().encode("utf-8")
	frappe.local.response.filename = f"coupons_{restaurant_id}.csv"
	frappe.local.response.filecontent = csv_bytes
	frappe.local.response.type = "download"


@frappe.whitelist()
def import_coupons(restaurant_id, csv_content, overwrite_existing=False):
	"""
	POST /api/method/flamezo_backend.flamezo.api.coupons.import_coupons
	Bulk-import coupons from CSV content string.
	Skips rows with duplicate codes unless overwrite_existing=True.
	Returns counts of created / updated / skipped rows.
	"""
	restaurant = validate_restaurant_for_api(restaurant_id)

	created = updated = skipped = 0
	errors = []

	try:
		reader = csv.DictReader(io.StringIO(csv_content))
	except Exception as e:
		return {"success": False, "error": f"Invalid CSV: {str(e)}"}

	for i, row in enumerate(reader, start=2):  # row 1 = header
		code = (row.get("code") or "").strip().upper()
		if not code:
			errors.append(f"Row {i}: missing code, skipped")
			skipped += 1
			continue

		existing = frappe.db.get_value("Coupon", {"code": code, "restaurant": restaurant}, "name")

		if existing and not overwrite_existing:
			skipped += 1
			continue

		fields = {
			"restaurant": restaurant,
			"code": code,
			"offer_type": row.get("offer_type") or "coupon",
			"discount_type": row.get("discount_type") or "flat",
			"discount_value": flt(row.get("discount_value") or 0),
			"min_order_amount": flt(row.get("min_order_amount") or 0),
			"max_discount_cap": flt(row.get("max_discount_cap") or 0) or None,
			"description": row.get("description") or "",
			"detailed_description": row.get("detailed_description") or "",
			"category": row.get("category") or "",
			"priority": int(row.get("priority") or 0),
			"can_stack": int(row.get("can_stack") or 0),
			"is_active": int(row.get("is_active") or 1),
			"valid_from": row.get("valid_from") or None,
			"valid_until": row.get("valid_until") or None,
			"valid_days_of_week": row.get("valid_days_of_week") or None,
			"valid_time_start": row.get("valid_time_start") or None,
			"valid_time_end": row.get("valid_time_end") or None,
			"max_uses": int(row.get("max_uses") or 0),
			"max_uses_per_user": int(row.get("max_uses_per_user") or 0),
		}

		try:
			if existing:
				doc = frappe.get_doc("Coupon", existing)
				doc.update(fields)
				doc.save(ignore_permissions=True)
				updated += 1
			else:
				doc = frappe.get_doc({"doctype": "Coupon", **fields})
				doc.insert(ignore_permissions=True)
				created += 1
		except Exception as e:
			errors.append(f"Row {i} ({code}): {str(e)}")
			skipped += 1

	frappe.db.commit()

	return {
		"success": True,
		"data": {
			"created": created,
			"updated": updated,
			"skipped": skipped,
			"errors": errors,
		}
	}


@frappe.whitelist()
def generate_coupon_suggestions(restaurant_id, tone="attractive", offer_type_filter=None, count=6):
	"""
	POST /api/method/flamezo_backend.flamezo.api.coupons.generate_coupon_suggestions
	Generate AI-powered coupon suggestions using Gemini 2.5 Flash.

	Quota: 10 free generations/restaurant/month.
	After quota: costs 2 wallet coins per generation.

	Args:
		restaurant_id: Restaurant identifier
		tone: "calm" | "attractive" | "aggressive"
		offer_type_filter: Optional offer type to restrict generation to
		count: Number of suggestions (3–8)
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		require_plan(restaurant, ["GOLD"])

		count = max(3, min(int(count or 6), 8))

		from flamezo_backend.flamezo.services.ai.coupon_generator import (
			generate_suggestions, FREE_MONTHLY_QUOTA, _check_quota_status,
		)
		from flamezo_backend.flamezo.api.coin_billing import deduct_coins

		COINS_PER_AI_COUPON = 2  # cost after free quota exhausted

		# Check quota WITHOUT incrementing to decide if we need coins
		quota_status = _check_quota_status(restaurant)

		if not quota_status["free_remaining"]:
			# Quota exhausted — deduct 2 coins per generation
			balance = flt(frappe.db.get_value("Restaurant", restaurant, "coins_balance") or 0)
			if balance < COINS_PER_AI_COUPON:
				return {
					"success": False,
					"error_code": "INSUFFICIENT_BALANCE",
					"message": (
						f"Your {FREE_MONTHLY_QUOTA} free AI generations for this month are used up. "
						f"Each additional generation costs {COINS_PER_AI_COUPON} wallet coins. "
						f"Your current balance is ₹{balance:.0f}. Please recharge your wallet."
					),
					"quota": quota_status,
					"coins_required": COINS_PER_AI_COUPON,
					"current_balance": balance,
				}

		# Run generation (this increments quota internally)
		result = generate_suggestions(
			restaurant_id=restaurant,
			tone=tone,
			offer_type_filter=offer_type_filter,
			count=count,
		)

		if not result.get("success"):
			return result

		# If we consumed a paid slot, deduct coins
		if not quota_status["free_remaining"]:
			try:
				deduct_coins(
					restaurant=restaurant,
					amount=COINS_PER_AI_COUPON,
					type="AI Deduction",
					description=f"AI coupon generation ({tone} tone, {count} suggestions)",
				)
				result["coins_deducted"] = COINS_PER_AI_COUPON
			except Exception as e:
				frappe.log_error(f"Coin deduction failed after AI coupon gen: {e}", "AI Coupon Billing")
				# Don't fail the request — suggestions were already generated

		return {
			"success": True,
			"data": {
				"suggestions": result["suggestions"],
				"quota": result["quota"],
				"tone": result["tone"],
				"coins_deducted": result.get("coins_deducted", 0),
			}
		}

	except Exception as e:
		frappe.log_error(f"Error in generate_coupon_suggestions: {str(e)}")
		return {
			"success": False,
			"error": {"code": "AI_GENERATION_ERROR", "message": str(e)}
		}


@frappe.whitelist()
def get_ai_coupon_quota(restaurant_id):
	"""
	GET quota status for AI coupon generation without consuming a generation.
	Returns used/limit/resets_on/free_remaining/coins_per_paid.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		from flamezo_backend.flamezo.services.ai.coupon_generator import (
			_check_quota_status, FREE_MONTHLY_QUOTA,
		)
		status = _check_quota_status(restaurant)
		balance = flt(frappe.db.get_value("Restaurant", restaurant, "coins_balance") or 0)
		return {
			"success": True,
			"data": {
				**status,
				"coins_per_paid_generation": 2,
				"wallet_balance": balance,
			}
		}
	except Exception as e:
		return {"success": False, "error": {"code": "QUOTA_CHECK_ERROR", "message": str(e)}}


@frappe.whitelist(allow_guest=True)
def get_applicable_offers(restaurant_id, cart_items, cart_total, customer_id=None, order_type=None):
	"""
	POST /api/method/flamezo_backend.flamezo.api.coupons.get_applicable_offers
	Get ALL offers (both eligible and ineligible) with detailed reasons
	Returns: {
		"eligibleOffers": [],
		"ineligibleOffers": [],
		"bestOffer": {}
	}
	Frontend can show ineligible offers in disabled state with hints
	"""
	try:
		# Validate restaurant
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Production Auth: Prioritize identity from session token for secure usage limit checks
		token = get_customer_token()
		token_customer_id = get_customer_from_token(token)
		if token_customer_id:
			customer_id = token_customer_id
		
		cart_total = flt(cart_total)
		
		# Get all active offers for restaurant (including coupons for display)
		today_date = today()
		current_day = now_datetime().strftime("%A").lower()
		current_time = now_datetime().time()
		
		offers = frappe.get_all(
			"Coupon",
			filters={
				"restaurant": restaurant,
				"is_active": 1
			},
			fields=[
				"name", "code", "discount_value", "min_order_amount", "discount_type",
				"offer_type", "valid_from", "valid_until", "max_uses", "usage_count",
				"max_discount_cap", "priority", "can_stack", "max_uses_per_user",
				"valid_days_of_week", "valid_time_start", "valid_time_end",
				"category", "description", "detailed_description",
				"combo_type", "combo_name", "required_items", "item_pool",
				"items_to_select", "combo_price", "bogo_free_item_value", "free_item", "display_on_menu",
			],
			order_by="priority desc, discount_value desc"
		)
		
		eligible_offers = []
		ineligible_offers = []
		
		if isinstance(cart_items, str):
			try:
				cart_items = json.loads(cart_items)
			except Exception:
				cart_items = []

		# Extract cart dish IDs once
		cart_dish_ids = []
		if isinstance(cart_items, list):
			for item in cart_items:
				if isinstance(item, dict):
					cart_dish_ids.append(item.get("dishId") or item.get("dish_id"))
				else:
					cart_dish_ids.append(str(item))
		
		for offer in offers:
			is_eligible = True
			is_truly_ineligible = False
			ineligibility_reasons = []

			# Skip if not within validity dates
			if offer.valid_from and getdate(offer.valid_from) > getdate(today_date):
				continue # Not valid yet
			if offer.valid_until and getdate(offer.valid_until) < getdate(today_date):
				continue # Expired
			
			# Check day of week
			if offer.valid_days_of_week:
				try:
					valid_days = json.loads(offer.valid_days_of_week) if isinstance(offer.valid_days_of_week, str) else offer.valid_days_of_week
					if valid_days and isinstance(valid_days, list):
						valid_days_lower = [d.lower() for d in valid_days]
						if current_day not in valid_days_lower:
							is_eligible = False
							is_truly_ineligible = True
							days_display = ", ".join([d.capitalize() for d in valid_days])
							ineligibility_reasons.append({
								"code": "INVALID_DAY",
								"message": f"Valid only on: {days_display}",
								"type": "schedule",
								"validDays": valid_days
							})
				except:
					pass
			
			# Check time of day
			if offer.valid_time_start:
				try:
					start_time = datetime.strptime(str(offer.valid_time_start).split(".")[0], "%H:%M:%S").time()
					if current_time < start_time:
						is_eligible = False
						is_truly_ineligible = True
						ineligibility_reasons.append({
							"code": "TOO_EARLY",
							"message": f"Available from {offer.valid_time_start}",
							"type": "schedule",
							"validFrom": str(offer.valid_time_start)
						})
				except:
					pass
			if offer.valid_time_end:
				try:
					end_time = datetime.strptime(str(offer.valid_time_end).split(".")[0], "%H:%M:%S").time()
					if current_time > end_time:
						is_eligible = False
						is_truly_ineligible = True
						ineligibility_reasons.append({
							"code": "TOO_LATE",
							"message": f"Available until {offer.valid_time_end}",
							"type": "schedule",
							"validUntil": str(offer.valid_time_end)
						})
				except:
					pass
			
			# Check minimum order amount
			amount_needed = 0
			if offer.min_order_amount and cart_total < offer.min_order_amount:
				is_eligible = False
				amount_needed = flt(offer.min_order_amount) - cart_total
				ineligibility_reasons.append({
					"code": "MIN_ORDER_NOT_MET",
					"message": f"Add ₹{int(amount_needed)} more to unlock",
					"type": "cart_value",
					"minOrderAmount": flt(offer.min_order_amount),
					"currentAmount": cart_total,
					"amountNeeded": amount_needed
				})
			
			# Check max uses
			if offer.max_uses and offer.usage_count and offer.usage_count >= offer.max_uses:
				is_eligible = False
				is_truly_ineligible = True
				ineligibility_reasons.append({
					"code": "LIMIT_REACHED",
					"message": "Offer limit reached",
					"type": "usage"
				})
			
			# Check per-customer usage
			if offer.max_uses_per_user and customer_id:
				customer_usage = frappe.db.count(
					"Coupon Usage",
					{"coupon": offer.name, "customer": customer_id}
				)
				if customer_usage >= offer.max_uses_per_user:
					is_eligible = False
					is_truly_ineligible = True
					ineligibility_reasons.append({
						"code": "CUSTOMER_LIMIT_REACHED",
						"message": f"You've already used this offer {customer_usage} time(s)",
						"type": "usage",
						"usedCount": customer_usage,
						"maxUses": offer.max_uses_per_user
					})

			# ── Combo eligibility checks ─────────────────────────────────────────
			combo_type = offer.get("combo_type") or "fixed_bundle"
			combo_meta = {}  # extra combo info sent to frontend

			# Dine-in: cart is always empty; validate on bill total only.
			# Online ordering: validate cart items against pool/required_items.
			is_dine_in = (order_type == "dine_in") or (not cart_items)

			if offer.offer_type == "combo":
				# Parse pools / required items
				required_ids = []
				item_pool_ids = []
				try:
					if offer.required_items:
						raw = offer.required_items
						required_ids = json.loads(raw) if isinstance(raw, str) else list(raw)
				except Exception: pass
				try:
					if offer.item_pool:
						raw = offer.item_pool
						item_pool_ids = json.loads(raw) if isinstance(raw, str) else list(raw)
				except Exception: pass

				items_needed = int(offer.get("items_to_select") or 2)
				combo_price_val = flt(offer.combo_price or 0)
				bogo_value = flt(offer.get("bogo_free_item_value") or 0)

				# Fetch product names for human-readable hints
				all_pool_ids = list(set(required_ids + item_pool_ids))
				product_names = {}
				if all_pool_ids:
					rows = frappe.get_all(
						"Menu Product",
						filters={"product_id": ["in", all_pool_ids]},
						fields=["product_id", "product_name", "price"],
					)
					product_names = {r.product_id: {"name": r.product_name, "price": flt(r.price)} for r in rows}

				if combo_type == "fixed_bundle":
					if is_dine_in:
						# Dine-in: bill must reach combo_price
						if combo_price_val > 0 and cart_total < combo_price_val:
							is_eligible = False
							ineligibility_reasons.append({
								"code": "BILL_TOO_LOW",
								"message": f"Bill must be at least ₹{int(combo_price_val)} for this combo",
								"type": "cart_value",
								"minOrderAmount": combo_price_val,
								"currentAmount": cart_total,
								"amountNeeded": max(0, combo_price_val - cart_total),
							})
					else:
						missing = [r for r in required_ids if r not in cart_dish_ids]
						if missing:
							is_eligible = False
							missing_names = [product_names.get(m, {}).get("name", m) for m in missing]
							ineligibility_reasons.append({
								"code": "COMBO_ITEMS_MISSING",
								"message": f"Add {', '.join(missing_names)} to use this combo",
								"type": "combo",
								"missingItems": missing,
								"missingItemNames": missing_names,
								"requiredItems": required_ids,
							})
					combo_meta = {
						"comboType": "fixed_bundle",
						"requiredItems": required_ids,
						"requiredItemNames": [product_names.get(r, {}).get("name", r) for r in required_ids],
						"comboPrice": combo_price_val,
						"comboName": offer.get("combo_name") or offer.description or "",
					}

				elif combo_type == "bogo":
					if is_dine_in:
						# Dine-in: bogo_free_item_value must be set and bill >= that value
						if bogo_value <= 0:
							is_eligible = False
							is_truly_ineligible = True
							ineligibility_reasons.append({
								"code": "BOGO_NOT_CONFIGURED",
								"message": "This BOGO offer is not fully configured",
								"type": "usage",
							})
						elif cart_total < bogo_value:
							is_eligible = False
							ineligibility_reasons.append({
								"code": "BILL_TOO_LOW",
								"message": f"Bill must be at least ₹{int(bogo_value)} for the free item",
								"type": "cart_value",
								"minOrderAmount": bogo_value,
								"currentAmount": cart_total,
								"amountNeeded": max(0, bogo_value - cart_total),
							})
					else:
						matching = [i for i in cart_items if str(i.get("dishId") or "") in item_pool_ids]
						if len(matching) < items_needed:
							short = items_needed - len(matching)
							pool_names = [product_names.get(p, {}).get("name", p) for p in item_pool_ids]
							is_eligible = False
							ineligibility_reasons.append({
								"code": "COMBO_ITEMS_MISSING",
								"message": f"Add {short} more item{'s' if short > 1 else ''} from the pool to unlock BOGO",
								"type": "combo",
								"missingCount": short,
								"itemPool": item_pool_ids,
								"itemPoolNames": pool_names,
							})
					combo_meta = {
						"comboType": "bogo",
						"itemPool": item_pool_ids,
						"itemPoolNames": [product_names.get(p, {}).get("name", p) for p in item_pool_ids],
						"itemsToSelect": items_needed,
						"bogoFreeItemValue": bogo_value,
						"comboName": offer.get("combo_name") or offer.description or "",
					}

				elif combo_type == "build_your_own":
					if is_dine_in:
						# Dine-in: bill must reach combo_price
						if combo_price_val > 0 and cart_total < combo_price_val:
							is_eligible = False
							ineligibility_reasons.append({
								"code": "BILL_TOO_LOW",
								"message": f"Bill must be at least ₹{int(combo_price_val)} for this combo",
								"type": "cart_value",
								"minOrderAmount": combo_price_val,
								"currentAmount": cart_total,
								"amountNeeded": max(0, combo_price_val - cart_total),
							})
					else:
						matching = [i for i in cart_items if str(i.get("dishId") or "") in item_pool_ids]
						if len(matching) < items_needed:
							short = items_needed - len(matching)
							pool_names = [product_names.get(p, {}).get("name", p) for p in item_pool_ids]
							is_eligible = False
							ineligibility_reasons.append({
								"code": "COMBO_ITEMS_MISSING",
								"message": f"Pick {short} more item{'s' if short > 1 else ''} from the combo pool",
								"type": "combo",
								"missingCount": short,
								"itemPool": item_pool_ids,
								"itemPoolNames": pool_names,
							})
					combo_meta = {
						"comboType": "build_your_own",
						"itemPool": item_pool_ids,
						"itemPoolNames": [product_names.get(p, {}).get("name", p) for p in item_pool_ids],
						"itemsToSelect": items_needed,
						"comboPrice": combo_price_val,
						"comboName": offer.get("combo_name") or offer.description or "",
					}

			# ── Calculate discount (even ineligible, to show potential savings) ─
			discount_amount = flt(offer.discount_value)
			potential_discount = discount_amount

			if offer.offer_type == "combo":
				if combo_type == "bogo":
					bogo_val = flt(offer.get("bogo_free_item_value") or 0)
					if is_dine_in:
						# Fixed value regardless of cart contents
						potential_discount = bogo_val
						discount_amount = bogo_val if is_eligible else 0
					else:
						# Online: cheapest matching pool item
						pool_ids = item_pool_ids if "item_pool_ids" in dir() else []
						prices = [flt(product_names.get(p, {}).get("price", 0)) for p in pool_ids]
						potential_discount = min(prices) if prices else bogo_val
						if is_eligible:
							pool = combo_meta.get("itemPool") or []
							matching_prices = sorted([flt(i.get("unitPrice", 0)) for i in cart_items if str(i.get("dishId") or "") in pool])
							discount_amount = matching_prices[0] if matching_prices else 0
						else:
							discount_amount = 0
				elif combo_type in ("fixed_bundle", "build_your_own"):
					cp = flt(offer.combo_price or 0)
					if cp > 0:
						potential_discount = max(0, flt(cart_total) - cp)
						discount_amount = potential_discount if is_eligible else 0
					else:
						discount_amount = flt(offer.discount_value) if is_eligible else 0
				else:
					discount_amount = flt(offer.discount_value) if is_eligible else 0
			elif offer.discount_type == "percent":
				calc_total = max(cart_total, flt(offer.min_order_amount or 0))
				discount_amount = (calc_total * flt(offer.discount_value)) / 100
				if offer.max_discount_cap and discount_amount > flt(offer.max_discount_cap):
					discount_amount = flt(offer.max_discount_cap)
				potential_discount = discount_amount

			# Build offer data
			offer_data = {
				"id": str(offer.name),
				"code": offer.code,
				"discount": flt(offer.discount_value),
				"discountAmount": discount_amount if is_eligible else 0,
				"potentialDiscount": potential_discount,
				"type": offer.discount_type or "flat",
				"offerType": offer.offer_type or "coupon",
				"priority": offer.priority or 0,
				"canStack": bool(offer.can_stack),
				"description": offer.description or "",
				"detailedDescription": offer.detailed_description or "",
				"isEligible": is_eligible,
				"minOrderAmount": flt(offer.min_order_amount or 0),
				"category": offer.category or "",
				**combo_meta,
			}

			# Add ineligibility info
			if not is_eligible:
				offer_data["ineligibilityReasons"] = ineligibility_reasons
				if ineligibility_reasons:
					offer_data["primaryReason"] = ineligibility_reasons[0]
			

			
			# Add to appropriate list — eligible_offers only if fully eligible
			if is_eligible:
				eligible_offers.append(offer_data)
			else:
				ineligible_offers.append(offer_data)
		
		# Find best eligible offer (highest discount)
		best_offer = None
		if eligible_offers:
			best_offer = max(eligible_offers, key=lambda x: x["discountAmount"])
		
		return {
			"success": True,
			"data": {
				"eligibleOffers": eligible_offers,
				"ineligibleOffers": ineligible_offers,
				"bestOffer": best_offer,
				"cartTotal": cart_total,
				"totalOffers": len(eligible_offers) + len(ineligible_offers)
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_applicable_offers: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "OFFER_FETCH_ERROR",
				"message": str(e)
			}
		}


# ──────────────────────────────────────────────────────────────────────────────
# Offer PIN management
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def set_offer_pin(restaurant_id, pin):
	"""
	POST /api/method/flamezo_backend.flamezo.api.coupons.set_offer_pin
	Merchant sets/updates their 4-digit offer verification PIN.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		pin = str(pin).strip()
		if not pin.isdigit() or len(pin) != 4:
			return {"success": False, "error": {"code": "INVALID_PIN", "message": "PIN must be exactly 4 digits"}}

		frappe.db.set_value("Restaurant Config", restaurant, "offer_verification_pin", pin)
		frappe.db.commit()

		return {"success": True, "data": {"message": "PIN updated successfully"}}
	except Exception as e:
		frappe.log_error(f"Error in set_offer_pin: {str(e)}")
		return {"success": False, "error": {"code": "PIN_SET_ERROR", "message": str(e)}}


@frappe.whitelist()
def get_offer_pin_status(restaurant_id):
	"""
	GET /api/method/flamezo_backend.flamezo.api.coupons.get_offer_pin_status
	Returns whether a PIN is set. Never returns the PIN value itself.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		stored = frappe.db.get_value("Restaurant Config", restaurant, "offer_verification_pin") or ""
		return {"success": True, "data": {"is_set": bool(stored)}}
	except Exception as e:
		return {"success": False, "error": {"code": "PIN_STATUS_ERROR", "message": str(e)}}


# ──────────────────────────────────────────────────────────────────────────────
# Offer claim flow  (customer-facing, called from flamezo-web)
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def claim_offer_with_pin(restaurant_id, coupon_id, pin):
	"""
	POST /api/method/flamezo_backend.flamezo.api.coupons.claim_offer_with_pin

	Customer flow: waiter enters 4-digit PIN on customer's phone.
	On success, records the claim in Offer Claim DocType.
	Returns the claim ID so the frontend can reference it later.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		# Require logged-in customer
		token = get_customer_token()
		if not token:
			return {"success": False, "error": {"code": "AUTH_REQUIRED", "message": "Please log in to claim offers"}}

		customer_id = get_customer_from_token(token)
		if not customer_id:
			return {"success": False, "error": {"code": "AUTH_REQUIRED", "message": "Session expired — please log in again"}}

		# Fetch customer phone
		customer_phone = frappe.db.get_value("Customer", customer_id, "phone") or ""

		# Validate PIN
		stored_pin = frappe.db.get_value("Restaurant Config", restaurant, "offer_verification_pin") or ""
		if not stored_pin:
			return {"success": False, "error": {"code": "PIN_NOT_SET", "message": "This restaurant has not set up offer verification"}}

		if str(pin).strip() != stored_pin:
			return {"success": False, "error": {"code": "INVALID_PIN", "message": "Incorrect PIN — please try again"}}

		# Validate the coupon exists and belongs to this restaurant
		coupon = frappe.db.get_value(
			"Coupon",
			{"name": coupon_id, "restaurant": restaurant, "is_active": 1},
			["name", "code", "daily_limit"],
			as_dict=True,
		)
		if not coupon:
			return {"success": False, "error": {"code": "COUPON_NOT_FOUND", "message": "Offer not found or inactive"}}

		if _check_daily_limit(coupon.name, coupon.daily_limit):
			return {"success": False, "error": {"code": "DAILY_LIMIT_REACHED", "message": "This offer has reached its daily claim limit. Try again tomorrow."}}

		# Server-side dedup: one claim per customer per restaurant within a 4-hour rolling window.
		four_hours_ago = add_to_date(now_datetime(), hours=-4)
		existing_lock = frappe.db.exists(
			"Offer Claim",
			{
				"restaurant": restaurant,
				"customer": customer_id,
				"claimed_at": [">=", four_hours_ago],
				"is_paid": 0,
			},
		)
		if existing_lock:
			return {"success": False, "error": {"code": "ALREADY_CLAIMED", "message": "You've already claimed an offer at this restaurant in the last 4 hours"}}

		# Record the claim with full customer attribution
		claim_time = now_datetime()
		claim = frappe.get_doc({
			"doctype": "Offer Claim",
			"restaurant": restaurant,
			"coupon": coupon.name,
			"coupon_code": coupon.code,
			"customer": customer_id,
			"customer_phone": customer_phone,
			"claimed_at": claim_time,
			"locked_until": add_to_date(claim_time, hours=4),
			"is_paid": 0,
		})
		claim.insert(ignore_permissions=True)
		frappe.db.commit()

		# Notify the customer on WhatsApp with their confirmed offer + pay-bill link
		frappe.enqueue(
			"flamezo_backend.flamezo.tasks.coupon_tasks.send_offer_claim_notification",
			claim_id=claim.name,
			queue="short",
			timeout=60,
			enqueue_after_commit=True,
		)

		# Build the pay-bill deep link so the frontend can surface it immediately too
		base_url = (frappe.conf.get("customer_web_url") or "").rstrip("/")
		restaurant_slug = frappe.db.get_value("Restaurant", restaurant, "restaurant_id") or restaurant
		pay_link = f"{base_url}/{restaurant_slug}/pay-bill?offer={coupon.code}" if base_url else ""

		return {
			"success": True,
			"data": {
				"claimId": claim.name,
				"couponCode": coupon.code,
				"payLink": pay_link,
				"message": "Offer claimed successfully!"
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in claim_offer_with_pin: {str(e)}")
		return {"success": False, "error": {"code": "CLAIM_ERROR", "message": str(e)}}


@frappe.whitelist(allow_guest=True)
def claim_offer(restaurant_id, coupon_id):
	"""
	POST /api/method/flamezo_backend.flamezo.api.coupons.claim_offer

	Self-serve offer claim — no staff PIN required.
	Customer taps Claim, offer is locked for the 4-hour visit window.
	Once claimed, they cannot switch to another offer for the same visit.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		token = get_customer_token()
		if not token:
			return {"success": False, "error": {"code": "AUTH_REQUIRED", "message": "Please log in to claim offers"}}

		customer_id = get_customer_from_token(token)
		if not customer_id:
			return {"success": False, "error": {"code": "AUTH_REQUIRED", "message": "Session expired — please log in again"}}

		customer_phone = frappe.db.get_value("Customer", customer_id, "phone") or ""

		coupon = frappe.db.get_value(
			"Coupon",
			{"name": coupon_id, "restaurant": restaurant, "is_active": 1},
			["name", "code", "daily_limit"],
			as_dict=True,
		)
		if not coupon:
			return {"success": False, "error": {"code": "COUPON_NOT_FOUND", "message": "Offer not found or inactive"}}

		if _check_daily_limit(coupon.name, coupon.daily_limit):
			return {"success": False, "error": {"code": "DAILY_LIMIT_REACHED", "message": "This offer has reached its daily claim limit. Try again tomorrow."}}

		four_hours_ago = add_to_date(now_datetime(), hours=-4)
		existing_lock = frappe.db.exists(
			"Offer Claim",
			{
				"restaurant": restaurant,
				"customer": customer_id,
				"claimed_at": [">=", four_hours_ago],
				"is_paid": 0,
			},
		)
		if existing_lock:
			return {"success": False, "error": {"code": "ALREADY_CLAIMED", "message": "You've already claimed an offer at this restaurant. Visit again to claim another."}}

		claim_time = now_datetime()
		claim = frappe.get_doc({
			"doctype": "Offer Claim",
			"restaurant": restaurant,
			"coupon": coupon.name,
			"coupon_code": coupon.code,
			"customer": customer_id,
			"customer_phone": customer_phone,
			"claimed_at": claim_time,
			"locked_until": add_to_date(claim_time, hours=4),
			"is_paid": 0,
		})
		claim.insert(ignore_permissions=True)
		frappe.db.commit()

		frappe.enqueue(
			"flamezo_backend.flamezo.tasks.coupon_tasks.send_offer_claim_notification",
			claim_id=claim.name,
			queue="short",
			timeout=60,
			enqueue_after_commit=True,
		)

		base_url = (frappe.conf.get("customer_web_url") or "").rstrip("/")
		restaurant_slug = frappe.db.get_value("Restaurant", restaurant, "restaurant_id") or restaurant
		pay_link = f"{base_url}/{restaurant_slug}/pay-bill?offer={coupon.code}" if base_url else ""

		return {
			"success": True,
			"data": {
				"claimId": claim.name,
				"couponCode": coupon.code,
				"payLink": pay_link,
				"message": "Offer claimed successfully!",
			},
		}
	except Exception as e:
		frappe.log_error(f"Error in claim_offer: {str(e)}")
		return {"success": False, "error": {"code": "CLAIM_ERROR", "message": str(e)}}


@frappe.whitelist(allow_guest=True)
def get_active_offer_claim(restaurant_id):
	"""
	Returns the customer's active (unpaid) Offer Claim for this restaurant
	within the last 4 hours, if any. Used by the pay-bill page to auto-select
	the claimed offer without depending on URL params or localStorage.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		token = get_customer_token()
		if not token:
			return {"success": True, "data": {"claim": None}}
		customer_id = get_customer_from_token(token)
		if not customer_id:
			return {"success": True, "data": {"claim": None}}

		four_hours_ago = add_to_date(now_datetime(), hours=-4)
		claim = frappe.db.get_value(
			"Offer Claim",
			{
				"restaurant": restaurant,
				"customer": customer_id,
				"is_paid": 0,
				"claimed_at": [">=", four_hours_ago],
			},
			["name", "coupon", "coupon_code", "claimed_at", "locked_until"],
			as_dict=True,
			order_by="claimed_at desc",
		)
		if not claim:
			return {"success": True, "data": {"claim": None}}

		return {
			"success": True,
			"data": {
				"claim": {
					"claimId": claim.name,
					"couponId": claim.coupon,
					"couponCode": claim.coupon_code,
					"claimedAt": str(claim.claimed_at),
					"lockedUntil": str(claim.locked_until) if claim.locked_until else None,
				}
			}
		}
	except Exception as e:
		frappe.log_error(f"get_active_offer_claim: {str(e)}", "Coupon")
		return {"success": True, "data": {"claim": None}}  # fail-open — page still works


@frappe.whitelist()
def mark_claim_paid(restaurant_id, claim_id, payment_id, paid_amount):
	"""
	POST /api/method/flamezo_backend.flamezo.api.coupons.mark_claim_paid
	Called from the payment webhook / verify_payment flow to mark a claim as paid.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		claim = frappe.get_doc("Offer Claim", claim_id)
		if claim.restaurant != restaurant:
			return {"success": False, "error": {"code": "FORBIDDEN", "message": "Claim does not belong to this restaurant"}}

		claim.is_paid = 1
		claim.paid_amount = flt(paid_amount)
		claim.paid_at = now_datetime()
		claim.payment_id = str(payment_id)
		claim.save(ignore_permissions=True)
		frappe.db.commit()

		return {"success": True, "data": {"message": "Claim marked as paid"}}
	except Exception as e:
		frappe.log_error(f"Error in mark_claim_paid: {str(e)}")
		return {"success": False, "error": {"code": "MARK_PAID_ERROR", "message": str(e)}}


# ──────────────────────────────────────────────────────────────────────────────
# Offer claims analytics  (merchant dashboard)
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_offer_claims_analytics(restaurant_id, period="30d", coupon_id=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.coupons.get_offer_claims_analytics

	Returns:
	  - summary: total_claims, paid_count, not_paid_count, conversion_rate, total_paid_amount
	  - by_coupon: per-coupon breakdown
	  - recent_claims: last 50 individual claim records
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		# Resolve date range
		period_map = {"7d": 7, "30d": 30, "90d": 90, "all": None}
		days = period_map.get(str(period), 30)
		date_filter = []
		if days:
			from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
			date_filter = [["claimed_at", ">=", from_date]]

		base_filters = [["restaurant", "=", restaurant]] + date_filter
		if coupon_id:
			base_filters.append(["coupon", "=", coupon_id])

		claims = frappe.get_all(
			"Offer Claim",
			filters=base_filters,
			fields=[
				"name", "coupon", "coupon_code", "customer_phone",
				"claimed_at", "is_paid", "paid_amount", "paid_at", "payment_id"
			],
			order_by="claimed_at desc",
			limit=500,
		)

		total_claims = len(claims)
		paid_claims = [c for c in claims if c.get("is_paid")]
		not_paid_claims = [c for c in claims if not c.get("is_paid")]
		total_paid_amount = sum(flt(c.get("paid_amount") or 0) for c in paid_claims)
		conversion_rate = round((len(paid_claims) / total_claims * 100) if total_claims else 0, 1)

		# Per-coupon breakdown
		coupon_map = {}
		for c in claims:
			key = c.get("coupon") or "unknown"
			code = c.get("coupon_code") or key
			if key not in coupon_map:
				coupon_map[key] = {
					"coupon_id": key,
					"coupon_code": code,
					"total_claims": 0,
					"paid_count": 0,
					"not_paid_count": 0,
					"total_paid_amount": 0.0,
					"conversion_rate": 0.0,
				}
			coupon_map[key]["total_claims"] += 1
			if c.get("is_paid"):
				coupon_map[key]["paid_count"] += 1
				coupon_map[key]["total_paid_amount"] += flt(c.get("paid_amount") or 0)
			else:
				coupon_map[key]["not_paid_count"] += 1

		for row in coupon_map.values():
			n = row["total_claims"]
			row["conversion_rate"] = round((row["paid_count"] / n * 100) if n else 0, 1)

		by_coupon = sorted(coupon_map.values(), key=lambda x: x["total_claims"], reverse=True)

		# Recent individual claims (last 50)
		recent = [
			{
				"id": c["name"],
				"couponCode": c.get("coupon_code") or "",
				"customerPhone": _mask_phone(c.get("customer_phone") or ""),
				"claimedAt": str(c.get("claimed_at") or ""),
				"isPaid": bool(c.get("is_paid")),
				"paidAmount": flt(c.get("paid_amount") or 0),
				"paidAt": str(c.get("paid_at") or "") if c.get("paid_at") else None,
			}
			for c in claims[:50]
		]

		return {
			"success": True,
			"data": {
				"summary": {
					"totalClaims": total_claims,
					"paidCount": len(paid_claims),
					"notPaidCount": len(not_paid_claims),
					"conversionRate": conversion_rate,
					"totalPaidAmount": total_paid_amount,
				},
				"byCoupon": by_coupon,
				"recentClaims": recent,
				"period": period,
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_offer_claims_analytics: {str(e)}")
		return {"success": False, "error": {"code": "ANALYTICS_ERROR", "message": str(e)}}


def _mask_phone(phone: str) -> str:
	"""Show only last 4 digits: ******1234"""
	if len(phone) >= 4:
		return "*" * (len(phone) - 4) + phone[-4:]
	return phone

