# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
API endpoints for Coupons
All endpoints require restaurant_id for SaaS multi-tenancy
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, now_datetime, get_datetime
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api, get_restaurant_from_id
from flamezo_backend.flamezo.utils.feature_gate import require_plan
from flamezo_backend.flamezo.utils.customer_helpers import get_customer_token, get_customer_from_token
import json
import csv
import io
from datetime import datetime


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
		
		# Get coupons
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
				"valid_until"
			],
			filters=filters,
			order_by="code asc"
		)
		
		# Format coupons and filter by dates if active_only
		formatted_coupons = []
		today_date = today() if active_only else None
		
		for coupon in coupons:
			# Check validity dates if active_only
			if active_only and today_date:
				valid_from = coupon.get("valid_from")
				valid_until = coupon.get("valid_until")
				if valid_from and getdate(valid_from) > getdate(today_date):
					continue  # Not valid yet
				if valid_until and getdate(valid_until) < getdate(today_date):
					continue  # Expired
			
			coupon_data = {
				"id": str(coupon["id"]),
				"code": coupon["code"],
				"discount": flt(coupon["discount"]),
				"minOrderAmount": flt(coupon.get("min_order_amount", 0)),
				"type": coupon.get("type", "flat"),
				"offerType": coupon.get("offer_type", "coupon"),
				"isActive": bool(coupon.get("is_active", False))
			}

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
def validate_coupon(restaurant_id, coupon_code, cart_total=0, customer_id=None, cart_items=None):
	"""API wrapper for get_coupon_details"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Production Auth: Prioritize identity from session token for secure usage limit checks
		token = get_customer_token()
		token_customer_id = get_customer_from_token(token)
		if token_customer_id:
			customer_id = token_customer_id
			
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
				"items_to_select", "combo_price", "free_item", "display_on_menu",
			],
			order_by="priority desc, discount_value desc"
		)
		
		eligible_offers = []
		ineligible_offers = []
		
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
			ineligibility_reasons = []

			# Check delivery specific logic
			is_delivery_offer = (offer.discount_type == 'delivery' or offer.category == 'delivery' or offer.offer_type == 'delivery')
			if is_delivery_offer and order_type != "delivery":
				is_eligible = False
				ineligibility_reasons.append({
					"code": "INVALID_MODE",
					"message": "Only available for delivery orders",
					"type": "schedule"
				})

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
						"comboPrice": flt(offer.combo_price or 0),
						"comboName": offer.get("combo_name") or offer.description or "",
					}

				elif combo_type == "bogo":
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
						"comboName": offer.get("combo_name") or offer.description or "",
					}

				elif combo_type == "build_your_own":
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
						"comboPrice": flt(offer.combo_price or 0),
						"comboName": offer.get("combo_name") or offer.description or "",
					}

			# ── Calculate discount (even ineligible, to show potential savings) ─
			discount_amount = flt(offer.discount_value)
			potential_discount = discount_amount

			if offer.offer_type == "combo":
				if combo_type == "bogo":
					# Potential = cheapest item in pool
					pool = combo_meta.get("itemPool") or required_ids
					prices = [flt(product_names.get(p, {}).get("price", 0)) for p in pool]
					potential_discount = min(prices) if prices else discount_amount
					if is_eligible:
						matching_prices = sorted([flt(i.get("unitPrice", 0)) for i in cart_items if str(i.get("dishId") or "") in pool])
						discount_amount = matching_prices[0] if matching_prices else 0
					else:
						discount_amount = 0
				elif combo_type in ("fixed_bundle", "build_your_own") and offer.combo_price:
					potential_discount = max(0, flt(cart_total) - flt(offer.combo_price))
					discount_amount = potential_discount if is_eligible else 0
				else:
					discount_amount = flt(offer.discount_value) if is_eligible else 0
			elif offer.discount_type == "percent":
				calc_total = max(cart_total, flt(offer.min_order_amount or 0))
				discount_amount = (calc_total * flt(offer.discount_value)) / 100
				if offer.max_discount_cap and discount_amount > flt(offer.max_discount_cap):
					discount_amount = flt(offer.max_discount_cap)
				potential_discount = discount_amount

			if is_delivery_offer:
				if offer.discount_type == 'delivery':
					discount_amount = 0
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
			

			
			# Add to appropriate list
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



