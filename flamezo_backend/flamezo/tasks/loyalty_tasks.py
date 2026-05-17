# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Loyalty Scheduler Tasks

  grant_birthday_bonuses — runs daily at 08:00 IST
    Finds customers whose birthday is today (month+day match), verifies they
    have order history at the restaurant, and credits birthday_bonus_coins.
    Idempotent: skips customers who already received a Birthday Bonus entry
    for the current calendar year at that restaurant.

  send_coin_expiry_notifications — runs daily at 10:00 IST
    Finds customers with settled, non-expired Earn coins expiring within 7 days.
    Sends a single push notification per customer (deduplicated via frappe.cache).
    Idempotent: a customer who already got a nudge today is skipped.

  reset_referral_cycles_monthly — runs on the 1st of each month at 00:00 UTC
    Resets rewarded_opens_in_cycle = 0 for ALL referral links globally.
"""

import frappe
from frappe.utils import today, getdate


def grant_birthday_bonuses():
	"""
	Daily scheduler job. Awards birthday bonus coins to all customers whose
	birthday is today at every restaurant with an active loyalty program.
	Only grants to customers who have prior order/loyalty history at the restaurant.
	"""
	today_date = getdate(today())
	today_month = today_date.month
	today_day = today_date.day
	current_year = today_date.year

	# Find all customers whose birth month+day matches today
	birthday_customers = frappe.db.sql("""
		SELECT name
		FROM `tabCustomer`
		WHERE date_of_birth IS NOT NULL
		  AND MONTH(date_of_birth) = %s
		  AND DAY(date_of_birth) = %s
	""", (today_month, today_day), as_dict=True)

	if not birthday_customers:
		return

	customer_ids = [c.name for c in birthday_customers]

	# Get all active loyalty programs
	active_configs = frappe.get_all(
		"Restaurant Loyalty Config",
		filters={"is_active": 1},
		fields=["restaurant"]
	)

	from flamezo_backend.flamezo.utils.loyalty import add_loyalty_coins
	from flamezo_backend.flamezo.utils.platform_config import get_birthday_bonus_coins

	for config in active_configs:
		restaurant = config.restaurant
		plan = frappe.db.get_value("Restaurant", restaurant, "plan_type") or "SILVER"
		bonus_coins = get_birthday_bonus_coins(plan)  # GOLD=100, SILVER=50

		if not frappe.db.get_value("Restaurant", restaurant, "enable_loyalty"):
			continue

		# Build set of customers who already got a birthday bonus this year at this restaurant
		already_granted_rows = frappe.db.sql("""
			SELECT DISTINCT customer
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s
			  AND reason = 'Birthday Bonus'
			  AND YEAR(posting_date) = %s
			  AND customer IN ({placeholders})
		""".format(placeholders=",".join(["%s"] * len(customer_ids))),
			tuple([restaurant, current_year] + customer_ids),
			as_dict=True
		)
		already_granted = {r.customer for r in already_granted_rows}

		# Build set of customers who have loyalty history at this restaurant
		has_history_rows = frappe.db.sql("""
			SELECT DISTINCT customer
			FROM `tabRestaurant Loyalty Entry`
			WHERE restaurant = %s
			  AND customer IN ({placeholders})
		""".format(placeholders=",".join(["%s"] * len(customer_ids))),
			tuple([restaurant] + customer_ids),
			as_dict=True
		)
		has_history = {r.customer for r in has_history_rows}

		eligible = [c for c in customer_ids if c in has_history and c not in already_granted]

		for customer_id in eligible:
			try:
				add_loyalty_coins(
					customer=customer_id,
					restaurant=restaurant,
					coins=bonus_coins,
					reason="Birthday Bonus"
				)
				frappe.db.commit()
			except Exception as e:
				frappe.log_error(
					f"Birthday bonus error for customer {customer_id} at {restaurant}: {str(e)}",
					"Birthday Bonus Task"
				)


def send_coin_expiry_notifications():
	"""
	Daily scheduler job (runs at 10:00 IST).
	Sends a push notification to customers whose loyalty coins expire within 7 days.

	Rules:
	  - Only considers settled Earn entries that are not yet expired
	  - Aggregates net balance per customer — skips if net balance is 0 (already spent)
	  - One nudge per customer per day (deduplicated via cache key)
	  - Only notifies customers who have push_fcm_tokens registered
	"""
	from frappe.utils import today, add_days, getdate

	today_date = getdate(today())
	window_end = add_days(today_date, 7)

	# Find customers with coins expiring within 7 days (settled, non-expired)
	expiry_rows = frappe.db.sql("""
		SELECT DISTINCT customer
		FROM `tabRestaurant Loyalty Entry`
		WHERE transaction_type = 'Earn'
		  AND is_settled = 1
		  AND expiry_date IS NOT NULL
		  AND expiry_date >= %s
		  AND expiry_date <= %s
	""", (str(today_date), str(window_end)), as_dict=True)

	if not expiry_rows:
		return

	customer_ids = [r.customer for r in expiry_rows]

	# Fetch only customers who have FCM tokens registered
	push_rows = frappe.db.sql("""
		SELECT name, push_fcm_tokens
		FROM `tabCustomer`
		WHERE name IN ({placeholders})
		  AND push_fcm_tokens IS NOT NULL
		  AND push_fcm_tokens != '[]'
		  AND push_fcm_tokens != ''
	""".format(placeholders=",".join(["%s"] * len(customer_ids))),
		tuple(customer_ids), as_dict=True)

	if not push_rows:
		return

	from flamezo_backend.flamezo.utils.loyalty import get_loyalty_balance
	from flamezo_backend.flamezo.api.push_notifications import _send_fcm_message
	import json

	for row in push_rows:
		customer_id = row.name

		# Deduplicate: skip if we already sent a nudge to this customer today
		cache_key = f"dm_expiry_nudge:{customer_id}:{str(today_date)}"
		if frappe.cache().get_value(cache_key):
			continue

		# Check they actually have a non-zero balance to redeem
		balance = get_loyalty_balance(customer_id)
		if balance <= 0:
			continue

		# Find the earliest expiry date for this customer's coins in the window
		earliest = frappe.db.sql("""
			SELECT MIN(expiry_date) AS earliest_expiry
			FROM `tabRestaurant Loyalty Entry`
			WHERE customer = %s
			  AND transaction_type = 'Earn'
			  AND is_settled = 1
			  AND expiry_date IS NOT NULL
			  AND expiry_date >= %s
			  AND expiry_date <= %s
		""", (customer_id, str(today_date), str(window_end)), as_dict=True)

		days_left = 7
		if earliest and earliest[0].earliest_expiry:
			exp_date = getdate(earliest[0].earliest_expiry)
			if exp_date is not None and today_date is not None:
				days_left = (exp_date - today_date).days

		# Parse FCM tokens
		try:
			tokens = json.loads(row.push_fcm_tokens or "[]")
		except Exception:
			tokens = []

		if not tokens:
			continue

		title = "Your Flamezo Cash is expiring soon!"
		if days_left == 0:
			body = f"₹{balance} Cash expires today. Use it on your next order!"
		elif days_left == 1:
			body = f"₹{balance} Cash expires tomorrow. Don't let it go to waste!"
		else:
			body = f"₹{balance} Cash expires in {days_left} days. Use it before it's gone!"

		sent = False
		stale_tokens = []
		for token in tokens:
			result = _send_fcm_message(
				fcm_token=token,
				title=title,
				body=body,
				data={"type": "loyalty_expiry", "balance": str(balance), "days_left": str(days_left)},
				icon="/assets/flamezo_backend/logo-192.png"
			)
			if result == "unregistered":
				stale_tokens.append(token)
			elif result:
				sent = True

		# Clean up stale tokens
		if stale_tokens:
			try:
				clean = [t for t in tokens if t not in stale_tokens]
				frappe.db.set_value("Customer", customer_id, "push_fcm_tokens", json.dumps(clean))
			except Exception:
				pass

		if sent:
			# Mark as nudged for today — 25h TTL to avoid DST edge cases
			frappe.cache().set_value(cache_key, 1, expires_in_sec=25 * 3600)

	try:
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Expiry notification commit error: {str(e)}", "Expiry Notifications")


def reset_referral_cycles_monthly():
	"""
	Monthly scheduler job (runs on 1st of each month at 00:00 UTC).
	Resets rewarded_opens_in_cycle = 0 for ALL referral links globally.

	Replaces the old per-order reset_referral_cycle() approach which allowed
	frequent orderers to bypass the 10-referral cap by placing orders often.
	Time-based reset is the industry standard (Swiggy, MagicPin model).
	"""
	try:
		frappe.db.sql("UPDATE `tabReferral Link` SET rewarded_opens_in_cycle = 0")
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Monthly referral cycle reset failed: {str(e)}", "Referral Cycle Reset")
