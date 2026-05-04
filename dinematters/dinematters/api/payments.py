"""
Razorpay Payment Integration API endpoints for Dinematters
"""

import frappe
import razorpay
import json
import math
from datetime import datetime
from frappe import _
from dinematters.dinematters.utils.api_helpers import validate_restaurant_for_api
from dinematters.dinematters.utils.customer_helpers import require_verified_phone, get_or_create_customer, validate_customer_session, is_phone_verified, normalize_phone
from dinematters.dinematters.utils.razorpay_utils import get_razorpay_config, get_razorpay_client, get_or_create_razorpay_customer

def get_or_create_mandate_plan(client):
	"""Get or create a high-limit registration plan for Autopay mandates."""
	try:
		# For production, we want the mandate to have a high enough limit
		# so that multiple coin recharges of ₹1,000, ₹5,000, etc. are allowed without re-verification.
		# A ₹15,000 limit is a safe production standard for DineMatters merchants.
		plan_name = "DineMatters Autopay Mandate (Limit ₹15,000)"
		plans = client.plan.all()
		for p in plans.get("items", []):
			if p.get("item", {}).get("name") == plan_name:
				return p.get("id")
		
		new_plan = client.plan.create({
			"period": "yearly",
			"interval": 10,
			"item": {
				"name": plan_name,
				"amount": 1500000, # ₹15,000 Safety Cap (Mandate Limit)
				"currency": "INR",
				"description": "Permanent mandate authorization for automatic coin recharges"
			}
		})
		return new_plan.get("id")
	except Exception as e:
		frappe.log_error(f"Failed to get/create mandate plan: {str(e)}", "razorpay.mandate_plan")
		return None





# (Local Razorpay helpers moved to utils.razorpay_utils)


@frappe.whitelist(allow_guest=True)
def create_linked_account(*args, **kwargs):
	"""Legacy Route linked-account functionality removed.
	This endpoint is deprecated and intentionally disabled in the SaaS billing implementation.
	"""
	return {"success": False, "error": "create_linked_account is deprecated in SaaS billing mode"}


@frappe.whitelist(allow_guest=True)
def create_payment_order(restaurant_id, order_items, total_amount, subtotal=None, packaging_fee=0, delivery_fee=0, customer_name=None, customer_email=None, customer_phone=None, table_number=None, existing_order_id=None, idempotency_key=None, order_type=None, coupon_code=None, loyalty_coins_redeemed=0, delivery_info=None, pickup_time=None, tax=None, cgst=None, sgst=None, tax_percent=None):
	"""Create or update a Razorpay order for customer payment (SaaS model: no Route/transfers)."""
	try:
		_restaurant_name = validate_restaurant_for_api(restaurant_id)
		restaurant = frappe.get_doc("Restaurant", _restaurant_name)

		# Parse delivery info if string
		if isinstance(delivery_info, str):
			delivery_info = json.loads(delivery_info)
		delivery_info = delivery_info or {}

		# Convert pickup_time to datetime if provided
		pickup_datetime = None
		if pickup_time:
			try:
				if isinstance(pickup_time, str):
					pickup_datetime = datetime.fromisoformat(pickup_time.replace('Z', '+00:00'))
				else:
					pickup_datetime = pickup_time
			except Exception:
				pickup_datetime = None

		# Auth gate: when verify_my_user is ON, require a valid session token OR a DB-verified phone.
		# Session token is preferred (X-Customer-Token header); DB verified_at is the grace fallback.
		# This prevents forced re-auth while keeping payment creation secure.
		if customer_phone:
			config = frappe.db.get_value("Restaurant Config", {"restaurant": _restaurant_name}, "verify_my_user")
			if config:
				session_token = frappe.request.headers.get("X-Customer-Token") if frappe.request else None
				normalized = normalize_phone(customer_phone)
				has_valid_session = validate_customer_session(normalized, session_token) if session_token else False
				has_verified_phone = is_phone_verified(normalized)
				if not has_valid_session and not has_verified_phone:
					return {"success": False, "error": {"code": "PHONE_NOT_VERIFIED", "message": "Please verify your phone with OTP first"}}

		# Get platform customer for linking
		platform_customer = None
		if customer_phone:
			cust = get_or_create_customer(customer_phone, customer_name, customer_email)
			platform_customer = cust.name if cust else None

		# Parse order items if string
		if isinstance(order_items, str):
			order_items = json.loads(order_items)

		# Convert total_amount to paise (integer)
		total_amount_paise = int(float(total_amount) * 100)

		# Calculate platform fee (Dynamic % by restaurant config)
		platform_fee_percent = float(restaurant.platform_fee_percent if restaurant.platform_fee_percent is not None else 1.5)
		platform_fee_paise = int(math.floor(total_amount_paise * (platform_fee_percent / 100.0)))

		# Create or Update order in ERPNext
		order_doc = None
		
		# Enterprise Idempotency: Check if an order with this idempotency_key already exists
		if idempotency_key:
			existing_name = frappe.db.get_value("Order", {"idempotency_key": idempotency_key}, "name")
			if existing_name:
				existing_order_id = existing_name

		if existing_order_id:
			try:
				order_doc = frappe.get_doc("Order", existing_order_id)
				# Only reuse if it's still pending payment and belongs to the same restaurant
				if order_doc.payment_status != "pending" or order_doc.restaurant != restaurant_id:
					order_doc = None
			except frappe.DoesNotExistError:
				order_doc = None

		if not order_doc:
			order_doc = frappe.new_doc("Order")
			order_id = frappe.generate_hash(length=10)
			# Generate a human-readable order number
			from dinematters.dinematters.api.orders import generate_order_number
			order_number = generate_order_number()
			order_doc.update({
				"order_id": order_id,
				"order_number": order_number,
				"restaurant": restaurant_id,
			})

		# Update basic info
		order_doc.update({
			"customer_name": customer_name,
			"customer_email": customer_email,
			"customer_phone": customer_phone,
			"platform_customer": platform_customer,
			"table_number": table_number,
			"order_type": order_type,
			"subtotal": total_amount, # This is the subtotal before discounts
			"status": "confirmed",
			"payment_status": "pending",
			"payment_method": "online",
			"platform_fee_amount": platform_fee_paise,
			"idempotency_key": idempotency_key,
			"delivery_address": delivery_info.get("address"),
			"delivery_landmark": delivery_info.get("landmark"),
			"delivery_city": delivery_info.get("city"),
			"delivery_state": delivery_info.get("state"),
			"delivery_zip_code": delivery_info.get("zipCode") or delivery_info.get("zip_code"),
			"delivery_instructions": delivery_info.get("instructions"),
			"pickup_time": pickup_datetime,
			"packaging_fee": float(packaging_fee or 0),
			"delivery_fee": float(delivery_fee or 0),
			"tax": float(tax or 0),
			"cgst": float(cgst or 0),
			"sgst": float(sgst or 0),
			"tax_percent": float(tax_percent or 0)
		})

		# total_amount from frontend is the final payable total
		# subtotal from frontend is the original total before discounts
		# If subtotal isn't provided (legacy frontend), fall back to total_amount
		# total_amount from frontend is the final payable total
		# subtotal from frontend is the original total before discounts
		# If subtotal isn't provided (legacy frontend), fall back to total_amount
		orig_subtotal = float(subtotal) if subtotal is not None else float(total_amount)
		pkg_fee = float(packaging_fee or 0)
		del_fee = float(delivery_fee or 0)
		
		# total_discount_frontend is the difference between (subtotal + fees) and the final total_amount
		total_discount_frontend = max(0, (orig_subtotal + pkg_fee + del_fee) - float(total_amount))
		
		applied_coupon = coupon_code
		redeemed_coins = int(loyalty_coins_redeemed or 0)
		loyalty_discount = 0
		coupon_discount_value = 0

		# 1. Handle Loyalty
		if redeemed_coins > 0 and platform_customer:
			try:
				from dinematters.dinematters.utils.loyalty import get_loyalty_balance, is_loyalty_enabled
				if is_loyalty_enabled(_restaurant_name):
					balance = get_loyalty_balance(platform_customer, _restaurant_name)
					if redeemed_coins > balance:
						redeemed_coins = balance
					
					loyalty_configs = frappe.get_all("Restaurant Loyalty Config", 
						filters={"restaurant": _restaurant_name, "is_active": 1}, 
						fields=["name", "coin_value_in_inr"],
						limit=1)
					
					if loyalty_configs:
						loyalty_prog = frappe.get_doc("Restaurant Loyalty Config", loyalty_configs[0].name)
						loyalty_discount = float(redeemed_coins * (loyalty_prog.coin_value_in_inr or 1))
						# Cap at 30% of subtotal
						max_ld = orig_subtotal * 0.3
						if loyalty_discount > max_ld:
							loyalty_discount = max_ld
							redeemed_coins = int(loyalty_discount / (loyalty_prog.coin_value_in_inr or 1))
				else:
					redeemed_coins = 0
					loyalty_discount = 0
			except Exception as e:
				frappe.log_error(f"Payment loyalty validation failed: {str(e)}", "Loyalty Error")
				redeemed_coins = 0
				loyalty_discount = 0

		# 2. Handle Coupon
		if coupon_code:
			try:
				from dinematters.dinematters.api.coupons import validate_coupon
				cart_items_val = [{"dishId": i.get("product_id") or i.get("dishId")} for i in order_items]
				coupon_res = validate_coupon(restaurant_id, coupon_code, orig_subtotal, customer_id=platform_customer, cart_items=json.dumps(cart_items_val))
				if coupon_res.get("success"):
					cdata = coupon_res.get("data", {}).get("coupon", {})
					applied_coupon = cdata.get("id")
					coupon_discount_value = float(cdata.get("discountAmount") or 0)
			except Exception as e:
				frappe.log_error(f"Payment coupon validation failed: {str(e)}")

		# Final discount calculation
		calculated_total_discount = loyalty_discount + coupon_discount_value
		final_discount = max(total_discount_frontend, calculated_total_discount)

		# Update totals and discount fields
		order_doc.update({
			"coupon": applied_coupon,
			"loyalty_coins_redeemed": redeemed_coins,
			"loyalty_discount": loyalty_discount,
			"discount": final_discount,
			"subtotal": orig_subtotal,
			"total": float(total_amount)
		})


		# Clear and Add order items
		order_doc.set("order_items", [])

		# Add order items
		for item in order_items:
			# Support both 'product_id' and 'dishId' (frontend consistency)
			product_id = item.get("product_id") or item.get("dishId")
			if not product_id:
				continue

				
			rate = float(item.get("rate") or item.get("unit_price") or 0)
			quantity = float(item.get("quantity") or 1)
			amount = float(item.get("amount") or item.get("total_price") or (rate * quantity))
			
			order_doc.append("order_items", {
				"product": product_id,
				"quantity": quantity,
				"unit_price": rate,
				"original_price": rate,
				"total_price": amount
			})

		# Save order
		if order_doc.is_new():
			order_doc.insert(ignore_permissions=True)
		else:
			order_doc.save(ignore_permissions=True)

		# Calculate Razorpay amount from final order total (in paise)
		final_total_paise = int(float(order_doc.total) * 100)
		
		# Create Razorpay order (standard, no transfers)
		# Prefer restaurant-specific merchant keys if configured (so customers pay the merchant)
		client = get_razorpay_client(restaurant_id)
		razorpay_order_data = {
			"amount": final_total_paise,
			"currency": "INR",
			"payment_capture": 1,
			"notes": {
				"order_id": order_doc.name,
				"restaurant_id": restaurant_id,
				"platform_fee": platform_fee_paise
			}
		}

		razorpay_order = client.order.create(razorpay_order_data)

		# Update order with Razorpay order ID
		order_doc.razorpay_order_id = razorpay_order["id"]
		order_doc.save(ignore_permissions=True)

		# Get public key for frontend.
		# If restaurant provided merchant keys, return merchant key_id so frontend Checkout uses merchant credentials.
		# Fetch Key ID via universal helper (mode-aware)
		cfg = get_razorpay_config(restaurant.name if restaurant else None)
		key_id = cfg.get("key_id")

		return {
			"success": True,
			"data": {
				"razorpay_order_id": razorpay_order["id"],
				"amount": total_amount_paise,
				"currency": "INR",
				"key_id": key_id,
				"order_id": order_doc.name,
				"platform_fee": platform_fee_paise
			}
		}
	except Exception as e:
		frappe.log_error(f"Razorpay order creation failed: {str(e)}", "razorpay.create_payment_order")
		return {
			"success": False,
			"error": str(e)
		}


@frappe.whitelist(allow_guest=True)
def verify_payment(razorpay_order_id, razorpay_payment_id, razorpay_signature):
	"""Verify payment signature (optional - webhooks are authoritative)"""
	try:
		# Prefer using the merchant's keys if the order belongs to a restaurant that has merchant credentials.
		order = None
		try:
			order = frappe.get_doc("Order", {"razorpay_order_id": razorpay_order_id})
		except Exception:
			order = None

		if order and getattr(order, "restaurant", None):
			client = get_razorpay_client(order.restaurant)
		else:
			client = get_razorpay_client()

		# Verify signature
		params_dict = {
			'razorpay_order_id': razorpay_order_id,
			'razorpay_payment_id': razorpay_payment_id,
			'razorpay_signature': razorpay_signature
		}
		client.utility.verify_payment_signature(params_dict)

		if order:
			# Update payment details (webhook will be authoritative)
			try:
				order.payment_status = "completed"
				if order.status == "pending_verification":
					order.status = "confirmed"
				order.razorpay_payment_id = razorpay_payment_id
				order.transaction_id = razorpay_payment_id
				order.save(ignore_permissions=True)
				
				# Process Loyalty and Coupons (since payment is now verified)
				process_loyalty_and_coupons(order)
				
			except Exception as e:
				frappe.log_error(f"Error updating order after verification: {str(e)}")
				frappe.db.set_value("Order", order.name, {
					"payment_status": "completed",
					"razorpay_payment_id": razorpay_payment_id,
					"transaction_id": razorpay_payment_id
				})
				if frappe.db.get_value("Order", order.name, "status") == "pending_verification":
					frappe.db.set_value("Order", order.name, "status", "confirmed")
				frappe.db.commit()
				
				# Try processing loyalty even if doc save failed (using db values)
				try:
					order_doc = frappe.get_doc("Order", order.name)
					process_loyalty_and_coupons(order_doc)
				except Exception:
					pass

		return {
			"success": True,
			"data": {
				"verified": True,
				"order_id": order.name if order else None
			}
		}
		
	except Exception as e:
		frappe.log_error(f"Payment verification failed: {str(e)}", "razorpay.verify_payment")
		return {
			"success": False,
			"error": "Payment verification failed"
		}


def process_loyalty_and_coupons(order):
	"""Process loyalty point deductions/earnings and coupon usage after payment success.
	Idempotent: checks existing Restaurant Loyalty Entry records to prevent double-processing.
	Each step (deduct / earn / coupon) is isolated so a failure in one does not block the others.
	"""
	from dinematters.dinematters.utils.loyalty import redeem_loyalty_coins, earn_loyalty_coins

	restaurant_id = order.restaurant
	platform_customer = order.platform_customer

	if not platform_customer:
		frappe.log_error(
			f"process_loyalty_and_coupons: no platform_customer on order {order.name}",
			"Loyalty Debug"
		)
		return

	# ── 1. Deduct Redeemed Coins ────────────────────────────────────────────────
	try:
		coins_to_redeem = int(order.loyalty_coins_redeemed or 0)
		if coins_to_redeem > 0:
			# Idempotency: skip if a Redeem entry already exists for this order
			already_redeemed = frappe.db.exists("Restaurant Loyalty Entry", {
				"customer": platform_customer,
				"restaurant": restaurant_id,
				"reference_doctype": "Order",
				"reference_name": order.name,
				"transaction_type": "Redeem"
			})
			if already_redeemed:
				frappe.log_error(
					f"Loyalty deduction already done for order {order.name}, skipping.",
					"Loyalty Debug"
				)
			else:
				result = redeem_loyalty_coins(
					customer=platform_customer,
					restaurant=restaurant_id,
					coins=coins_to_redeem,
					reason="Redemption",
					ref_doctype="Order",
					ref_name=order.name
				)
				frappe.db.commit()
				frappe.log_error(
					f"Loyalty REDEEMED {coins_to_redeem} coins for order {order.name}, entry={result.name if result else None}",
					"Loyalty Debug"
				)
	except Exception as e:
		frappe.log_error(
			f"Loyalty deduction failed for order {order.name}: {str(e)}",
			"Loyalty Deduction Error"
		)

	# ── 2. Earn Coins on Final Paid Amount ──────────────────────────────────────
	try:
		# Idempotency: skip if an Earn entry already exists for this order
		already_earned = frappe.db.exists("Restaurant Loyalty Entry", {
			"customer": platform_customer,
			"restaurant": restaurant_id,
			"reference_doctype": "Order",
			"reference_name": order.name,
			"transaction_type": "Earn"
		})
		if not already_earned:
			earn_loyalty_coins(
				customer=platform_customer,
				restaurant=restaurant_id,
				amount_paid=order.total,
				reason="Order",
				ref_doctype="Order",
				ref_name=order.name
			)
			frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Loyalty earning failed for order {order.name}: {str(e)}",
			"Loyalty Earning Error"
		)

	# ── 3. Track Coupon Usage ───────────────────────────────────────────────────
	if order.coupon:
		try:
			if not frappe.db.exists("Coupon Usage", {"order": order.name, "coupon": order.coupon}):
				usage_doc = frappe.get_doc({
					"doctype": "Coupon Usage",
					"coupon": order.coupon,
					"customer": platform_customer,
					"order": order.name,
					"restaurant": restaurant_id,
					"discount_amount": order.discount
				})
				usage_doc.insert(ignore_permissions=True)
				frappe.db.sql("UPDATE `tabCoupon` SET usage_count = COALESCE(usage_count, 0) + 1 WHERE name = %s", (order.coupon,))
				frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"Coupon tracking failed: {str(e)}"[:140], "Coupon Tracking Error")



@frappe.whitelist(allow_guest=True)
def get_restaurant_payment_stats(restaurant_id):
	"""Get payment statistics for a restaurant"""
	try:
		# Validate restaurant (returns restaurant doc name), then fetch doc
		_restaurant_name = validate_restaurant_for_api(restaurant_id)
		restaurant = frappe.get_doc("Restaurant", _restaurant_name)

		def mask_identifier(value, prefix_len=4):
			if not value:
				return None
			value = str(value)
			if len(value) <= 8:
				return value[:2] + "****" + value[-2:]
			return value[:prefix_len] + "********" + value[-4:]
		
		# Get current month stats
		from datetime import datetime
		current_month = datetime.now().strftime("%Y-%m")
		
		# Get total orders and revenue for current month
		orders = frappe.db.sql("""
			SELECT 
				COUNT(*) as total_orders,
				COALESCE(SUM(total), 0) as total_revenue,
				COALESCE(SUM(platform_fee_amount), 0) as total_platform_fee
			FROM `tabOrder`
			WHERE restaurant = %s 
			AND payment_status = 'completed'
			AND DATE_FORMAT(creation, '%%Y-%%m') = %s
		""", (restaurant_id, current_month), as_dict=True)
		
		stats = orders[0] if (orders and orders[0]) else {
			"total_orders": 0,
			"total_revenue": 0,
			"total_platform_fee": 0
		}
		
		# Get monthly minimum info (ensure numeric values)
		monthly_minimum = float(restaurant.monthly_minimum if restaurant.monthly_minimum is not None else 999.0)
		platform_fee_collected = (stats["total_platform_fee"] or 0) / 100.0  # Convert from paise to rupees
		minimum_due = max(0, monthly_minimum - platform_fee_collected)
		
		return {
			"success": True,
			"data": {
				"current_month": current_month,
				"total_orders": stats["total_orders"],
				"total_revenue": stats["total_revenue"],
				"platform_fee_collected": platform_fee_collected,
				"monthly_minimum": monthly_minimum,
				"minimum_due": minimum_due,
				"razorpay_customer_id": restaurant.razorpay_customer_id,
				"razorpay_token_id": restaurant.razorpay_token_id,
				"mandate_status": restaurant.mandate_status,
				"masked_customer_id": mask_identifier(restaurant.razorpay_customer_id),
				"masked_token_id": mask_identifier(restaurant.razorpay_token_id),
				"masked_key_id": mask_identifier(restaurant.razorpay_merchant_key_id, prefix_len=8),
				"billing_status": restaurant.billing_status,
				"razorpay_keys_updated_at": getattr(restaurant, "razorpay_keys_updated_at", None),
				"razorpay_keys_updated_by": getattr(restaurant, "razorpay_keys_updated_by", None),
				"merchant_key_configured": bool(getattr(restaurant, "razorpay_merchant_key_id", None))
			}
		}
		
	except Exception as e:
		frappe.log_error(f"Payment stats fetch failed: {str(e)}", "razorpay.get_payment_stats")
		return {
			"success": False,
			"error": str(e)
		}



@frappe.whitelist()
def create_razorpay_customer_and_token(restaurant_id, customer_name, customer_email, token_id=None):
	"""Create a Razorpay customer record and optionally store a token id for recurring charges."""
	try:
		_restaurant_name = validate_restaurant_for_api(restaurant_id)
		restaurant = frappe.get_doc("Restaurant", _restaurant_name)

		client = get_razorpay_client()

		# Create customer on Razorpay if not exists
		if not restaurant.razorpay_customer_id:
			customer_payload = {
				"name": customer_name,
				"email": customer_email,
				"contact": restaurant.owner_phone or customer_email,
				"notes": {"restaurant": restaurant_id}
			}
			customer = client.customer.create(customer_payload)
			restaurant.razorpay_customer_id = customer.get("id")

		# If a token_id was provided (from frontend tokenization), store it
		if token_id:
			restaurant.razorpay_token_id = token_id
			restaurant.mandate_status = "active"

		restaurant.billing_status = restaurant.billing_status or "active"
		restaurant.save()

		return {"success": True, "customer_id": restaurant.razorpay_customer_id, "token_id": restaurant.razorpay_token_id}
	except Exception as e:
		frappe.log_error(f"Failed to create Razorpay customer/token: {str(e)}", "razorpay.create_customer_token")
		return {"success": False, "error": str(e)}

@frappe.whitelist()
def set_restaurant_razorpay_keys(restaurant_id, key_id, key_secret, webhook_secret=None):
	"""Set per-restaurant Razorpay merchant credentials. Admin-only."""
	try:
		# Only allow System Managers
		roles = frappe.get_roles(frappe.session.user)
		if 'System Manager' not in roles and 'Administrator' not in roles:
			frappe.throw(_("Not permitted"), frappe.PermissionError)

		_restaurant_name = validate_restaurant_for_api(restaurant_id)
		restaurant = frappe.get_doc("Restaurant", _restaurant_name)
		restaurant.razorpay_merchant_key_id = key_id
		restaurant.razorpay_merchant_key_secret = key_secret
		# optional webhook secret
		if webhook_secret:
			restaurant.razorpay_webhook_secret = webhook_secret
		# Audit: record who updated keys and when
		try:
			restaurant.razorpay_keys_updated_at = frappe.utils.now_datetime()
			restaurant.razorpay_keys_updated_by = frappe.session.user
		except Exception:
			# ignore if fields missing
			pass
		restaurant.save()
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Failed to set restaurant razorpay keys: {str(e)}", "razorpay.set_keys")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def can_set_merchant_keys():
	"""Return whether current user can set merchant keys (System Manager or Administrator)."""
	try:
		user = frappe.session.user
		roles = frappe.get_roles(user)
		allowed = 'System Manager' in roles or 'Administrator' in roles
		return {"success": True, "allowed": allowed, "user": user, "roles": roles}
	except Exception as e:
		return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
def create_tokenization_order(restaurant_id, customer_name=None, customer_email=None):
	"""
	Create a Razorpay Subscription to register a production mandate (UPI, Card, eNACH).
	We use the Subscriptions API to ensure full multi-method support for live customers.
	"""
	try:
		_restaurant_name = validate_restaurant_for_api(restaurant_id)
		client = get_razorpay_client()
		customer_id = get_or_create_razorpay_customer(restaurant_id)
		
		plan_id = get_or_create_mandate_plan(client)
		if not plan_id:
			raise Exception("Could not create registration plan")

		# Create a TokenizationAttempt doc
		attempt_doc = frappe.get_doc({
			"doctype": "Tokenization Attempt",
			"restaurant": restaurant_id,
			"amount": 100, # ₹1
			"currency": "INR",
			"status": "pending",
			"notes": json.dumps({"via": "subscription"})
		})
		attempt_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		# Create Subscription
		subscription_payload = {
			"plan_id": plan_id,
			"customer_id": customer_id,
			"total_count": 120, # 10 years, will be cancelled after token capture
			"quantity": 1,
			"customer_notify": 0,
			"notes": {
				"attempt_id": attempt_doc.name,
				"restaurant_id": restaurant_id,
				"description": "Production Autopay Mandate Registration (Limit: ₹15,000)",
				"type": "tokenization"
			}
		}
		
		subscription = client.subscription.create(subscription_payload)

		sub_id = subscription.get("id")
		attempt_doc.razorpay_order_id = sub_id # store sub_id in order_id field for webhook mapping
		attempt_doc.status = "created"
		attempt_doc.save(ignore_permissions=True)
		frappe.db.commit()

		cfg = get_razorpay_config()
		return {
			"success": True,
			"data": {
				"razorpay_subscription_id": sub_id,
				"amount": 100,
				"currency": "INR",
				"key_id": cfg.get("key_id"),
				"customer_id": customer_id,
				"attempt_doc": attempt_doc.name
			}
		}
	except Exception as e:
		frappe.log_error(f"Failed to create tokenization order: {str(e)}", "razorpay.create_token_order")
		return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def confirm_mandate_setup(restaurant_id, razorpay_payment_id, razorpay_order_id, razorpay_signature):
	"""
	Confirm mandate registration after Razorpay Checkout handler fires.
	Verifies signature, fetches token from Razorpay, and saves to Restaurant doc.
	This is called by the frontend after the Checkout handler returns.
	"""
	try:
		_restaurant_name = validate_restaurant_for_api(restaurant_id)
		
		# 1. Verify payment signature
		cfg = get_razorpay_config()
		client = get_razorpay_client()
		
		# Signature verification varies by type (Order vs Subscription)
		try:
			if razorpay_order_id.startswith('sub_'):
				client.utility.verify_subscription_payment_signature({
					'razorpay_subscription_id': razorpay_order_id,
					'razorpay_payment_id': razorpay_payment_id,
					'razorpay_signature': razorpay_signature
				})
			else:
				client.utility.verify_payment_signature({
					'razorpay_order_id': razorpay_order_id,
					'razorpay_payment_id': razorpay_payment_id,
					'razorpay_signature': razorpay_signature
				})
		except Exception as e:
			frappe.log_error(f"Mandate signature verification failed for {_restaurant_name}: {str(e)}", "razorpay.confirm_mandate")
			return {"success": False, "error": "Payment signature verification failed"}
		
		# 2. Fetch payment details from Razorpay to get the token
		try:
			payment = client.payment.fetch(razorpay_payment_id)
		except Exception as e:
			# Signature verified so trust is established; fall back to webhook for token
			frappe.log_error(f"Could not fetch payment {razorpay_payment_id} from Razorpay: {str(e)}", "razorpay.confirm_mandate")
			payment = {}
		
		customer_id = payment.get("customer_id") or payment.get("customer")
		token_id = (
			payment.get("token_id") or
			payment.get("token") or
			(payment.get("card") or {}).get("token_id") or
			(payment.get("card") or {}).get("token") or
			payment.get("notes", {}).get("token_id")
		)
		
		# 3. Save to restaurant doc
		restarurant_doc = frappe.get_doc("Restaurant", _restaurant_name)
		updated = False
		
		if customer_id and not restarurant_doc.razorpay_customer_id:
			restarurant_doc.razorpay_customer_id = customer_id
			updated = True
			
		if token_id:
			restarurant_doc.razorpay_token_id = token_id
			restarurant_doc.mandate_status = "active"
			updated = True
		elif customer_id:
			# Token not yet in payment response (webhook will deliver it via token.confirmed)
			# Set mandate as "pending" so UI shows correct state
			if restarurant_doc.mandate_status != "active":
				restarurant_doc.mandate_status = "pending"
			updated = True
		
		if updated:
			restarurant_doc.save(ignore_permissions=True)
			frappe.db.commit()
		
		# 4. Update Tokenization Attempt doc
		try:
			attempt = frappe.db.get_value("Tokenization Attempt", {"razorpay_order_id": razorpay_order_id}, "name")
			if attempt:
				frappe.db.set_value("Tokenization Attempt", attempt, {
					"razorpay_payment_id": razorpay_payment_id,
					"customer_id": customer_id,
					"token_id": token_id,
					"status": "captured",
					"processed": 1
				})
				frappe.db.commit()
		except Exception:
			pass  # Non-fatal
		
		return {
			"success": True,
			"mandate_active": restarurant_doc.mandate_status == "active",
			"token_saved": bool(token_id),
			"message": "Mandate registered successfully" if token_id else "Payment verified. Mandate will activate shortly via webhook."
		}
	except Exception as e:
		frappe.log_error(f"confirm_mandate_setup failed for {restaurant_id}: {str(e)}", "razorpay.confirm_mandate")
		return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
def download_guide(guide_name):
	import os
	try:
		from markdown_pdf import MarkdownPdf, Section
	except ImportError:
		frappe.throw("markdown-pdf library is required. Please install it.")
		
	# Validate guide_name to prevent directory traversal
	if not guide_name or not guide_name.replace('_', '').replace('-', '').isalnum():
		frappe.throw("Invalid guide name")
		
	# Use deterministic path relative to this script
	base_dir = os.path.join(os.path.dirname(__file__), '..', 'customer-readme-notes')
	file_path = os.path.abspath(os.path.join(base_dir, f"{guide_name}.md"))
	
	# Ensure the resolved path is actually inside the expected directory
	if not file_path.startswith(os.path.abspath(base_dir)):
		frappe.throw("Invalid path")
		
	if not os.path.exists(file_path):
		frappe.throw(f"Guide not found: {guide_name}")
		
	with open(file_path, "r") as f:
		md_content = f.read()
		
	pdf = MarkdownPdf(toc_level=0)
	pdf.add_section(Section(md_content))
	
	import tempfile
	with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
		tmp_path = tmp.name
	
	try:
		pdf.save(tmp_path)
		with open(tmp_path, "rb") as f:
			pdf_data = f.read()
	finally:
		if os.path.exists(tmp_path):
			os.remove(tmp_path)
	
	frappe.local.response.filename = f"{guide_name}.pdf"
	frappe.local.response.filecontent = pdf_data
	frappe.local.response.type = "download"



@frappe.whitelist()
def schedule_monthly_billing():
	"""Create Monthly Billing Ledger entries for all restaurants for the current month."""
	try:
		from datetime import datetime
		current_month = datetime.now().strftime("%Y-%m")
		# For each active restaurant, compute GMV and create ledger row if not present
		restaurants = frappe.get_all("Restaurant", filters={"is_active": 1}, fields=["name"])
		created = []
		for r in restaurants:
			if frappe.db.exists("Monthly Billing Ledger", {"restaurant": r.name, "billing_month": current_month}):
				continue
			# Sum completed orders for month
			total = frappe.db.sql("""
				SELECT COALESCE(SUM(total),0) FROM `tabOrder` 
				WHERE restaurant=%s AND payment_status='completed' AND DATE_FORMAT(creation, '%%Y-%%m')=%s
			""", (r.name, current_month))[0][0] or 0
			# Convert to paise
			total_paise = int(float(total) * 100)
			# Fetch commission settings from Restaurant
			res_doc = frappe.get_doc("Restaurant", r.name)
			platform_fee_percent = float(res_doc.platform_fee_percent if res_doc.platform_fee_percent is not None else 1.5)
			monthly_min = float(res_doc.monthly_minimum if res_doc.monthly_minimum is not None else 999.0)
			
			calculated_fee = int(math.floor(total_paise * (platform_fee_percent / 100.0)))
			min_amt_paise = int(monthly_min * 100)
			base_commission = max(min_amt_paise, calculated_fee)
			
			# GST Compliance (18% standard for SaaS)
			tax_rate = 18.0
			gst_amount = int(math.floor(base_commission * (tax_rate / 100.0)))
			final_total = base_commission + gst_amount

			ledger = frappe.get_doc({
				"doctype": "Monthly Billing Ledger",
				"restaurant": r.name,
				"billing_month": current_month,
				"total_gmv": total_paise,
				"calculated_fee": base_commission,
				"gst_amount": gst_amount,
				"tax_percent": tax_rate,
				"final_amount": final_total,
				"payment_status": "pending",
				"notes": f"Base Commission: ₹{base_commission/100:.2f}, GST ({tax_rate}%): ₹{gst_amount/100:.2f}"
			})
			ledger.insert(ignore_permissions=True)
			created.append(ledger.name)
		return {"success": True, "created": created}
	except Exception as e:
		frappe.log_error(f"Monthly billing scheduler failed: {str(e)}", "razorpay.schedule_billing")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def process_retry_charges():
	"""Process Monthly Billing Ledger entries marked for retry whose next_retry_at is due."""
	try:
		from datetime import datetime
		now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		ledgers = frappe.get_all("Monthly Billing Ledger", filters={"payment_status": "retry", "next_retry_at": ("<=", now)}, fields=["name"])
		for l in ledgers:
			try:
				charge_monthly_bill(l.name)
			except Exception as e:
				frappe.log_error(f"Retry charge failed for {l.name}: {str(e)}", "razorpay.retry_charge")
		return {"success": True, "processed": len(ledgers)}
	except Exception as e:
		frappe.log_error(f"Retry processor failed: {str(e)}", "razorpay.retry_processor")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def charge_monthly_bill(ledger_name):
	"""Attempt to charge a Monthly Billing Ledger using stored token/customer."""
	try:
		ledger = frappe.get_doc("Monthly Billing Ledger", ledger_name)
		if ledger.payment_status == "paid":
			return {"success": False, "error": "Already paid"}

		restaurant = frappe.get_doc("Restaurant", ledger.restaurant)
		if not restaurant.razorpay_customer_id or not restaurant.razorpay_token_id:
			return {"success": False, "error": "Restaurant missing customer/token"}

		client = get_razorpay_client(restaurant.name)

		# RBI Threshold Check (₹15,000 = 1500000 paise)
		# For charges > ₹15,000, e-mandates require additional authentication (AFA).
		# We fallback to a Payment Link in such cases to ensure compliance and success.
		if int(ledger.final_amount) > 1500000:
			try:
				payment_link_payload = {
					"amount": int(ledger.final_amount),
					"currency": "INR",
					"accept_partial": False,
					"description": f"DineMatters SaaS Bill: {ledger.billing_month}",
					"customer": {
						"name": restaurant.owner_name or restaurant.restaurant_name,
						"email": restaurant.owner_email or "",
						"contact": restaurant.owner_phone or ""
					},
					"notify": {
						"sms": True,
						"email": True
					},
					"reminder_enable": True,
					"notes": {"ledger": ledger.name}
				}
				
				# SDK check: generic request vs SDK method
				if hasattr(client, 'payment_link'):
					link = client.payment_link.create(payment_link_payload)
				else:
					link = client.request('POST', '/payment_links', payment_link_payload)
				
				short_url = link.get('short_url')
				frappe.db.set_value("Monthly Billing Ledger", ledger.name, {
					"payment_status": "pending",
					"notes": (ledger.notes or "") + f"\nRBI Limit exceeded (>₹15k). Payment Link: {short_url}"
				})
				frappe.db.commit()
				
				return {"success": True, "message": "RBI Limit Exceeded. Payment link generated.", "link": short_url}
			except Exception as e:
				frappe.log_error(f"Failed to create RBI fallback link for {ledger.name}: {str(e)}", "razorpay.charge_monthly_bill")
				# Fall through to attempt autopay as last resort

		# STEP 1: Create Razorpay Order (required before recurring charge for RBI pre-debit compliance)
		import time
		payment_after_ts = int(time.time()) + (36 * 3600) + (5 * 60)  # 36h 5m minimum TAT

		billing_order = client.order.create({
			"amount": int(ledger.final_amount),
			"currency": "INR",
			"payment_capture": True,
			"receipt": f"bill_{ledger.name[:20]}",
			"notification": {
				"token_id": restaurant.razorpay_token_id,
				"payment_after": payment_after_ts
			},
			"notes": {
				"ledger": ledger.name,
				"restaurant": ledger.restaurant,
				"type": "monthly_bill"
			}
		})
		billing_order_id = billing_order.get("id")
		if not billing_order_id:
			raise Exception("Billing order creation returned no id")

		# STEP 2: Create recurring charge via mandate token
		# Uses SDK: client.payment.createRecurring -> POST /v1/payments/create/recurring
		contact = restaurant.get("owner_phone") or "9999999999"
		email = restaurant.get("owner_email") or f"billing@{ledger.restaurant.replace(' ', '').lower()}.com"

		payment = None
		try:
			payment = client.payment.createRecurring({
				"email": email,
				"contact": contact,
				"amount": int(ledger.final_amount),
				"currency": "INR",
				"order_id": billing_order_id,
				"customer_id": restaurant.razorpay_customer_id,
				"token": restaurant.razorpay_token_id,
				"recurring": True,
				"description": f"DineMatters Monthly Bill: {ledger.billing_month}",
				"notes": {
					"ledger": ledger.name,
					"restaurant": ledger.restaurant,
					"type": "monthly_bill"
				}
			})
		except Exception as e:
			# mark ledger for retry with exponential backoff
			try:
				retry = (ledger.retry_count or 0) + 1
				frappe.db.set_value("Monthly Billing Ledger", ledger.name, "retry_count", retry)
				# exponential backoff in minutes, cap at 1440 (1 day)
				delay_minutes = min(2 ** retry, 1440)
				from datetime import datetime, timedelta
				next_try = (datetime.now() + timedelta(minutes=delay_minutes)).strftime("%Y-%m-%d %H:%M:%S")
				frappe.db.set_value("Monthly Billing Ledger", ledger.name, "next_retry_at", next_try)
				frappe.db.set_value("Monthly Billing Ledger", ledger.name, "payment_status", "retry")
				frappe.db.commit()
			except Exception:
				pass
			frappe.log_error(f"Charge monthly bill failed: {str(e)}", "razorpay.charge_monthly_bill")
			return {"success": False, "error": str(e)}

		# Record payment id and mark as pending until webhook confirms
		try:
			payment_id = payment.get("id") if isinstance(payment, dict) else None
			frappe.db.set_value("Monthly Billing Ledger", ledger.name, "razorpay_payment_id", payment_id)
			frappe.db.set_value("Monthly Billing Ledger", ledger.name, "payment_status", "pending")
			frappe.db.commit()
			return {"success": True, "payment_id": payment_id}
		except Exception as e:
			frappe.log_error(f"Failed to record charge result: {str(e)}", "razorpay.charge_monthly_bill")
			return {"success": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(f"Charge monthly bill failed: {str(e)}", "razorpay.charge_monthly_bill")
		# mark ledger as failed
		try:
			frappe.db.set_value("Monthly Billing Ledger", ledger_name, "payment_status", "failed")
			frappe.db.commit()
		except Exception:
			pass
		return {"success": False, "error": str(e)}
@frappe.whitelist()
def get_razorpay_payments(restaurant_id, from_date=None, to_date=None, count=10, skip=0):
	"""Fetch transactions directly from Razorpay for a restaurant."""
	try:
		validate_restaurant_for_api(restaurant_id)
		client = get_razorpay_client(restaurant_id)
		
		params = {
			"count": count,
			"skip": skip
		}
		
		if from_date:
			# from_date is expected as YYYY-MM-DD
			from datetime import datetime
			dt = datetime.strptime(from_date, "%Y-%m-%d")
			params["from"] = int(dt.timestamp())
			
		if to_date:
			from datetime import datetime
			dt = datetime.strptime(to_date, "%Y-%m-%d")
			# include the whole day
			params["to"] = int(dt.timestamp()) + 86399
			
		payments = client.payment.all(params)
		return {
			"success": True,
			"data": payments
		}
	except Exception as e:
		frappe.log_error(f"Failed to fetch Razorpay payments: {str(e)}", "razorpay.get_payments")
		return {"success": False, "error": str(e)}

@frappe.whitelist()
def initiate_razorpay_refund(restaurant_id, payment_id, amount=None, reason=None):
	"""Initiate a refund for a Razorpay payment."""
	try:
		validate_restaurant_for_api(restaurant_id)
		client = get_razorpay_client(restaurant_id)
		
		params = {}
		if amount:
			# amount in rupees, convert to paise
			params["amount"] = int(float(amount) * 100)
		
		if reason:
			params["notes"] = {"reason": reason}
			if reason.lower() in ["duplicate", "fraud", "requested_by_customer"]:
				params["speed"] = "normal"
				
		refund = client.payment.refund(payment_id, params)
		
		# Log refund in Order if found
		order_name = frappe.db.get_value("Order", {"razorpay_payment_id": payment_id}, "name")
		if order_name:
			frappe.get_doc("Order", order_name).add_comment("Info", text=f"Refund of ₹{amount if amount else 'full'} initiated via Razorpay. Refund ID: {refund.get('id')}")
			
		return {
			"success": True,
			"data": refund
		}
	except Exception as e:
		frappe.log_error(f"Failed to initiate Razorpay refund: {str(e)}", "razorpay.initiate_refund")
		return {"success": False, "error": str(e)}
