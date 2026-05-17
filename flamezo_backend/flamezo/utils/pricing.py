import frappe
from frappe.utils import flt, cint, now_datetime, today, getdate
from flamezo_backend.flamezo.api.coupons import get_coupon_details
from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance, is_loyalty_enabled
from flamezo_backend.flamezo.utils.platform_config import get_max_redemption_percent
import json
from datetime import datetime

def calculate_cart_totals(restaurant, items, coupon_code=None, loyalty_coins=0, customer=None, delivery_type="Dine-in", latitude=None, longitude=None):
	"""
	Authoritative pricing calculation engine.
	restaurant: Restaurant ID or name
	items: List of objects with {price, quantity, dishId}
	coupon_code: Optional manual coupon code to apply
	loyalty_coins: Optional number of loyalty coins to redeem
	customer: Optional Customer ID (for loyalty and coupon limits)
	delivery_type: Optional (Dine-in, Takeaway, Delivery)
	"""

	# 0. Global Context
	restaurant_doc = frappe.get_doc("Restaurant", restaurant)
	max_dist = flt(restaurant_doc.max_delivery_distance or 10.0)
	serviceable = True
	road_distance = 0
	distance_error = None
	
	# 1. Calculate Subtotal
	subtotal = 0
	for item in items:
		qty = cint(item.get("quantity") or 1)
		price = flt(item.get("unitPrice") or item.get("price") or 0)
		subtotal += qty * price

	# 2. Pre-calculate Delivery and Packaging Fees (needed for delivery-specific offers)
	delivery_fee = 0
	packaging_fee = 0
	delivery_details = {}

	if delivery_type == "Delivery":
		cust_lat = latitude or (items[0].get("delivery_location", {}).get("latitude") if items else None)
		cust_lng = longitude or (items[0].get("delivery_location", {}).get("longitude") if items else None)

		if cust_lat is not None and cust_lng is not None and restaurant_doc.latitude is not None and restaurant_doc.longitude is not None:
			from flamezo_backend.flamezo.utils.geoutils import calculate_distance, get_osrm_road_distance, estimate_road_distance
			road_distance = get_osrm_road_distance(restaurant_doc.latitude, restaurant_doc.longitude, cust_lat, cust_lng)
			if road_distance is None:
				straight_dist = calculate_distance(restaurant_doc.latitude, restaurant_doc.longitude, cust_lat, cust_lng)
				road_distance = round(estimate_road_distance(straight_dist), 2)
			
			if road_distance > max_dist:
				serviceable = False
				distance_error = f"Location is {road_distance}km away. Max delivery distance is {max_dist}km."
			
			if serviceable:
				from flamezo_backend.flamezo.logistics.manager import LogisticsManager
				try:
					manager = LogisticsManager(restaurant)
					quote_res = manager.get_quote({
						"address": items[0].get("delivery_location", {}).get("address") if items else None,
						"latitude": cust_lat,
						"longitude": cust_lng,
						"items": items,
						"total": subtotal
					})
					if quote_res.get("success"):
						delivery_fee = flt(quote_res.get("delivery_fee"))
						delivery_details = quote_res
					else:
						if quote_res.get("locationServiceAble") == False or quote_res.get("riderServiceAble") == False:
							serviceable = False
							distance_error = quote_res.get("error") or "Location not serviceable by delivery partner."
						else:
							delivery_fee = flt(restaurant_doc.default_delivery_fee or 0)
				except:
					delivery_fee = flt(restaurant_doc.default_delivery_fee or 0)
		else:
			# If delivery selected but no location, we can't calculate fee yet but it's not unserviceable yet either
			# We might want to show a default fee or keep it 0.
			delivery_fee = flt(restaurant_doc.default_delivery_fee or 0)
			
		packaging_fee_val = flt(restaurant_doc.default_packaging_fee or 0)
		if restaurant_doc.packaging_fee_type == "Percentage":
			packaging_fee = round(subtotal * (packaging_fee_val / 100.0), 2)
		else:
			packaging_fee = packaging_fee_val
	elif delivery_type == "Takeaway":
		packaging_fee_val = flt(restaurant_doc.default_packaging_fee or 0)
		if restaurant_doc.packaging_fee_type == "Percentage":
			packaging_fee = round(subtotal * (packaging_fee_val / 100.0), 2)
		else:
			packaging_fee = packaging_fee_val
	
	# 3. Identify and Apply Offers (Auto + Manual)
	applied_offers = []
	total_item_discount = 0
	total_delivery_discount = 0
	
	all_offers = frappe.get_all(
		"Coupon",
		filters={"restaurant": restaurant, "is_active": 1},
		fields=["*"]
	)
	
	eligible_offers = []
	for offer in all_offers:
		is_manual = (coupon_code and offer.code == coupon_code)
		is_auto = (offer.offer_type == "auto")
		
		if not (is_manual or is_auto):
			continue
			
		# Validate eligibility
		# Pass delivery_type to validation so we can reject delivery-only offers if type is Dine-in
		res = validate_offer_eligibility(offer, subtotal, customer, items, delivery_type, delivery_fee)
		if res.get("success"):
			offer.discount_amount = res.get("discount_amount")
			offer.is_delivery_discount = (offer.discount_type == 'delivery' or offer.category == 'delivery')
			eligible_offers.append(offer)
	
	# Sort by priority DESC, then by discount_amount DESC as tiebreaker
	eligible_offers.sort(key=lambda x: (x.priority or 0, x.discount_amount), reverse=True)
	
	if eligible_offers:
		best = eligible_offers[0]
		if not best.can_stack:
			applied_offers.append(best)
			if best.is_delivery_discount:
				total_delivery_discount = best.discount_amount
			else:
				total_item_discount = best.discount_amount
		else:
			for o in eligible_offers:
				if o.can_stack:
					applied_offers.append(o)
					if o.is_delivery_discount:
						total_delivery_discount += o.discount_amount
					else:
						total_item_discount += o.discount_amount
	
	# Cap delivery discount to current delivery fee
	total_delivery_discount = min(total_delivery_discount, delivery_fee)
	delivery_fee = max(0, delivery_fee - total_delivery_discount)

	# 4. Apply Loyalty Discount
	loyalty_discount = 0
	if loyalty_coins > 0 and customer and is_loyalty_enabled(restaurant):
		balance = get_loyalty_balance(customer)  # global balance — universal wallet
		actual_coins = min(cint(loyalty_coins), balance)
		# Plan-tiered per-order cap: GOLD 30%, SILVER 20%
		plan = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"
		max_redeem_pct = get_max_redemption_percent(plan) / 100.0
		remaining = subtotal - total_item_discount
		loyalty_discount = min(flt(actual_coins), max(0, remaining), subtotal * max_redeem_pct)
	
	# 5. Calculate Tax
	tax_rate_val = frappe.db.get_value("Restaurant", restaurant, "tax_rate")
	tax_rate = flt(tax_rate_val if tax_rate_val is not None else 5.0)
	taxable_amount = max(0, subtotal - total_item_discount)
	tax_amount = round(taxable_amount * (tax_rate / 100.0), 2)
	
	cgst = round(tax_amount / 2.0, 2)
	sgst = round(tax_amount - cgst, 2)
	
	# 6. Final Total
	total = taxable_amount + tax_amount + delivery_fee + packaging_fee - loyalty_discount
	
	# 7. Generate Bill Details
	bill_details = [
		{"label": "Item Total", "value": subtotal, "type": "subtotal"}
	]
	for offer in applied_offers:
		label = f"Offer: {offer.code}" if offer.offer_type == "coupon" else f"Offer: {offer.description or 'Auto Discount'}"
		val = -offer.discount_amount
		# If it's a delivery discount, cap it in the UI label too
		if offer.is_delivery_discount:
			val = -min(offer.discount_amount, total_delivery_discount) # approximation for label
		
		bill_details.append({"label": label, "value": val, "type": "discount"})
	
	if loyalty_discount > 0:
		bill_details.append({"label": "Loyalty Discount", "value": -loyalty_discount, "type": "discount"})
	
	if cgst > 0:
		bill_details.append({"label": f"CGST ({tax_rate/2}%)", "value": cgst, "type": "tax"})
	if sgst > 0:
		bill_details.append({"label": f"SGST ({tax_rate/2}%)", "value": sgst, "type": "tax"})
	
	if packaging_fee > 0:
		bill_details.append({"label": "Packaging and Extra Charges", "value": packaging_fee, "type": "fee"})
	if delivery_type == "Delivery" and serviceable:
		bill_details.append({"label": "Delivery Fee", "value": (delivery_fee + total_delivery_discount), "type": "fee"})
		if total_delivery_discount > 0:
			bill_details.append({"label": "Delivery Discount", "value": -total_delivery_discount, "type": "discount"})
	
	bill_details.append({"label": "Total Payable", "value": max(0, total), "type": "total"})

	from flamezo_backend.flamezo.utils.currency_helpers import get_restaurant_currency_info
	currency_info = get_restaurant_currency_info(restaurant)
	
	return {
		"subtotal": subtotal,
		"discount": total_item_discount,
		"deliveryDiscount": total_delivery_discount,
		"appliedCoupon": coupon_code if any(o.code == coupon_code for o in applied_offers) else None,
		"appliedOffers": [o.code for o in applied_offers],
		"loyaltyDiscount": loyalty_discount,
		"tax": tax_amount,
		"cgst": cgst,
		"sgst": sgst,
		"taxRate": tax_rate,
		"deliveryFee": delivery_fee,
		"deliveryDetails": delivery_details,
		"packagingFee": packaging_fee,
		"total": total,
		"payableAmount": max(0, total),
		"serviceable": serviceable,
		"distance": road_distance,
		"distanceError": distance_error,
		"billDetails": bill_details,
		"currency": currency_info.get("currency", "INR"),
		"currencySymbol": currency_info.get("symbol", "₹"),
		"currencySymbolOnRight": currency_info.get("symbolOnRight", False)
	}

def validate_offer_eligibility(offer, cart_total, customer_id, cart_items, delivery_type=None, delivery_fee=0):
	"""Internal helper to validate a single offer doc against current cart."""
	# 0. Delivery Specific Validation
	is_delivery_offer = (offer.discount_type == 'delivery' or offer.category == 'delivery' or offer.offer_type == 'delivery')
	if is_delivery_offer and delivery_type != "Delivery":
		return {"success": False}

	# 1. Date Checks
	today_date = today()
	if offer.valid_from and getdate(offer.valid_from) > getdate(today_date):
		return {"success": False}
	if offer.valid_until and getdate(offer.valid_until) < getdate(today_date):
		return {"success": False}
	
	# 2. Min Order
	if offer.min_order_amount and flt(cart_total) < flt(offer.min_order_amount):
		return {"success": False}
	
	# 3. Day of Week
	if offer.valid_days_of_week:
		try:
			valid_days = json.loads(offer.valid_days_of_week)
			current_day = now_datetime().strftime("%A").lower()
			if current_day not in [d.lower() for d in valid_days]:
				return {"success": False}
		except: pass

	# 4. Time Check
	if offer.valid_time_start or offer.valid_time_end:
		current_time = now_datetime().time()
		if offer.valid_time_start:
			start = datetime.strptime(str(offer.valid_time_start).split(".")[0], "%H:%M:%S").time()
			if current_time < start: return {"success": False}
		if offer.valid_time_end:
			end = datetime.strptime(str(offer.valid_time_end).split(".")[0], "%H:%M:%S").time()
			if current_time > end: return {"success": False}

	# 5. Usage Limits
	if offer.max_uses and offer.usage_count and offer.usage_count >= offer.max_uses:
		return {"success": False}
	if offer.max_uses_per_user and customer_id:
		usage = frappe.db.count("Coupon Usage", {"coupon": offer.name, "customer": customer_id})
		if usage >= offer.max_uses_per_user: return {"success": False}

	# 6. Combo Checks (type-aware)
	_raw_combo_type = getattr(offer, "combo_type", None)
	combo_type = _raw_combo_type if isinstance(_raw_combo_type, str) and _raw_combo_type else "fixed_bundle"

	if offer.offer_type == "combo":
		cart_dish_ids = [str(item.get("dishId") or item.get("dish_id") or "") for item in cart_items]

		if combo_type == "fixed_bundle":
			# All required items must be present in cart
			if offer.required_items:
				try:
					required = json.loads(offer.required_items) if isinstance(offer.required_items, str) else offer.required_items
					if any(str(r) not in cart_dish_ids for r in required):
						return {"success": False}
				except Exception:
					pass

		elif combo_type == "bogo":
			# At least items_to_select qualifying items from item_pool must be in cart
			pool = []
			if offer.item_pool:
				try:
					pool = json.loads(offer.item_pool) if isinstance(offer.item_pool, str) else offer.item_pool
				except Exception:
					pass
			required_count = int(getattr(offer, "items_to_select", 2) or 2)
			matching = [i for i in cart_items if str(i.get("dishId") or "") in pool]
			if len(matching) < required_count:
				return {"success": False}

		elif combo_type == "build_your_own":
			# At least items_to_select items from item_pool present
			pool = []
			if offer.item_pool:
				try:
					pool = json.loads(offer.item_pool) if isinstance(offer.item_pool, str) else offer.item_pool
				except Exception:
					pass
			required_count = int(getattr(offer, "items_to_select", 2) or 2)
			matching = [i for i in cart_items if str(i.get("dishId") or "") in pool]
			if len(matching) < required_count:
				return {"success": False}

	# Calculate Discount
	discount_amount = 0
	if is_delivery_offer:
		if offer.discount_type == 'delivery':
			discount_amount = flt(delivery_fee)
		elif offer.discount_type == 'flat':
			discount_amount = flt(offer.discount_value)
		elif offer.discount_type == 'percent':
			discount_amount = (flt(delivery_fee) * flt(offer.discount_value)) / 100
	else:
		if offer.offer_type == "combo":
			if combo_type == "bogo":
				# Cheapest qualifying item is free
				pool = []
				if offer.item_pool:
					try:
						pool = json.loads(offer.item_pool) if isinstance(offer.item_pool, str) else offer.item_pool
					except Exception:
						pass
				matching_prices = sorted(
					[flt(i.get("unitPrice", 0)) for i in cart_items if str(i.get("dishId") or "") in pool]
				)
				discount_amount = matching_prices[0] if matching_prices else 0

			elif combo_type == "build_your_own" and offer.combo_price is not None:
				# Sum of qualifying items minus combo_price
				pool = []
				if offer.item_pool:
					try:
						pool = json.loads(offer.item_pool) if isinstance(offer.item_pool, str) else offer.item_pool
					except Exception:
						pass
				selected_total = sum(flt(i.get("unitPrice", 0)) for i in cart_items if str(i.get("dishId") or "") in pool)
				discount_amount = max(0, selected_total - flt(offer.combo_price))

			elif combo_type == "fixed_bundle" and offer.combo_price is not None:
				discount_amount = max(0, flt(cart_total) - flt(offer.combo_price))

			else:
				discount_amount = flt(offer.discount_value)

		elif offer.discount_type == "percent":
			discount_amount = (flt(cart_total) * flt(offer.discount_value)) / 100
			if offer.max_discount_cap and discount_amount > flt(offer.max_discount_cap):
				discount_amount = flt(offer.max_discount_cap)
		else:
			discount_amount = flt(offer.discount_value)

	return {"success": True, "discount_amount": discount_amount}
