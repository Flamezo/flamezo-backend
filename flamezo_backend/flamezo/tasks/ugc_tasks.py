# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
UGC Cashback background tasks
=============================
- send_ugc_whatsapp     : transactional WhatsApp notifications (enqueued per event)
- send_proof_reminders  : hourly cron — nudge diners to upload their view-count
                          proof (max 2 reminders) and expire stale claims.
"""

import frappe
from frappe.utils import now_datetime, get_datetime, add_to_date, cint

from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_message


def _restaurant_name(restaurant):
	return frappe.db.get_value("Restaurant", restaurant, "restaurant_name") or "the restaurant"


def _customer_phone(customer):
	return frappe.db.get_value("Customer", customer, "phone")


def _claim_link(sub):
	"""Best-effort deep link to the diner's claim page. Empty if no web URL configured."""
	base = frappe.conf.get("customer_web_url")
	if not base:
		return ""
	slug = frappe.db.get_value("Restaurant", sub.restaurant, "restaurant_id") or sub.restaurant
	return f"\n\n{base.rstrip('/')}/ugc-claim?r={slug}&order={sub.order}"


def send_ugc_whatsapp(submission_name, kind):
	"""Send a single transactional WhatsApp message for a submission event."""
	try:
		sub = frappe.get_doc("UGC Story Submission", submission_name)
	except frappe.DoesNotExistError:
		return

	phone = _customer_phone(sub.customer)
	if not phone:
		return
	rname = _restaurant_name(sub.restaurant)

	messages = {
		"story_verified": (
			f"✅ Your story for {rname} is verified! Tomorrow, upload a quick screen "
			f"recording of your story's view count to claim your cashback." + _claim_link(sub)
		),
		"story_rejected": (
			f"Your story submission for {rname} couldn't be verified. "
			f"Please make sure it was posted exactly as shown and try again."
		),
		"proof_reminder": (
			f"⏰ Don't miss your cashback from {rname}! Upload a screen recording of your "
			f"Instagram/Facebook story views to claim it." + _claim_link(sub)
		),
		"cashback_credited": (
			f"🎉 Cashback credited! {cint(sub.cashback_coins)} Cash from {rname} is now in "
			f"your Flamezo wallet — use it on your next order."
		),
		"proof_rejected": (
			f"Your cashback claim at {rname} couldn't be approved. "
			f"Reach out to the restaurant if you think this was a mistake."
		),
	}
	message = messages.get(kind)
	if not message:
		return

	try:
		send_whatsapp_message(phone, message)
	except Exception as e:
		frappe.log_error(f"send_ugc_whatsapp({kind}) for {submission_name}: {e}", "UGC")


def send_proof_reminders():
	"""
	Hourly cron. Two responsibilities:
	  1. Nudge diners whose story is verified but who haven't uploaded proof yet
	     (up to 2 reminders, spaced ≥10h, starting ≥20h after verification).
	  2. Expire claims whose proof window has fully elapsed.
	"""
	now = now_datetime()

	# ── 1. Reminders ─────────────────────────────────────────────────────────
	pending = frappe.get_all(
		"UGC Story Submission",
		filters={"status": "story_verified", "reminder_count": ["<", 2]},
		fields=["name", "restaurant", "customer", "story_verified_at", "last_reminder_at", "reminder_count"],
		limit_page_length=500,
	)
	for row in pending:
		if not row.story_verified_at:
			continue
		hours_since_verify = (now - get_datetime(row.story_verified_at)).total_seconds() / 3600
		if hours_since_verify < 20:
			continue
		if row.last_reminder_at:
			hours_since_last = (now - get_datetime(row.last_reminder_at)).total_seconds() / 3600
			if hours_since_last < 10:
				continue
		try:
			send_ugc_whatsapp(row.name, "proof_reminder")
			frappe.db.set_value("UGC Story Submission", row.name, {
				"reminder_count": cint(row.reminder_count) + 1,
				"last_reminder_at": now,
			}, update_modified=False)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"UGC reminder for {row.name}: {e}", "UGC")

	# ── 2. Expiry sweep ──────────────────────────────────────────────────────
	# Default window 48h; read per-restaurant config where present.
	open_claims = frappe.get_all(
		"UGC Story Submission",
		filters={"status": ["in", ("offer_shown", "story_shared", "story_verified")]},
		fields=["name", "restaurant", "submission_date"],
		limit_page_length=1000,
	)
	window_cache = {}
	for row in open_claims:
		if not row.submission_date:
			continue
		if row.restaurant not in window_cache:
			window_cache[row.restaurant] = cint(frappe.db.get_value(
				"UGC Cashback Config", {"restaurant": row.restaurant}, "proof_window_hours"
			)) or 48
		deadline = add_to_date(get_datetime(row.submission_date), hours=window_cache[row.restaurant])
		if now > deadline:
			try:
				frappe.db.set_value("UGC Story Submission", row.name, "status", "expired", update_modified=False)
				frappe.db.commit()
			except Exception as e:
				frappe.log_error(f"UGC expiry for {row.name}: {e}", "UGC")
