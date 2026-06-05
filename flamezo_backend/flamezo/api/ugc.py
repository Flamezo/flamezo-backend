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
import hashlib

import frappe
from frappe import _
from frappe.utils import now_datetime, today, add_days, add_to_date, flt, cint, get_datetime

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import get_customer_token, get_customer_from_token
from flamezo_backend.flamezo.utils.roles import GLOBAL_ADMIN_ROLES, SUPERVISOR_ROLES
from flamezo_backend.flamezo.utils.platform_config import get_expiry_days
from flamezo_backend.flamezo.media.storage import (
	generate_object_key,
	generate_signed_upload_url,
	verify_object_exists,
	get_cdn_url,
)

# ── Constants ────────────────────────────────────────────────────────────────
ALLOWED_PROOF_MIME = {
	"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/3gpp",
}
MAX_PROOF_BYTES = 80 * 1024 * 1024  # 80 MB — generous for a short screen recording
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
PLATFORM_TERMS = (
	"Cashback = your story's view count in rupees, capped at the final amount you paid (max "
	"100%). Up to 2 claims per restaurant every 30 days. Paid as Flamezo wallet cash, "
	"redeemable on your next visit at any Flamezo restaurant. Stories must stay live for at "
	"least 24 hours. Flamezo may reject views that appear edited, inflated, or fraudulent, and "
	"repeat offenders lose eligibility."
)

# ── Platform-fixed rules (same for every Flamezo restaurant; not editable in the
#    merchant dashboard — only the story template + linked coupons are). ──────────
PLATFORM_MIN_ORDER = 250            # ₹ — min final paid amount to qualify
PLATFORM_MAX_CLAIMS_PER_RESTAURANT_30D = 2   # rolling 30-day cap per restaurant (unlimited across different restaurants)
PLATFORM_CASHBACK_PERCENT_CAP = 100  # % of the final paid amount
PLATFORM_ABSOLUTE_CAP = 0          # 0 = no extra ₹ ceiling beyond the bill
PLATFORM_PROOF_WINDOW_HOURS = 48
PLATFORM_AI_PROVIDER = "Gemini"
PLATFORM_AI_CONFIDENCE = 0.85
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
	name = frappe.db.get_value("UGC Cashback Config", {"restaurant": restaurant}, "name")
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
			"restaurant": restaurant,
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


def _resolve_templates(config):
	"""Return the list of shareable template images with their CDN URLs."""
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


def _load_owned_order(restaurant, order_id, customer):
	"""Fetch an order and assert it belongs to this restaurant + customer."""
	if not frappe.db.exists("Order", order_id):
		return None
	order = frappe.get_doc("Order", order_id)
	if order.restaurant != restaurant:
		return None
	if order.platform_customer and order.platform_customer != customer:
		return None
	if not order.platform_customer:
		# Cannot attribute cashback without a platform customer on the order.
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
def get_ugc_eligibility(restaurant_id, order_id):
	"""Is this diner eligible to claim UGC cashback for this order?"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED", "Please verify your phone to continue.")

		config = _get_active_config(restaurant)
		if not config:
			return _ok({"eligible": False, "reason": "not_available"})

		order = _load_owned_order(restaurant, order_id, customer)
		if not order:
			return _ok({"eligible": False, "reason": "order_not_found"})

		# If a submission already exists, surface its state instead of a fresh offer.
		existing = _active_submission_for_order(order_id)
		if existing:
			return _ok({
				"eligible": True,
				"already_started": True,
				"submission_id": existing.name,
				"status": existing.status,
				"cashback_coins": cint(existing.cashback_coins),
				"max_cashback": _max_cashback(existing.order_amount or order.total),
			})

		if not _order_is_eligible(order):
			return _ok({"eligible": False, "reason": "order_not_completed"})

		if flt(order.total) < PLATFORM_MIN_ORDER:
			return _ok({"eligible": False, "reason": "below_min_order"})

		if _is_blocked(customer):
			return _ok({"eligible": False, "reason": "not_eligible"})

		# Mandatory feature, but only surfaces once a template is available to share.
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
			"viewer_coupon": _coupon_brief(config.coupon_for_viewers),
			"next_visit_coupon": _coupon_brief(config.next_visit_coupon),
		})
	except frappe.DoesNotExistError:
		return _err("RESTAURANT_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"get_ugc_eligibility: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def start_ugc_offer(restaurant_id, order_id):
	"""Diner taps the cashback CTA — create (or resume) a submission."""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		config = _get_active_config(restaurant)
		if not config:
			return _err("NOT_AVAILABLE", "UGC cashback is not active for this restaurant.")

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
			"restaurant": restaurant,
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
		return _err("RESTAURANT_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"start_ugc_offer: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def mark_story_shared(restaurant_id, submission_id, template_media_id=None):
	"""Diner confirms they shared the story to their IG/FB story."""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
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
		return _err("RESTAURANT_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"mark_story_shared: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def request_ugc_video_upload(restaurant_id, submission_id, filename, content_type, size_bytes):
	"""Issue a signed R2 URL for the diner to upload their view-count screen recording."""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		submission = _load_owned_submission(submission_id, restaurant, customer)
		if not submission:
			return _err("SUBMISSION_NOT_FOUND")

		# Proof can only be uploaded after staff verified the story is live.
		if submission.status not in ("story_verified", "proof_submitted"):
			return _err("STORY_NOT_VERIFIED", "Your story is awaiting staff verification.")

		content_type = (content_type or "").lower().strip()
		if content_type not in ALLOWED_PROOF_MIME:
			return _err("INVALID_FILE_TYPE", "Please upload a screen recording (mp4/mov/webm).")
		if cint(size_bytes) <= 0 or cint(size_bytes) > MAX_PROOF_BYTES:
			return _err("FILE_TOO_LARGE", "Video must be under 80 MB.")

		media_id = f"med_{uuid.uuid4().hex[:12]}"
		safe_filename = _sanitize_filename(filename)
		object_key = generate_object_key(
			restaurant_id=restaurant,
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
			"restaurant": restaurant,
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
		return _err("RESTAURANT_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"request_ugc_video_upload: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def submit_ugc_proof(restaurant_id, submission_id, upload_id):
	"""Confirm the uploaded proof video and queue AI view-count verification."""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
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
				"restaurant": restaurant,
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

		# Hand off to the AI verifier (string path → no import cycle).
		frappe.enqueue(
			"flamezo_backend.flamezo.services.ai.ugc_verifier.verify_submission",
			submission_name=submission.name,
			queue="default",
			timeout=300,
			enqueue_after_commit=True,
		)

		return _ok({"status": "proof_submitted"})
	except frappe.DoesNotExistError:
		return _err("RESTAURANT_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"submit_ugc_proof: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist(allow_guest=True)
def get_ugc_status(restaurant_id, order_id):
	"""Status of the diner's UGC claim for an order (for the in-progress / wallet UI)."""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		customer = _require_customer()
		if not customer:
			return _err("SESSION_REQUIRED")

		name = frappe.db.get_value(
			"UGC Story Submission",
			{"order": order_id, "customer": customer, "restaurant": restaurant},
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
		return _err("RESTAURANT_NOT_FOUND")
	except Exception as e:
		frappe.log_error(f"get_ugc_status: {e}", "UGC")
		return _err("INTERNAL_ERROR")


def _load_owned_submission(submission_id, restaurant, customer):
	if not frappe.db.exists("UGC Story Submission", submission_id):
		return None
	sub = frappe.get_doc("UGC Story Submission", submission_id)
	if sub.restaurant != restaurant or sub.customer != customer:
		return None
	return sub


def _proof_window_open(submission):
	deadline = add_to_date(get_datetime(submission.submission_date), hours=PLATFORM_PROOF_WINDOW_HOURS)
	return now_datetime() <= deadline


# ══════════════════════════════════════════════════════════════════════════════
#  STAFF ENDPOINTS  (Restaurant Admin / Staff)
# ══════════════════════════════════════════════════════════════════════════════
def _resolve_restaurant(restaurant_id):
	from flamezo_backend.flamezo.utils.api_helpers import get_restaurant_from_id
	doc_name = frappe.db.get_value("Restaurant", restaurant_id, "name") or get_restaurant_from_id(restaurant_id)
	if not doc_name:
		frappe.throw(_("Restaurant not found"), frappe.DoesNotExistError)
	return doc_name


def _assert_staff_or_admin(restaurant):
	"""Allow Restaurant Admin OR Staff for this restaurant (plus global/supervisor)."""
	user = frappe.session.user
	roles = frappe.get_roles(user)
	if (
		user == "Administrator"
		or any(r in GLOBAL_ADMIN_ROLES or r in SUPERVISOR_ROLES for r in roles)
		or "Restaurant Admin" in roles
	):
		return
	rec_role = frappe.db.get_value(
		"Restaurant User", {"user": user, "restaurant": restaurant, "is_active": 1}, "role"
	)
	if rec_role not in ("Restaurant Admin", "Restaurant Staff"):
		frappe.throw(_("You don't have access to this restaurant."), frappe.PermissionError)


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
def list_pending_story_verifications(restaurant_id, page=1, page_size=20):
	"""Day-0 queue: stories the diner shared, awaiting in-person staff verification."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)
		page, page_size = cint(page) or 1, cint(page_size) or 20
		filters = {"restaurant": restaurant, "status": "story_shared"}
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
def verify_ugc_story(restaurant_id, submission_id, action, notes=None):
	"""Staff approves/rejects the in-person story check. action: 'approve' | 'reject'."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)

		sub = frappe.get_doc("UGC Story Submission", submission_id)
		if sub.restaurant != restaurant:
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
def list_flagged_ugc(restaurant_id, page=1, page_size=20):
	"""Day-1 queue: claims the AI couldn't auto-approve, awaiting human review."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)
		page, page_size = cint(page) or 1, cint(page_size) or 20
		filters = {"restaurant": restaurant, "status": "flagged"}
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
def review_ugc(restaurant_id, submission_id, action, view_count=None, notes=None):
	"""Staff resolves a flagged claim. action: 'approve' | 'reject'."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)

		sub = frappe.get_doc("UGC Story Submission", submission_id)
		if sub.restaurant != restaurant:
			return _err("NOT_FOUND")
		if sub.status not in ("flagged", "proof_submitted"):
			return _err("INVALID_STATE", f"Cannot review from '{sub.status}'.")

		if action == "reject":
			sub.status = "rejected"
			sub.rejection_reason = notes or "Proof rejected on review."
			sub.reviewed_by = frappe.session.user
			sub.save(ignore_permissions=True)
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
def get_ugc_analytics(restaurant_id, days=None):
	"""Aggregate UGC performance for the merchant dashboard."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)

		filters = {"restaurant": restaurant}
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
	"coupon_for_viewers", "next_visit_coupon",
)


def _get_or_create_config(restaurant):
	name = frappe.db.get_value("UGC Cashback Config", {"restaurant": restaurant}, "name")
	if name:
		return frappe.get_doc("UGC Cashback Config", name)
	doc = frappe.get_doc({
		"doctype": "UGC Cashback Config",
		"restaurant": restaurant,
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
		"restaurant": config.restaurant,
		"coins_issued_this_month": cint(config.coins_issued_this_month),
		"templates": templates,
		"viewer_coupon": _coupon_brief(config.coupon_for_viewers),
		"next_visit_coupon_brief": _coupon_brief(config.next_visit_coupon),
	})
	return data


@frappe.whitelist()
def get_ugc_config(restaurant_id):
	"""Fetch (creating if missing) the UGC config for the dashboard."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)
		config = _get_or_create_config(restaurant)
		return _ok(_config_to_dict(config))
	except frappe.PermissionError as e:
		return _err("PERMISSION_DENIED", str(e))
	except Exception as e:
		frappe.log_error(f"get_ugc_config: {e}", "UGC")
		return _err("INTERNAL_ERROR")


@frappe.whitelist()
def save_ugc_config(restaurant_id, payload):
	"""Upsert scalar config fields and (optionally) replace the template list."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)
		data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})

		config = _get_or_create_config(restaurant)
		config.is_active = 1  # mandatory feature — always on
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
		["name", "media_id", "raw_object_key", "restaurant", "owner_doctype", "is_deleted"],
		as_dict=True,
	)
	if not info:
		return
	if info.restaurant != restaurant or info.owner_doctype != TEMPLATE_OWNER_DOCTYPE:
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
def delete_ugc_template(restaurant_id, media_asset):
	"""Remove the story template from the config AND delete its file from Cloudflare R2."""
	try:
		restaurant = _resolve_restaurant(restaurant_id)
		_assert_staff_or_admin(restaurant)
		config = _get_or_create_config(restaurant)

		remaining = [r for r in (config.template_assets or []) if r.media_asset != media_asset]
		config.set("template_assets", [])
		for r in remaining:
			config.append("template_assets", {"media_asset": r.media_asset, "label": r.label, "is_default": 1})
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
def credit_ugc_cashback(submission, view_count, reviewed_by=None, source="ai"):
	"""
	Credit cashback = min(view_count, order_amount, caps, budget) as universal
	loyalty coins. Idempotent on (submission, reason='UGC Cashback'). Returns the
	created Restaurant Loyalty Entry name, or None.
	"""
	if isinstance(submission, str):
		submission = frappe.get_doc("UGC Story Submission", submission)

	# Idempotency guard — never double-credit a submission.
	existing = frappe.db.exists("Restaurant Loyalty Entry", {
		"reference_doctype": "UGC Story Submission",
		"reference_name": submission.name,
		"reason": "UGC Cashback",
	})
	if existing or submission.status == "credited":
		return existing or submission.reward_entry

	# cashback = min(views, final paid amount) under platform caps (% + absolute).
	order_amount = flt(submission.order_amount)
	coins = min(cint(view_count), int(order_amount))
	coins = min(coins, int(order_amount * PLATFORM_CASHBACK_PERCENT_CAP / 100.0))
	if PLATFORM_ABSOLUTE_CAP > 0:
		coins = min(coins, PLATFORM_ABSOLUTE_CAP)

	if coins <= 0:
		submission.status = "rejected"
		submission.rejection_reason = "Computed cashback was zero (no readable views)."
		submission.reviewed_by = reviewed_by
		submission.save(ignore_permissions=True)
		frappe.db.commit()
		return None

	expiry = add_days(today(), get_expiry_days())  # platform-standard Cash expiry (30 days)
	entry = frappe.get_doc({
		"doctype": "Restaurant Loyalty Entry",
		"customer": submission.customer,
		"restaurant": submission.restaurant,
		"coins": int(coins),
		"transaction_type": "Earn",
		"reason": "UGC Cashback",
		"reference_doctype": "UGC Story Submission",
		"reference_name": submission.name,
		"posting_date": today(),
		"expiry_date": expiry,
		"is_settled": 1,
	})
	entry.insert(ignore_permissions=True)

	submission.cashback_coins = int(coins)
	submission.reward_entry = entry.name
	submission.ai_view_count = submission.ai_view_count or cint(view_count)
	submission.status = "credited"
	if reviewed_by:
		submission.reviewed_by = reviewed_by
	submission.save(ignore_permissions=True)
	frappe.db.commit()

	# Wallet push + WhatsApp confirmation (background, never blocks).
	frappe.enqueue(
		"flamezo_backend.flamezo.utils.loyalty.send_coin_credit_push",
		customer=submission.customer, restaurant=submission.restaurant,
		coins=int(coins), reason="UGC Cashback", queue="short", timeout=30,
	)
	_notify(submission.name, "cashback_credited")
	return entry.name


def _notify(submission_name, kind):
	"""Fire a WhatsApp notification in the background (safe if WA not configured)."""
	frappe.enqueue(
		"flamezo_backend.flamezo.tasks.ugc_tasks.send_ugc_whatsapp",
		submission_name=submission_name, kind=kind,
		queue="short", timeout=60, enqueue_after_commit=True,
	)
