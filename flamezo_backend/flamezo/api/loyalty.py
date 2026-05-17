# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime, get_datetime_str
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.feature_gate import require_plan
from flamezo_backend.flamezo.utils.customer_helpers import (
	normalize_phone,
	get_or_create_customer,
	get_customer_token,
	validate_customer_session,
	mask_name,
	mask_phone
)
from flamezo_backend.flamezo.utils.platform_config import (
	PLATFORM_LOYALTY,
	get_welcome_reward_coins,
	get_referral_share_coins,
	get_max_opens_rewarded_per_share,
	get_tier_threshold,
)
import json
import random
import string

# ── Per-restaurant guardrails removed ────────────────────────────────────────
# Flamezo now operates a fully centralized loyalty model.
# All earn/redeem rates are fixed platform-wide in utils/platform_config.py.
# Restaurants only control whether loyalty is enabled or disabled.
# LOYALTY_GUARDRAILS and validate_loyalty_config() are no longer needed.


@frappe.whitelist(allow_guest=True)
@require_plan('SILVER', 'GOLD')
def get_loyalty_summary(restaurant_id, phone):
	"""
	GET /api/method/flamezo_backend.flamezo.api.loyalty.get_loyalty_summary
	Get customer's loyalty balance and history for a specific restaurant
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}
		
		# Production Auth Gate
		session_token = get_customer_token()
		if not session_token or not validate_customer_session(normalized_phone, session_token):
			return {"success": False, "error": {"code": "SECURE_SESSION_INVALID", "message": "Authentication required"}}
		
		customer = get_or_create_customer(normalized_phone)
		
		# Get all point entries (Global History)
		entries = frappe.get_all(
			"Restaurant Loyalty Entry",
			filters={"customer": customer.name},
			fields=["transaction_type", "coins", "reason", "posting_date", "reference_doctype", "reference_name", "creation", "is_settled", "restaurant"],
			order_by="creation desc"
		)
		
		from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance, get_loyalty_tier
		# Centralized Balance (Sums all restaurants)
		balance = get_loyalty_balance(customer.name)
		pending_balance = get_loyalty_balance(customer.name, include_pending=True) - balance
		
		# Tier is also calculated globally based on total lifetime spend/coins
		tier = get_loyalty_tier(customer.name)
		
		# Expiring soon (within 30 days) - Global check
		from frappe.utils import add_days, today
		expiring_soon_filters = {
			"customer": customer.name,
			"is_settled": 1,
			"transaction_type": "Earn",
			"expiry_date": ["between", [today(), add_days(today(), 30)]]
		}
		expiring_soon_entries = frappe.get_all("Restaurant Loyalty Entry", filters=expiring_soon_filters, fields=["coins"])
		gross_expiring = sum(e.coins for e in expiring_soon_entries)
		expiring_soon_balance = min(gross_expiring, balance)
		
		lifetime_coins = sum(e.coins for e in entries if e.transaction_type == 'Earn' and e.is_settled == 1)
		
		return {
			"success": True,
			"data": {
				"balance": balance,
				"pending_balance": pending_balance,
				"expiring_soon_balance": expiring_soon_balance,
				"lifetime_coins": lifetime_coins,
				"tier": tier,
				"transactions": entries
			}
		}
	except Exception as e:
		frappe.log_error(f"Error in get_loyalty_summary: {str(e)}")
		return {"success": False, "error": {"code": "LOYALTY_FETCH_ERROR", "message": str(e)}}

@frappe.whitelist(allow_guest=True)
def get_loyalty_config(restaurant_id):
	"""
	Get loyalty configuration for the cart and admin.
	All earn/redeem rates are now Flamezo platform constants — uniform across
	the entire network. Only enable_loyalty and program metadata come from the
	per-restaurant doc.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		
		# Check if loyalty is enabled for this restaurant
		is_enabled = frappe.db.get_value("Restaurant", restaurant, "enable_loyalty")
		if not is_enabled:
			return {"success": True, "data": None}

		# Try to fetch non-rate fields from the restaurant doc if it exists
		restaurant_doc_config = frappe.db.get_value(
			"Restaurant Loyalty Config",
			{"restaurant": restaurant},
			["program_name", "earn_on_status"],
			as_dict=True
		) or {}

		# Plan-aware rates
		from flamezo_backend.flamezo.utils.platform_config import (
			get_earn_percentage, get_max_coins_per_order, get_max_redemption_percent,
			get_expiry_months, get_birthday_bonus_coins,
		)
		plan = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"
		is_gold = plan == "GOLD"

		# Build config: plan-tiered platform constants + program metadata
		config = {
			"program_name":                 restaurant_doc_config.get("program_name") or "Flamezo Rewards",
			"earn_on_status":               restaurant_doc_config.get("earn_on_status") or "Completed",
			"plan_type":                    plan,
			"is_gold":                      is_gold,
			# ── Plan-tiered rates ─────────────────────────────────────────────────
			"earn_type":                    PLATFORM_LOYALTY["earn_type"],
			"earn_percentage":              get_earn_percentage(plan),          # 7% GOLD / 5% SILVER
			"max_coins_per_order":          get_max_coins_per_order(plan),      # 700 / 500
			"max_redemption_percent":       get_max_redemption_percent(plan),   # 30% / 20%
			"loyalty_expiry_months":        get_expiry_months(plan),            # 6 (GOLD) / 3 (SILVER)
			"birthday_bonus_coins":         get_birthday_bonus_coins(plan),     # 100 / 50
			# ── Plan-independent constants ────────────────────────────────────────
			"coin_value_in_inr":            PLATFORM_LOYALTY["coin_value_in_inr"],
			"min_order_to_earn":            PLATFORM_LOYALTY["min_order_to_earn"],
			"min_redemption_threshold":     PLATFORM_LOYALTY["min_redemption_threshold"],
			"min_billing_for_redemption":   PLATFORM_LOYALTY["min_billing_for_redemption"],
			"new_user_welcome_reward_coins":PLATFORM_LOYALTY.get("welcome_reward_coins", 50),
			"coins_per_unique_open":        PLATFORM_LOYALTY.get("referral_share_coins", 30),
			"max_opens_rewarded_per_share": PLATFORM_LOYALTY.get("max_opens_rewarded_per_share", 10),
			"tier_silver_threshold":        get_tier_threshold("silver"),
			"tier_gold_threshold":          get_tier_threshold("gold"),
			"tier_platinum_threshold":      get_tier_threshold("platinum"),
		}

		# Add current restaurant's city
		restaurant_info = frappe.db.get_value("Restaurant", restaurant, ["city", "address", "company"], as_dict=True)
		config["city"] = restaurant_info.city or "Surat"

		# Fetch other outlets (Real + Mock)
		filters = {"is_active": 1, "enable_loyalty": 1, "name": ["!=", restaurant]}
		if restaurant_info.company:
			filters["company"] = restaurant_info.company
		else:
			filters["city"] = restaurant_info.city

		other_outlets = frappe.get_all(
			"Restaurant",
			filters=filters,
			fields=["restaurant_id as id", "restaurant_name as name", "logo as imageSrc", "address", "city"],
			limit=5
		)

		# Add Mock Data if needed
		mock_outlets = [
			{
				"id": "mock-1",
				"name": "The Spice Route",
				"imageSrc": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800&q=80",
				"address": "Vesu Canal Rd, Surat",
				"cuisine": "Continental · Italian",
				"service": "Dine-in · Delivery",
				"offerBanner": "60% OFF up to ₹120",
				"offers": ["60% OFF up to ₹120", "Free Delivery above ₹499", "Flat ₹50 Cashback"],
				"loyaltyBanner": "Earn 50 Cash",
				"rating": 4.4,
				"isNew": True
			},
			{
				"id": "mock-2",
				"name": "Sky High Lounge",
				"imageSrc": "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=800&q=80",
				"address": "Adajan Gam, Surat",
				"cuisine": "Multi-cuisine · Bar",
				"service": "Table booking · Live Music",
				"offerBanner": "Flat ₹100 OFF",
				"offers": ["Flat ₹100 OFF", "10% Cashback on first order", "Free Beer on groups of 4+"],
				"loyaltyBanner": "10% Cash Back",
				"rating": 4.1
			},
			{
				"id": "mock-3",
				"name": "Coastal Cravings",
				"imageSrc": "https://images.unsplash.com/photo-1534422298391-e4f8c170db76?w=800&q=80",
				"address": "Dumas Road, Surat",
				"cuisine": "Seafood · Coastal",
				"service": "Dine-in · Takeaway",
				"offerBanner": "Free Dessert on Orders",
				"offers": ["Free Dessert on Orders", "Buy 2 Get 1 Free on Prawns", "Earn 2X Cash on Weekends"],
				"loyaltyBanner": "Earn 30 Cash",
				"rating": 4.6
			},
			{
				"id": "mock-4",
				"name": "The Artisan Bakery",
				"imageSrc": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=800&q=80",
				"address": "City Light, Surat",
				"cuisine": "Bakery · Desserts",
				"service": "Takeaway · Delivery",
				"offerBanner": "Buy 1 Get 1 Free",
				"offers": ["Buy 1 Get 1 Free", "Fresh Bakes @ 50% OFF after 9PM", "Free Cookie on Every Order"],
				"loyaltyBanner": "5% Cash Back",
				"rating": 4.5
			},
			{
				"id": "mock-5",
				"name": "Zen Garden Sushi",
				"imageSrc": "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=800&q=80",
				"address": "Piplod, Surat",
				"cuisine": "Japanese · Sushi",
				"service": "Dine-in · Table booking",
				"offerBanner": "20% OFF Special Rolls",
				"offers": ["20% OFF Special Rolls", "Free Miso Soup on Weekdays", "Sake Tasting Event this Friday"],
				"loyaltyBanner": "Earn 100 Cash",
				"rating": 4.3,
				"isNew": True
			},
			{
				"id": "mock-6",
				"name": "The Rustic Grill",
				"imageSrc": "https://images.unsplash.com/photo-1544025162-d76694265947?w=800&q=80",
				"address": "VIP Road, Surat",
				"cuisine": "BBQ · Steaks",
				"service": "Dine-in · Live Sports",
				"offerBanner": "Flat 15% OFF",
				"offers": ["Flat 15% OFF", "Unlimited BBQ Night - Wed", "Earn 100 Cash on ₹1000+"],
				"loyaltyBanner": "Premium Rewards",
				"rating": 4.2
			}
		]
		
		# Merge real and mock for now
		config["other_outlets"] = other_outlets + mock_outlets

		return {"success": True, "data": config}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Get Config Error")
		return {"success": False, "error": str(e)}

@frappe.whitelist(allow_guest=True)
@require_plan('SILVER', 'GOLD')
def generate_referral_link(restaurant_id, phone, platform="WhatsApp"):
	"""
	POST /api/method/flamezo_backend.flamezo.api.loyalty.generate_referral_link
	Generate or get a unique referral link for a customer
	"""
	try:
		# Simple Rate Limiting
		cache_key = f"referral_gen_limit:{phone}:{restaurant_id}"
		if frappe.cache().get_value(cache_key):
			return {"success": False, "error": {"code": "RATE_LIMIT", "message": "Please wait a moment before generating another link"}}
		frappe.cache().set_value(cache_key, 1, expires_in_sec=5)

		restaurant = validate_restaurant_for_api(restaurant_id)
		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}
			
		# Production Auth Gate
		session_token = get_customer_token()
		if not session_token or not validate_customer_session(normalized_phone, session_token):
			return {"success": False, "error": {"code": "SECURE_SESSION_INVALID", "message": "Authentication required"}}
		
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
		
		from flamezo_backend.flamezo.utils.config_helpers import get_app_base_url
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
	POST /api/method/flamezo_backend.flamezo.api.loyalty.track_referral_visit
	Track a visit to a referral link. ONLY records the visit — no coins awarded here.
	Coins are awarded in claim_referral_reward() after phone verification.
	"""
	try:
		# Auto-detect IP and User agent if not passed (Production Level Tracking)
		try:
			if not ip_address and frappe.request:
				ip_address = frappe.request.remote_addr
		except Exception:
			pass
		try:
			if not user_agent and frappe.request:
				user_agent = frappe.request.headers.get('User-Agent')
		except Exception:
			pass

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
		try:
			visit_doc.insert(ignore_permissions=True)
			frappe.db.commit() # Ensure visit is saved immediately
		except Exception as insert_err:
			# If DB unique constraint fires (concurrent duplicate request from same IP),
			# treat this visit as non-unique — no problem.
			err_str = str(insert_err).lower()
			if "duplicate" in err_str or "unique" in err_str:
				is_unique = False
				frappe.db.rollback()
			else:
				raise

		# NOTE: No coins awarded here. Rewards are deferred to claim_referral_reward()
		# which fires after the referee verifies their phone number. This prevents
		# bot/spam abuse where fake link clicks farm referrer coins.

		return {
			"success": True,
			"data": {
				"restaurant_id": link_doc.restaurant,
				"referral_id": identifier,
				"is_unique": is_unique
			}
		}
	except Exception as e:
		frappe.log_error("Referral Tracking Error", str(e))
		return {"success": False, "error": {"code": "TRACKING_ERROR", "message": str(e)}}


@frappe.whitelist(allow_guest=True)
@require_plan('SILVER', 'GOLD')
def claim_referral_reward(restaurant_id, referral_id, phone):
	"""
	POST /api/method/flamezo_backend.flamezo.api.loyalty.claim_referral_reward
	Called after phone verification to atomically award:
	  1. Welcome Bonus to the referee (new user)
	  2. Referral Share to the referrer (if within cycle limit)
	This is the fraud-safe approach — no coins until identity is verified.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return {"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid phone number"}}

		# Auth gate — must have a valid session (post-OTP)
		session_token = get_customer_token()
		if not session_token or not validate_customer_session(normalized_phone, session_token):
			return {"success": False, "error": {"code": "SECURE_SESSION_INVALID", "message": "Authentication required"}}

		# 1. Validate the referral link belongs to this restaurant
		link_info = frappe.db.get_value(
			"Referral Link",
			{"identifier": referral_id},
			["name", "referrer", "restaurant", "rewarded_opens_in_cycle"],
			as_dict=True
		)
		if not link_info:
			return {"success": False, "error": {"code": "LINK_NOT_FOUND", "message": "Invalid referral link"}}

		if link_info.restaurant != restaurant:
			return {"success": False, "error": {"code": "RESTAURANT_MISMATCH", "message": "Referral link does not belong to this restaurant"}}

		# 2. Get or create the referee customer
		referee = get_or_create_customer(normalized_phone)

		# 3. Bot detection: reject accounts created in the last 60 seconds (script abuse)
		from frappe.utils import now_datetime, get_datetime
		age_seconds = (now_datetime() - get_datetime(referee.creation)).total_seconds()
		if age_seconds < 60:
			return {"success": False, "error": {"code": "ACCOUNT_TOO_NEW", "message": "Please try again in a moment"}}

		# 4. Global idempotency: one Welcome Bonus per phone number ever, across all restaurants
		already_rewarded = frappe.db.exists("Restaurant Loyalty Entry", {
			"customer": referee.name,
			"reason": "Welcome Bonus"
			# No "restaurant" filter — global check
		})
		if already_rewarded:
			return {"success": False, "error": {"code": "ALREADY_CLAIMED", "message": "Welcome bonus already claimed"}}

		# 5. Prevent self-referral
		if link_info.referrer == referee.name:
			return {"success": False, "error": {"code": "SELF_REFERRAL", "message": "Cannot use your own referral link"}}

		# 6. Use platform-fixed reward values (no per-restaurant config needed)
		welcome_coins        = get_welcome_reward_coins()           # ₹75 platform standard
		referral_share_coins = get_referral_share_coins()           # ₹40 per verified open
		max_limit            = get_max_opens_rewarded_per_share()   # 10 per cycle
		current_cycle = int(frappe.db.get_value("Referral Link", link_info.name, "rewarded_opens_in_cycle") or 0)

		# 7. Award Welcome Bonus to referee
		credit_loyalty_points(
			customer=referee.name,
			restaurant=restaurant,
			coins=welcome_coins,
			reason="Welcome Bonus",
			ref_doctype="Referral Link",
			ref_name=link_info.name
		)

		# 8. Award Referral Share to referrer (if within cycle limit)
		referrer_coins_awarded = 0
		if current_cycle < max_limit:
			credit_loyalty_points(
				customer=link_info.referrer,
				restaurant=restaurant,
				coins=referral_share_coins,
				reason="Referral Share",
				ref_doctype="Referral Link",
				ref_name=link_info.name
			)
			referrer_coins_awarded = referral_share_coins
			frappe.db.set_value("Referral Link", link_info.name, "rewarded_opens_in_cycle", current_cycle + 1)

		# 9. Mark referral visit as converted (best-effort, not blocking)
		try:
			frappe.db.sql("""
				UPDATE `tabReferral Visit`
				SET status = 'Converted'
				WHERE referral_link = %s AND status != 'Converted'
				ORDER BY creation DESC LIMIT 1
			""", (link_info.name,))
		except Exception:
			pass

		frappe.db.commit()
		return {
			"success": True,
			"data": {
				"welcome_coins": welcome_coins,
				"referrer_coins": referrer_coins_awarded
			}
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Claim Referral Reward Error")
		return {"success": False, "error": {"code": "CLAIM_ERROR", "message": str(e)}}

@frappe.whitelist(allow_guest=True)
def get_referral_details(identifier):
	"""
	GET /api/method/flamezo_backend.flamezo.api.loyalty.get_referral_details
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
		
		# Get welcome coins from platform config (source of truth)
		welcome_coins = get_welcome_reward_coins()
		
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
				"banner": banner,
				"welcome_coins": welcome_coins
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
			
		# 2. Global idempotency: one Welcome Bonus per phone number ever, across all restaurants
		already_rewarded = frappe.db.exists("Restaurant Loyalty Entry", {
			"customer": customer,
			"reason": "Welcome Bonus"
			# No "restaurant" filter — global check prevents multi-restaurant bonus farming
		})
		
		if already_rewarded:
			return False
			
		# 3. Ensure an active loyalty config exists for this restaurant
		if not frappe.db.get_value("Restaurant Loyalty Config", {"restaurant": restaurant, "is_active": 1}, "name"):
			return False

		# 4. Award the Welcome Bonus (always platform value — not per-restaurant config)
		coins = get_welcome_reward_coins()
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
	from flamezo_backend.flamezo.utils.loyalty import add_loyalty_coins, redeem_loyalty_coins
	if transaction_type == "Earn":
		return add_loyalty_coins(customer, restaurant, coins, reason, ref_doctype, ref_name)
	else:
		return redeem_loyalty_coins(customer, restaurant, coins, reason, ref_doctype, ref_name)


@frappe.whitelist()
@require_plan('SILVER', 'GOLD')
def update_loyalty_config(restaurant_id, config, enable_loyalty=None):
	"""
	Update loyalty settings for a restaurant.
	In the centralized model, restaurants can ONLY toggle loyalty on/off.
	All earn/redeem rates are platform-fixed and ignored if passed.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		if isinstance(config, str):
			config = json.loads(config)

		# ── Strip all earn/redeem fields — platform owns these now ───────────────
		# Even if a restaurant somehow passes these fields, they are ignored.
		_LOCKED_FIELDS = {
			"earn_type", "earn_percentage", "earn_flat_coins", "points_per_inr",
			"min_order_to_earn", "max_coins_per_order", "coin_value_in_inr",
			"min_billing_for_redemption", "min_redemption_threshold",
			"loyalty_expiry_months", "share_reward_coins", "birthday_bonus_coins",
			"referral_order_reward_coins", "new_user_welcome_reward_coins",
			"coins_per_unique_open", "max_opens_rewarded_per_share",
			"welcome_coupon_discount",
			"tier_silver_threshold", "tier_gold_threshold", "tier_platinum_threshold",
		}
		for field in _LOCKED_FIELDS:
			config.pop(field, None)

		# ── Write back plan-tiered platform constants into the doc ───────────────
		from flamezo_backend.flamezo.utils.platform_config import (
			get_earn_percentage, get_expiry_months,
		)
		plan = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"
		config["earn_type"]       = PLATFORM_LOYALTY["earn_type"]
		config["earn_percentage"] = get_earn_percentage(plan)
		config["points_per_inr"]  = round(get_earn_percentage(plan) / 100, 4)
		config["coin_value_in_inr"] = PLATFORM_LOYALTY["coin_value_in_inr"]

		# ── Save the config document ─────────────────────────────────────────────
		if frappe.db.exists("Restaurant Loyalty Config", {"restaurant": restaurant}):
			prog_name = frappe.db.get_value("Restaurant Loyalty Config", {"restaurant": restaurant}, "name")
			prog_doc = frappe.get_doc("Restaurant Loyalty Config", prog_name)
			prog_doc.update(config)
			prog_doc.save(ignore_permissions=True)
		else:
			config["doctype"]   = "Restaurant Loyalty Config"
			config["restaurant"]= restaurant
			if not config.get("program_name"):
				config["program_name"] = "Flamezo Rewards"
			prog_doc = frappe.get_doc(config)
			prog_doc.insert(ignore_permissions=True)

		# ── Update master enable_loyalty toggle ──────────────────────────────────
		if enable_loyalty is not None:
			enabled = 1 if enable_loyalty else 0
			plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"

			frappe.db.set_value("Restaurant", restaurant, "enable_loyalty", enabled)
			frappe.db.set_value("Restaurant Config", {"restaurant": restaurant}, "enable_loyalty", enabled)

			# For Silver restaurants: loyalty and ordering are tied together.
			# Disabling loyalty also disables ordering and Club listing.
			# Gold restaurants always have ordering regardless of loyalty toggle.
			if plan_type == "SILVER":
				frappe.db.set_value("Restaurant", restaurant, {
					"no_ordering": 0 if enabled else 1,
				})

		frappe.db.commit()
		return {"success": True}
	except Exception as e:
		frappe.log_error("Loyalty Save Error", frappe.get_traceback())
		return {"success": False, "error": str(e)}

@frappe.whitelist()
@require_plan('SILVER', 'GOLD')
def get_customer_insights(restaurant_id, search_query=None):
	"""
	Get list of customers with their points for a restaurant.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)

		# Get all customers who have ever had a loyalty entry at this restaurant
		# or placed an order, then compute all metrics in bulk SQL (no N+1).
		
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

		if not all_customer_ids:
			return {"success": True, "data": []}

		if search_query:
			# Filter these IDs by customer name/phone
			matching_customers = frappe.get_all(
				"Customer",
				filters={
					"name": ["in", all_customer_ids],
					"or": [
						{"customer_name": ["like", f"%{search_query}%"]},
						{"phone": ["like", f"%{search_query}%"]}
					]
				},
				pluck="name"
			)
			all_customer_ids = matching_customers

		if not all_customer_ids:
			return {"success": True, "data": []}

		placeholders = ",".join(["%s"] * len(all_customer_ids))

		# ── Single SQL: net spendable balance per customer ────────────────────────
		balance_rows = frappe.db.sql(f"""
			SELECT
				customer,
				GREATEST(0, SUM(
					CASE
						WHEN transaction_type = 'Earn'
						 AND is_settled = 1
						 AND (expiry_date IS NULL OR expiry_date >= CURDATE())
						THEN coins
						WHEN transaction_type = 'Redeem'
						 AND is_settled = 1
						 AND (expiry_date IS NULL OR expiry_date >= CURDATE())
						THEN -coins
						ELSE 0
					END
				)) AS net_balance
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s AND customer IN ({placeholders})
			GROUP BY customer
		""", tuple([restaurant] + all_customer_ids), as_dict=True)
		balance_map = {r.customer: int(r.net_balance or 0) for r in balance_rows}

		# ── Single SQL: lifetime Earn coins per customer (for tier) ───────────────
		lifetime_rows = frappe.db.sql(f"""
			SELECT customer, COALESCE(SUM(coins), 0) AS lifetime_coins
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s AND customer IN ({placeholders}) AND transaction_type = 'Earn'
			GROUP BY customer
		""", tuple([restaurant] + all_customer_ids), as_dict=True)
		lifetime_map = {r.customer: int(r.lifetime_coins or 0) for r in lifetime_rows}

		# ── Single SQL: referral stats for all customers ──────────────────────────
		referral_rows = frappe.db.sql(f"""
			SELECT
				l.referrer,
				COALESCE(SUM(l.rewarded_opens_in_cycle), 0) AS cycle_opens,
				COALESCE(SUM(v_counts.unique_opens), 0) AS total_opens
			FROM `tabReferral Link` l
			LEFT JOIN (
				SELECT referral_link, COUNT(*) AS unique_opens
				FROM `tabReferral Visit`
				WHERE is_unique = 1
				GROUP BY referral_link
			) v_counts ON v_counts.referral_link = l.name
			WHERE l.restaurant = %s AND l.referrer IN ({placeholders})
			GROUP BY l.referrer
		""", tuple([restaurant] + all_customer_ids), as_dict=True)
		referral_map = {r.referrer: r for r in referral_rows}

		# ── Bulk fetch customer fields ─────────────────────────────────────────────
		customer_docs = frappe.get_all(
			"Customer",
			filters={"name": ["in", all_customer_ids]},
			fields=["name", "customer_name", "phone", "date_of_birth", "modified"]
		)

		# ── Tier thresholds (single config fetch) ─────────────────────────────────
		from flamezo_backend.flamezo.utils.loyalty import get_loyalty_tier
		tier_config = frappe.db.get_value(
			"Restaurant Loyalty Config",
			{"restaurant": restaurant, "is_active": 1},
			["tier_silver_threshold", "tier_gold_threshold", "tier_platinum_threshold"],
			as_dict=True
		) or {}
		silver_t = int(tier_config.get("tier_silver_threshold") or 500)
		gold_t   = int(tier_config.get("tier_gold_threshold") or 2000)
		plat_t   = int(tier_config.get("tier_platinum_threshold") or 5000)

		def _tier_from_lifetime(lt):
			if lt >= plat_t:   return "Platinum"
			if lt >= gold_t:   return "Gold"
			if lt >= silver_t: return "Silver"
			return "Bronze"

		plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type")
		is_gold = plan_type == "GOLD"
		is_admin = "System Manager" in frappe.get_roles() or "Supervisor" in frappe.get_roles()

		results = []
		for c in customer_docs:
			cid = c.name
			balance = balance_map.get(cid, 0)
			lifetime = lifetime_map.get(cid, 0)
			ref = referral_map.get(cid, frappe._dict(total_opens=0, cycle_opens=0))
			
			is_unlocked = is_gold or frappe.db.exists("Customer Data Unlock", {"restaurant": restaurant, "customer": cid})
			
			phone = c.phone
			display_phone = phone if is_unlocked else mask_phone(phone)
			display_name = c.customer_name or cid
			if not is_unlocked:
				display_name = mask_name(display_name)

			results.append({
				"id": cid,
				"name": display_name,
				"phone": display_phone,
				"birthday": str(c.date_of_birth) if c.date_of_birth and is_unlocked else "********",
				"balance": balance,
				"tier": _tier_from_lifetime(lifetime),
				"lifetime_coins": lifetime,
				"referral_opens": int(ref.total_opens or 0),
				"cycle_opens": int(ref.cycle_opens or 0),
				"last_active": c.modified,
				"is_unlocked": is_unlocked
			})

		# Sort by balance descending
		results.sort(key=lambda x: x["balance"], reverse=True)

		return {"success": True, "data": results}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Insights Error")
		return {"success": False, "error": str(e)}

@frappe.whitelist()
@require_plan('SILVER', 'GOLD')
def get_customer_transactions(restaurant_id, customer_id):
	"""
	Get all loyalty transactions for a specific customer and restaurant
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		
		# Check if unlocked for non-GOLD restaurants
		plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type")
		is_gold = plan_type == "GOLD"
		is_admin = "System Manager" in frappe.get_roles() or "Supervisor" in frappe.get_roles()
		is_unlocked = is_admin or is_gold or frappe.db.exists("Customer Data Unlock", {"restaurant": restaurant, "customer": customer_id})

		if not is_unlocked:
			return {"success": False, "error": "Access denied. Please unlock customer profile first."}

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
@require_plan('SILVER', 'GOLD')
def get_loyalty_analytics(restaurant_id):
	"""
	Merchant loyalty analytics dashboard.
	Returns programme-level KPIs in a single API call — no N+1 queries.

	Metrics returned:
	  summary     — total_coins_issued, total_coins_redeemed, active_customers,
	                customers_expiring_soon (within 7 days), redemption_rate_percent,
	                avg_balance, daily_redemption_cap_utilization_today
	  earn_by_reason — breakdown of Earn coins by reason (Order, Welcome Bonus, etc.)
	  top_earners  — top 5 customers by lifetime coins (masked if Silver plan)
	  expiring_soon — list of customers with coins expiring ≤7 days (for operator action)
	  daily_trend  — last 30 days of daily earn + redeem volumes
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		plan_type = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"
		is_gold = plan_type == "GOLD"

		from frappe.utils import today, add_days, getdate
		today_str = today()
		window_end = str(add_days(today_str, 7))
		thirty_days_ago = str(add_days(today_str, -30))

		# ── 1. Programme-level summary ─────────────────────────────────────────────
		summary_row = frappe.db.sql("""
			SELECT
				COALESCE(SUM(CASE WHEN transaction_type = 'Earn'   AND is_settled = 1 THEN coins ELSE 0 END), 0) AS total_issued,
				COALESCE(SUM(CASE WHEN transaction_type = 'Redeem' AND is_settled = 1 THEN coins ELSE 0 END), 0) AS total_redeemed,
				COUNT(DISTINCT CASE WHEN transaction_type = 'Earn' AND is_settled = 1 THEN customer END)          AS active_customers
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s
		""", (restaurant,), as_dict=True)[0]

		total_issued   = int(summary_row.total_issued or 0)
		total_redeemed = int(summary_row.total_redeemed or 0)
		active_customers = int(summary_row.active_customers or 0)
		redemption_rate = round((total_redeemed / total_issued * 100) if total_issued else 0, 1)

		# Customers with coins expiring ≤7 days (and positive net balance)
		expiring_rows = frappe.db.sql("""
			SELECT
				e.customer,
				MIN(e.expiry_date) AS earliest_expiry,
				GREATEST(0, SUM(
					CASE
						WHEN e.transaction_type = 'Earn'   AND e.is_settled = 1
						 AND (e.expiry_date IS NULL OR e.expiry_date >= CURDATE()) THEN  e.coins
						WHEN e.transaction_type = 'Redeem' AND e.is_settled = 1   THEN -e.coins
						ELSE 0
					END
				)) AS net_balance
			FROM `tabRestaurant Loyalty Entry` e
			WHERE e.restaurant = %s
			  AND EXISTS (
				SELECT 1 FROM `tabRestaurant Loyalty Entry` x
				WHERE x.restaurant = e.restaurant
				  AND x.customer  = e.customer
				  AND x.transaction_type = 'Earn'
				  AND x.is_settled = 1
				  AND x.expiry_date IS NOT NULL
				  AND x.expiry_date >= %s
				  AND x.expiry_date <= %s
			  )
			GROUP BY e.customer
			HAVING net_balance > 0
			ORDER BY earliest_expiry ASC
			LIMIT 50
		""", (restaurant, today_str, window_end), as_dict=True)

		customers_expiring_soon = len(expiring_rows)

		# Average wallet balance across all customers with any balance
		avg_row = frappe.db.sql("""
			SELECT COALESCE(AVG(net_bal), 0) AS avg_balance FROM (
				SELECT customer,
					GREATEST(0, SUM(
						CASE
							WHEN transaction_type = 'Earn'   AND is_settled = 1
							 AND (expiry_date IS NULL OR expiry_date >= CURDATE()) THEN  coins
							WHEN transaction_type = 'Redeem' AND is_settled = 1   THEN -coins
							ELSE 0
						END
					)) AS net_bal
				FROM `tabRestaurant Loyalty Entry`
				WHERE restaurant = %s
				GROUP BY customer
				HAVING net_bal > 0
			) t
		""", (restaurant,), as_dict=True)
		avg_balance = round(float(avg_row[0].avg_balance or 0), 1) if avg_row else 0.0

		# Today's total redemptions across the whole restaurant (all customers)
		today_redeem_row = frappe.db.sql("""
			SELECT COALESCE(SUM(coins), 0) AS today_redeemed
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s
			  AND transaction_type = 'Redeem'
			  AND reason = 'Redemption'
			  AND posting_date = CURDATE()
		""", (restaurant,), as_dict=True)
		today_redeemed_total = int(today_redeem_row[0].today_redeemed or 0) if today_redeem_row else 0

		# ── 2. Earn breakdown by reason ────────────────────────────────────────────
		reason_rows = frappe.db.sql("""
			SELECT reason, COALESCE(SUM(coins), 0) AS total_coins, COUNT(*) AS count
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s AND transaction_type = 'Earn' AND is_settled = 1
			GROUP BY reason
			ORDER BY total_coins DESC
		""", (restaurant,), as_dict=True)
		earn_by_reason = [
			{"reason": r.reason, "total_coins": int(r.total_coins), "count": int(r.count)}
			for r in reason_rows
		]

		# ── 3. Top 5 earners (lifetime coins) ─────────────────────────────────────
		top_rows = frappe.db.sql("""
			SELECT customer, SUM(coins) AS lifetime_coins
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s AND transaction_type = 'Earn' AND is_settled = 1
			GROUP BY customer
			ORDER BY lifetime_coins DESC
			LIMIT 5
		""", (restaurant,), as_dict=True)

		top_earner_ids = [r.customer for r in top_rows]
		customer_names_map = {}
		if top_earner_ids:
			name_rows = frappe.get_all(
				"Customer",
				filters={"name": ["in", top_earner_ids]},
				fields=["name", "customer_name", "phone"]
			)
			customer_names_map = {c.name: c for c in name_rows}

		top_earners = []
		for r in top_rows:
			c = customer_names_map.get(r.customer, frappe._dict())
			display_name = c.get("customer_name") or r.customer
			display_phone = c.get("phone") or ""
			if not is_gold:
				display_name  = mask_name(display_name)
				display_phone = mask_phone(display_phone)
			top_earners.append({
				"customer": r.customer,
				"name": display_name,
				"phone": display_phone,
				"lifetime_coins": int(r.lifetime_coins or 0),
			})

		# ── 4. Expiring soon customer list (for operator action) ───────────────────
		expiring_customer_ids = [r.customer for r in expiring_rows]
		exp_name_map = {}
		if expiring_customer_ids:
			exp_name_rows = frappe.get_all(
				"Customer",
				filters={"name": ["in", expiring_customer_ids]},
				fields=["name", "customer_name", "phone"]
			)
			exp_name_map = {c.name: c for c in exp_name_rows}

		expiring_list = []
		for r in expiring_rows[:20]:   # cap UI list at 20
			c = exp_name_map.get(r.customer, frappe._dict())
			display_name  = c.get("customer_name") or r.customer
			display_phone = c.get("phone") or ""
			if not is_gold:
				display_name  = mask_name(display_name)
				display_phone = mask_phone(display_phone)
			expiring_list.append({
				"customer": r.customer,
				"name": display_name,
				"phone": display_phone,
				"net_balance": int(r.net_balance or 0),
				"earliest_expiry": str(r.earliest_expiry) if r.earliest_expiry else None,
			})

		# ── 5. Daily trend — last 30 days ─────────────────────────────────────────
		trend_rows = frappe.db.sql("""
			SELECT
				posting_date,
				COALESCE(SUM(CASE WHEN transaction_type = 'Earn'   THEN coins ELSE 0 END), 0) AS earned,
				COALESCE(SUM(CASE WHEN transaction_type = 'Redeem' THEN coins ELSE 0 END), 0) AS redeemed
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s
			  AND is_settled = 1
			  AND posting_date >= %s
			GROUP BY posting_date
			ORDER BY posting_date ASC
		""", (restaurant, thirty_days_ago), as_dict=True)

		daily_trend = [
			{
				"date":     str(r.posting_date),
				"earned":   int(r.earned or 0),
				"redeemed": int(r.redeemed or 0),
			}
			for r in trend_rows
		]

		return {
			"success": True,
			"data": {
				"summary": {
					"total_coins_issued":           total_issued,
					"total_coins_redeemed":         total_redeemed,
					"active_customers":             active_customers,
					"customers_expiring_soon":      customers_expiring_soon,
					"redemption_rate_percent":      redemption_rate,
					"avg_balance":                  avg_balance,
					"today_redeemed_restaurant":    today_redeemed_total,
				},
				"earn_by_reason":    earn_by_reason,
				"top_earners":       top_earners,
				"expiring_soon":     expiring_list,
				"daily_trend":       daily_trend,
			}
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Analytics Error")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
@require_plan('GOLD')
def adjust_customer_points(restaurant_id, customer_id, coins, reason, transaction_type="Earn"):
	"""
	Manually adjust customer points (for admin use).
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id, frappe.session.user)
		coins = cint(coins)

		if coins <= 0:
			return {"success": False, "error": "Coins must be greater than 0"}

		max_adjustment: int = PLATFORM_LOYALTY.get("max_manual_adjustment_coins", 500)  # type: ignore[assignment]
		if coins > max_adjustment:
			return {"success": False, "error": f"Max single adjustment is ₹{max_adjustment} coins. Split into multiple if needed."}

		credit_loyalty_points(customer_id, restaurant, coins, reason or "Manual Adjustment", transaction_type=transaction_type)
		
		return {
			"success": True, 
			"message": f"Successfully {transaction_type.lower()}ed {coins} coins"
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Loyalty Adjustment Error")
		return {"success": False, "error": str(e)}
