# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

"""
API endpoints for Coupons
All endpoints require restaurant_id for SaaS multi-tenancy
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, now_datetime, get_datetime
from dinematters.dinematters.utils.api_helpers import validate_restaurant_for_api, get_restaurant_from_id
from dinematters.dinematters.utils.feature_gate import require_plan
import json
from datetime import datetime


@frappe.whitelist(allow_guest=True)
def get_coupons(restaurant_id, active_only=True):
	"""
	GET /api/method/dinematters.dinematters.api.coupons.get_coupons
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
		
		# Parse cart_items if provided as string
		if isinstance(cart_items, str):
			try: cart_items = json.loads(cart_items)
			except: cart_items = None
			
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



@frappe.whitelist(allow_guest=True)
def get_applicable_offers(restaurant_id, cart_items, cart_total, customer_id=None, order_type=None):
	"""
	POST /api/method/dinematters.dinematters.api.coupons.get_applicable_offers
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
		
		# Parse cart_items if string
		if isinstance(cart_items, str):
			try:
				cart_items = json.loads(cart_items)
			except:
				cart_items = []
		
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
				"max_discount_cap", "priority", "can_stack",
				"category", "description", "detailed_description"
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
			

			
			# Calculate discount (even for ineligible to show potential savings)
			discount_amount = flt(offer.discount_value)
			potential_discount = discount_amount  # What they could save
			
			if offer.discount_type == "percent":
				# Calculate based on current cart or min order amount
				calc_total = max(cart_total, flt(offer.min_order_amount or 0))
				discount_amount = (calc_total * flt(offer.discount_value)) / 100
				if offer.max_discount_cap and discount_amount > flt(offer.max_discount_cap):
					discount_amount = flt(offer.max_discount_cap)
			
			if is_delivery_offer:
				if offer.discount_type == 'delivery':
					# "Free delivery" — actual saving depends on order-time fee; show 0 until applied
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
				"category": offer.category or ""
			}
			
			# Add ineligibility info
			if not is_eligible:
				offer_data["ineligibilityReasons"] = ineligibility_reasons
				# Add primary reason (most actionable)
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



