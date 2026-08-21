# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Hot Drops Scheduler Tasks

  nudge_before_lunch_rush — runs daily at 10:30 IST (lunch rush starts ~12:30)
  nudge_before_dinner_rush — runs daily at 17:30 IST (dinner rush starts ~19:30,
    Fri/Sat get an extra "weekend" line in the copy)

Busy restaurant owners won't reliably remember to open the app and post a
Hot Drop on their own — a proactive nudge right before a real traffic window
is what actually drives adoption of a self-serve growth feature like this.
Deliberately NOT a "traffic prediction model" — these are honest, simple,
fixed meal-time heuristics (dining/cafe only, the industries a "rush" even
applies to), not a fabricated ML system.

Only nudges outlets that:
  - are dining/cafe (industries a meal-time rush window is relevant to)
  - are active
  - have ZERO active/upcoming Hot Drop right now (never spam a merchant
    who's already using the feature)
  - have at least one registered merchant push token

Idempotent: a per-outlet, per-window, per-day dedup key in Redis so a
re-run of the scheduler (or a manual trigger) never double-sends.
"""

import json
import frappe
from frappe.utils import now_datetime, today

from flamezo_backend.flamezo.api.push_notifications import _send_fcm_message

RUSH_OUTLET_TYPES = ("dining", "cafe")


def _eligible_outlets():
	"""Active dining/cafe outlets with zero active/upcoming Hot Drops and at
	least one merchant push token registered."""
	now = now_datetime()
	rows = frappe.db.sql(
		"""
		SELECT r.name, r.restaurant_name, rc.merchant_push_tokens
		FROM `tabOutlet` r
		INNER JOIN `tabRestaurant Config` rc ON rc.restaurant = r.name
		WHERE r.is_active = 1
		  AND r.outlet_type IN %(types)s
		  AND rc.merchant_push_tokens IS NOT NULL
		  AND rc.merchant_push_tokens != ''
		  AND rc.merchant_push_tokens != '[]'
		  AND NOT EXISTS (
		    SELECT 1 FROM `tabHot Drop` hd
		    WHERE hd.restaurant = r.name AND hd.is_active = 1 AND hd.ends_at > %(now)s
		  )
		""",
		{"types": RUSH_OUTLET_TYPES, "now": now},
		as_dict=True,
	)
	return rows


def _send_nudge(window_key, title, body):
	dedup_key = f"hotdrops_nudge:{window_key}:{today()}"
	outlets = _eligible_outlets()
	sent = 0
	for r in outlets:
		outlet_dedup = f"{dedup_key}:{r.name}"
		if frappe.cache().get_value(outlet_dedup):
			continue
		try:
			tokens = json.loads(r.merchant_push_tokens or "[]")
		except Exception:
			continue
		if not tokens:
			continue

		stale_tokens = []
		for tok in tokens:
			result = _send_fcm_message(
				fcm_token=tok, title=title, body=body,
				data={"type": "hot_drop_nudge", "outlet_id": r.name},
				icon="/assets/flamezo_backend/logo-192.png",
			)
			if result == "unregistered":
				stale_tokens.append(tok)

		if stale_tokens:
			clean = [t for t in tokens if t not in stale_tokens]
			frappe.db.set_value("Restaurant Config", {"restaurant": r.name}, "merchant_push_tokens", json.dumps(clean))
			frappe.db.commit()

		frappe.cache().set_value(outlet_dedup, "1", expires_in_sec=6 * 3600)
		sent += 1

	return sent


def nudge_before_lunch_rush():
	sent = _send_nudge(
		"lunch",
		"🔥 Lunch rush starts in 2 hours",
		"Post a Hot Drop now and be the first thing hungry customers see today.",
	)
	if sent:
		frappe.logger().info(f"Hot Drops lunch nudge sent to {sent} outlets")


def nudge_before_dinner_rush():
	is_weekend_eve = now_datetime().weekday() in (4, 5)  # Fri, Sat
	body = (
		"Weekend dinner rush starts in 2 hours — this is your biggest window. Post a Hot Drop now."
		if is_weekend_eve
		else "Dinner rush starts in 2 hours. Post a Hot Drop now and get seen first tonight."
	)
	sent = _send_nudge("dinner", "🔥 Dinner rush starts in 2 hours", body)
	if sent:
		frappe.logger().info(f"Hot Drops dinner nudge sent to {sent} outlets")
