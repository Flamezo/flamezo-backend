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
from flamezo_backend.flamezo.utils.platform_config import get_expiry_days


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
	return f"\n\n{base.rstrip('/')}/ugc-claim?r={slug}&bill={getattr(sub, 'order', '')}"


def send_ugc_cashback_nudge(order_name):
	"""
	Enqueued 3 minutes after payment success (via frappe.enqueue eta).
	Sends a personalized WhatsApp nudge only if the customer hasn't already
	started a UGC submission for this order.

	Meta template: ugc_cashback_nudge
	Body params: {{1}} first name, {{2}} order amount, {{3}} restaurant name
	Button: dynamic URL suffix → /{restaurant_slug}/ugc-claim?r={slug}&bill={order_name}
	"""
	try:
		order = frappe.get_doc("Order", order_name)
	except frappe.DoesNotExistError:
		return

	# Skip if customer already started the UGC claim
	already_started = frappe.db.exists(
		"UGC Story Submission",
		{"order": order_name, "status": ["not in", ("rejected", "expired")]},
	)
	if already_started:
		return

	phone = order.customer_phone or ""
	if not phone and order.platform_customer:
		phone = frappe.db.get_value("Platform Customer", order.platform_customer, "phone") or ""
	if not phone:
		return

	# Customer first name
	full_name = ""
	if order.platform_customer:
		full_name = frappe.db.get_value("Platform Customer", order.platform_customer, "full_name") or ""
	if not full_name:
		full_name = order.customer_name or ""
	first_name = (full_name.strip().split()[0] if full_name.strip() else "").title() or "there"

	restaurant_name = frappe.db.get_value("Restaurant", order.restaurant, "restaurant_name") or "the restaurant"
	restaurant_slug = frappe.db.get_value("Restaurant", order.restaurant, "restaurant_id") or order.restaurant
	amount = int(order.total or 0)

	from flamezo_backend.flamezo.api.otp import generate_whatsapp_auth_token
	wa_token = generate_whatsapp_auth_token(phone, order.platform_customer) if order.platform_customer else ""
	token_suffix = f"&wt={wa_token}" if wa_token else ""
	button_url_suffix = f"ugc-claim?r={restaurant_slug}&bill={order_name}{token_suffix}"

	from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message
	try:
		success, result = send_whatsapp_cloud_message(
			to_phone=phone,
			template_name="ugc_cashback_nudge",
			body_params=[first_name, str(amount), restaurant_name],
			button_url_param=button_url_suffix,
		)
		if not success:
			frappe.log_error(f"send_ugc_cashback_nudge({order_name}): {result}", "UGC")
	except Exception as e:
		frappe.log_error(f"send_ugc_cashback_nudge({order_name}): {e}", "UGC")


def dispatch_ugc_cashback_nudges():
	"""
	Every 5 min cron: send WhatsApp cashback nudge to customers whose payment
	was marked eligible by verify_payment, and at least 3 minutes have passed.

	Flow:
	  verify_payment → sets Redis key ugc_nudge_eligible:{order}  (TTL 10 min)
	  5-min cron     → finds eligible keys, sends nudge, sets ugc_nudge_sent key
	                    to prevent double-send across parallel cron runs.

	The 3-min delay is approximated: the eligible key is set at payment time,
	and this cron runs every 5 min, so the effective delay is 3–8 min.
	"""
	from frappe.utils import now_datetime, add_to_date

	now = now_datetime()
	# Scan orders paid in the last 3–10 min window that are marked eligible
	window_start = add_to_date(now, minutes=-10)
	window_end = add_to_date(now, minutes=-3)

	# Find recently completed orders whose restaurants have UGC active
	orders = frappe.get_all(
		"Order",
		filters={
			"payment_status": "completed",
			"modified": ["between", [window_start, window_end]],
			"platform_customer": ["is", "set"],
		},
		fields=["name", "restaurant"],
		limit_page_length=200,
	)

	for row in orders:
		order_name = row.name
		eligible_key = f"ugc_nudge_eligible:{order_name}"
		sent_key = f"ugc_nudge_sent:{order_name}"

		# Only process orders flagged eligible by verify_payment
		if not frappe.cache().get_value(eligible_key):
			continue
		# Skip if already sent (guard against parallel cron runs)
		if frappe.cache().get_value(sent_key):
			continue

		# Mark sent immediately before the API call to prevent double-send
		frappe.cache().set_value(sent_key, 1, expires_in_sec=86400)
		frappe.cache().delete_value(eligible_key)

		try:
			send_ugc_cashback_nudge(order_name)
		except Exception as e:
			frappe.log_error(f"dispatch_ugc_cashback_nudges({order_name}): {e}", "UGC")


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
			f"✅ Your story for {rname} is verified! You have 48 hours to upload a "
			f"10–15 second screen recording of your story's view count.\n\n"
			f"How to record:\n"
			f'📱 Instagram: Open your story → swipe up → see "Seen by" count → screen record for 10–15 sec.\n'
			f"📱 Facebook: Open your story → tap the eye icon → screen record for 10–15 sec.\n\n"
			f"Make sure your phone's clock and battery bar are visible. Max 20 MB."
			+ _claim_link(sub)
		),
		"story_rejected": (
			f"Your story submission for {rname} couldn't be verified. "
			f"Please make sure it was posted exactly as shown and try again."
		),
		"proof_reminder": (
			f"⏰ Last reminder! Upload your story views to claim cashback from {rname}.\n\n"
			f'Instagram: Open story → swipe up → screen record the "Seen by" count (10–15 sec).\n'
			f"Facebook: Open story → tap eye icon → screen record (10–15 sec).\n\n"
			f"Keep it under 20 MB. Upload here before your 48-hour window closes:"
			+ _claim_link(sub)
		),
		"cashback_credited": (
			f"🎉 Your Story Cashback voucher is ready! ₹{cint(sub.cashback_coins)} from {rname} "
			f"— use 33% off each visit until it's fully redeemed. Valid for 45 days, only at {rname}."
			+ _claim_link(sub)
		),
		"proof_rejected": (
			f"Your cashback claim at {rname} couldn't be approved. "
			f"Reach out to the restaurant if you think this was a mistake."
		),
		"flagged": (
			f"Your story cashback at {rname} is under manual review. "
			f"Our team is checking the view count — we'll update you within 24 hours."
		),
		"expired": (
			f"Your story cashback at {rname} has expired — the 48-hour window to upload "
			f"your view-count proof has passed. Visit again and share your next story to earn cashback!"
		),
	}
	message = messages.get(kind)
	if not message:
		return

	try:
		send_whatsapp_message(phone, message)
	except Exception as e:
		frappe.log_error(f"send_ugc_whatsapp({kind}) for {submission_name}: {e}", "UGC")


def purge_old_proof_videos():
	"""
	Daily: delete diners' proof videos (Media Asset + Cloudflare R2 objects) once
	they're older than the retention window. The submission record is KEPT for
	audit/analytics — only the personal Instagram/Facebook content is removed.

	This complements the 7-day staff-visibility cutoff (restaurants lose access
	after a week; storage is purged after the retention window).
	"""
	from flamezo_backend.flamezo.api.ugc import PLATFORM_PROOF_RETENTION_DAYS

	cutoff = add_to_date(now_datetime(), days=-PLATFORM_PROOF_RETENTION_DAYS)
	rows = frappe.get_all(
		"UGC Story Submission",
		filters={"proof_video": ["is", "set"], "proof_submitted_at": ["<", cutoff]},
		fields=["name", "proof_video"],
		limit_page_length=500,
	)
	for r in rows:
		try:
			media_id = frappe.db.get_value("Media Asset", r.proof_video, "media_id")
			frappe.db.set_value("UGC Story Submission", r.name, "proof_video", None)
			if media_id:
				from flamezo_backend.flamezo.media.api import delete_media_asset
				delete_media_asset(media_id)  # soft-delete + async R2 cleanup
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"UGC proof purge failed for {r.name}: {e}", "UGC")


def retry_stalled_submissions():
	"""
	Every 30 minutes: find UGC Story Submissions stuck in 'proof_submitted' for
	more than 30 minutes (media processing or AI verification job silently died)
	and re-enqueue the AI verifier.

	This is a safety net — the happy path goes:
	  submit_ugc_proof → media processing job → verify_submission (AI)
	If the media job or AI job crashes without updating status, the submission
	stays in 'proof_submitted' forever with no cashback. This cron rescues those.

	Capped at 3 retries to avoid infinite loops on persistently broken proofs.
	"""
	now = now_datetime()
	cutoff = add_to_date(now, minutes=-30)
	stalled = frappe.get_all(
		"UGC Story Submission",
		filters={
			"status": "proof_submitted",
			"proof_submitted_at": ["<", cutoff],
		},
		fields=["name", "proof_submitted_at"],
		limit_page_length=100,
	)
	for row in stalled:
		# Use ai_raw as a lightweight retry counter (set to "retry:N" on each attempt).
		existing_raw = frappe.db.get_value("UGC Story Submission", row.name, "ai_raw") or ""
		retry_count = 0
		if existing_raw.startswith("retry:"):
			try:
				retry_count = int(existing_raw.split(":")[1])
			except (IndexError, ValueError):
				pass
		if retry_count >= 3:
			# Give up — flag for manual review rather than silently expire.
			try:
				frappe.db.set_value("UGC Story Submission", row.name, {
					"status": "flagged",
					"ai_tamper_signals": "stalled_job",
				}, update_modified=False)
				frappe.db.commit()
				send_ugc_whatsapp(row.name, "flagged")
			except Exception as e:
				frappe.log_error(f"UGC stall-flag for {row.name}: {e}", "UGC")
			continue

		try:
			frappe.db.set_value(
				"UGC Story Submission", row.name, "ai_raw",
				f"retry:{retry_count + 1}", update_modified=False,
			)
			frappe.db.commit()
			frappe.enqueue(
				"flamezo_backend.flamezo.services.ai.ugc_verifier.verify_submission",
				submission_name=row.name,
				queue="long",
				timeout=300,
			)
		except Exception as e:
			frappe.log_error(f"UGC stall-retry enqueue for {row.name}: {e}", "UGC")


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
	# Each state has its own anchor and window:
	#   offer_shown / story_shared  — 7 days from submission_date
	#     (diner never posted or staff never showed up; long window to be fair)
	#   story_verified              — 48 h from story_verified_at
	#     (diner has a full 48 h from the moment staff taps Approve)
	open_claims = frappe.get_all(
		"UGC Story Submission",
		filters={"status": ["in", ("offer_shown", "story_shared", "story_verified")]},
		fields=["name", "status", "submission_date", "story_verified_at"],
		limit_page_length=1000,
	)
	for row in open_claims:
		if row.status == "story_verified":
			# Proof window: 48 h from staff verification.
			anchor = row.story_verified_at or row.submission_date
			window_hours = 48
		else:
			# Unverified offers expire after 7 days so they don't clog the queue.
			anchor = row.submission_date
			window_hours = 7 * 24

		if not anchor:
			continue
		deadline = add_to_date(get_datetime(anchor), hours=window_hours)
		if now > deadline:
			try:
				frappe.db.set_value("UGC Story Submission", row.name, "status", "expired", update_modified=False)
				frappe.db.commit()
				# Only notify when the diner had an active proof window — unverified
				# offers (offer_shown/story_shared) expired before the diner was
				# ever told they had a deadline, so messaging them would be confusing.
				if row.status == "story_verified":
					send_ugc_whatsapp(row.name, "expired")
			except Exception as e:
				frappe.log_error(f"UGC expiry for {row.name}: {e}", "UGC")
