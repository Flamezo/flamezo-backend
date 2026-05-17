import frappe
from frappe import _
from frappe.utils import flt, cint, today, add_months
from flamezo_backend.flamezo.utils.platform_config import (
	get_earn_percentage,
	get_max_coins_per_order,
	get_min_order_to_earn,
	get_min_redemption_threshold,
	get_expiry_months,
)

def is_loyalty_enabled(restaurant):
	"""Check if loyalty is enabled for a restaurant."""
	if not restaurant:
		return False
	return frappe.db.get_value("Restaurant", restaurant, "enable_loyalty")

def get_loyalty_balance(customer, restaurant=None, include_pending=False):
	"""
	Calculate current loyalty coin balance for a customer.
	Now centralized: Sums all entries across all restaurants if restaurant is None.
	Filters by is_settled=1 and expiry_date >= today for Earn entries.
	"""
	if not customer:
		return 0
		
	filters = {"customer": customer}
	if restaurant:
		# If restaurant is provided, we can still filter if needed, 
		# but for the universal wallet, we usually want the global sum.
		# For now, let's keep the option but default to global if restaurant is None.
		filters["restaurant"] = restaurant

	if not include_pending:
		filters["is_settled"] = 1

	entries = frappe.get_all(
		"Restaurant Loyalty Entry",
		filters=filters,
		fields=["transaction_type", "coins", "expiry_date"]
	)
	
	balance = 0
	curr_today = today()
	for entry in entries:
		if entry.transaction_type == "Earn":
			# Only count Earn entries that haven't expired
			if not entry.expiry_date or entry.expiry_date >= curr_today:
				balance += entry.coins
		else:
			# Redemptions always deduct from balance
			balance -= entry.coins

	return max(0, balance)

def redeem_loyalty_coins(customer, restaurant, coins, reason="Redemption", ref_doctype=None, ref_name=None):
	"""
	Deduct coins from customer's loyalty balance.
	Returns the created entry document or None.
	"""
	if not customer or not restaurant or not coins or coins <= 0:
		return None
	
	# Verify balance
	if not is_loyalty_enabled(restaurant):
		return None
		
	# Use global balance for redemption (Universal Wallet)
	include_pending = reason == "Cancellation Revert"
	balance = get_loyalty_balance(customer, include_pending=include_pending)
	
	if coins > balance:
		frappe.log_error(
			f"Loyalty redeem clipped: requested {coins}, available balance {balance}, customer {customer}, restaurant {restaurant}",
			"Loyalty Clip Warning"
		)
		coins = balance

	if coins <= 0:
		return 0

	entry = frappe.get_doc({
		"doctype": "Restaurant Loyalty Entry",
		"customer": customer,
		"restaurant": restaurant,
		"coins": int(coins),
		"transaction_type": "Redeem",
		"reason": reason,
		"reference_doctype": ref_doctype,
		"reference_name": ref_name,
		"posting_date": today()
	})
	entry.insert(ignore_permissions=True)
	# We don't commit here to allow the caller to manage the transaction
	return int(coins)

def earn_loyalty_coins(customer, restaurant, amount_paid, reason="Order", ref_doctype=None, ref_name=None):
	"""
	Calculate and credit loyalty coins using Flamezo platform-fixed rates.
	All earn logic is centralized — restaurants cannot override these values.

	Platform rules (from utils/platform_config.py):
	  - Earn rate:        10% of bill
	  - Min order:        ₹100
	  - Max per order:    ₹1000
	  - Expiry:           6 months

	Sets is_settled=0 initially if reference is an Order (settled on completion).
	"""
	if not customer or not restaurant or not amount_paid or amount_paid <= 0:
		return 0

	if not is_loyalty_enabled(restaurant):
		return 0

	# ── Platform-Constant Rates (no DB read for earn config) ──────────────────
	plan_type    = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"
	min_order    = get_min_order_to_earn()     # ₹100
	max_cap      = get_max_coins_per_order(plan_type)
	expiry_months = get_expiry_months()        # 6

	# ── Minimum Order Check ───────────────────────────────────────────────────
	if min_order > 0 and flt(amount_paid) < min_order:
		return 0  # Order doesn't qualify

	# ── Coin Calculation: tiered by plan (7% GOLD / 5% SILVER) ──────────────
	rate = get_earn_percentage(plan_type) / 100
	coins_earned = int(flt(amount_paid) * rate)
	coins_earned = min(coins_earned, max_cap)  # Hard cap

	if coins_earned <= 0:
		return 0

	expiry_date = add_months(today(), expiry_months)

	entry = frappe.get_doc({
		"doctype": "Restaurant Loyalty Entry",
		"customer": customer,
		"restaurant": restaurant,
		"coins": coins_earned,
		"transaction_type": "Earn",
		"reason": reason,
		"reference_doctype": ref_doctype,
		"reference_name": ref_name,
		"posting_date": today(),
		"expiry_date": expiry_date,
		"is_settled": 0 if ref_doctype == "Order" else 1
	})
	entry.insert(ignore_permissions=True)

	# Update Order doc if reference is an Order
	if ref_doctype == "Order" and ref_name:
		frappe.db.set_value("Order", ref_name, "coins_earned", coins_earned)

	# Push notification — only for settled entries (pending not yet spendable)
	if entry.is_settled:
		frappe.enqueue(
			"flamezo_backend.flamezo.utils.loyalty.send_coin_credit_push",
			customer=customer, restaurant=restaurant, coins=coins_earned, reason=reason,
			queue="short", timeout=30
		)

	return coins_earned


def add_loyalty_coins(customer, restaurant, coins, reason, ref_doctype=None, ref_name=None):
	"""
	General purpose function to add a fixed number of loyalty coins (welcome, referral, etc.).
	Expiry is always the platform-standard 12 months.
	"""
	if not customer or not restaurant or not coins or coins <= 0:
		return 0

	if not is_loyalty_enabled(restaurant):
		return 0

	# Always use platform-standard expiry — no per-restaurant override
	expiry_months = get_expiry_months()  # 6
	expiry_date = add_months(today(), expiry_months)
		
	entry = frappe.get_doc({
		"doctype": "Restaurant Loyalty Entry",
		"customer": customer,
		"restaurant": restaurant,
		"coins": int(coins),
		"transaction_type": "Earn",
		"reason": reason,
		"reference_doctype": ref_doctype,
		"reference_name": ref_name,
		"posting_date": today(),
		"expiry_date": expiry_date,
		"is_settled": 0 if ref_doctype == "Order" else 1
	})
	entry.insert(ignore_permissions=True)
	
	# Update Order doc if reference is an Order
	if ref_doctype == "Order" and ref_name:
		current_coins = frappe.db.get_value("Order", ref_name, "coins_earned") or 0
		frappe.db.set_value("Order", ref_name, "coins_earned", current_coins + int(coins))

	# Push notification for fixed-amount bonuses (always settled immediately)
	frappe.enqueue(
		"flamezo_backend.flamezo.utils.loyalty.send_coin_credit_push",
		customer=customer, restaurant=restaurant, coins=int(coins), reason=reason,
		queue="short", timeout=30
	)

	return int(coins)

def settle_loyalty_points(order_name):
	"""
	Marks all loyalty entries for a specific order as is_settled=1.
	Called when order is completed or billed.
	"""
	try:
		frappe.db.sql("""
			UPDATE `tabRestaurant Loyalty Entry`
			SET is_settled = 1
			WHERE reference_doctype = 'Order' AND reference_name = %s
		""", (order_name,))
		frappe.db.commit()
		return True
	except Exception as e:
		frappe.log_error(f"Error in settle_loyalty_points: {str(e)}")
		return False


def handle_order_cancellation(doc, method=None):
	"""
	Hook function for Order on_update.
	If status changes to 'cancelled', refund redeemed points and revert earned points.
	Uses idempotency checks based on specific reasons.
	"""
	if doc.status != 'cancelled':
		return
	
	# Only proceed if status JUST changed to cancelled (optional but safer)
	# For now, idempotency check on entry reasons is enough to handle repeated calls
	
	if not doc.platform_customer or not doc.restaurant:
		return

	# 1. Refund Redeemed Coins
	if doc.loyalty_coins_redeemed > 0:
		# Idempotency: check if refund already exists for this order
		already_refunded = frappe.db.exists("Restaurant Loyalty Entry", {
			"customer": doc.platform_customer,
			"restaurant": doc.restaurant,
			"reference_doctype": "Order",
			"reference_name": doc.name,
			"reason": "Cancellation Refund"
		})
		if not already_refunded:
			# Create the entry manually to be 100% safe (avoiding add_loyalty_coins side effects on current doc)
			entry = frappe.get_doc({
				"doctype": "Restaurant Loyalty Entry",
				"customer": doc.platform_customer,
				"restaurant": doc.restaurant,
				"coins": int(doc.loyalty_coins_redeemed or 0),
				"transaction_type": "Earn",
				"reason": "Cancellation Refund",
				"reference_doctype": "Order",
				"reference_name": doc.name,
				"posting_date": today()
			})
			entry.insert(ignore_permissions=True)
			# frappe.log_error(f"Loyalty REFUNDED {doc.loyalty_coins_redeemed} for cancelled order {doc.name}", "Loyalty")

	# 2. Revert Earned Coins
	if doc.coins_earned > 0:
		# Idempotency: check if revert already exists
		already_reverted = frappe.db.exists("Restaurant Loyalty Entry", {
			"customer": doc.platform_customer,
			"restaurant": doc.restaurant,
			"reference_doctype": "Order",
			"reference_name": doc.name,
			"reason": "Cancellation Revert"
		})
		if not already_reverted:
			redeem_loyalty_coins(
				customer=doc.platform_customer,
				restaurant=doc.restaurant,
				coins=doc.coins_earned,
				reason="Cancellation Revert",
				ref_doctype="Order",
				ref_name=doc.name
			)
			# frappe.log_error(f"Loyalty REVERTED {doc.coins_earned} for cancelled order {doc.name}", "Loyalty")

	# Final cleanup — zero both coin fields so cancelled orders don't show stale values
	frappe.db.set_value("Order", doc.name, {
		"coins_earned": 0,
		"loyalty_coins_redeemed": 0
	})

def handle_loyalty_settlement(doc, method=None):
	"""
	Hook function for Order on_update.
	Settles loyalty points when order reaches the configured status.
	"""
	if doc.status not in ["confirmed", "completed", "billed"] and doc.payment_status != "completed":
		return
	
	if not doc.restaurant:
		return

	# Get settlement status from config
	config = frappe.db.get_value("Restaurant Loyalty Config", {"restaurant": doc.restaurant, "is_active": 1}, "earn_on_status")
	settle_on = (config or "Completed").lower()
	
	current_status = str(doc.status).lower()
	
	# "billed" is a terminal billing state — always settle, same as "completed"
	# If payment is completed, we always settle regardless of order status
	if doc.payment_status == "completed" or current_status == settle_on or current_status == "billed" or (settle_on == "confirmed" and current_status in ["confirmed", "completed", "billed"]):
		settle_loyalty_points(doc.name)
		
		# Reset referral cycle so user can earn sharing rewards again
		from flamezo_backend.flamezo.api.loyalty import reset_referral_cycle
		reset_referral_cycle(doc.platform_customer, doc.restaurant)


def get_loyalty_tier(customer, restaurant=None):
	"""
	Calculate the customer's tier based on GLOBAL LIFETIME Earn coins.
	Tiers are now platform-wide Flamezo tiers.
	Thresholds: Bronze (default) → Silver (500) → Gold (2000) → Platinum (5000)
	"""
	if not customer:
		return "Bronze"

	# Calculate lifetime coins across ALL restaurants for the centralized wallet vision
	result = frappe.db.sql("""
		SELECT COALESCE(SUM(coins), 0) AS lifetime_coins
		FROM `tabRestaurant Loyalty Entry`
		WHERE customer = %s AND transaction_type = 'Earn' AND is_settled = 1
	""", (customer,), as_dict=True)

	lifetime_coins = result[0].lifetime_coins if result else 0

	# Platform-standard thresholds
	silver = 500
	gold   = 2000
	plat   = 5000

	if lifetime_coins >= plat:   return "Platinum"
	if lifetime_coins >= gold:   return "Gold"
	if lifetime_coins >= silver: return "Silver"
	return "Bronze"


def send_coin_credit_push(customer, restaurant, coins, reason):
	"""
	Sends a FCM push notification to the customer when they earn loyalty coins.
	Always runs in the background via frappe.enqueue — never blocks order flow.
	Stale/unregistered tokens are cleaned up automatically.
	"""
	try:
		import json
		raw = frappe.db.get_value("Customer", customer, "push_fcm_tokens") or "[]"
		try:
			tokens = json.loads(raw)
		except Exception:
			tokens = []

		if not tokens:
			return

		restaurant_name = frappe.db.get_value("Restaurant", restaurant, "restaurant_name") or restaurant

		REASON_MESSAGES = {
			"Order":            f"You earned {coins} coins on your order at {restaurant_name}!",
			"Welcome Bonus":    f"Welcome! You've received {coins} bonus coins at {restaurant_name}.",
			"Referral Share":   f"Someone clicked your invite link — you earned {coins} coins!",
			"Referral Order":   f"Your friend placed their first order — you earned {coins} coins!",
			"Birthday Bonus":   f"Happy Birthday! 🎂 We've gifted you {coins} coins at {restaurant_name}.",
			"Manual Adjustment": f"You've received {coins} coins at {restaurant_name}.",
		}

		body  = REASON_MESSAGES.get(reason, f"You earned {coins} coins at {restaurant_name}!")
		title = f"🪙 +{coins} Coins Earned!"

		from flamezo_backend.flamezo.api.push_notifications import _send_fcm_message
		stale = []
		for token in tokens:
			result = _send_fcm_message(
				fcm_token=token,
				title=title,
				body=body,
				data={"type": "coins_earned", "coins": str(coins), "restaurant_id": restaurant},
			)
			if result == "unregistered":
				stale.append(token)

		# Clean up expired tokens
		if stale:
			clean = [t for t in tokens if t not in stale]
			frappe.db.set_value("Customer", customer, "push_fcm_tokens", json.dumps(clean))
			frappe.db.commit()

	except Exception as e:
		frappe.log_error(f"send_coin_credit_push error for customer {customer}: {str(e)}", "Push Notifications")


def send_birthday_push(customer, restaurant, coins):
	"""Convenience wrapper used by the birthday scheduler."""
	send_coin_credit_push(customer, restaurant, coins, "Birthday Bonus")
