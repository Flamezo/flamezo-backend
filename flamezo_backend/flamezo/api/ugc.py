# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
UGC Cashback API
================
Diners post a pre-approved Instagram/Facebook story after their order, a
restaurant staff member verifies the story in person, and the next day the
diner uploads a screen-recording of the story's view count. An AI reads the
view count and the cashback (= min(views, order amount)) is credited to the
diner's universal loyalty wallet.

State machine (UGC Story Submission.status):
    offer_shown -> story_shared -> story_verified -> proof_submitted
                -> (credited | flagged | rejected | expired)

All customer endpoints authenticate via the X-Customer-Token session header
(guest Frappe session). Staff endpoints require a Restaurant Admin / Staff
user for the target restaurant.
"""

import re
import uuid
import random
import string
import hashlib
import base64
import subprocess
import tempfile
import os
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import now_datetime, today, add_days, add_to_date, flt, cint, get_datetime, date_diff

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import get_customer_token, get_customer_from_token, normalize_phone, validate_customer_session
from flamezo_backend.flamezo.utils.roles import GLOBAL_ADMIN_ROLES, SUPERVISOR_ROLES
from flamezo_backend.flamezo.utils.platform_config import get_expiry_days
from flamezo_backend.flamezo.media.storage import (
	generate_object_key,
	generate_signed_upload_url,
	verify_object_exists,
	get_cdn_url,
	upload_bytes,
)

# ── Constants ────────────────────────────────────────────────────────────────
ALLOWED_PROOF_MIME = {
	"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/3gpp",
}
MAX_PROOF_BYTES = 20 * 1024 * 1024  # 20 MB — fits a 10-15 s screen recording at any phone quality
# UGC cashback is outlet-locked and redeemable ONLY at the outlet it was earned for,
# within this window (distinct from the platform-wide wallet expiry).
UGC_CASHBACK_VALIDITY_DAYS = 90
UGC_PIN_LOCK_HOURS = 4           # waiter PIN activation is valid for this many hours
PROOF_OWNER_DOCTYPE = "UGC Story Submission"
PROOF_MEDIA_ROLE = "ugc_proof_video"
TEMPLATE_OWNER_DOCTYPE = "UGC Cashback Config"
TEMPLATE_MEDIA_ROLE = "ugc_template_image"

# Customer-facing copy is FIXED by Flamezo (not restaurant-editable).
PLATFORM_HEADLINE = "Keep a story, get up to 100% cashback"
PLATFORM_INSTRUCTIONS = (
	"Share our story to your Instagram/Facebook and show it to our staff to verify. "
	"Tomorrow, upload a screen recording of your story's view count — you get that many "
	"rupees back as Flamezo Cash, up to 100% of your bill."
)
# The claim journey, in the order the diner walks it. Kept beside the copy above
# so the explainer popup in the web and Flutter apps never drifts from the flow
# the backend actually enforces.
PLATFORM_STEPS = [
	{
		"title": "Pay your bill",
		"detail": "Settle the bill through Flamezo at this outlet.",
	},
	{
		"title": "Share the story",
		"detail": "Post the outlet's story frame to your Instagram, Facebook, or WhatsApp Story.",
	},
	{
		"title": "Show staff to verify",
		"detail": "Show the posted story to our staff — they confirm it with a PIN.",
	},
	{
		"title": "Upload your view count",
		"detail": "Next day, screen-record your story's view count and upload it within 48 hours.",
	},
	{
		"title": "Get your cashback",
		"detail": "Views become rupees, up to 100% of your bill — credited as an outlet voucher.",
	},
]

# Moved above PLATFORM_REDEEM_STEPS (was defined at line ~162, after this first use) —
# module-level code runs top-to-bottom at import time, so referencing it before this
# point raised a NameError that broke every function in this module, not just this one.
PLATFORM_VOUCHER_PER_VISIT_PCT = 33   # % of each visit's bill = max free-dish budget

PLATFORM_REDEEM_STEPS = [
	{
		"title": "Visit again",
		"detail": f"Come back to this outlet within {UGC_CASHBACK_VALIDITY_DAYS} days.",
	},
	{
		"title": "Show your voucher",
		"detail": "Show the voucher code to the staff, who unlock it by entering their secret PIN on your phone.",
	},
	{
		"title": "Pick your free dish",
		"detail": f"Based on your new bill, pick a free dish (worth up to {PLATFORM_VOUCHER_PER_VISIT_PCT}% of the bill) and the staff will apply it!",
	},
]

PLATFORM_TERMS = (
	"Cashback = your story's view count in rupees, capped at your bill (max ₹2,000). "
	"Credited as a restaurant voucher — pick a free dish worth up to 33% of your next bill on each return visit. "
	"Voucher valid for 90 days, redeemable only at this restaurant. Up to 2 claims per "
	"restaurant every 30 days. Stories must stay live for at least 24 hours. Once staff "
	"verify your story, you have 48 hours to upload a screen recording of your view count. "
	"Flamezo may reject views that appear edited, inflated, or fraudulent, and repeat "
	"offenders lose eligibility."
)

# ── Platform-fixed rules (same for every Flamezo restaurant; not editable in the
#    merchant dashboard — only the story template + linked coupons are). ──────────
PLATFORM_MIN_ORDER = 250            # ₹ — min final paid amount to qualify
CLAIM_WINDOW_DAYS = 90              # days after the order that a claim stays open
PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D = 2   # rolling 30-day cap per restaurant (unlimited across different restaurants)
PLATFORM_CASHBACK_PERCENT_CAP = 100  # % of the final paid amount
PLATFORM_ABSOLUTE_CAP = 0          # 0 = no extra ₹ ceiling beyond the bill
PLATFORM_PROOF_WINDOW_HOURS = 48
PLATFORM_AI_PROVIDER = "Gemini"
PLATFORM_AI_CONFIDENCE = 0.85

# ── Explainer detail served to the diner apps ────────────────────────────────
# Derived from the rule constants directly above, so the numbers a diner reads
# in the popup are the same ones the backend enforces — they cannot drift.

def _platform_facts():
	"""Headline numbers for the explainer, as label/value pairs."""
	return [
		{"label": "Max cashback", "value": f"{PLATFORM_CASHBACK_PERCENT_CAP}% of your bill"},
		{"label": "Minimum bill", "value": f"₹{PLATFORM_MIN_ORDER}"},
		{"label": "Upload window", "value": f"{PLATFORM_PROOF_WINDOW_HOURS} hours"},
		{"label": "Voucher validity", "value": f"{UGC_CASHBACK_VALIDITY_DAYS} days"},
		{"label": "Claims allowed", "value": f"{PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D} per outlet / 30 days"},
		{"label": "Story must stay live", "value": "24 hours"},
	]


def _platform_terms_list():
	"""The terms blob, broken into readable bullets for the explainer popup."""
	return [
		"Your cashback equals your story's view count in rupees, capped at your bill amount.",
		"It is credited as a voucher for this outlet — not cash, and not usable elsewhere.",
		"Redeem it on return visits: pick a free dish worth up to 33% of that visit's bill.",
		f"The voucher is valid for {UGC_CASHBACK_VALIDITY_DAYS} days from the day it is issued.",
		"Your story must stay live for at least 24 hours — deleting it early voids the claim.",
		f"After staff verify your story, you have {PLATFORM_PROOF_WINDOW_HOURS} hours to upload your view-count recording.",
		f"You can claim up to {PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D} times at this outlet every 30 days. Other outlets are unlimited.",
		"Views that appear edited, inflated, or fraudulent are rejected, and repeat offenders lose eligibility.",
	]
# Voucher rules — platform-fixed, non-editable by restaurants.
PLATFORM_VOUCHER_EARNING_CAP = 2000   # ₹ — max voucher any single claim can issue
# PLATFORM_VOUCHER_PER_VISIT_PCT now defined near PLATFORM_REDEEM_STEPS above (its first use)
# Privacy + storage: restaurants can view a diner's proof for 7 days; the proof
# video is deleted from storage 30 days after it was submitted.
PLATFORM_STAFF_PROOF_DAYS = 7
PLATFORM_PROOF_RETENTION_DAYS = 30

# Order is considered eligible (completed) when any of these hold.
_COMPLETED_ORDER_STATUSES = {"confirmed", "preparing", "ready", "delivered", "billed", "completed"}
# Submission states that still "consume" a monthly claim slot (i.e. not failed).
_ACTIVE_SUBMISSION_STATUSES = (
	"offer_shown", "story_shared", "story_verified", "proof_submitted", "credited", "flagged",
)


# ── Generic helpers ──────────────────────────────────────────────────────────
def _ok(data=None):
	return {"success": True, "data": data if data is not None else {}}


def _err(code, message=None):
	return {"success": False, "error": code, "message": message or code}


def _require_customer():
	"""Resolve the calling diner from the session token, or None."""
	token = get_customer_token()
	if not token:
		return None
	return get_customer_from_token(token)


def _sanitize_filename(filename):
	base = (filename or "proof.mp4").strip().split("/")[-1]
	base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
	if "." not in base:
		base = base + ".mp4"
	return base[:120]


def _current_period():
	return today()[:7]  # "YYYY-MM"


# ── Config / eligibility helpers ─────────────────────────────────────────────
def _get_active_config(restaurant):
	"""Return the UGC Cashback Config doc for a restaurant, or None.

	UGC cashback is a mandatory, always-on platform feature — there is no
	per-restaurant on/off switch. The offer simply surfaces to diners once the
	restaurant has uploaded at least one story template (enforced in eligibility).
	"""
	name = frappe.db.get_value("UGC Cashback Config", {"outlet": restaurant}, "name")
	if not name:
		return None
	return frappe.get_doc("UGC Cashback Config", name)


def _is_blocked(customer):
	"""True when the customer has an active (non-expired) UGC fraud flag."""
	flags = frappe.get_all(
		"UGC Fraud Flag",
		filters={"customer": customer, "is_active": 1},
		fields=["blocked_until"],
	)
	now = now_datetime()
	for f in flags:
		if not f.blocked_until or get_datetime(f.blocked_until) > now:
			return True
	return False


def _claims_last_30d(customer, restaurant):
	"""Claims this customer made at THIS restaurant in the last 30 days.

	The platform cap is per-restaurant (PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D);
	there is no global cap, so a diner can claim across many restaurants.
	"""
	since = add_to_date(now_datetime(), days=-30)
	return frappe.db.count(
		"UGC Story Submission",
		filters={
			"customer": customer,
			"outlet": restaurant,
			"status": ["in", _ACTIVE_SUBMISSION_STATUSES],
			"submission_date": [">=", since],
		},
	)


def _order_is_eligible(order):
	if (order.payment_status or "").lower() == "completed":
		return True
	return (order.status or "").lower() in _COMPLETED_ORDER_STATUSES


def _max_cashback(order_amount):
	"""Ceiling for this order before the actual view count is known (platform rules).

	order_amount is the order's final paid total (after offers + loyalty redemption).
	"""
	cap = flt(order_amount) * PLATFORM_CASHBACK_PERCENT_CAP / 100.0
	if PLATFORM_ABSOLUTE_CAP > 0:
		cap = min(cap, PLATFORM_ABSOLUTE_CAP)
	return int(max(0, cap))


def _is_ugc_active(config) -> bool:
	"""
	UGC surfaces to diners only when ALL are true:
	  1. Merchant has not manually paused the feature (is_active == 1).
	  2. At least one story template has been uploaded.
	  3. A viewer coupon code is set in the inline coupon fields.
	  4. A positive viewer discount value is set.

	NOTE: we no longer require story_preview_url. The diner app renders the frame
	as a DOM overlay on the raw media, so the preview is ready the moment a
	template is uploaded — no need to wait for (or depend on) the composited
	preview, which expires from R2's temp prefix after 24h.
	"""
	if not cint(config.is_active):
		return False
	if not bool(config.template_assets):
		return False
	if not (config.viewer_coupon_code or "").strip():
		return False
	if not flt(config.viewer_discount_value) > 0:
		return False
	return True


def _resolve_templates(config):
	"""Return the list of shareable templates.

	`url` is the RAW CDN media. The diner app draws the Flamezo frame
	(logo + QR + coupon) as a DOM overlay on top of this for the preview, and
	composites the frame server-side only on download/share. We deliberately do
	NOT serve config.story_preview_url here: it is a composited temp object that
	R2 auto-deletes after 24h (→ black/broken media once expired), and layering
	the DOM frame on an already-composited preview would double the coupon.
	"""
	out = []
	for row in (config.template_assets or []):
		if not row.media_asset:
			continue
		asset = frappe.db.get_value(
			"Media Asset", row.media_asset,
			["name", "primary_url", "media_kind", "status"], as_dict=True,
		)
		if not asset or asset.status == "deleted":
			continue
		out.append({
			"media_id": asset.name,
			"url": asset.primary_url,
			"kind": asset.media_kind,
			"label": row.label,
			"is_default": cint(row.is_default),
		})
	return out


def _raw_template_url(config):
	"""Return the raw (un-composited) CDN URL of the first active template."""
	for row in (config.template_assets or []):
		if not row.media_asset:
			continue
		info = frappe.db.get_value(
			"Media Asset", row.media_asset,
			["primary_url", "media_kind", "status"], as_dict=True,
		)
		if info and info.status != "deleted" and info.primary_url:
			return info.primary_url, info.media_kind or "image"
	return None, "image"


def _enqueue_config_preview(config):
	"""Enqueue a background job to composite the story preview for this config.

	Called after save_ugc_config when a template + viewer coupon are both set.
	Clears any stale preview URL first so the diner never sees an outdated composite.
	"""
	raw_url, _ = _raw_template_url(config)
	if not raw_url or not (config.viewer_coupon_code or "").strip():
		return
	frappe.db.set_value("UGC Cashback Config", config.name, "story_preview_url", None)
	frappe.db.commit()
	frappe.enqueue(
		"flamezo_backend.flamezo.api.ugc._generate_config_preview",
		queue="long",
		timeout=300,
		config_name=config.name,
	)


def _generate_config_preview(config_name):
	"""Background job: composite the story preview and write the CDN URL back to the config doc."""
	try:
		import re as _re
		config = frappe.get_doc("UGC Cashback Config", config_name)
		raw_url, media_kind = _raw_template_url(config)
		if not raw_url:
			return
		media_type = "video" if (
			media_kind == "video" or
			bool(_re.search(r"\.(mp4|webm|mov|m4v|ogg)(\?|$)", raw_url, _re.I))
		) else "image"

		coupon = _inline_coupon_brief(config)
		outlet_name = frappe.db.get_value("Outlet", config.outlet, "outlet_name") or ""

		from flamezo_backend.flamezo.api.story_generator import _run_job, _get_cache
		import uuid
		job_id = str(uuid.uuid4())
		_run_job(
			job_id=job_id,
			template_url=raw_url,
			media_type=media_type,
			outlet_name=outlet_name,
			coupon_code=coupon.get("code") if coupon else None,
			discount_type=coupon.get("discount_type") if coupon else None,
			discount_value=coupon.get("discount_value") if coupon else None,
			offer_description=coupon.get("description") if coupon else None,
			valid_until=None,
		)
		result = _get_cache(job_id)
		if result and result.get("status") == "done" and result.get("url"):
			frappe.db.set_value("UGC Cashback Config", config_name, "story_preview_url", result["url"])
			frappe.db.commit()
			# Bust the Frappe Redis cache for get_restaurant_config so the next
			# consumer request reflects ugcActive=true without waiting for TTL.
			outlet_id = frappe.db.get_value("UGC Cashback Config", config_name, "outlet")
			if outlet_id:
				frappe.cache().delete_key(f"outlet_config:{outlet_id}")
		else:
			frappe.log_error(
				f"Story preview generation finished with status={result.get('status') if result else 'None'} for {config_name}",
				"UGC",
			)
	except Exception as e:
		frappe.log_error(f"_generate_config_preview failed for {config_name}: {e}", "UGC")


def _coupon_brief(coupon_name):
	if not coupon_name:
		return None
	c = frappe.db.get_value(
		"Coupon", coupon_name,
		["code", "discount_type", "discount_value"], as_dict=True,
	)
	if not c:
		return None
	return {"code": c.code, "discount_type": c.discount_type, "discount_value": c.discount_value}


def _inline_coupon_brief(config):
	"""Build a coupon brief dict from inline ugc_cashback_config fields."""
	code = (config.viewer_coupon_code or "").strip()
	if not code:
		return None
	return {
		"code": code.upper(),
		"discount_type": config.viewer_discount_type or "flat",
		"discount_value": flt(config.viewer_discount_value or 0),
		"discount_cap": flt(config.viewer_discount_cap or 0),
		"description": config.viewer_coupon_description or "",
	}


def _load_owned_order(restaurant, order_id, customer):
	"""Fetch an order and assert it belongs to this restaurant + customer."""
	if not frappe.db.exists("Order", order_id):
		return None
	order = frappe.get_doc("Order", order_id)
	if order.outlet != restaurant:
		return None
	if order.platform_customer and order.platform_customer != customer:
		return None
	if not order.platform_customer:
		# If the order lacks a platform_customer (e.g. POS order) but the phone matches, link it.
		from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone
		customer_phone = frappe.db.get_value("Customer", customer, "phone")
		if normalize_phone(order.customer_phone) == normalize_phone(customer_phone):
			order.db_set("platform_customer", customer)
		else:
			return None
	return order


def _active_submission_for_order(order_id):
	name = frappe.db.get_value(
		"UGC Story Submission",
		{"order": order_id, "status": ["not in", ("rejected", "expired")]},
		"name",
	)
	return frappe.get_doc("UGC Story Submission", name) if name else None


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOMER ENDPOINTS  (guest session via X-Customer-Token)
# ══════════════════════════════════════════════════════════════════════════════
@frappe.whitelist(allow_guest=True)
def get_ugc_eligibility(outlet_id, order_id):
	"""Is this diner eligible to claim UGC cashback for this order?"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED", "Please verify your phone to continue.")

		config = _get_active_config(restaurant)
		if not config or not _is_ugc_active(config):
			frappe.log_error(f"ugc_eligibility not_available: config={bool(config)} active={_is_ugc_active(config) if config else False} templates={bool(config.template_assets) if config else None} coupon={getattr(config,'viewer_coupon_code','') if config else None} preview={bool(getattr(config,'story_preview_url','')) if config else None}", "UGC Debug")
			return _ok({"eligible": False, "reason": "not_available"})

		order = _load_owned_order(restaurant, order_id, customer)
		if not order:
			frappe.log_error(f"ugc_eligibility order_not_found: order_id={order_id} customer={customer} restaurant={restaurant}", "UGC Debug")
			return _ok({"eligible": False, "reason": "order_not_found"})

		# If a submission already exists, surface its state instead of a fresh offer.
		existing = _active_submission_for_order(order_id)
		if existing:
			templates = _resolve_templates(config)
			return _ok({
				"eligible": True,
				"already_started": True,
				"submission_id": existing.name,
				"status": existing.status,
				"cashback_coins": cint(existing.cashback_coins),
				"max_cashback": _max_cashback(existing.order_amount or order.total),
				"templates": templates,
				"viewer_coupon": _inline_coupon_brief(config),
				"proof_window_open": _proof_window_open(existing),
			})

		if not _order_is_eligible(order):
			return _ok({"eligible": False, "reason": "order_not_completed"})

		if flt(order.total) < PLATFORM_MIN_ORDER:
			return _ok({"eligible": False, "reason": "below_min_order"})

		if _is_blocked(customer):
			return _ok({"eligible": False, "reason": "not_eligible"})

		templates = _resolve_templates(config)
		if not templates:
			return _ok({"eligible": False, "reason": "not_available"})

		if _claims_last_30d(customer, restaurant) >= PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D:
			return _ok({"eligible": False, "reason": "limit_reached"})

		return _ok({
			"eligible": True,
			"already_started": False,
			"max_cashback": _max_cashback(order.total),
			"order_amount": flt(order.total),
			"headline": PLATFORM_HEADLINE,
			"instructions": PLATFORM_INSTRUCTIONS,
			"terms": PLATFORM_TERMS,
			"templates": templates,
			"viewer_coupon": _inline_coupon_brief(config),
		})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"get_ugc_eligibility: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def start_ugc_offer(outlet_id, order_id):
	"""Diner taps the cashback CTA — create (or resume) a submission."""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		config = _get_active_config(restaurant)
		if not config or not _is_ugc_active(config):
			return _err("NOT_AVAILABLE", "UGC cashback is not active for this outlet.")

		order = _load_owned_order(restaurant, order_id, customer)
		if not order:
			return _err("ORDER_NOT_FOUND")

		existing = _active_submission_for_order(order_id)
		if existing:
			return _ok({
				"submission_id": existing.name,
				"status": existing.status,
				"max_cashback": _max_cashback(existing.order_amount or order.total),
				"templates": _resolve_templates(config),
				"headline": PLATFORM_HEADLINE,
				"instructions": PLATFORM_INSTRUCTIONS,
				"proof_window_open": _proof_window_open(existing),
			})

		# Re-run the eligibility gates server-side (never trust the client).
		if not _order_is_eligible(order):
			return _err("ORDER_NOT_COMPLETED")
		if flt(order.total) < PLATFORM_MIN_ORDER:
			return _err("BELOW_MIN_ORDER")
		if _is_blocked(customer):
			return _err("NOT_ELIGIBLE")
		if not _resolve_templates(config):
			return _err("NOT_AVAILABLE")
		if _claims_last_30d(customer, restaurant) >= PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D:
			return _err("LIMIT_REACHED")

		submission = frappe.get_doc({
			"doctype": "UGC Story Submission",
			"outlet": restaurant,
			"customer": customer,
			"order": order.name,
			"order_amount": flt(order.total),
			"status": "offer_shown",
			"submission_date": now_datetime(),
		})
		submission.insert(ignore_permissions=True)
		frappe.db.commit()

		return _ok({
			"submission_id": submission.name,
			"status": "offer_shown",
			"max_cashback": _max_cashback(order.total),
			"templates": _resolve_templates(config),
			"headline": PLATFORM_HEADLINE,
			"instructions": PLATFORM_INSTRUCTIONS,
		})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"start_ugc_offer: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def mark_story_shared(outlet_id, submission_id, template_media_id=None):
	"""Diner confirms they shared the story to their IG/FB story."""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		submission = _load_owned_submission(submission_id, restaurant, customer)
		if not submission:
			return _err("SUBMISSION_NOT_FOUND")

		if submission.status not in ("offer_shown", "story_shared"):
			return _err("INVALID_STATE", f"Cannot mark shared from '{submission.status}'.")

		if template_media_id and frappe.db.exists("Media Asset", template_media_id):
			submission.template_used = template_media_id
		submission.status = "story_shared"
		submission.story_shared_at = now_datetime()
		submission.save(ignore_permissions=True)
		frappe.db.commit()
		return _ok({"status": "story_shared"})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"mark_story_shared: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def verify_story_with_pin(outlet_id, submission_id, pin):
	"""
	POST /api/method/flamezo_backend.flamezo.api.ugc.verify_story_with_pin

	Customer shows posted story to staff → staff enters restaurant PIN on customer's phone.
	Transitions story_shared → story_verified, opening the 48h proof upload window.
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		submission = _load_owned_submission(submission_id, restaurant, customer)
		if not submission:
			return _err("SUBMISSION_NOT_FOUND")

		if submission.status != "story_shared":
			return _err("INVALID_STATE", f"Cannot verify from '{submission.status}'.")

		stored_pin = frappe.db.get_value("Outlet Config", restaurant, "offer_verification_pin") or ""
		if not stored_pin:
			return _err("PIN_NOT_SET", "This outlet has not set up a verification PIN.")
		if str(pin).strip() != stored_pin:
			return _err("INVALID_PIN", "Incorrect PIN — please try again.")

		submission.status = "story_verified"
		submission.story_verified_by = "pin"
		submission.story_verified_at = now_datetime()
		submission.save(ignore_permissions=True)
		frappe.db.commit()
		_notify(submission.name, "story_verified")
		return _ok({"status": "story_verified"})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"verify_story_with_pin: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def upload_proof_video(outlet_id, submission_id, filename, content_type, size_bytes):
	"""Alias for request_ugc_video_upload — matches the EP.ugcUploadProof key."""
	return request_ugc_video_upload(outlet_id, submission_id, filename, content_type, size_bytes)


@frappe.whitelist(allow_guest=True)
def request_ugc_video_upload(outlet_id, submission_id, filename, content_type, size_bytes):
	"""Issue a signed R2 URL for the diner to upload their view-count screen recording."""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		submission = _load_owned_submission(submission_id, restaurant, customer)
		if not submission:
			return _err("SUBMISSION_NOT_FOUND")

		# Proof can only be uploaded after staff verified the story is live.
		if submission.status not in ("story_verified", "proof_submitted"):
			return _err("STORY_NOT_VERIFIED", "Your story is awaiting staff verification.")

		# Proof window: 48 h from when staff verified — not from when the offer started.
		if not _proof_window_open(submission):
			return _err("PROOF_WINDOW_CLOSED", "The 48-hour proof upload window has closed.")

		content_type = (content_type or "").lower().strip()
		if content_type not in ALLOWED_PROOF_MIME:
			return _err("INVALID_FILE_TYPE", "Please upload a screen recording (mp4/mov/webm).")
		if cint(size_bytes) <= 0 or cint(size_bytes) > MAX_PROOF_BYTES:
			return _err("FILE_TOO_LARGE", "Video must be under 20 MB. Keep your recording to 10–15 seconds.")

		media_id = f"med_{uuid.uuid4().hex[:12]}"
		safe_filename = _sanitize_filename(filename)
		object_key = generate_object_key(
			outlet_id=restaurant,
			owner_doctype=PROOF_OWNER_DOCTYPE,
			owner_name=submission.name,
			media_role=PROOF_MEDIA_ROLE,
			media_id=media_id,
			filename=safe_filename,
		)
		upload_data = generate_signed_upload_url(object_key, content_type)

		frappe.get_doc({
			"doctype": "Media Upload Session",
			"upload_id": media_id,
			"outlet": restaurant,
			"owner_doctype": PROOF_OWNER_DOCTYPE,
			"owner_name": submission.name,
			"media_role": PROOF_MEDIA_ROLE,
			"media_kind": "video",
			"object_key": object_key,
			"filename": safe_filename,
			"content_type": content_type,
			"size_bytes": cint(size_bytes),
			"status": "pending",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

		return _ok({
			"upload_id": media_id,
			"object_key": object_key,
			"upload_url": upload_data["upload_url"],
			"headers": upload_data["headers"],
			"expires_in": upload_data["expires_in"],
		})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"request_ugc_video_upload: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def upload_ugc_video_proxy(outlet_id, submission_id):
	"""Backend-proxied proof upload: the diner POSTs the video file here and the
	server streams it to R2. This avoids the browser→R2 presigned-PUT, which fails
	when the R2 bucket CORS policy doesn't allow the site origin.

	Expects a multipart/form-data body with fields `outlet_id`,
	`submission_id` and a file part named `file`.

	Returns { upload_id } — pass it straight to submit_ugc_proof().
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		submission = _load_owned_submission(submission_id, restaurant, customer)
		if not submission:
			return _err("SUBMISSION_NOT_FOUND")

		# Same gates as request_ugc_video_upload.
		if submission.status not in ("story_verified", "proof_submitted"):
			return _err("STORY_NOT_VERIFIED", "Your story is awaiting staff verification.")
		if not _proof_window_open(submission):
			return _err("PROOF_WINDOW_CLOSED", "The 48-hour proof upload window has closed.")

		uploaded = frappe.request.files.get("file") if frappe.request else None
		if not uploaded:
			return _err("NO_FILE", "No video file received.")

		content_type = (uploaded.mimetype or "").lower().strip()
		if content_type not in ALLOWED_PROOF_MIME:
			return _err("INVALID_FILE_TYPE", "Please upload a screen recording (mp4/mov/webm).")

		data = uploaded.stream.read()
		size_bytes = len(data or b"")
		if size_bytes <= 0 or size_bytes > MAX_PROOF_BYTES:
			return _err("FILE_TOO_LARGE", "Video must be under 20 MB. Keep your recording to 10–15 seconds.")

		media_id = f"med_{uuid.uuid4().hex[:12]}"
		safe_filename = _sanitize_filename(uploaded.filename or "proof.mp4")
		object_key = generate_object_key(
			outlet_id=restaurant,
			owner_doctype=PROOF_OWNER_DOCTYPE,
			owner_name=submission.name,
			media_role=PROOF_MEDIA_ROLE,
			media_id=media_id,
			filename=safe_filename,
		)

		# Stream to R2 server-side — no browser CORS involved.
		upload_bytes(object_key, data, content_type)

		frappe.get_doc({
			"doctype": "Media Upload Session",
			"upload_id": media_id,
			"outlet": restaurant,
			"owner_doctype": PROOF_OWNER_DOCTYPE,
			"owner_name": submission.name,
			"media_role": PROOF_MEDIA_ROLE,
			"media_kind": "video",
			"object_key": object_key,
			"filename": safe_filename,
			"content_type": content_type,
			"size_bytes": size_bytes,
			# Media Upload Session only allows pending/confirmed/expired. The file is
			# already in R2, but the session stays "pending" until submit_ugc_proof
			# verifies it and flips it to "confirmed".
			"status": "pending",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

		return _ok({"upload_id": media_id, "object_key": object_key})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"upload_ugc_video_proxy: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def submit_ugc_proof(outlet_id, submission_id, upload_id):
	"""Confirm the uploaded proof video and queue AI view-count verification."""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		submission = _load_owned_submission(submission_id, restaurant, customer)
		if not submission:
			return _err("SUBMISSION_NOT_FOUND")
		if submission.status not in ("story_verified", "proof_submitted"):
			return _err("STORY_NOT_VERIFIED")

		session = frappe.db.get_value(
			"Media Upload Session", {"upload_id": upload_id},
			["object_key", "content_type", "size_bytes", "owner_name"], as_dict=True,
		)
		if not session or session.owner_name != submission.name:
			return _err("UPLOAD_NOT_FOUND")

		verification = verify_object_exists(session.object_key)
		if not verification.get("exists"):
			return _err("UPLOAD_INCOMPLETE", "We couldn't find your video. Please retry.")

		cdn_url = get_cdn_url(session.object_key)
		# Dedup signal: prefer the storage ETag (content MD5), fall back to a key hash.
		etag = (verification.get("etag") or "").strip('"')
		proof_hash = etag or hashlib.sha1(session.object_key.encode()).hexdigest()

		# Idempotency: reuse the Media Asset if this upload was already confirmed.
		asset_name = frappe.db.get_value("Media Asset", {"media_id": upload_id}, "name")
		if not asset_name:
			asset = frappe.get_doc({
				"doctype": "Media Asset",
				"media_id": upload_id,
				"outlet": restaurant,
				"owner_doctype": PROOF_OWNER_DOCTYPE,
				"owner_name": submission.name,
				"media_role": PROOF_MEDIA_ROLE,
				"media_kind": "video",
				"source_filename": session.object_key.split("/")[-1],
				"source_mime_type": session.content_type,
				"source_size_bytes": verification.get("size") or session.size_bytes,
				"storage_provider": "cloudflare_r2",
				"raw_object_key": session.object_key,
				"primary_url": cdn_url,
				"status": "uploaded",
				"is_active": 1,
			})
			asset.insert(ignore_permissions=True)
			asset_name = asset.name

		frappe.db.set_value("Media Upload Session", {"upload_id": upload_id}, "status", "confirmed")

		submission.proof_video = asset_name
		submission.proof_video_hash = proof_hash
		submission.proof_submitted_at = now_datetime()
		submission.status = "proof_submitted"
		submission.save(ignore_permissions=True)
		frappe.db.commit()

		# Hand off to media processing first (which will trigger AI verification after compression)
		frappe.enqueue(
			"flamezo_backend.flamezo.media.jobs.process_media_asset",
			media_asset_name=asset_name,
			queue="default",
			timeout=600,
			is_async=True,
			now=False,
			enqueue_after_commit=True,
		)

		# Notify customer their proof was received and is under review
		# Notification is skipped here so the user only gets the final cashback message.
		# _notify(submission.name, "proof_received")

		return _ok({"status": "proof_submitted"})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"submit_ugc_proof: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def get_ugc_status(outlet_id, order_id):
	"""Status of the diner's UGC claim for an order (for the in-progress / wallet UI)."""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		name = frappe.db.get_value(
			"UGC Story Submission",
			{"order": order_id, "customer": customer, "outlet": restaurant},
			"name", order_by="creation desc",
		)
		if not name:
			return _ok({"exists": False})

		sub = frappe.get_doc("UGC Story Submission", name)
		return _ok({
			"exists": True,
			"submission_id": sub.name,
			"status": sub.status,
			"cashback_coins": cint(sub.cashback_coins),
			"order_amount": flt(sub.order_amount),
			"proof_window_open": _proof_window_open(sub),
		})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"get_ugc_status: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def get_outlet_ugc_status(outlet_id):
	"""
	Lightweight public endpoint — returns whether UGC cashback is active for a
	restaurant. Used by the consumer app to show/hide the promo banner and the
	ugc-claim page without requiring authentication.
	Active = story template uploaded AND a flat-discount viewer coupon is set.
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		config = _get_active_config(restaurant)
		active = _is_ugc_active(config) if config else False
		return _ok({
			"ugc_active": active,
			# Platform-fixed explainer copy. Served from here so the web app and the
			# Flutter app render the same words without either hardcoding them —
			# these are the same constants the order-scoped endpoints return.
			"headline": PLATFORM_HEADLINE,
			"instructions": PLATFORM_INSTRUCTIONS,
			"terms": PLATFORM_TERMS,
			"steps": PLATFORM_STEPS,
			"redeem_steps": PLATFORM_REDEEM_STEPS,
			"facts": _platform_facts(),
			"terms_list": _platform_terms_list(),
			"min_order_amount": PLATFORM_MIN_ORDER,
			"cashback_percent_cap": PLATFORM_CASHBACK_PERCENT_CAP,
			"proof_window_hours": PLATFORM_PROOF_WINDOW_HOURS,
			"validity_days": UGC_CASHBACK_VALIDITY_DAYS,
			"max_claims_per_30d": PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D,
		})
	except frappe.DoesNotExistError:
		return _ok({"ugc_active": False})
	except Exception as e:
		frappe.log_error(f"get_outlet_ugc_status: {e}", "UGC")
		return _ok({"ugc_active": False})  # fail-safe: hide the feature on error


@frappe.whitelist(allow_guest=True)
def get_claimable_orders(outlet_id, phone):
	"""
	Return the customer's recent completed orders for this restaurant that are
	eligible for a UGC cashback claim. Mirrors the loyalty API auth pattern:
	phone + session token are validated together.
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return _err("INVALID_PHONE", "Invalid phone number")

		session_token = get_customer_token()
		if not session_token or not validate_customer_session(normalized_phone, session_token):
			return _err("SESSION_REQUIRED", "Please verify your phone to continue.")

		# Real outlet name for the claim page (the WhatsApp deep link can't
		# resolve the brand config, so the page must get the name from the API).
		outlet_name = frappe.db.get_value("Outlet", restaurant, "outlet_name") or ""

		config = _get_active_config(restaurant)
		if not config or not _is_ugc_active(config):
			return _ok({"orders": [], "outletName": outlet_name})

		# Fetch completed orders within the claim window (covers delayed claims)
		from frappe.utils import add_days, today
		since = add_days(today(), -CLAIM_WINDOW_DAYS)
		rows = frappe.db.sql(
			"""
			SELECT name, order_number, total, payment_status, status, creation
			FROM `tabOrder`
			WHERE outlet = %s
			  AND customer_phone = %s
			  AND payment_status = 'completed'
			  AND DATE(creation) >= %s
			  AND order_number LIKE 'FZ-%%'
			ORDER BY creation DESC
			LIMIT 10
			""",
			(restaurant, phone, since),
			as_dict=True,
		)

		# Filter to eligible ones and check for existing submissions
		items = []
		for row in rows:
			order_id = row["name"]
			# Last date this order can still be claimed.
			expires_on = add_days(row["creation"], CLAIM_WINDOW_DAYS)
			# Skip if already has an active submission
			existing = _active_submission_for_order(order_id)
			if existing:
				items.append({
					"orderId": order_id,
					"orderNumber": row["order_number"],
					"amount": flt(row["total"]),
					"maxCashback": _max_cashback(row["total"]),
					"expiresOn": expires_on,
					"alreadyClaimed": True,
					"submissionId": existing.name,
					"submissionStatus": existing.status,
				})
				continue
			if flt(row["total"]) < PLATFORM_MIN_ORDER:
				continue
			items.append({
				"orderId": order_id,
				"orderNumber": row["order_number"],
				"amount": flt(row["total"]),
				"maxCashback": _max_cashback(row["total"]),
				"expiresOn": expires_on,
				"alreadyClaimed": False,
			})

		return _ok({"orders": items, "outletName": outlet_name})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"get_claimable_orders: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def get_claimable_orders_bulk(outlet_ids, phone):
	"""
	Same eligibility logic as `get_claimable_orders`, batched across multiple
	outlets in a single query. Lets the wallet "Claim your cashback" feed
	replace up to 8 sequential HTTP round-trips (one per recently-paid outlet)
	with one call.
	"""
	try:
		if isinstance(outlet_ids, str):
			raw_ids = [r.strip() for r in outlet_ids.split(",") if r.strip()]
		else:
			raw_ids = [str(r).strip() for r in outlet_ids if str(r).strip()]

		normalized_phone = normalize_phone(phone)
		if not normalized_phone:
			return _err("INVALID_PHONE", "Invalid phone number")

		session_token = get_customer_token()
		if not session_token or not validate_customer_session(normalized_phone, session_token):
			return _err("SESSION_REQUIRED", "Please verify your phone to continue.")

		# Resolve + de-dupe valid outlets, dropping any that don't exist
		# rather than failing the whole batch.
		resolved = {}
		for rid in raw_ids:
			try:
				resolved[rid] = validate_restaurant_for_api(rid)
			except Exception:
				continue

		if not resolved:
			return _ok({"byOutlet": {}})

		outlet_names = {
			doc_id: (frappe.db.get_value("Outlet", doc_id, "outlet_name") or "")
			for doc_id in set(resolved.values())
		}

		from frappe.utils import add_days, today
		since = add_days(today(), -CLAIM_WINDOW_DAYS)
		doc_ids = list(set(resolved.values()))
		placeholders = ", ".join(["%s"] * len(doc_ids))
		rows = frappe.db.sql(
			f"""
			SELECT name, outlet, order_number, total, payment_status, status, creation
			FROM `tabOrder`
			WHERE outlet IN ({placeholders})
			  AND customer_phone = %s
			  AND payment_status = 'completed'
			  AND DATE(creation) >= %s
			  AND order_number LIKE 'FZ-%%'
			ORDER BY creation DESC
			""",
			(*doc_ids, phone, since),
			as_dict=True,
		)

		# Only outlets with an active UGC config can surface claims.
		active_doc_ids = {
			doc_id for doc_id in doc_ids
			if (config := _get_active_config(doc_id)) and _is_ugc_active(config)
		}

		by_outlet: dict = {}
		counts: dict = {}
		for row in rows:
			doc_id = row["outlet"]
			if doc_id not in active_doc_ids:
				continue
			if counts.get(doc_id, 0) >= 10:
				continue
			counts[doc_id] = counts.get(doc_id, 0) + 1

			order_id = row["name"]
			expires_on = add_days(row["creation"], CLAIM_WINDOW_DAYS)
			existing = _active_submission_for_order(order_id)
			item = {
				"orderId": order_id,
				"orderNumber": row["order_number"],
				"amount": flt(row["total"]),
				"maxCashback": _max_cashback(row["total"]),
				"expiresOn": expires_on,
			}
			if existing:
				item.update({"alreadyClaimed": True, "submissionId": existing.name, "submissionStatus": existing.status})
			else:
				if flt(row["total"]) < PLATFORM_MIN_ORDER:
					continue
				item["alreadyClaimed"] = False

			# Key the response by the outlet slug the client already uses.
			for slug, doc_id2 in resolved.items():
				if doc_id2 == doc_id:
					bucket = by_outlet.setdefault(slug, {"outletName": outlet_names.get(doc_id, ""), "orders": []})
					bucket["orders"].append(item)

		return _ok({"byOutlet": by_outlet})
	except Exception as e:
		frappe.log_error(f"get_claimable_orders_bulk: {e}", "UGC")
		return _err("INTERNAL_ERROR")


def _load_owned_submission(submission_id, restaurant, customer):
	if not frappe.db.exists("UGC Story Submission", submission_id):
		return None
	sub = frappe.get_doc("UGC Story Submission", submission_id)
	if sub.outlet != restaurant or sub.customer != customer:
		return None
	return sub


def _proof_window_open(submission):
	# Proof window opens when staff verifies the story, not when the offer started.
	# Fall back to submission_date only if story_verified_at is somehow missing.
	anchor = submission.story_verified_at or submission.submission_date
	if not anchor:
		return False
	deadline = add_to_date(get_datetime(anchor), hours=PLATFORM_PROOF_WINDOW_HOURS)
	return now_datetime() <= deadline


# ══════════════════════════════════════════════════════════════════════════════
#  STAFF ENDPOINTS  (Restaurant Admin / Staff)
# ══════════════════════════════════════════════════════════════════════════════
def _resolve_restaurant(outlet_id):
	from flamezo_backend.flamezo.utils.api_helpers import get_restaurant_from_id
	doc_name = frappe.db.get_value("Outlet", outlet_id, "name") or get_restaurant_from_id(outlet_id)
	if not doc_name:
		frappe.throw(_("Outlet not found"), frappe.DoesNotExistError)
	return doc_name


def _assert_staff_or_admin(restaurant):
	"""Allow Restaurant Admin OR Staff for this restaurant (plus global/supervisor)."""
	user = frappe.session.user
	roles = frappe.get_roles(user)
	if (
		user == "Administrator"
		or any(r in GLOBAL_ADMIN_ROLES or r in SUPERVISOR_ROLES for r in roles)
		or "Outlet Admin" in roles
	):
		return
	rec_role = frappe.db.get_value(
		"Outlet User", {"user": user, "outlet": restaurant, "is_active": 1}, "role"
	)
	if rec_role not in ("Outlet Admin", "Outlet Staff"):
		frappe.throw(_("You don't have access to this outlet."), frappe.PermissionError)


def _enrich_submission_row(row):
	cust = frappe.db.get_value("Customer", row.get("customer"), ["customer_name", "phone"], as_dict=True) or {}
	row["customer_name"] = cust.get("customer_name")
	row["customer_phone"] = cust.get("phone")
	if row.get("template_used"):
		row["template_url"] = frappe.db.get_value("Media Asset", row["template_used"], "primary_url")
	if row.get("proof_video"):
		# Privacy: the restaurant can only view the diner's story proof for a limited
		# window; after that the URL is withheld (and the file is later purged).
		proof_dt = row.get("proof_submitted_at")
		within_window = True
		if proof_dt:
			age_days = (now_datetime() - get_datetime(proof_dt)).total_seconds() / 86400
			within_window = age_days < PLATFORM_STAFF_PROOF_DAYS
		if within_window:
			row["proof_video_url"] = frappe.db.get_value("Media Asset", row["proof_video"], "primary_url")
		else:
			row["proof_hidden"] = True
	return row


@frappe.whitelist()
def list_pending_story_verifications(outlet_id, page=1, page_size=20):
	"""Day-0 queue: stories the diner shared, awaiting in-person staff verification."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)
		page, page_size = cint(page) or 1, cint(page_size) or 20
		filters = {"outlet": restaurant, "status": "story_shared"}
		total = frappe.db.count("UGC Story Submission", filters=filters)
		rows = frappe.get_all(
			"UGC Story Submission", filters=filters,
			fields=["name", "customer", "order", "order_amount", "template_used",
					"story_shared_at", "submission_date"],
			order_by="story_shared_at asc",
			limit_page_length=page_size, start=(page - 1) * page_size,
		)
		return _ok({"submissions": [_enrich_submission_row(r) for r in rows],
					"total": total, "page": page, "page_size": page_size})
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"list_pending_story_verifications: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def verify_ugc_story(outlet_id, submission_id, action, notes=None):
	"""Staff approves/rejects the in-person story check. action: 'approve' | 'reject'."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)

		sub = frappe.get_doc("UGC Story Submission", submission_id)
		if sub.outlet != restaurant:
			return _err("NOT_FOUND")
		if sub.status != "story_shared":
			return _err("INVALID_STATE", f"Cannot verify from '{sub.status}'.")

		if action == "approve":
			sub.status = "story_verified"
			sub.story_verified_by = frappe.session.user
			sub.story_verified_at = now_datetime()
			sub.save(ignore_permissions=True)
			frappe.db.commit()
			_notify(sub.name, "story_verified")
			return _ok({"status": "story_verified"})
		elif action == "reject":
			sub.status = "rejected"
			sub.rejection_reason = notes or "Story not posted as required."
			sub.reviewed_by = frappe.session.user
			sub.save(ignore_permissions=True)
			frappe.db.commit()
			_notify(sub.name, "story_rejected")
			return _ok({"status": "rejected"})
		return _err("INVALID_ACTION")
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except frappe.DoesNotExistError:
		return _err("NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"verify_ugc_story: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def verify_ugc_story_with_pin(outlet_id, submission_id, pin):
	"""
	Waiter enters the restaurant PIN on the merchant dashboard to approve a story.
	PIN check replaces the raw Verify button — reject still uses the plain endpoint.
	"""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)

		stored_pin = frappe.db.get_value("Outlet Config", restaurant, "offer_verification_pin") or ""
		if not stored_pin:
			return _err("PIN_NOT_SET", "No verification PIN set for this outlet. Set it under Setup & Config.")
		if str(pin).strip() != str(stored_pin).strip():
			return _err("INVALID_PIN", "Incorrect PIN — please try again.")

		sub = frappe.get_doc("UGC Story Submission", submission_id)
		if sub.outlet != restaurant:
			return _err("NOT_FOUND")
		if sub.status != "story_shared":
			return _err("INVALID_STATE", f"Cannot verify from '{sub.status}'.")

		sub.status = "story_verified"
		sub.story_verified_by = frappe.session.user
		sub.story_verified_at = now_datetime()
		sub.save(ignore_permissions=True)
		frappe.db.commit()
		_notify(sub.name, "story_verified")
		return _ok({"status": "story_verified"})
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except frappe.DoesNotExistError:
		return _err("NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"verify_ugc_story_with_pin: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def claim_ugc_with_pin(outlet_id, order_id, pin):
	"""
	Customer-facing: waiter enters the restaurant PIN on the customer's phone.
	Creates the submission and immediately marks it story_verified in one step.
	No submission exists before this call — the card stays active until PIN is correct.
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		# Verify PIN first — fail fast before touching any data
		stored_pin = frappe.db.get_value("Outlet Config", restaurant, "offer_verification_pin") or ""
		if not stored_pin:
			return _err("PIN_NOT_SET", "No verification PIN has been set for this outlet.")
		if str(pin).strip() != str(stored_pin).strip():
			return _err("INVALID_PIN", "Incorrect PIN.")

		config = _get_active_config(restaurant)
		if not config or not _is_ugc_active(config):
			return _err("NOT_AVAILABLE")

		order = _load_owned_order(restaurant, order_id, customer)
		if not order:
			return _err("ORDER_NOT_FOUND")

		# Idempotent: if a submission already exists, just verify it if possible
		existing = _active_submission_for_order(order_id)
		if existing:
			if existing.status in ("offer_shown", "story_shared"):
				existing.status = "story_verified"
				existing.story_verified_at = now_datetime()
				existing.save(ignore_permissions=True)
				frappe.db.commit()
				_notify(existing.name, "story_verified")
				return _ok({"status": "story_verified", "submission_id": existing.name})
			return _ok({"status": existing.status, "submission_id": existing.name})

		# Gate checks
		if not _order_is_eligible(order):
			return _err("ORDER_NOT_COMPLETED")
		if flt(order.total) < PLATFORM_MIN_ORDER:
			return _err("BELOW_MIN_ORDER")
		if _is_blocked(customer):
			return _err("NOT_ELIGIBLE")
		if _claims_last_30d(customer, restaurant) >= PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D:
			return _err("LIMIT_REACHED")

		# Create submission directly in story_verified state
		submission = frappe.get_doc({
			"doctype": "UGC Story Submission",
			"outlet": restaurant,
			"customer": customer,
			"order": order.name,
			"order_amount": flt(order.total),
			"status": "story_verified",
			"submission_date": now_datetime(),
			"story_verified_at": now_datetime(),
		})
		submission.insert(ignore_permissions=True)
		frappe.db.commit()
		_notify(submission.name, "story_verified")
		return _ok({"status": "story_verified", "submission_id": submission.name})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"claim_ugc_with_pin: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def list_flagged_ugc(outlet_id, page=1, page_size=20):
	"""Day-1 queue: claims the AI couldn't auto-approve, awaiting human review."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)
		page, page_size = cint(page) or 1, cint(page_size) or 20
		filters = {"outlet": restaurant, "status": "flagged"}
		total = frappe.db.count("UGC Story Submission", filters=filters)
		rows = frappe.get_all(
			"UGC Story Submission", filters=filters,
			fields=["name", "customer", "order", "order_amount", "proof_video",
					"ai_view_count", "ai_confidence", "ai_tamper_signals", "proof_submitted_at"],
			order_by="proof_submitted_at asc",
			limit_page_length=page_size, start=(page - 1) * page_size,
		)
		return _ok({"submissions": [_enrich_submission_row(r) for r in rows],
					"total": total, "page": page, "page_size": page_size})
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"list_flagged_ugc: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def review_ugc(outlet_id, submission_id, action, view_count=None, notes=None):
	"""Staff resolves a flagged claim. action: 'approve' | 'reject'."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)

		sub = frappe.get_doc("UGC Story Submission", submission_id)
		if sub.outlet != restaurant:
			return _err("NOT_FOUND")
		if sub.status not in ("flagged", "proof_submitted"):
			return _err("INVALID_STATE", f"Cannot review from '{sub.status}'.")

		if action == "reject":
			# Use db.set_value (not sub.save) so a stale/invalid link on the
			# submission — e.g. a legacy customer value that no longer resolves —
			# can't block staff from rejecting the proof with an INTERNAL_ERROR.
			frappe.db.set_value("UGC Story Submission", sub.name, {
				"status": "rejected",
				"rejection_reason": notes or "Proof rejected on review.",
				"reviewed_by": frappe.session.user,
			})
			frappe.db.commit()
			_notify(sub.name, "proof_rejected")
			return _ok({"status": "rejected"})

		if action == "approve":
			views = cint(view_count) if view_count is not None else cint(sub.ai_view_count)
			if views <= 0:
				return _err("VIEW_COUNT_REQUIRED", "Enter the view count to approve.")
			entry = credit_ugc_cashback(sub, view_count=views, reviewed_by=frappe.session.user, source="manual")
			if not entry:
				return _err("CREDIT_FAILED")
			coins = cint(frappe.db.get_value("UGC Story Submission", sub.name, "cashback_coins"))
			return _ok({"status": "credited", "cashback_coins": coins})

		return _err("INVALID_ACTION")
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except frappe.DoesNotExistError:
		return _err("NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"review_ugc: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def get_ugc_analytics(outlet_id, days=None):
	"""Aggregate UGC performance for the merchant dashboard."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)

		filters = {"outlet": restaurant}
		if days:
			since = add_to_date(now_datetime(), days=-cint(days))
			filters["submission_date"] = [">=", since]

		rows = frappe.get_all(
			"UGC Story Submission",
			filters=filters,
			fields=["status", "cashback_coins", "ai_view_count", "order_amount"],
		)
		by_status = {}
		coins_issued = 0
		reach = 0
		credited = 0
		total_revenue = 0.0
		for r in rows:
			by_status[r.status] = by_status.get(r.status, 0) + 1
			if r.status == "credited":
				credited += 1
				coins_issued += cint(r.cashback_coins)
				reach += cint(r.ai_view_count)
				total_revenue += flt(r.order_amount or 0)
		verified_or_better = sum(
			by_status.get(s, 0) for s in ("story_verified", "proof_submitted", "credited", "flagged")
		)
		approval_rate = round((credited / verified_or_better) * 100, 1) if verified_or_better else 0.0

		config = _get_active_config(restaurant)
		budget = cint(config.monthly_budget_coins) if config else 0
		issued_this_month = cint(config.coins_issued_this_month) if config else 0

		# Compute live business impact
		referral_revenue = round(reach * 1.5, 2)
		roi = round((total_revenue + referral_revenue) / coins_issued, 1) if coins_issued else 0.0
		conversion_rate = round((credited / reach) * 100, 1) if reach else 4.8

		return _ok({
			"total_submissions": len(rows),
			"by_status": by_status,
			"coins_issued": coins_issued,
			"reach_impressions": reach,
			"approval_rate": approval_rate,
			"monthly_budget": budget,
			"issued_this_month": issued_this_month,
			"total_revenue": total_revenue,
			"referral_revenue": referral_revenue,
			"roi": roi,
			"conversion_rate": conversion_rate,
			"days": cint(days) if days else "all",
		})
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"get_ugc_analytics: {e}", "UGC")
		return _err("INTERNAL_ERROR")


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG MANAGEMENT  (staff — the dashboard config page)
# ══════════════════════════════════════════════════════════════════════════════
# Only the linked coupons are restaurant-editable now — caps, budget, AI and copy
# are all platform-fixed constants. (The offer itself is mandatory/always-on.)
_CONFIG_SCALAR_FIELDS = (
	"viewer_coupon_code",
	"viewer_discount_type",
	"viewer_discount_value",
	"viewer_discount_cap",
	"viewer_coupon_description",
)


def _get_or_create_config(restaurant):
	name = frappe.db.get_value("UGC Cashback Config", {"outlet": restaurant}, "name")
	if name:
		return frappe.get_doc("UGC Cashback Config", name)
	doc = frappe.get_doc({
		"doctype": "UGC Cashback Config",
		"outlet": restaurant,
		"is_active": 1,  # mandatory, always-on feature
		"budget_period": _current_period(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


def _config_to_dict(config):
	templates = []
	for row in (config.template_assets or []):
		info = frappe.db.get_value(
			"Media Asset", row.media_asset, ["primary_url", "media_kind"], as_dict=True
		) if row.media_asset else None
		templates.append({
			"media_asset": row.media_asset, "label": row.label,
			"is_default": cint(row.is_default),
			"url": (info or {}).get("primary_url"),
			"kind": (info or {}).get("media_kind"),
		})
	data = {f: config.get(f) for f in _CONFIG_SCALAR_FIELDS}
	data.update({
		"name": config.name,
		"restaurant": config.outlet,
		"is_active": cint(config.is_active),
		"coins_issued_this_month": cint(config.coins_issued_this_month),
		"templates": templates,
		"viewer_coupon": _inline_coupon_brief(config),
		"story_preview_url": config.story_preview_url or None,
		"ugc_is_active": _is_ugc_active(config),
	})
	return data


@frappe.whitelist()
def get_ugc_config(outlet_id):
	"""Fetch (creating if missing) the UGC config for the dashboard."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)
		config = _get_or_create_config(restaurant)
		return _ok(_config_to_dict(config))
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"get_ugc_config: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def save_ugc_config(outlet_id, payload):
	"""Upsert scalar config fields and (optionally) replace the template list."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)
		data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})

		config = _get_or_create_config(restaurant)
		# is_active is handled explicitly (not via _CONFIG_SCALAR_FIELDS) so it's
		# always coerced to int and never accidentally set by an unrelated field loop.
		if "is_active" in data:
			config.is_active = cint(data["is_active"])
		for f in _CONFIG_SCALAR_FIELDS:
			if f in data:
				config.set(f, data.get(f))

		if "templates" in data and isinstance(data["templates"], list):
			config.set("template_assets", [])
			# Exactly one template is allowed per restaurant.
			for t in data["templates"][:1]:
				media = t.get("media_asset")
				if not media or not frappe.db.exists("Media Asset", media):
					continue
				config.append("template_assets", {
					"media_asset": media,
					"label": t.get("label"),
					"is_default": 1,
				})

		config.save(ignore_permissions=True)
		frappe.db.commit()

		# Kick off compositing whenever the config has both a template and a coupon.
		# The job runs in the background so save_ugc_config returns instantly.
		# It also clears any stale story_preview_url so the diner never sees an
		# outdated composite while the new one is being generated.
		if config.template_assets and (config.viewer_coupon_code or "").strip():
			_enqueue_config_preview(config)

		return _ok(_config_to_dict(config))
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except frappe.ValidationError as e:
		return _err("VALIDATION_ERROR", str(e))
	except Exception as e:
		frappe.log_error(f"save_ugc_config: {e}", "UGC")
		return _err("INTERNAL_ERROR")


def _purge_template_media(media_asset, restaurant):
	"""Delete a template's Media Asset AND its Cloudflare R2 objects.

	Routes through the standard media pipeline (soft-delete + cleanup_deleted_media)
	so the raw object, all image variants, and any video poster are removed from R2
	— exactly like deleting media anywhere else in the app. Safe-guarded to only
	ever touch a UGC template owned by this restaurant.
	"""
	info = frappe.db.get_value(
		"Media Asset", media_asset,
		["name", "media_id", "raw_object_key", "outlet", "owner_doctype", "is_deleted"],
		as_dict=True,
	)
	if not info:
		return
	if info.outlet != restaurant or info.owner_doctype != TEMPLATE_OWNER_DOCTYPE:
		return  # never delete an unrelated asset
	if info.is_deleted:
		return
	try:
		if info.media_id:
			from flamezo_backend.flamezo.media.api import delete_media_asset
			delete_media_asset(info.media_id)  # soft-delete + async R2 cleanup (raw + variants + poster)
		else:
			# Fallback for assets without a media_id: delete the raw object + doc directly.
			from flamezo_backend.flamezo.media.storage import delete_object
			if info.raw_object_key:
				delete_object(info.raw_object_key)
			frappe.delete_doc("Media Asset", info.name, ignore_permissions=True, force=True)
	except Exception as e:
		frappe.log_error(f"UGC template media purge failed for {media_asset}: {e}", "UGC Cleanup")


@frappe.whitelist()
def delete_ugc_template(outlet_id, media_asset):
	"""Remove the story template from the config AND delete its file from Cloudflare R2."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)
		config = _get_or_create_config(restaurant)

		remaining = [r for r in (config.template_assets or []) if r.media_asset != media_asset]
		config.set("template_assets", [])
		for r in remaining:
			config.append("template_assets", {"media_asset": r.media_asset, "label": r.label, "is_default": 1})

		# Clear the pre-generated preview — it was composited from the deleted media.
		config.story_preview_url = None

		config.save(ignore_permissions=True)

		_purge_template_media(media_asset, restaurant)
		frappe.db.commit()
		return _ok(_config_to_dict(config))
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"delete_ugc_template: {e}", "UGC")
		return _err("INTERNAL_ERROR")


# ══════════════════════════════════════════════════════════════════════════════
#  CREDIT HELPER  (shared by AI verifier + staff review — idempotent)
# ══════════════════════════════════════════════════════════════════════════════
@frappe.whitelist(allow_guest=True)
def get_my_ugc_vouchers(outlet_id=None):
	"""
	List the diner's active UGC vouchers.
	If outlet_id is provided, returns only the voucher for that outlet.
	Used by the consumer storefront to surface the voucher card.
	"""
	try:
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED", "Please verify your phone to continue.")

		now = now_datetime()
		filters = {
			"customer": customer,
			"status": "active",
			"expires_at": [">", now],
			"balance": [">", 0],
		}
		if outlet_id:
			try:
				restaurant = validate_restaurant_for_api(outlet_id)
			except Exception:
				return _err("OUTLET_NOT_FOUND")
			filters["outlet"] = restaurant

		rows = frappe.get_all(
			"UGC Voucher",
			filters=filters,
			fields=["name", "voucher_code", "outlet", "original_amount", "balance", "issued_at", "expires_at"],
			order_by="expires_at asc",
		)

		# Consolidate: multiple active vouchers for the same outlet collapse into
		# ONE combined coupon so the diner never sees stacked/double coupons on the
		# Pay Bill page. Sum the balances onto the latest-expiring voucher (keeps
		# the most redemption time) and void the rest; the single kept code then
		# holds the full balance, so redemption drains all of it.
		by_outlet = {}
		for r in rows:
			by_outlet.setdefault(r["outlet"], []).append(r)
		merged_rows = []
		mutated = False
		for _rest, grp in by_outlet.items():
			if len(grp) == 1:
				merged_rows.append(grp[0])
				continue
			keeper = grp[-1]  # rows are expires_at asc → last = latest expiry
			extra = sum(flt(g["balance"]) for g in grp if g is not keeper)
			if extra > 0:
				keeper["balance"] = flt(keeper["balance"]) + extra
				frappe.db.set_value("UGC Voucher", keeper["name"], "balance", keeper["balance"])
				for g in grp:
					if g is keeper:
						continue
					frappe.db.set_value("UGC Voucher", g["name"], {"balance": 0, "status": "expired"})
				mutated = True
			merged_rows.append(keeper)
		if mutated:
			frappe.db.commit()
		rows = merged_rows

		# Resolve restaurant meta
		restaurant_names = list({r["outlet"] for r in rows})
		meta = {}
		if restaurant_names:
			for m in frappe.get_all(
				"Outlet",
				filters={"name": ["in", restaurant_names]},
				fields=["name", "outlet_id", "outlet_name", "city", "logo"],
			):
				meta[m["name"]] = m

		items = []
		for r in rows:
			m = meta.get(r["outlet"], {})
			days_left = date_diff(r["expires_at"], today()) if r["expires_at"] else None
			# What the customer can use on their next visit (33% of a typical bill).
			# We don't know the next bill here, so we show the balance and the rule.
			items.append({
				"voucherCode": r["voucher_code"],
				"outletId": r["outlet"],
				# Public URL slug (the /[outlet_id] route segment). Falls back to the
				# doc name so navigation still resolves if the slug field is unset.
				"outletSlug": m.get("outlet_id") or r["outlet"],
				"outletName": m.get("outlet_name") or r["outlet"],
				"city": m.get("city") or "",
				"logo": get_cdn_url(m.get("logo")) if m.get("logo") else None,
				"originalAmount": flt(r["original_amount"]),
				"balance": flt(r["balance"]),
				"expiresOn": str(r["expires_at"]) if r["expires_at"] else None,
				"daysLeft": days_left,
				"perVisitPct": PLATFORM_VOUCHER_PER_VISIT_PCT,
			})
		return _ok({"items": items})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_my_ugc_vouchers")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def get_my_ugc_submissions(outlet_id=None, page=1, page_size=10):
	"""
	Paginated list of all UGC Story Submissions for the logged-in diner.
	Optionally filtered to a single restaurant.
	Used by the consumer app's "My Story Claims" history view.

	Returns lightweight rows — enough to render status chips, cashback amounts,
	and a deep-link "Continue" button for in-progress claims.
	"""
	try:
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED", "Please verify your phone to continue.")

		page, page_size = cint(page) or 1, min(cint(page_size) or 10, 50)
		filters: dict = {"customer": customer}

		if outlet_id:
			try:
				restaurant = validate_restaurant_for_api(outlet_id)
				filters["outlet"] = restaurant
			except Exception:
				pass

		total = frappe.db.count("UGC Story Submission", filters=filters)
		rows = frappe.get_all(
			"UGC Story Submission",
			filters=filters,
			fields=[
				"name", "outlet", "order", "status",
				"order_amount", "cashback_coins",
				"submission_date", "story_verified_at",
			],
			order_by="submission_date desc",
			limit_page_length=page_size,
			start=(page - 1) * page_size,
		)

		items = []
		for r in rows:
			outlet_name = frappe.db.get_value("Outlet", r.outlet, "outlet_name") or r.outlet
			outlet_slug = frappe.db.get_value("Outlet", r.outlet, "outlet_id") or r.outlet
			items.append({
				"submission_id": r.name,
				"outlet_id": outlet_slug,
				"outlet_name": outlet_name,
				"order_id": r.order,
				"status": r.status,
				"order_amount": flt(r.order_amount),
				"cashback_coins": cint(r.cashback_coins),
				"submission_date": str(r.submission_date) if r.submission_date else None,
				"story_verified_at": str(r.story_verified_at) if r.story_verified_at else None,
				"proof_window_open": _proof_window_open(frappe._dict(r)),
			})

		return _ok({"items": items, "total": total, "page": page, "page_size": page_size})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_my_ugc_submissions")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def activate_ugc_with_pin(outlet_id, voucher_code, pin):
	"""
	Waiter enters the 4-digit PIN on the customer's phone to activate a UGC voucher
	for redemption at this restaurant. Activation is valid for UGC_PIN_LOCK_HOURS hours.

	Guards:
	- Customer must not have an active regular offer claim at this restaurant in the last 4h
	  (UGC redemption cannot be stacked with other offers).
	- Voucher must be active, unexpired, and belong to this restaurant.
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		# Validate PIN
		stored_pin = frappe.db.get_value("Outlet Config", restaurant, "offer_verification_pin") or ""
		if not stored_pin:
			return _err("PIN_NOT_SET", "This outlet has not set up offer verification.")
		if str(pin).strip() != stored_pin:
			return _err("INVALID_PIN", "Incorrect PIN — please ask your waiter.")

		# Fetch and validate voucher
		voucher = frappe.db.get_value(
			"UGC Voucher",
			{"voucher_code": voucher_code, "customer": customer, "outlet": restaurant},
			["name", "balance", "status", "expires_at"],
			as_dict=True,
		)
		if not voucher:
			return _err("VOUCHER_NOT_FOUND", "Voucher not found or does not belong to you.")
		if voucher.status != "active":
			return _err("VOUCHER_INACTIVE", "This voucher has already been fully redeemed or expired.")
		if get_datetime(voucher.expires_at) < now_datetime():
			frappe.db.set_value("UGC Voucher", voucher.name, "status", "expired")
			frappe.db.commit()
			return _err("VOUCHER_EXPIRED", "This voucher has expired.")

		# UGC cannot be combined with a regular offer claim active in the last 4 hours
		four_hours_ago = add_to_date(now_datetime(), hours=-UGC_PIN_LOCK_HOURS)
		has_active_claim = frappe.db.exists(
			"Offer Claim",
			{
				"outlet": restaurant,
				"customer": customer,
				"claimed_at": [">=", four_hours_ago],
				"is_paid": 0,
			},
		)
		if has_active_claim:
			return _err(
				"OFFER_CONFLICT",
				"You have an active offer at this outlet. UGC cashback cannot be combined with other offers.",
			)

		# Stamp the activation on the voucher
		lock_until = add_to_date(now_datetime(), hours=UGC_PIN_LOCK_HOURS)
		frappe.db.set_value("UGC Voucher", voucher.name, {
			"pin_activated_at": now_datetime(),
			"pin_activated_restaurant": restaurant,
		})
		frappe.db.commit()

		return _ok({
			"voucherCode": voucher_code,
			"balance": int(flt(voucher.balance)),
			"lockedUntil": str(lock_until),
			"message": "Cashback activated! Pick your free dish.",
		})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"activate_ugc_with_pin: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def get_ugc_redeemable_dishes(outlet_id, voucher_code, bill_amount):
	"""
	Returns menu products marked is_ugc_redeemable=1 for this restaurant whose price
	fits within min(bill * 30%, voucher_balance).

	This is a read-only *preview* of what the diner can claim, so it does NOT require
	PIN activation — the customer types their bill and immediately sees the dishes that
	fit their cashback. The PIN gate lives on apply_ugc_dish_redemption, which is what
	actually deducts the balance.
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		bill = flt(bill_amount)
		if bill <= 0:
			return _err("INVALID_AMOUNT", "Bill amount must be positive.")

		voucher = frappe.db.get_value(
			"UGC Voucher",
			{"voucher_code": voucher_code, "customer": customer, "outlet": restaurant},
			["name", "balance", "status", "expires_at", "pin_activated_at", "pin_activated_restaurant"],
			as_dict=True,
		)
		if not voucher:
			return _err("VOUCHER_NOT_FOUND")
		if voucher.status != "active":
			return _err("VOUCHER_INACTIVE")
		if get_datetime(voucher.expires_at) < now_datetime():
			frappe.db.set_value("UGC Voucher", voucher.name, "status", "expired")
			frappe.db.commit()
			return _err("VOUCHER_EXPIRED")

		# NOTE: No PIN gate here — this is a preview of claimable dishes shown as soon
		# as the diner enters their bill. PIN activation is enforced at redemption time
		# (apply_ugc_dish_redemption), which is what actually spends the balance.

		# Compute dish budget
		max_budget = int(min(bill * PLATFORM_VOUCHER_PER_VISIT_PCT / 100.0, flt(voucher.balance)))

		dishes = frappe.get_all(
			"Menu Product",
			filters={
				"outlet": restaurant,
				"is_active": 1,
				"price": ["<=", max_budget],
			},
			fields=["name", "product_name", "price", "original_price", "description",
					"is_vegetarian", "category_name", "main_category"],
			order_by="price desc",
		)

		# Attach media URL for each dish
		dish_list = []
		for d in dishes:
			media = frappe.db.get_value(
				"Product Media",
				{"parent": d.name, "idx": 1},
				"media_asset",
			)
			media_url = None
			if media:
				media_url = frappe.db.get_value("Media Asset", media, "primary_url")
			dish_list.append({
				"id": d.name,
				"name": d.product_name,
				"price": int(flt(d.price)),
				"originalPrice": int(flt(d.original_price or d.price)),
				"description": d.description or "",
				"isVeg": bool(d.is_vegetarian),
				"category": d.category_name or d.main_category or "",
				"imageUrl": media_url,
			})

		return _ok({
			"dishes": dish_list,
			"dishBudget": max_budget,
			"voucherBalance": int(flt(voucher.balance)),
			"perVisitPct": PLATFORM_VOUCHER_PER_VISIT_PCT,
		})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"get_ugc_redeemable_dishes: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def apply_ugc_dish_redemption(outlet_id, voucher_code, dish_id, bill_amount):
	"""
	Final step: customer has selected a free dish. Deducts the dish price from the
	voucher balance and records the redemption. Requires prior PIN activation.

	Idempotent on (voucher, dish_id) within the same PIN session.
	"""
	try:
		restaurant = validate_restaurant_for_api(outlet_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		bill = flt(bill_amount)

		# Validate voucher + PIN activation
		voucher = frappe.db.get_value(
			"UGC Voucher",
			{"voucher_code": voucher_code, "customer": customer, "outlet": restaurant},
			["name", "balance", "status", "expires_at", "pin_activated_at", "pin_activated_restaurant"],
			as_dict=True,
		)
		if not voucher:
			return _err("VOUCHER_NOT_FOUND")
		if voucher.status != "active":
			return _err("VOUCHER_INACTIVE")
		if get_datetime(voucher.expires_at) < now_datetime():
			frappe.db.set_value("UGC Voucher", voucher.name, "status", "expired")
			frappe.db.commit()
			return _err("VOUCHER_EXPIRED")
		if not voucher.pin_activated_at:
			return _err("PIN_REQUIRED", "PIN activation is required before redeeming.")
		activation_age = now_datetime() - get_datetime(voucher.pin_activated_at)
		if activation_age.total_seconds() > UGC_PIN_LOCK_HOURS * 3600:
			return _err("PIN_EXPIRED", "Your cashback session has expired.")
		if voucher.pin_activated_restaurant != restaurant:
			return _err("WRONG_RESTAURANT")

		# Validate dish
		dish = frappe.db.get_value(
			"Menu Product",
			{"name": dish_id, "outlet": restaurant, "is_active": 1},
			["name", "product_name", "price"],
			as_dict=True,
		)
		if not dish:
			return _err("DISH_NOT_FOUND", "This dish is not available.")

		dish_price = int(flt(dish.price))
		max_budget = int(min(bill * PLATFORM_VOUCHER_PER_VISIT_PCT / 100.0, flt(voucher.balance)))
		if dish_price > max_budget:
			return _err("DISH_TOO_EXPENSIVE", f"This dish exceeds your free-dish budget of ₹{max_budget}.")

		# Idempotency: if same dish was already redeemed in this PIN session, return existing
		pin_session_start = get_datetime(voucher.pin_activated_at)
		existing = frappe.db.get_value(
			"UGC Voucher Redemption",
			{
				"voucher": voucher.name,
				"redeemed_dish": dish_id,
				"redeemed_at": [">=", pin_session_start],
			},
			["name", "amount_used", "balance_after"],
			as_dict=True,
		)
		if existing:
			return _ok({
				"dishName": dish.product_name,
				"dishPrice": dish_price,
				"newBalance": int(flt(existing.balance_after)),
				"voucherCode": voucher_code,
			})

		balance_before = flt(voucher.balance)
		balance_after = balance_before - dish_price
		new_status = "exhausted" if balance_after <= 0 else "active"

		frappe.get_doc({
			"doctype": "UGC Voucher Redemption",
			"voucher": voucher.name,
			"customer": customer,
			"outlet": restaurant,
			"bill_amount": int(bill),
			"amount_used": dish_price,
			"balance_before": int(balance_before),
			"balance_after": int(balance_after),
			"redeemed_at": now_datetime(),
			"redeemed_dish": dish_id,
			"dish_name": dish.product_name,
			"dish_price": dish_price,
		}).insert(ignore_permissions=True)

		frappe.db.set_value("UGC Voucher", voucher.name, {
			"balance": balance_after,
			"status": new_status,
		})
		frappe.db.commit()

		return _ok({
			"dishName": dish.product_name,
			"dishPrice": dish_price,
			"newBalance": int(balance_after),
			"voucherCode": voucher_code,
		})
	except frappe.DoesNotExistError:
		return _err("OUTLET_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"apply_ugc_dish_redemption: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def get_voucher_stats(outlet_id, days=None):
	"""Voucher issuance + redemption stats for the merchant dashboard."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)

		filters = {"outlet": restaurant}
		if days:
			since = add_to_date(now_datetime(), days=-cint(days))
			filters["issued_at"] = [">=", since]

		vouchers = frappe.get_all(
			"UGC Voucher",
			filters=filters,
			fields=["name", "status", "original_amount", "balance", "issued_at"],
		)
		total_issued = len(vouchers)
		total_issued_value = sum(flt(v["original_amount"]) for v in vouchers)
		active = sum(1 for v in vouchers if v["status"] == "active")
		exhausted = sum(1 for v in vouchers if v["status"] == "exhausted")
		expired = sum(1 for v in vouchers if v["status"] == "expired")
		total_redeemed_value = total_issued_value - sum(flt(v["balance"]) for v in vouchers)

		# Redemptions for this restaurant in the same window
		redemption_filters = {"outlet": restaurant}
		if days:
			redemption_filters["redeemed_at"] = [">=", since]
		redemptions = frappe.get_all(
			"UGC Voucher Redemption",
			filters=redemption_filters,
			fields=["amount_used"],
		)
		redemption_count = len(redemptions)

		# Expiring in next 7 days
		expiring_soon = frappe.db.count(
			"UGC Voucher",
			filters={
				"outlet": restaurant,
				"status": "active",
				"expires_at": ["between", [now_datetime(), add_to_date(now_datetime(), days=7)]],
			},
		)

		return _ok({
			"totalIssued": total_issued,
			"totalIssuedValue": int(total_issued_value),
			"active": active,
			"exhausted": exhausted,
			"expired": expired,
			"totalRedeemedValue": int(total_redeemed_value),
			"redemptionCount": redemption_count,
			"expiringSoon": expiring_soon,
			"days": cint(days) if days else "all",
		})
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"get_voucher_stats: {e}", "UGC")
		return _err("INTERNAL_ERROR")



@frappe.whitelist()
def get_ugc_funnel(outlet_id, days=30):
	"""Submission funnel counts for the UGC analytics tab."""
	try:
		restaurant = _resolve_restaurant(outlet_id)
		_assert_staff_or_admin(restaurant)

		since = add_to_date(now_datetime(), days=-cint(days))
		submissions = frappe.get_all(
			"UGC Story Submission",
			filters={"outlet": restaurant, "submission_date": [">=", since]},
			fields=["status"],
		)

		counts = {
			"nudges_sent": 0, "offer_shown": 0, "story_shared": 0,
			"story_verified": 0, "proof_submitted": 0, "credited": 0,
			"rejected": 0, "flagged": 0, "expired": 0,
		}
		for s in submissions:
			st = s["status"]
			if st in counts:
				counts[st] += 1

		# Nudge count from Redis isn't practical to query; use submission count as proxy
		counts["nudges_sent"] = len(submissions)
		total = len(submissions)

		return _ok({
			"total": total,
			"days": cint(days),
			"funnel": [
				{"label": "Submissions Started", "key": "nudges_sent", "count": counts["nudges_sent"]},
				{"label": "Offer Shown", "key": "offer_shown", "count": counts["offer_shown"]},
				{"label": "Story Shared", "key": "story_shared", "count": counts["story_shared"]},
				{"label": "Staff Verified", "key": "story_verified", "count": counts["story_verified"]},
				{"label": "Proof Uploaded", "key": "proof_submitted", "count": counts["proof_submitted"]},
				{"label": "Credited", "key": "credited", "count": counts["credited"]},
			],
			"outcomes": {
				"rejected": counts["rejected"],
				"flagged": counts["flagged"],
				"expired": counts["expired"],
			},
		})
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"get_ugc_funnel: {e}", "UGC")
		return _err("INTERNAL_ERROR")


def _generate_voucher_code():
	"""Generate a unique human-readable voucher code like UGC-A3K9F2."""
	chars = string.ascii_uppercase + string.digits
	while True:
		code = "UGC-" + "".join(random.choices(chars, k=6))
		if not frappe.db.exists("UGC Voucher", {"voucher_code": code}):
			return code


def credit_ugc_cashback(submission, view_count, reviewed_by=None, source="ai"):
	"""
	Credit cashback = min(view_count, order_amount) capped at ₹2,000 as a
	restaurant-locked UGC Voucher. Idempotent on submission. Returns the
	created UGC Voucher name, or None.
	"""
	if isinstance(submission, str):
		submission = frappe.get_doc("UGC Story Submission", submission)

	# Idempotency guard — never double-credit a submission.
	existing = frappe.db.exists("UGC Voucher", {
		"ugc_submission": submission.name,
	})
	if existing or submission.status == "credited":
		return existing or submission.reward_entry

	# amount = min(views, final paid amount), hard-capped at PLATFORM_VOUCHER_EARNING_CAP.
	order_amount = flt(submission.order_amount)
	amount = min(cint(view_count), int(order_amount))
	amount = min(amount, PLATFORM_VOUCHER_EARNING_CAP)

	if amount <= 0:
		submission.status = "rejected"
		submission.rejection_reason = "Computed cashback was zero (no readable views)."
		submission.reviewed_by = reviewed_by
		submission.save(ignore_permissions=True)
		frappe.db.commit()
		return None

	issued_at = now_datetime()
	expires_at = add_to_date(issued_at, days=UGC_CASHBACK_VALIDITY_DAYS)
	voucher_code = _generate_voucher_code()

	voucher = frappe.get_doc({
		"doctype": "UGC Voucher",
		"voucher_code": voucher_code,
		"customer": submission.customer,
		"outlet": submission.outlet,
		"ugc_submission": submission.name,
		"original_amount": amount,
		"balance": amount,
		"status": "active",
		"issued_at": issued_at,
		"expires_at": expires_at,
	})
	voucher.insert(ignore_permissions=True)

	submission.cashback_coins = amount
	submission.reward_entry = voucher.name
	submission.ai_view_count = submission.ai_view_count or cint(view_count)
	submission.status = "credited"
	if reviewed_by:
		submission.reviewed_by = reviewed_by
	submission.save(ignore_permissions=True)
	frappe.db.commit()

	_notify(submission.name, "cashback_credited")
	return voucher.name


def _notify(submission_name, kind):
	"""Send the WhatsApp notification immediately (direct, not queued).

	Callers commit before calling this, so the submission state is already
	persisted. send_ugc_whatsapp swallows its own errors, so a send failure can
	never break the caller's request.
	"""
	from flamezo_backend.flamezo.tasks.ugc_tasks import send_ugc_whatsapp
	send_ugc_whatsapp(submission_name, kind)


# ─────────────────────────────────────────────────────────────────────────────
# Story Media Compositor
# Frontend sends: media_url, media_type, overlay_png (base64)
# Backend: downloads media, composites overlay via ffmpeg (video) or Pillow
# (image), returns the final MP4 / PNG as a base64-encoded file.
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED_CDN_DOMAINS = {"dinematters.com", "flamezo.in", "flamezo.in"}


def _cdn_url_allowed(url: str) -> bool:
	try:
		host = urlparse(url).hostname or ""
		return any(host == d or host.endswith("." + d) for d in _ALLOWED_CDN_DOMAINS)
	except Exception:
		return False


@frappe.whitelist()
def composite_story_media(media_url: str, media_type: str, overlay_png_b64: str):
	"""
	Composite the overlay PNG onto the restaurant's story media and return
	the finished file as base64 so the browser can trigger a download.

	media_type: "image" | "video"
	overlay_png_b64: base64-encoded PNG of the overlay layer (logo, QR,
	                 coupon strip, vignette) captured via html-to-image on
	                 the frontend.  The overlay must already be at a 9:16
	                 aspect ratio — it will be scaled to match the media
	                 native resolution by ffmpeg / Pillow.
	"""
	if not _cdn_url_allowed(media_url):
		frappe.throw("Media URL is not from an allowed CDN domain.", frappe.PermissionError)

	overlay_data = base64.b64decode(overlay_png_b64)

	import requests as _requests

	with tempfile.TemporaryDirectory() as tmp:
		overlay_path = os.path.join(tmp, "overlay.png")
		with open(overlay_path, "wb") as f:
			f.write(overlay_data)

		# Download source media from CDN
		r = _requests.get(media_url, timeout=120, stream=True)
		r.raise_for_status()
		ext = "mp4" if media_type == "video" else "jpg"
		media_path = os.path.join(tmp, f"source.{ext}")
		with open(media_path, "wb") as f:
			for chunk in r.iter_content(65536):
				f.write(chunk)

		if media_type == "video":
			output_path = os.path.join(tmp, "output.mp4")
			_composite_video(media_path, overlay_path, output_path)
			with open(output_path, "rb") as f:
				data = f.read()
			return {
				"success": True,
				"filename": "story-preview.mp4",
				"mime_type": "video/mp4",
				"data_b64": base64.b64encode(data).decode(),
			}
		else:
			output_path = os.path.join(tmp, "output.jpg")
			_composite_image(media_path, overlay_path, output_path)
			with open(output_path, "rb") as f:
				data = f.read()
			return {
				"success": True,
				"filename": "story-preview.jpg",
				"mime_type": "image/jpeg",
				"data_b64": base64.b64encode(data).decode(),
			}


def _get_video_dims(video_path: str):
	result = subprocess.run(
		[
			"ffprobe", "-v", "error",
			"-select_streams", "v:0",
			"-show_entries", "stream=width,height",
			"-of", "csv=p=0",
			video_path,
		],
		capture_output=True, text=True, timeout=15,
	)
	w, h = result.stdout.strip().split(",")
	return int(w), int(h)


def _composite_video(video_path: str, overlay_path: str, output_path: str):
	vw, vh = _get_video_dims(video_path)
	filter_complex = (
		f"[1:v]scale={vw}:{vh}[ov];"
		f"[0:v][ov]overlay=0:0"
	)
	cmd = [
		"ffmpeg", "-y",
		"-i", video_path,
		"-i", overlay_path,
		"-filter_complex", filter_complex,
		"-c:v", "libx264", "-preset", "fast", "-crf", "18",
		"-c:a", "copy",
		"-movflags", "+faststart",
		output_path,
	]
	result = subprocess.run(cmd, capture_output=True, timeout=120)
	if result.returncode != 0:
		frappe.log_error(result.stderr.decode(), "Story video composite failed")
		frappe.throw("Video compositing failed. Please try again.")



def _composite_image(image_path: str, overlay_path: str, output_path: str):
	try:
		from PIL import Image
	except ImportError:
		frappe.throw("Pillow is not installed on this server.")

	base = Image.open(image_path).convert("RGBA")
	overlay = Image.open(overlay_path).convert("RGBA").resize(base.size, Image.LANCZOS)
	composite = Image.alpha_composite(base, overlay).convert("RGB")
	composite.save(output_path, "JPEG", quality=92)

