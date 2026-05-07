# Copyright (c) 2026, DineMatters and contributors
# For license information, please see license.txt

"""
Loyalty Scheduler Tasks

  grant_birthday_bonuses — runs daily at 08:00 IST
    Finds customers whose birthday is today (month+day match), verifies they
    have order history at the restaurant, and credits birthday_bonus_coins.
    Idempotent: skips customers who already received a Birthday Bonus entry
    for the current calendar year at that restaurant.
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
		fields=["restaurant", "birthday_bonus_coins"]
	)

	from dinematters.dinematters.utils.loyalty import add_loyalty_coins

	for config in active_configs:
		restaurant = config.restaurant
		bonus_coins = int(config.birthday_bonus_coins or 100)

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
