"""
Scheduled tasks for Flamezo Boost campaigns.

- sync_boost_performance: every 30 min — pull Meta insights for Live campaigns
- check_boost_campaigns_health: daily 9 AM — alert if guarantee at risk
- finalize_completed_boosts: midnight — complete expired campaigns, calculate guarantee
- recover_stuck_boost_launches: every 5 min — self-heal campaigns whose Meta launch
  job never ran (worker restart, queue drop) instead of sitting silently forever
- send_boost_booking_reminders: hourly — WhatsApp reminder before a Boost-linked
  table reservation, to cut no-shows on guaranteed-visit bookings
"""
import frappe
from datetime import datetime, timedelta
from frappe.utils import today, getdate, flt, now, now_datetime, time_diff_in_hours
from frappe.utils.user import get_system_managers

MAX_LAUNCH_RETRIES = 3
STUCK_AFTER_MINUTES = 15
BOOKING_REMINDER_LEAD_MINUTES = 120


def _alert_ops(subject, message):
	"""Send a real email to System Managers, in addition to the Error Log entry.
	Error Log alone was silently going unread — this ensures a human sees it."""
	recipients = get_system_managers(only_name=False)
	if not recipients:
		return
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			content=f"<pre style='font-family:monospace;white-space:pre-wrap'>{frappe.utils.escape_html(message)}</pre>",
			now=True,
		)
	except Exception:
		# Never let a notification failure break the calling job.
		frappe.log_error(message=f"Failed to send Boost ops alert: {subject}", title="Boost Alert Email Failed")


def sync_boost_performance():
	"""Pull Meta campaign insights for all Live Boost campaigns (every 30 min)."""
	live_campaigns = frappe.get_all("Boost Campaign",
		filters={"status": "Live", "meta_campaign_id": ["is", "set"]},
		fields=["name", "meta_campaign_id", "coupons_redeemed"]
	)

	if not live_campaigns:
		return

	from flamezo_backend.flamezo.services.meta_ads import get_campaign_insights

	for campaign in live_campaigns:
		try:
			insights = get_campaign_insights(campaign.meta_campaign_id)
			updates = {
				"impressions": int(insights.get("impressions", 0)),
				"reach": int(insights.get("reach", 0)),
				"link_clicks": int(insights.get("clicks", 0)),
				"amount_spent_meta": flt(insights.get("spend", 0)),
			}
			redeemed = campaign.coupons_redeemed or 0
			if redeemed > 0:
				updates["cost_per_redemption"] = flt(updates["amount_spent_meta"]) / redeemed

			for field, value in updates.items():
				frappe.db.set_value("Boost Campaign", campaign.name, field, value,
									update_modified=False)
		except Exception as e:
			frappe.log_error(
				message=f"Campaign: {campaign.name}\nError: {str(e)}",
				title="Boost Performance Sync Error"
			)

	frappe.db.commit()


def check_boost_campaigns_health():
	"""Daily health check — alert admin if campaigns are underperforming (9 AM)."""
	live_campaigns = frappe.get_all("Boost Campaign",
		filters={"status": "Live", "is_first_campaign": 0},
		fields=["name", "campaign_name", "outlet", "launch_date", "end_date",
				"guaranteed_redemptions", "coupons_redeemed", "campaign_duration"]
	)

	for campaign in live_campaigns:
		if not campaign.launch_date or not campaign.guaranteed_redemptions:
			continue

		days_total = int(campaign.campaign_duration or 14)
		launch_dt = getdate(str(campaign.launch_date))
		today_dt = getdate(today())
		days_elapsed = (today_dt - launch_dt).days if launch_dt and today_dt else 0
		days_elapsed = max(days_elapsed, 1)
		progress_pct = min(days_elapsed / days_total, 1.0)

		expected_by_now = int(campaign.guaranteed_redemptions * progress_pct)
		actual = campaign.coupons_redeemed or 0

		if actual < expected_by_now * 0.5:  # Less than 50% of expected
			message = (
				f"Campaign {campaign.name} ({campaign.campaign_name}) for {campaign.outlet}\n"
				f"Guarantee: {campaign.guaranteed_redemptions} | Actual: {actual} | "
				f"Expected by now: {expected_by_now}\n"
				f"Days elapsed: {days_elapsed}/{days_total}"
			)
			frappe.log_error(message=message, title="Boost Campaign Guarantee At Risk")
			_alert_ops(
				subject=f"Boost campaign at risk: {campaign.outlet} ({campaign.name})",
				message=message,
			)


def finalize_completed_boosts():
	"""Midnight job — finalize expired campaigns and calculate guarantee compliance."""
	expired = frappe.get_all("Boost Campaign",
		filters={
			"status": "Live",
			"end_date": ["<=", today()]
		},
		fields=["name", "meta_campaign_id"]
	)

	for row in expired:
		try:
			# Pause on Meta
			if row.meta_campaign_id:
				from flamezo_backend.flamezo.services.meta_ads import pause_campaign
				try:
					pause_campaign(row.meta_campaign_id)
				except Exception:
					pass  # Campaign might already be paused

			# Deactivate linked coupon
			campaign = frappe.get_doc("Boost Campaign", row.name)
			if campaign.linked_coupon:
				frappe.db.set_value("Coupon", campaign.linked_coupon, "is_active", 0)

			# Mark completed (handles guarantee calculation)
			campaign.mark_completed()
			frappe.db.commit()

			frappe.logger().info(f"Boost campaign {row.name} finalized. "
								f"Redemptions: {campaign.coupons_redeemed}/{campaign.guaranteed_redemptions}")

		except Exception as e:
			frappe.log_error(
				message=f"Campaign: {row.name}\nError: {str(e)}",
				title="Boost Finalization Error"
			)

	frappe.db.commit()


def recover_stuck_boost_launches():
	"""
	Self-heal campaigns whose Meta launch job never ran — e.g. worker restart,
	Redis flush, or a deployment during the enqueue window. Without this, a
	campaign paid for stays stuck in "Submitted" forever with no Meta IDs, no
	error logged, and no way for the merchant to know something went wrong.

	Runs every 5 minutes:
	- Submitted + Captured + no meta_campaign_id + paid >15 min ago → re-enqueue,
	  up to MAX_LAUNCH_RETRIES times.
	- Past the retry cap → mark Failed and alert ops for manual refund/relaunch.
	"""
	stuck = frappe.get_all("Boost Campaign",
		filters={
			"status": "Submitted",
			"payment_status": "Captured",
			"meta_campaign_id": ["in", ["", None]],
		},
		fields=["name", "outlet", "paid_at", "razorpay_payment_id", "launch_retry_count"]
	)

	for row in stuck:
		if not row.paid_at:
			continue
		age_hours = time_diff_in_hours(now_datetime(), row.paid_at)
		if age_hours * 60 < STUCK_AFTER_MINUTES:
			continue  # still within the normal launch window, not stuck yet

		retry_count = row.launch_retry_count or 0

		if retry_count >= MAX_LAUNCH_RETRIES:
			frappe.db.set_value("Boost Campaign", row.name, "status", "Failed", update_modified=False)
			message = (
				f"Campaign {row.name} for {row.outlet} paid (Razorpay payment "
				f"{row.razorpay_payment_id}) but never launched on Meta after "
				f"{retry_count} retries. Marked Failed — needs manual refund or relaunch."
			)
			frappe.log_error(message=message, title="Boost Launch Permanently Stuck")
			_alert_ops(subject=f"Boost campaign stuck — needs manual action: {row.name}", message=message)
			continue

		frappe.db.set_value("Boost Campaign", row.name, "launch_retry_count", retry_count + 1, update_modified=False)
		frappe.db.commit()
		frappe.enqueue(
			"flamezo_backend.flamezo.services.meta_ads.launch_boost_campaign",
			campaign_name=row.name,
			queue="long",
			timeout=180,
			is_async=True,
			at_front=True,
		)
		frappe.logger().info(f"Boost campaign {row.name} re-enqueued for launch (retry {retry_count + 1}).")


def send_boost_booking_reminders():
	"""
	Hourly job — WhatsApp reminder ~2 hours before a Boost-linked table
	reservation. The reservation itself is what turns a soft "maybe I'll go"
	coupon claim into a specific, committed visit; this reminder is what
	actually protects that commitment from being forgotten.

	Scoped to boost_campaign-linked bookings only — regular (non-Boost) table
	bookings are untouched by this job.
	"""
	candidates = frappe.get_all("Table Booking",
		filters={
			"boost_campaign": ["is", "set"],
			"status": ["in", ["pending", "confirmed"]],
			"reminder_sent": 0,
			"customer_phone": ["is", "set"],
		},
		fields=["name", "outlet", "customer_name", "customer_phone", "date", "time_slot", "boost_campaign"]
	)

	if not candidates:
		return

	# Official Meta WhatsApp Cloud API (Graph API) — same one OTP uses, reads
	# whatsapp_access_token/whatsapp_phone_number_id from site_config. NOT
	# Evolution API. Requires an APPROVED Meta template — free-form text isn't
	# possible on this path (Meta's business-initiated-message rules).
	from flamezo_backend.flamezo.utils.whatsapp_utils import send_whatsapp_cloud_message

	BOOKING_REMINDER_TEMPLATE = "flamezo_boost_booking_reminder"

	now_dt = now_datetime()
	for booking in candidates:
		try:
			slot_dt = datetime.combine(getdate(booking.date), datetime.strptime(booking.time_slot, "%I:%M %p").time())
		except (ValueError, TypeError):
			# Unparseable time_slot — skip rather than crash the whole batch.
			continue

		minutes_until = (slot_dt - now_dt).total_seconds() / 60
		# Fire once the reservation is within the lead window and hasn't already
		# passed — the hourly cadence means this can catch it anywhere in a
		# ~60min band inside the 120min lead time, which is fine for a reminder.
		if not (0 < minutes_until <= BOOKING_REMINDER_LEAD_MINUTES):
			continue

		restaurant_name = frappe.db.get_value("Outlet", booking.outlet, "outlet_name") or booking.outlet
		coupon_code = frappe.db.get_value("Boost Campaign", booking.boost_campaign, "coupon_code")

		try:
			# body_params map in order to the template's {{1}}, {{2}}, {{3}} —
			# adjust to match whatever the approved template's copy actually is.
			sent, result = send_whatsapp_cloud_message(
				booking.customer_phone,
				template_name=BOOKING_REMINDER_TEMPLATE,
				body_params=[booking.customer_name or "there", restaurant_name, booking.time_slot, coupon_code],
			)
		except Exception as e:
			sent, result = False, str(e)

		if sent:
			frappe.db.set_value("Table Booking", booking.name, "reminder_sent", 1, update_modified=False)
			frappe.db.commit()
		else:
			frappe.log_error(
				message=f"Booking: {booking.name}\nPhone: {booking.customer_phone}\nError: {result}",
				title="Boost Booking Reminder Failed"
			)
