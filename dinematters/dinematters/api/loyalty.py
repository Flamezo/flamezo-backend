# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime, get_datetime_str
from dinematters.dinematters.utils.api_helpers import validate_restaurant_for_api
from dinematters.dinematters.utils.feature_gate import require_plan
from dinematters.dinematters.utils.customer_helpers import normalize_phone, get_or_create_customer
import json
import random
import string

@frappe.whitelist(allow_guest=True)
@require_plan('DIAMOND')
def get_loyalty_summary(restaurant_id, phone):
	"""
	GET /api/method/dinematters.dinematters.api.loyalty.get_loyalty_summary
	Get customer's loyalty balance and history for a specific restaurant
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}
		
		customer = get_or_create_customer(normalized_phone)
		
		# Get all point entries
		entries = frappe.get_all(
			"Restaurant Loyalty Entry",
			filters={"customer": customer.name, "restaurant": restaurant},
			fields=["transaction_type", "coins", "reason", "posting_date", "reference_doctype", "reference_name", "creation", "is_settled"],
			order_by="creation desc"
		)
		
		from dinematters.dinematters.utils.loyalty import get_loyalty_balance
		balance = get_loyalty_balance(customer.name, restaurant)
		pending_balance = get_loyalty_balance(customer.name, restaurant, include_pending=True) - balance
		
		# Expiring soon (within 30 days)
		from frappe.utils import add_days, today
		expiring_soon_filters = {
			"customer": customer.name, 
			"restaurant": restaurant,
			"is_settled": 1,
			"transaction_type": "Earn",
			"expiry_date": ["between", [today(), add_days(today(), 30)]]
		}
		expiring_soon_entries = frappe.get_all("Restaurant Loyalty Entry", filters=expiring_soon_filters, fields=["coins"])
		expiring_soon_balance = sum(e.coins for e in expiring_soon_entries)
		
		return {
			"success": True,
			"data": {
				"balance": balance,
				"pending_balance": pending_balance,
				"expiring_soon_balance": expiring_soon_balance,
				"transactions": entries
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_loyalty_summary: {str(e)}")
		return {"success": False, "error": {"code": "LOYALTY_FETCH_ERROR", "message": str(e)}}

@frappe.whitelist(allow_guest=True)
def get_loyalty_config(restaurant_id):
	"""Get loyalty configurations for admin and cart"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		if not frappe.db.exists("Restaurant Loyalty Config", {"restaurant": restaurant}):
			return {"success": True, "data": None}
			
		prog_name = frappe.db.get_value("Restaurant Loyalty Config", {"restaurant": restaurant}, "name")
		config = frappe.get_doc("Restaurant Loyalty Config", prog_name)
		return {"success": True, "data": config}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Get Config Error")
		return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
@require_plan('DIAMOND')
def generate_referral_link(restaurant_id, phone, platform="WhatsApp"):
	"""
	POST /api/method/dinematters.dinematters.api.loyalty.generate_referral_link
	Generate or get a unique referral link for a customer
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		normalized_phone = normalize_phone(phone)
		
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}
		
		customer = get_or_create_customer(normalized_phone)
		
		# Check if link already exists for this restaurant
		existing_link = frappe.db.get_value(
			"Referral Link",
			{"referrer": customer.name, "restaurant": restaurant},
			["name", "identifier"],
			as_dict=True
		)
		
		if existing_link:
			identifier = existing_link.identifier
		else:
			# Generate unique identifier / Personalized Slug
			name_part = customer.customer_name or customer.name
			# Slugify and take first part
			slug_base = "".join(e for e in name_part if e.isalnum()).lower()[:10]
			rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
			identifier = f"{slug_base}-{rand_part}"
			
			while frappe.db.exists("Referral Link", {"identifier": identifier}):
				rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
				identifier = f"{slug_base}-{rand_part}"
			
			link_doc = frappe.get_doc({
				"doctype": "Referral Link",
				"referrer": customer.name,
				"restaurant": restaurant,
				"identifier": identifier,
				"platform": platform,
				"is_active": 1,
				"rewarded_opens_in_cycle": 0
			})
			link_doc.insert(ignore_permissions=True)
		
		from dinematters.dinematters.utils.config_helpers import get_app_base_url
		base_url = get_app_base_url()
		referral_url = f"{base_url.rstrip('/')}/{restaurant_id}/invite/{identifier}"
		
		return {
			"success": True,
			"data": {
				"identifier": identifier,
				"link": referral_url
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in generate_referral_link: {str(e)}")
		return {"success": False, "error": {"code": "REFERRAL_LINK_ERROR", "message": str(e)}}

@frappe.whitelist(allow_guest=True)
def track_referral_visit(identifier, ip_address=None, user_agent=None):
	"""
	POST /api/method/dinematters.dinematters.api.loyalty.track_referral_visit
	Track a visit to a referral link and reward the referrer if unique
	"""
	try:
		# Auto-detect IP and User agent if not passed (Production Level Tracking)
		if not ip_address and hasattr(frappe, 'request'):
			ip_address = frappe.request.remote_addr
			
		if not user_agent and hasattr(frappe, 'request'):
			user_agent = frappe.request.headers.get('User-Agent')

		link_name = frappe.db.get_value("Referral Link", {"identifier": identifier}, "name")
		if not link_name:
			return {"success": False, "error": {"code": "LINK_NOT_FOUND", "message": "Invalid referral link"}}
		
		link_doc = frappe.get_doc("Referral Link", link_name)
		
		# Check if this identifier + IP has visited before
		is_unique = not frappe.db.exists("Referral Visit", {
			"referral_link": link_name,
			"ip_address": ip_address
		})
		
		visit_doc = frappe.get_doc({
			"doctype": "Referral Visit",
			"referral_link": link_name,
			"ip_address": ip_address,
			"user_agent": user_agent,
			"is_unique": 1 if is_unique else 0,
			"timestamp": now_datetime()
		})
		visit_doc.insert(ignore_permissions=True)
		frappe.db.commit() # Ensure visit is saved immediately
		
		# If unique, reward the referrer if within their current cycle limit
		if is_unique:
			loyalty_prog = frappe.get_doc("Restaurant Loyalty Config", {"restaurant": link_doc.restaurant, "is_active": 1})
			if loyalty_prog:
				# Check current cycle limit (Default 7 if not set)
				max_limit = loyalty_prog.max_opens_rewarded_per_share or 7
				current_count = link_doc.rewarded_opens_in_cycle or 0
				
				if current_count < max_limit:
					# Reward for unique open
					credit_loyalty_points(
						customer=link_doc.referrer,
						restaurant=link_doc.restaurant,
						coins=loyalty_prog.coins_per_unique_open or 2,
						reason="Referral Share", # Must match allowed Select options in Loyalty Point Entry
						ref_doctype="Referral Link",
						ref_name=link_name
					)
					
					# Increment cycle count
					link_doc.db_set("rewarded_opens_in_cycle", current_count + 1)
		
		return {
			"success": True,
			"data": {
				"restaurant_id": link_doc.restaurant,
				"is_unique": is_unique
			}
		}
	except Exception as e:
		frappe.log_error("Referral Tracking Error", str(e))
		return {"success": False, "error": {"code": "TRACKING_ERROR", "message": str(e)}}

@frappe.whitelist(allow_guest=True)
def get_referral_details(identifier):
	"""
	GET /api/method/dinematters.dinematters.api.loyalty.get_referral_details
	Get basic details about a referral link for social sharing previews
	"""
	try:
		link_info = frappe.db.get_value(
			"Referral Link", 
			{"identifier": identifier}, 
			["referrer", "restaurant"], 
			as_dict=True
		)
		if not link_info:
			return {"success": False, "message": "Link not found"}
			
		referrer_full_name = frappe.db.get_value("Customer", link_info.referrer, "customer_name") or link_info.referrer
		# Swiggy/Zomato style: Show first name only for privacy
		referrer_name = referrer_full_name.split(' ')[0] if referrer_full_name else link_info.referrer
		restaurant_name = frappe.db.get_value("Restaurant", link_info.restaurant, "name")
		
		# Get restaurant config for images
		logo = frappe.db.get_value("Restaurant Config", {"restaurant": link_info.restaurant}, "logo")
		# Using logo as fallback for banner as ‘banner_image’ field doesn’t exist
		banner = logo 
		
		return {
			"success": True,
			"data": {
				"referrer": referrer_name,
				"restaurant_name": restaurant_name,
				"restaurant_id": link_info.restaurant,
				"logo": logo,
				"banner": banner
			}
		}
	except Exception as e:
		return {"success": False, "error": str(e)}
		
def reset_referral_cycle(customer, restaurant):
	"""
	Resets the rewarded_opens_in_cycle counter for all referral links 
	owned by a customer at a specific restaurant.
	Called after order placement to 'renew' the sharing limit.
	"""
	try:
		frappe.db.sql("""
			UPDATE `tabReferral Link` 
			SET rewarded_opens_in_cycle = 0 
			WHERE referrer = %s AND restaurant = %s
		""", (customer, restaurant))
		frappe.db.commit()
		return True
	except Exception as e:
		frappe.log_error(f"Error in reset_referral_cycle: {str(e)}")
		return False

def process_referral_welcome_bonus(customer, restaurant, referral_id):
	"""
	Awards the Welcome Bonus instantly upon signup/verification.
	Validates that the referral_id belongs to the specified restaurant.
	"""
	try:
		# 1. Validate the referral link
		link_info = frappe.db.get_value("Referral Link", {"identifier": referral_id}, ["name", "restaurant"], as_dict=True)
		if not link_info:
			return False
		
		# Strict Scoping: Referral must match the restaurant the user is currently joining
		if link_info.get("restaurant") != restaurant:
			return False
			
		# 2. Check if customer already received a Welcome Bonus for this restaurant
		# This prevents duplicate claims even if they re-verify
		from dinematters.dinematters.utils.loyalty import get_loyalty_balance
		already_rewarded = frappe.db.exists("Restaurant Loyalty Entry", {
			"customer": customer,
			"restaurant": restaurant,
			"reason": "Welcome Bonus"
		})
		
		if already_rewarded:
			return False
			
		# 3. Get loyalty config
		loyalty_prog = frappe.get_doc("Restaurant Loyalty Config", {"restaurant": restaurant, "is_active": 1})
		if not loyalty_prog:
			return False
			
		# 4. Award the Welcome Bonus
		coins = loyalty_prog.new_user_welcome_reward_coins or 50
		credit_loyalty_points(
			customer=customer,
			restaurant=restaurant,
			coins=coins,
			reason="Welcome Bonus",
			ref_doctype="Referral Link",
			ref_name=link_info.name
		)
		
		frappe.db.commit()
		return True
	except Exception as e:
		frappe.log_error(f"Error in process_referral_welcome_bonus: {str(e)}")
		return False

def credit_loyalty_points(customer, restaurant, coins, reason, ref_doctype=None, ref_name=None, transaction_type="Earn"):
	"""Helper function to create a Restaurant Loyalty Entry"""
	from dinematters.dinematters.utils.loyalty import add_loyalty_coins, redeem_loyalty_coins
	if transaction_type == "Earn":
		return add_loyalty_coins(customer, restaurant, coins, reason, ref_doctype, ref_name)
	else:
		return redeem_loyalty_coins(customer, restaurant, coins, reason, ref_doctype, ref_name)


@frappe.whitelist()
@require_plan('DIAMOND')
def update_loyalty_config(restaurant_id, config, enable_loyalty=None):
	"""Update loyalty configurations for admin"""
	try:
		# Correct logging: title is first, message (config) is second
		frappe.log_error("Loyalty API Update Call", f"Updating for {restaurant_id} with config: {config}")
		
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		if isinstance(config, str):
			config = json.loads(config)
			
		# Handle Restaurant Loyalty Config record
		if frappe.db.exists("Restaurant Loyalty Config", {"restaurant": restaurant}):
			prog_name = frappe.db.get_value("Restaurant Loyalty Config", {"restaurant": restaurant}, "name")
			prog_doc = frappe.get_doc("Restaurant Loyalty Config", prog_name)
			prog_doc.update(config)
			prog_doc.save(ignore_permissions=True)
			frappe.log_error("Restaurant Loyalty Config Updated", f"Updated {prog_doc.name}")
		else:
			config["doctype"] = "Restaurant Loyalty Config"
			config["restaurant"] = restaurant
			prog_doc = frappe.get_doc(config)
			prog_doc.insert(ignore_permissions=True)
			frappe.log_error("Restaurant Loyalty Config Created", f"Created {prog_doc.name}")
		
		# Update Restaurant enable_loyalty
		if enable_loyalty is not None:
			frappe.db.set_value("Restaurant", restaurant, "enable_loyalty", 1 if enable_loyalty else 0)
			frappe.db.set_value("Restaurant Config", {"restaurant": restaurant}, "enable_loyalty", 1 if enable_loyalty else 0)
			
		frappe.db.commit()
		return {"success": True}
	except Exception as e:
		frappe.log_error("Loyalty Save Error", frappe.get_traceback())
		return {"success": False, "error": str(e)}

@frappe.whitelist()
@require_plan('DIAMOND')
def get_customer_insights(restaurant_id, search_query=None):
	"""
	Get list of customers with their points for a restaurant.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Build basic filters
		filters = {"restaurant": restaurant}
		
		# Get all customers who have ever had a loyalty entry at this restaurant
		# Or just get all customers and calculate their balance?
		# Better: Get all platform customers linked to this restaurant via orders or loyalty entries
		
		# Find customers via Restaurant Loyalty Entry
		customer_names = frappe.get_all(
			"Restaurant Loyalty Entry",
			filters={"restaurant": restaurant},
			pluck="customer",
			distinct=True
		)
		
		# Also find customers via Orders
		order_customers = frappe.get_all(
			"Order",
			filters={"restaurant": restaurant, "platform_customer": ["is", "set"]},
			pluck="platform_customer",
			distinct=True
		)
		
		all_customer_ids = list(set(customer_names + order_customers))
		
		if search_query:
			# Filter these IDs by customer name/phone
			matching_customers = frappe.get_all(
				"Customer",
				filters={
					"name": ["in", all_customer_ids],
					"or": [
						{"full_name": ["like", f"%{search_query}%"]},
						{"phone": ["like", f"%{search_query}%"]}
					]
				},
				pluck="name"
			)
			all_customer_ids = matching_customers
			
		results = []
		for cust_id in all_customer_ids:
			customer = frappe.get_doc("Customer", cust_id)
			
			# Get balance
			from dinematters.dinematters.utils.loyalty import get_loyalty_balance
			balance = get_loyalty_balance(cust_id, restaurant)
			
			# Get referral stats
			referral_stats = frappe.db.sql("""
				SELECT 
					(SELECT COUNT(*) 
					 FROM `tabReferral Visit` v 
					 JOIN `tabReferral Link` l2 ON v.referral_link = l2.name 
					 WHERE l2.referrer = %s AND l2.restaurant = %s AND v.is_unique = 1) as total_opens,
					COALESCE(SUM(rewarded_opens_in_cycle), 0) as cycle_opens
				FROM `tabReferral Link`
				WHERE referrer = %s AND restaurant = %s
			""", (cust_id, restaurant, cust_id, restaurant), as_dict=1)[0]
			
			results.append({
				"id": customer.name,
				"name": customer.customer_name or customer.name,
				"phone": customer.phone,
				"balance": balance,
				"referral_opens": int(referral_stats.total_opens or 0),
				"cycle_opens": int(referral_stats.cycle_opens or 0),
				"last_active": customer.modified
			})
			
		# Sort by balance descending
		results.sort(key=lambda x: x["balance"], reverse=True)
		
		return {"success": True, "data": results}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Insights Error")
		return {"success": False, "error": str(e)}

@frappe.whitelist()
@require_plan('DIAMOND')
def get_customer_transactions(restaurant_id, customer_id):
	"""
	Get all loyalty transactions for a specific customer and restaurant
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Get all loyalty entries for this customer at this restaurant
		transactions = frappe.get_all(
			"Restaurant Loyalty Entry",
			filters={"customer": customer_id, "restaurant": restaurant},
			fields=["transaction_type", "coins", "reason", "posting_date", "creation", "reference_doctype", "reference_name"],
			order_by="creation desc"
		)
		
		return {"success": True, "data": transactions}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Transactions Error")
		return {"success": False, "error": str(e)}

@frappe.whitelist()
@require_plan('DIAMOND')
def adjust_customer_points(restaurant_id, customer_id, coins, reason, transaction_type="Earn"):
	"""
	Manually adjust customer points (for admin use).
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		coins = cint(coins)
		
		if coins <= 0:
			return {"success": False, "error": "Coins must be greater than 0"}
			
		from dinematters.dinematters.api.loyalty import credit_loyalty_points
		credit_loyalty_points(customer_id, restaurant, coins, reason or "Manual Adjustment", transaction_type=transaction_type)
		
		return {
			"success": True, 
			"message": f"Successfully {transaction_type.lower()}ed {coins} coins"
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Adjustment Error")
		return {"success": False, "error": str(e)}
