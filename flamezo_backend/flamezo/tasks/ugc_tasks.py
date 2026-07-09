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

from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message
from flamezo_backend.flamezo.utils.platform_config import get_expiry_days


def _restaurant_name(restaurant):
	return frappe.db.get_value("Restaurant", restaurant, "restaurant_name") or "the restaurant"


def _customer_phone(customer):
	return frappe.db.get_value("Customer", customer, "phone")



def send_ugc_cashback_nudge(order_name):
	"""
	Sent ~3 minutes after payment success by the dispatch_ugc_cashback_nudges cron.
	Sends a personalized WhatsApp nudge to the diner, regardless of whether they've
	opened the UGC page / tapped Unlock (the message always goes out once per order).

	Meta template: flamezo_ugc_earn_invite
	Body params: {{1}} first name, {{2}} order amount, {{3}} restaurant name
	Button: dynamic URL suffix → /{restaurant_slug}/ugc-claim?r={slug}&bill={order_name}
	"""
	# Idempotency guard — skip only if a previous run already sent successfully.
	# (The key is set *after* a successful send below, so a failed attempt retries.)
	sent_key = f"ugc_nudge_sent:{order_name}"
	if frappe.cache().get_value(sent_key):
		return

	try:
		order = frappe.get_doc("Order", order_name)
	except frappe.DoesNotExistError:
		return

	# NOTE: the nudge is sent whether or not the diner has opened the UGC page or
	# tapped Unlock — there is intentionally no "already started" suppression here.

	phone = order.customer_phone or ""
	if not phone and order.platform_customer:
		phone = frappe.db.get_value("Customer", order.platform_customer, "phone") or ""
	if not phone:
		return

	# Customer first name
	full_name = ""
	if order.platform_customer:
		full_name = frappe.db.get_value("Customer", order.platform_customer, "customer_name") or ""
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

	try:
		success, result = send_whatsapp_cloud_message(
			to_phone=phone,
			template_name="flamezo_ugc_earn_invite",
			body_params=[first_name, str(amount), restaurant_name],
			button_url_param=button_url_suffix,
		)
		if not success:
			frappe.log_error(message=str(result), title=f"UGC Nudge Error: {order_name}")
		else:
			# Only set the idempotency key if the message was actually sent successfully!
			frappe.cache().set_value(sent_key, 1, expires_in_sec=86400)
	except Exception as e:
		frappe.log_error(message=str(e), title=f"UGC Nudge Exception: {order_name}")


def dispatch_ugc_cashback_nudges():
	"""
	Cron (every 5 min) — the PRIMARY delivery path for the post-payment UGC nudge.

	verify_payment marks each paid order eligible (Redis key ugc_nudge_eligible:*);
	this cron sends the WhatsApp ~3-8 min later, but only if the diner hasn't started
	a UGC claim in the meantime. Timing lives here because frappe.enqueue (RQ) has no
	delay/eta support, so a delayed job can't be scheduled directly.
	"""
	from frappe.utils import now_datetime, add_to_date

	now = now_datetime()
	# 6-min window (> the 5-min cron interval, so no paid order is skipped), starting
	# 3 min back to give the diner a short grace period to open the UGC page first.
	window_start = add_to_date(now, minutes=-9)
	window_end = add_to_date(now, minutes=-3)

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
		if not frappe.cache().get_value(f"ugc_nudge_eligible:{order_name}"):
			continue
		if frappe.cache().get_value(f"ugc_nudge_sent:{order_name}"):
			continue
		# Don't clear the eligible key here: send_ugc_cashback_nudge sets the sent key
		# only on a successful send, so a failed attempt is retried next run and a
		# successful one is deduped by that sent key.
		try:
			send_ugc_cashback_nudge(order_name)
		except Exception as e:
			frappe.log_error(f"dispatch_ugc_cashback_nudges({order_name}): {e}", "UGC")


def send_ugc_whatsapp(submission_name, kind):
	"""
	Send a transactional WhatsApp message via Meta Cloud API template.

	Template map:
	  story_verified    → flamezo_story_approved      params: {{1}} restaurant_name
	  story_rejected    → flamezo_story_not_approved  params: {{1}} restaurant_name
	  proof_received    → flamezo_proof_acknowledged  params: {{1}} restaurant_name
	  proof_reminder    → flamezo_upload_reminder     params: {{1}} restaurant_name  + button URL (with auth token)
	  cashback_credited → flamezo_cashback_added      params: {{1}} amount, {{2}} restaurant_name  + button URL (with auth token)
	  proof_rejected    → flamezo_proof_not_approved  params: {{1}} restaurant_name
	  flagged           → flamezo_manual_review       params: {{1}} restaurant_name
	  expired           → flamezo_window_expired      params: {{1}} restaurant_name
	"""
	try:
		sub = frappe.get_doc("UGC Story Submission", submission_name)
	except frappe.DoesNotExistError:
		return

	phone = _customer_phone(sub.customer)
	if not phone:
		return

	rname = _restaurant_name(sub.restaurant)
	amount = str(cint(sub.cashback_coins))

	# Build deep-link suffix for templates that include a button.
	# For customer-facing links (proof_reminder, cashback_credited) include a WhatsApp
	# auth token so the customer lands directly on the upload page without a login prompt.
	base = frappe.conf.get("customer_web_url", "")
	slug = frappe.db.get_value("Restaurant", sub.restaurant, "restaurant_id") or sub.restaurant
	order = getattr(sub, "order", "") or ""
	customer = getattr(sub, "customer", "")

	# proof_reminder → back to ugc-claim (upload the screen recording)
	proof_link_no_auth = f"{slug}/ugc-claim?r={slug}&bill={order}" if base else ""
	# cashback_credited → to cashback-rewards (view & redeem the voucher)
	wallet_link_no_auth = "cashback-rewards" if base else ""

	# Attach a WhatsApp auth token to both deep-links so the customer lands
	# already logged in without an OTP prompt.
	proof_link = proof_link_no_auth
	wallet_link = wallet_link_no_auth
	if customer:
		try:
			from flamezo_backend.flamezo.api.otp import generate_whatsapp_auth_token
			platform_customer = frappe.db.get_value("Customer", customer, "platform_customer")
			phone = _customer_phone(customer)
			if platform_customer and phone:
				wa_token = generate_whatsapp_auth_token(phone, platform_customer)
				if wa_token:
					if proof_link_no_auth:
						proof_link = f"{proof_link_no_auth}&wt={wa_token}"
					if wallet_link_no_auth:
						wallet_link = f"{wallet_link_no_auth}?wt={wa_token}"
		except Exception:
			pass  # fall back to links without auth token

	TEMPLATES = {
		"story_verified":    ("flamezo_story_approved",     [rname],          None),
		"story_rejected":    ("flamezo_story_not_approved", [rname],          None),
		"proof_received":    ("flamezo_proof_acknowledged", [rname],          None),
		"proof_reminder":    ("flamezo_upload_reminder",    [rname],          proof_link),
		"cashback_credited": ("flamezo_cashback_added",     [amount, rname],  wallet_link),
		"proof_rejected":    ("flamezo_proof_not_approved", [rname],          None),
		"flagged":           ("flamezo_manual_review",      [rname],          None),
		"expired":           ("flamezo_window_expired",     [rname],          None),
	}

	entry = TEMPLATES.get(kind)
	if not entry:
		return

	template_name, body_params, button_url_param = entry
	try:
		success, result = send_whatsapp_cloud_message(
			to_phone=phone,
			template_name=template_name,
			body_params=body_params,
			button_url_param=button_url_param,
		)
		if not success:
			frappe.log_error(f"send_ugc_whatsapp({kind}) for {submission_name}: {result}", "UGC")
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
