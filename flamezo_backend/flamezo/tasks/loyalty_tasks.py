# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Loyalty Scheduler Tasks

  grant_birthday_bonuses — runs daily at 08:00 IST
    Finds verified customers whose birthday is today (month+day match) and
    credits ONE platform-wide birthday_bonus_coins (spendable at any outlet).
    Idempotent: skips customers who already received a Birthday Bonus entry
    this calendar year (at any outlet).

  send_coin_expiry_notifications — runs daily at 10:00 IST
    Finds customers with settled, non-expired Earn coins expiring within 7 days.
    Sends a single push notification per customer (deduplicated via frappe.cache).
    Idempotent: a customer who already got a nudge today is skipped.

  reset_referral_cycles_monthly — runs on the 1st of each month at 00:00 UTC
    Resets rewarded_opens_in_cycle = 0 for ALL referral links globally.
"""

import calendar

import frappe
from frappe.utils import today, getdate


def grant_birthday_bonuses():
	"""
	Daily scheduler job. Credits ONE platform-wide Birthday Bonus to every
	verified customer whose birthday is today — no outlet history needed.

	  - Once per customer per calendar year, checked across ALL outlets (so a
	    legacy per-outlet bonus earlier this year also counts).
	  - Platform-wide Cash with no outlet: spendable at any outlet.
	  - 29 Feb birthdays are credited on 28 Feb in non-leap years.
	"""
	today_date = getdate(today())
	current_year = today_date.year
	leap_day_fallback = (
		today_date.month == 2 and today_date.day == 28 and not calendar.isleap(current_year)
	)

	# Only OTP-verified (app) customers — mirrors the verified gate on order cashback.
	verified_clause = (
		"AND verified_at IS NOT NULL" if frappe.db.has_column("Customer", "verified_at") else ""
	)
	customer_ids = frappe.db.sql_list(f"""
		SELECT name
		FROM `tabCustomer`
		WHERE date_of_birth IS NOT NULL
		  {verified_clause}
		  AND (
		    (MONTH(date_of_birth) = %(month)s AND DAY(date_of_birth) = %(day)s)
		    OR (%(leap_day_fallback)s AND MONTH(date_of_birth) = 2 AND DAY(date_of_birth) = 29)
		  )
	""", {
		"month": today_date.month,
		"day": today_date.day,
		"leap_day_fallback": 1 if leap_day_fallback else 0,
	})

	if not customer_ids:
		return

	already_granted = set(frappe.db.sql_list("""
		SELECT DISTINCT customer
		FROM `tabOutlet Loyalty Entry`
		WHERE reason = 'Birthday Bonus'
		  AND transaction_type = 'Earn'
		  AND YEAR(posting_date) = %s
		  AND customer IN ({placeholders})
	""".format(placeholders=",".join(["%s"] * len(customer_ids))),
		tuple([current_year] + customer_ids)
	))

	from flamezo_backend.flamezo.utils.loyalty import add_platform_coins
	from flamezo_backend.flamezo.utils.platform_config import get_birthday_bonus_coins

	bonus_coins = get_birthday_bonus_coins()

	for customer_id in customer_ids:
		if customer_id in already_granted:
			continue
		try:
			add_platform_coins(
				customer=customer_id,
				coins=bonus_coins,
				reason="Birthday Bonus"
			)
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(
				f"Birthday bonus error for customer {customer_id}: {str(e)}",
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
		FROM `tabOutlet Loyalty Entry`
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
			FROM `tabOutlet Loyalty Entry`
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
			body = f"₹{balance} Cash expires today. Use it on your next bill!"
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


def _do_reset_referral_cycles():
	"""Execute the actual DB reset. Separated so tests can call it directly."""
	frappe.db.sql("UPDATE `tabReferral Link` SET rewarded_opens_in_cycle = 0")
	frappe.db.commit()


def reset_referral_cycles_monthly():
	"""
	Monthly job: resets rewarded_opens_in_cycle = 0 for all Referral Links.

	Cron fires at 18:30 UTC on days 28–31 (= 00:00 IST on those dates).
	Guard: only execute on the last calendar day of the month in IST so the
	reset happens exactly at midnight IST on the 1st — closing the 5.5-hour
	exploit window that UTC midnight left open for India-timezone users.
	"""
	import calendar
	from datetime import datetime, timezone, timedelta

	IST = timezone(timedelta(hours=5, minutes=30))
	now_ist = datetime.now(IST)
	last_day = calendar.monthrange(now_ist.year, now_ist.month)[1]
	if now_ist.day != last_day:
		return  # Not the last day of the month in IST — skip

	try:
		_do_reset_referral_cycles()
	except Exception as e:
		frappe.log_error(f"Monthly referral cycle reset failed: {str(e)}", "Referral Cycle Reset")
