import frappe
from frappe import _
from frappe.utils import flt, cint, today, add_months, add_days, getdate
from flamezo_backend.flamezo.utils.platform_config import (
	get_earn_percentage,
	get_max_coins_per_order,
	get_min_order_to_earn,
	get_min_redemption_threshold,
	get_expiry_days,
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
	curr_today = getdate(today())
	for entry in entries:
		if entry.transaction_type == "Earn":
			# Only count Earn entries that haven't expired
			if not entry.expiry_date or getdate(entry.expiry_date) >= curr_today:
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

	# Daily redemption cap enforcement
	if reason != "Cancellation Revert":
		from flamezo_backend.flamezo.utils.platform_config import PLATFORM_LOYALTY
		max_daily_cap = int(PLATFORM_LOYALTY.get("max_daily_redemption_inr", 500))

		today_redemptions = frappe.db.get_all(
			"Restaurant Loyalty Entry",
			filters={
				"customer": customer,
				"transaction_type": "Redeem",
				"reason": ["!=", "Cancellation Revert"],
				"posting_date": today()
			},
			fields=["coins"]
		)
		today_total = sum(r.coins for r in today_redemptions)
		remaining_cap = max_daily_cap - today_total
		if remaining_cap <= 0:
			frappe.throw(_("You've reached your daily Cash redemption limit (₹{0}/day). Try again tomorrow.").format(max_daily_cap))
		if coins > remaining_cap:
			frappe.log_error(
				f"Loyalty daily cap clamp: requested {coins}, remaining cap {remaining_cap}, customer {customer}",
				"Loyalty Cap Clip"
			)
			coins = remaining_cap

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

def earn_loyalty_coins(customer, restaurant, amount_paid, reason="Order", ref_doctype=None,
                       ref_name=None, payment_method=None, settle_immediately=False, description=None):
	"""
	Calculate and credit loyalty coins using Flamezo platform-fixed rates.
	All earn logic is centralized — restaurants cannot override these values.

	Platform rules (from utils/platform_config.py):
	  - Earn rate:        platform constant (see get_earn_percentage)
	  - Min order:        ₹100
	  - Max per order:    platform cap
	  - Expiry:           platform constant

	Order-sourced cashback is gated behind BOTH:
	  1. payment_method == 'pay_online'  (cash-on-counter earns 0), and
	  2. an OTP-verified customer        (unverified earns 0).

	settle_immediately: when True the entry is created is_settled=1 (spendable
	right away). The online-payment flow passes this once Razorpay has CAPTURED
	the payment (verify_payment → process_loyalty_and_coupons), so verified
	online payers get their cashback instantly. Other paths (order created but
	payment not yet captured) leave it pending and settle on order completion.
	"""
	if not customer or not restaurant or not amount_paid or amount_paid <= 0:
		return 0

	if not is_loyalty_enabled(restaurant):
		return 0

	# Order-sourced earning is online-only AND verified-only. Non-order earns
	# (welcome bonus, referral, manual adjustment) bypass this — no payment.
	if ref_doctype == "Order":
		normalized_pm = (payment_method or "").strip().lower()
		if normalized_pm != "pay_online":
			return 0
		# Backend-enforced verification gate (not just the frontend UI gate):
		# instant cashback is only awarded to OTP-verified customers.
		if not frappe.db.get_value("Customer", customer, "verified_at"):
			return 0

	# ── Platform-Constant Rates (no DB read for earn config) ──────────────────
	min_order    = get_min_order_to_earn()     # ₹100
	max_cap      = get_max_coins_per_order()   # 700
	expiry_days  = get_expiry_days()           # 30

	# ── Minimum Order Check ───────────────────────────────────────────────────
	if min_order > 0 and flt(amount_paid) < min_order:
		return 0  # Order doesn't qualify

	# ── Coin Calculation (7% earn rate) ───────────────────────────────────────
	rate = get_earn_percentage() / 100
	coins_earned = int(flt(amount_paid) * rate)
	coins_earned = min(coins_earned, max_cap)  # Hard cap

	if coins_earned <= 0:
		return 0

	expiry_date = add_days(today(), expiry_days)

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
		# Non-order earns are always settled. Order earns settle instantly only
		# when the caller confirms payment is captured (settle_immediately).
		"is_settled": 1 if (settle_immediately or ref_doctype != "Order") else 0,
		"description": description,
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


def reverse_earned_cashback(customer, restaurant, coins_to_reverse, reason="Refund Reversal",
                            description=None, ref_doctype="Order", ref_name=None, refund_id=None):
	"""
	Claw back previously-earned cashback (e.g. on a refund), using the
	"deduct available + log owed" policy:

	  - Deduct min(available_balance, coins_to_reverse) as a Redeem entry so the
	    visible balance never goes negative (it floors at 0).
	  - If the user already spent some of the instant cashback, the shortfall is
	    recorded in `owed_coins` (+ noted in the description) for finance/audit.

	Idempotent per (order, refund_id): a second webhook delivery for the same
	refund is a no-op. Returns {"deducted", "owed"} or None if nothing to do.
	"""
	coins_to_reverse = int(coins_to_reverse or 0)
	if not customer or not restaurant or coins_to_reverse <= 0:
		return None

	# Stable idempotency marker stamped into the entry's description by THIS
	# function (not the caller), so a webhook retry for the same refund is a
	# no-op regardless of how the caller wrote the description.
	marker = f"[refund:{refund_id}]" if refund_id else None

	if ref_name:
		existing = frappe.get_all(
			"Restaurant Loyalty Entry",
			filters={
				"customer": customer,
				"reference_doctype": ref_doctype,
				"reference_name": ref_name,
				"transaction_type": "Redeem",
				"reason": ["in", ["Refund Reversal", "Cancellation Revert"]],
			},
			fields=["name", "description"],
		)
		for e in existing:
			# refund-scoped: same refund id already reversed.
			# cancellation-scoped (no refund_id): any prior reversal blocks a repeat.
			if marker is None or (e.description and marker in e.description):
				return None

	available = get_loyalty_balance(customer)
	deducted = min(available, coins_to_reverse)
	owed = coins_to_reverse - deducted

	stored_desc = description or ""
	if marker and marker not in stored_desc:
		stored_desc = f"{stored_desc} {marker}".strip()

	entry = frappe.get_doc({
		"doctype": "Restaurant Loyalty Entry",
		"customer": customer,
		"restaurant": restaurant,
		"coins": int(deducted),
		"transaction_type": "Redeem",
		"reason": reason,
		"reference_doctype": ref_doctype,
		"reference_name": ref_name,
		"posting_date": today(),
		"is_settled": 1,
		"owed_coins": int(owed),
		"description": stored_desc or None,
	})
	entry.insert(ignore_permissions=True)
	return {"deducted": int(deducted), "owed": int(owed)}


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
	expiry_days = get_expiry_days()  # 30
	expiry_date = add_days(today(), expiry_days)
		
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

	# 2. Revert Earned Coins (full reversal — cancellation/full-refund).
	# Uses the deduct-available + log-owed policy so an already-spent instant
	# cashback doesn't push the balance negative; the shortfall is recorded.
	if doc.coins_earned > 0:
		refunded = (getattr(doc, "payment_status", "") or "").lower() == "refunded"
		reason = "Refund Reversal" if refunded else "Cancellation Revert"
		verb = "refunded" if refunded else "cancelled"
		reverse_earned_cashback(
			customer=doc.platform_customer,
			restaurant=doc.restaurant,
			coins_to_reverse=int(doc.coins_earned or 0),
			reason=reason,
			description=f"Order {doc.name} {verb} — ₹{int(doc.coins_earned or 0)} cashback reversed",
			ref_doctype="Order",
			ref_name=doc.name,
		)

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
			"UGC Cashback":     f"🎉 Your story cashback is in! {coins} Cash added to your wallet from {restaurant_name}.",
			"Manual Adjustment": f"You've received {coins} coins at {restaurant_name}.",
		}

		body  = REASON_MESSAGES.get(reason, f"You earned {coins} coins at {restaurant_name}!")
		# Urgency: Cash is short-lived now — always remind them of the window.
		body += f" Use it within {get_expiry_days()} days."
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


def process_referral_cashback_on_order(order_doc):
	"""
	Called on every completed order. If the order's customer was referred by
	someone, credits the referrer with:
	  • ₹50 flat on the referee's first completed order
	  • 1% of subsequent orders (up to 15 more orders)
	Total capped at ₹500 per referred customer.

	Safe to call multiple times — idempotent via Customer Referral counters.
	"""
	from flamezo_backend.flamezo.utils.platform_config import (
		get_referral_flat_first_order,
		get_referral_cashback_percent,
		get_referral_cashback_orders,
		get_referral_max_cashback,
	)

	try:
		referee = getattr(order_doc, "loyalty_customer", None) or getattr(order_doc, "customer_name", None)
		if not referee:
			return

		# Find active Customer Referral for this referee
		ref_doc_name = frappe.db.get_value(
			"Customer Referral",
			{"referee": referee, "status": "active"},
			"name"
		)
		if not ref_doc_name:
			return

		ref_doc = frappe.get_doc("Customer Referral", ref_doc_name)
		referrer = ref_doc.referrer

		flat_coins      = get_referral_flat_first_order()     # 50
		cashback_pct    = get_referral_cashback_percent()     # 1.0
		max_orders      = get_referral_cashback_orders()      # 15
		cap             = get_referral_max_cashback()         # 500
		already_earned  = float(ref_doc.cashback_total or 0)
		remaining_cap   = cap - already_earned

		if remaining_cap <= 0:
			frappe.db.set_value("Customer Referral", ref_doc_name, "status", "completed")
			return

		coins_to_credit = 0
		reason = ""

		# --- First order: flat ₹50 ---
		if not ref_doc.first_order_credited:
			coins_to_credit = min(flat_coins, remaining_cap)
			reason = "Referral Flat Bonus"
			frappe.db.set_value("Customer Referral", ref_doc_name, "first_order_credited", 1)

		# --- Subsequent orders: 1% cashback (up to 15 orders) ---
		elif ref_doc.orders_credited <= max_orders:
			order_total = float(getattr(order_doc, "total", 0) or 0)
			raw = round(order_total * cashback_pct / 100, 2)
			coins_to_credit = min(int(raw), int(remaining_cap))
			reason = "Referral Cashback"

		if coins_to_credit <= 0:
			return

		# Determine which restaurant to use for the loyalty entry
		# Use the restaurant from the order so the cross-network context is accurate
		restaurant = getattr(order_doc, "restaurant", None) or getattr(order_doc, "restaurant_id", None)
		if not restaurant:
			return

		add_loyalty_coins(
			customer=referrer,
			restaurant=restaurant,
			coins=coins_to_credit,
			reason=reason,
			ref_doctype="Customer Referral",
			ref_name=ref_doc_name,
		)

		# Update counters
		new_orders  = int(ref_doc.orders_credited or 0) + 1
		new_total   = already_earned + coins_to_credit
		new_status  = "completed" if (new_orders > max_orders or new_total >= cap) else "active"

		frappe.db.set_value("Customer Referral", ref_doc_name, {
			"orders_credited": new_orders,
			"cashback_total":  new_total,
			"status":          new_status,
		}, update_modified=False)

		# Notify referrer
		frappe.enqueue(
			"flamezo_backend.flamezo.utils.loyalty.send_coin_credit_push",
			customer=referrer,
			restaurant=restaurant,
			coins=coins_to_credit,
			reason=reason,
			queue="short",
		)

	except Exception as e:
		frappe.log_error(
			f"process_referral_cashback_on_order failed for order {getattr(order_doc, 'name', '?')}: {e}",
			"Referral Cashback Error"
		)
