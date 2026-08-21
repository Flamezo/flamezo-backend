# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
OTP verification API — send, verify, check.
WhatsApp (Meta Cloud API) primary, SMS fallback. Platform-wide verification.
"""

import random
import string
import frappe
from flamezo_backend.flamezo.utils.customer_helpers import (
	normalize_phone,
	get_or_create_customer,
	is_phone_verified,
	create_customer_session,
	get_customer_from_token,
	_find_customer_by_normalized_phone,
)
from flamezo_backend.flamezo.utils.otp_service import (
	send_otp_via_whatsapp,
	send_otp_via_sms,
	send_otp_via_evolution_api,
	OTP_LENGTH,
	OTP_EXPIRY_MINUTES,
	OTP_RESEND_COOLDOWN,
	OTP_MAX_PER_HOUR,
)


@frappe.whitelist(allow_guest=True)
def send_otp(outlet_id, phone, purpose="verification", outlet_name=None, channel=None, app_signature=None):
	"""
	Send OTP via WhatsApp (Meta Cloud API) first, SMS (Fast2SMS) fallback.
	Every user must verify via OTP — no skip path.
	Returns: { success, token, expires_in, channel }
	"""
	try:
		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "error": "INVALID_PHONE", "message": "Invalid phone number"}

		# Rate limit
		rate_key = f"otp_rate:{normalized}"
		count = int(frappe.cache().get_value(rate_key) or 0)
		if count >= OTP_MAX_PER_HOUR:
			return {"success": False, "error": "RATE_LIMIT_EXCEEDED", "message": "Max 3 OTPs per hour. Try again later."}

		cooldown_key = f"otp_cooldown:{normalized}"
		if frappe.cache().get_value(cooldown_key):
			return {"success": False, "error": "COOLDOWN", "message": "Wait 30 seconds before resending."}

		settings = frappe.get_single("Flamezo Settings")
		otp = "".join(random.choices(string.digits, k=OTP_LENGTH))
		used_channel = None

		# 1. Meta Cloud API (WhatsApp Business) — production primary
		if channel != "sms":
			if send_otp_via_whatsapp(normalized, otp, outlet_name=outlet_name or outlet_id):
				used_channel = "whatsapp"

		# 2. Fallback to SMS if WhatsApp failed or was skipped
		if not used_channel:
			# API key: prefer site_config.json (secure), else Flamezo Settings.
			sms_key = frappe.conf.get("fast2sms_api_key")
			if not sms_key:
				try:
					sms_key = settings.get_password("fast2sms_api_key") if settings else None
				except Exception:
					sms_key = None
			if sms_key and send_otp_via_sms(sms_key, normalized, otp, outlet_name=outlet_name or outlet_id, app_signature=app_signature):
				used_channel = "sms"

		if not used_channel:
			_create_otp_log(outlet_id, phone, channel or "whatsapp", 0, purpose, "All channels failed")
			return {"success": False, "error": "OTP_SEND_FAILED", "message": "Failed to send OTP"}

		# Store OTP in cache
		token = frappe.generate_hash(length=32)
		frappe.cache().set_value(
			f"otp:{normalized}:{token}",
			{"otp": otp, "purpose": purpose, "attempts": 0},
			expires_in_sec=OTP_EXPIRY_MINUTES * 60
		)

		# Rate limit & cooldown
		frappe.cache().set_value(rate_key, count + 1, expires_in_sec=3600)
		frappe.cache().set_value(cooldown_key, "1", expires_in_sec=OTP_RESEND_COOLDOWN)

		_create_otp_log(outlet_id, phone, used_channel, 0, purpose, None)

		return {
			"success": True,
			"token": token,
			"expires_in": OTP_EXPIRY_MINUTES * 60,
			"channel": used_channel,
			"message": "OTP sent successfully"
		}
	except Exception as e:
		frappe.log_error(f"send_otp error: {e}", "OTP_Send_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def verify_otp(outlet_id, phone, otp, token, name=None, email=None, referral_id=None):
	"""Verify OTP. On success, create/update Customer and return session token.
	referral_id is accepted for API compatibility but no longer acted on here —
	the Welcome Bonus is claimed explicitly via claim_referral_reward() in the UI."""
	try:
		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "error": "INVALID_PHONE"}

		cached = frappe.cache().get_value(f"otp:{normalized}:{token}")
		if not cached:
			return {"success": False, "error": "OTP_EXPIRED_OR_INVALID"}

		# Anti-Brute Force: 5-Strikes Rule
		attempts = cached.get("attempts", 0)
		if attempts >= 5:
			frappe.cache().delete_value(f"otp:{normalized}:{token}")
			return {"success": False, "error": "MAX_ATTEMPTS_EXCEEDED", "message": "Too many failed attempts. Request a new OTP."}

		if cached.get("otp") != otp:
			# Increment attempts
			cached["attempts"] = attempts + 1
			frappe.cache().set_value(f"otp:{normalized}:{token}", cached, expires_in_sec=OTP_EXPIRY_MINUTES * 60)
			return {"success": False, "error": "INVALID_OTP", "message": f"Invalid OTP. {5 - (attempts + 1)} attempts remaining."}

		frappe.cache().delete_value(f"otp:{normalized}:{token}")

		customer = get_or_create_customer(phone=normalized, name=name, email=email)
		if not customer:
			return {"success": False, "error": "CUSTOMER_CREATE_FAILED"}

		# Update verified_at and ensure phone is set (use db.set_value when ERPNext Customer lacks attrs)
		now_ts = frappe.utils.now()
		if frappe.db.has_column("Customer", "verified_at"):
			current = frappe.db.get_value("Customer", customer.name, "verified_at")
			if not current:
				frappe.db.set_value("Customer", customer.name, "verified_at", now_ts)
			if frappe.db.has_column("Customer", "first_verified_at_restaurant"):
				frappe.db.set_value("Customer", customer.name, "first_verified_at_restaurant", outlet_id)
		# Ensure phone is set so is_phone_verified() finds this customer when order checks
		if frappe.db.has_column("Customer", "phone"):
			current_phone = frappe.db.get_value("Customer", customer.name, "phone")
			if not current_phone:
				frappe.db.set_value("Customer", customer.name, "phone", normalized)
		frappe.db.commit()
		
		# NOTE: Welcome Bonus is NOT awarded here anymore.
		# It is awarded when the user clicks "Claim X Coins" in the welcome modal,
		# which calls claim_referral_reward() post-OTP. This prevents silent
		# background grants that conflict with the explicit Claim UX.
		# Fallback: if user skips the modal and places an order, orders.py awards it.

		# Generate session token using specialized helper (ensures DB persistence)
		session_token = create_customer_session(phone=normalized, customer_id=customer.name)

		# Treat auto-generated placeholder names as "no name yet" so the
		# frontend shows the name/DOB collection step for new users.
		display_name = customer.customer_name or ""
		if display_name == f"Customer {normalized}":
			display_name = ""

		return {
			"success": True,
			"verified": True,
			"customer_id": customer.name,
			"customer_name": display_name,
			"session_token": session_token
		}
	except Exception as e:
		frappe.log_error(f"verify_otp error: {e}", "OTP_Verify_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def send_flamezo_otp(phone, purpose="verification", channel=None):
	"""
	Send a platform-level OTP for the FLAMEZO consumer super-app.
	No outlet_id is required. Uses "Flamezo" as the brand.
	"""
	try:
		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "error": "INVALID_PHONE", "message": "Invalid phone number"}

		# Rate limit
		rate_key = f"otp_rate:{normalized}"
		count = int(frappe.cache().get_value(rate_key) or 0)
		if count >= OTP_MAX_PER_HOUR:
			return {"success": False, "error": "RATE_LIMIT_EXCEEDED", "message": "Max 3 OTPs per hour. Try again later."}

		cooldown_key = f"otp_cooldown:{normalized}"
		if frappe.cache().get_value(cooldown_key):
			return {"success": False, "error": "COOLDOWN", "message": "Wait 30 seconds before resending."}

		settings = frappe.get_single("Flamezo Settings")
		otp = "".join(random.choices(string.digits, k=OTP_LENGTH))
		used_channel = None

		# 1. Meta Cloud API (WhatsApp Business) — production primary. The provider
		#    HTTP call has a short timeout (see otp_service) so a slow WhatsApp/SMS
		#    endpoint can't stall this request the way it used to (~25s → the app
		#    sat on "Sending...").
		if channel != "sms":
			if send_otp_via_whatsapp(normalized, otp, outlet_name="Flamezo"):
				used_channel = "whatsapp"

		# 2. Fallback to SMS
		if not used_channel:
			# API key: prefer site_config.json (secure), else Flamezo Settings.
			sms_key = frappe.conf.get("fast2sms_api_key")
			if not sms_key:
				try:
					sms_key = settings.get_password("fast2sms_api_key") if settings else None
				except Exception:
					sms_key = None
			if sms_key and send_otp_via_sms(sms_key, normalized, otp, outlet_name="Flamezo"):
				used_channel = "sms"

		if not used_channel:
			_create_otp_log("Flamezo", phone, channel or "whatsapp", 0, purpose, "All channels failed")
			return {"success": False, "error": "OTP_SEND_FAILED", "message": "Failed to send OTP"}

		# Store OTP in cache
		token = frappe.generate_hash(length=32)
		frappe.cache().set_value(
			f"otp:{normalized}:{token}",
			{"otp": otp, "purpose": purpose, "attempts": 0},
			expires_in_sec=OTP_EXPIRY_MINUTES * 60
		)

		# Rate limit & cooldown
		frappe.cache().set_value(rate_key, count + 1, expires_in_sec=3600)
		frappe.cache().set_value(cooldown_key, "1", expires_in_sec=OTP_RESEND_COOLDOWN)

		_create_otp_log("Flamezo", phone, used_channel, 0, purpose, None)

		return {
			"success": True,
			"token": token,
			"expires_in": OTP_EXPIRY_MINUTES * 60,
			"channel": used_channel,
			"message": "OTP sent successfully"
		}
	except Exception as e:
		frappe.log_error(f"send_flamezo_otp error: {e}", "OTP_Flamezo_Send_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def verify_flamezo_otp(phone, otp, token, name=None, email=None):
	"""
	Verify platform-level OTP.
	Creates/retrieves a Customer and returns a unified session token.
	"""
	try:
		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "error": "INVALID_PHONE"}

		cached = frappe.cache().get_value(f"otp:{normalized}:{token}")
		if not cached:
			return {"success": False, "error": "OTP_EXPIRED_OR_INVALID"}

		# Anti-Brute Force: 5-Strikes Rule
		attempts = cached.get("attempts", 0)
		if attempts >= 5:
			frappe.cache().delete_value(f"otp:{normalized}:{token}")
			return {"success": False, "error": "MAX_ATTEMPTS_EXCEEDED", "message": "Too many failed attempts. Request a new OTP."}

		if cached.get("otp") != otp:
			# Increment attempts
			cached["attempts"] = attempts + 1
			frappe.cache().set_value(f"otp:{normalized}:{token}", cached, expires_in_sec=OTP_EXPIRY_MINUTES * 60)
			return {"success": False, "error": "INVALID_OTP", "message": f"Invalid OTP. {5 - (attempts + 1)} attempts remaining."}

		frappe.cache().delete_value(f"otp:{normalized}:{token}")

		customer = get_or_create_customer(phone=normalized, name=name, email=email)
		if not customer:
			return {"success": False, "error": "CUSTOMER_CREATE_FAILED"}

		# Update verified_at and ensure phone is set
		now_ts = frappe.utils.now()
		if frappe.db.has_column("Customer", "verified_at"):
			current = frappe.db.get_value("Customer", customer.name, "verified_at")
			if not current:
				frappe.db.set_value("Customer", customer.name, "verified_at", now_ts)
		
		if frappe.db.has_column("Customer", "phone"):
			current_phone = frappe.db.get_value("Customer", customer.name, "phone")
			if not current_phone:
				frappe.db.set_value("Customer", customer.name, "phone", normalized)
		frappe.db.commit()

		# Generate unified session token
		session_token = create_customer_session(phone=normalized, customer_id=customer.name)

		display_name = customer.customer_name or ""
		if display_name == f"Customer {normalized}":
			display_name = ""

		return {
			"success": True,
			"verified": True,
			"customer_id": customer.name,
			"customer_name": display_name,
			"session_token": session_token
		}
	except Exception as e:
		frappe.log_error(f"verify_flamezo_otp error: {e}", "OTP_Flamezo_Verify_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def change_flamezo_phone(session_token, new_phone, otp, token):
	"""
	Change the logged-in customer's phone number.

	POST /api/method/flamezo_backend.flamezo.api.otp.change_flamezo_phone

	- session_token : current session (identifies the customer)
	- new_phone     : the number the OTP was sent to (send_flamezo_otp, purpose='phone_change')
	- otp, token    : OTP verification for new_phone

	Verifies the OTP for the new number, ensures it isn't already registered to
	another account, repoints Customer.phone, revokes the old session and issues
	a fresh session bound to the new number.
	"""
	try:
		if not session_token:
			return {"success": False, "error": "AUTH_REQUIRED", "message": "Authentication required"}

		customer_id = get_customer_from_token(session_token)
		if not customer_id:
			return {"success": False, "error": "SESSION_INVALID", "message": "Invalid or expired session"}

		normalized = normalize_phone(new_phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "error": "INVALID_PHONE", "message": "Enter a valid 10-digit number."}

		# Already this customer's number?
		current_phone = frappe.db.get_value("Customer", customer_id, "phone")
		if normalize_phone(current_phone or "") == normalized:
			return {"success": False, "error": "SAME_NUMBER", "message": "This is already your number."}

		# New number must not belong to a DIFFERENT customer.
		other = _find_customer_by_normalized_phone(normalized)
		if other and other != customer_id:
			return {"success": False, "error": "PHONE_IN_USE", "message": "This number is already registered with another account."}

		# ── Verify the OTP sent to the new number (mirrors verify_flamezo_otp) ──
		cached = frappe.cache().get_value(f"otp:{normalized}:{token}")
		if not cached:
			return {"success": False, "error": "OTP_EXPIRED_OR_INVALID", "message": "OTP expired or invalid. Request a new one."}

		attempts = cached.get("attempts", 0)
		if attempts >= 5:
			frappe.cache().delete_value(f"otp:{normalized}:{token}")
			return {"success": False, "error": "MAX_ATTEMPTS_EXCEEDED", "message": "Too many failed attempts. Request a new OTP."}

		if cached.get("otp") != otp:
			cached["attempts"] = attempts + 1
			frappe.cache().set_value(f"otp:{normalized}:{token}", cached, expires_in_sec=OTP_EXPIRY_MINUTES * 60)
			return {"success": False, "error": "INVALID_OTP", "message": f"Invalid OTP. {5 - (attempts + 1)} attempts remaining."}

		frappe.cache().delete_value(f"otp:{normalized}:{token}")

		# ── Apply the change ──
		frappe.db.set_value("Customer", customer_id, "phone", normalized)
		if frappe.db.has_column("Customer", "mobile_no"):
			frappe.db.set_value("Customer", customer_id, "mobile_no", normalized)
		if frappe.db.has_column("Customer", "verified_at"):
			frappe.db.set_value("Customer", customer_id, "verified_at", frappe.utils.now())
		frappe.db.commit()

		# ── Revoke the old session, issue a fresh one for the new number ──
		try:
			logout_customer(session_token)
		except Exception:
			pass
		new_token = create_customer_session(phone=normalized, customer_id=customer_id)

		return {
			"success": True,
			"phone": normalized,
			"customer_id": customer_id,
			"session_token": new_token,
		}
	except Exception as e:
		frappe.log_error(f"change_flamezo_phone error: {e}", "OTP_Flamezo_ChangePhone_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def delete_flamezo_account(session_token):
	"""
	Anonymise and permanently close a Flamezo customer account.
	DPDP Act (India) compliance — all PII is scrubbed within the request.
	Sessions are hard-revoked so the token cannot be reused.
	Returns: { success: true }
	"""
	try:
		if not session_token:
			return {"success": False, "error": "MISSING_TOKEN"}

		from flamezo_backend.flamezo.utils.customer_helpers import (
			get_customer_from_token, _hard_revoke, _session_doctype_exists, _SESSION_DOCTYPE
		)

		customer_id = get_customer_from_token(session_token)
		if not customer_id:
			return {"success": False, "error": "INVALID_SESSION"}

		# 1. Anonymise PII fields on the Customer record
		anon_fields = {}
		if frappe.db.has_column("Customer", "phone"):
			anon_fields["phone"] = ""
		if frappe.db.has_column("Customer", "email"):
			anon_fields["email"] = ""
		if frappe.db.has_column("Customer", "image"):
			anon_fields["image"] = ""
		if frappe.db.has_column("Customer", "date_of_birth"):
			anon_fields["date_of_birth"] = None
		if frappe.db.has_column("Customer", "verified_at"):
			anon_fields["verified_at"] = None

		anon_fields["customer_name"] = f"Deleted User"

		for field, value in anon_fields.items():
			frappe.db.set_value("Customer", customer_id, field, value)

		# 2. Revoke ALL sessions for this customer (not just the current one)
		if _session_doctype_exists():
			active_tokens = frappe.get_all(
				_SESSION_DOCTYPE,
				filters={"customer": customer_id, "revoked": 0},
				fields=["session_token"],
			)
			for s in active_tokens:
				_hard_revoke(s.session_token)
		else:
			# Fallback: revoke only the current session
			_hard_revoke(session_token)

		frappe.db.commit()

		frappe.log_error(
			f"Account deleted: {customer_id}",
			"Account_Deletion"
		)

		return {"success": True, "message": "Account deleted"}
	except Exception as e:
		frappe.log_error(f"delete_flamezo_account error: {e}", "Account_Deletion_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def logout_customer(session_token):
	"""
	Invalidate a customer session token.
	Deletes from Redis AND marks revoked=1 in DB so the session cannot be
	resurrected via the DB fallback after a cache flush.
	Returns: { success: true }
	"""
	try:
		if not session_token:
			return {"success": False, "error": "MISSING_TOKEN", "message": "session_token is required"}

		from flamezo_backend.flamezo.utils.customer_helpers import _hard_revoke
		_hard_revoke(session_token)
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"logout_customer error: {e}", "OTP_Logout_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def check_session(session_token):
	"""
	Validate a session token. Returns customer_id and phone if valid.
	This is the secure replacement for checking 'is_phone_verified' based only on phone.
	"""
	try:
		if not session_token:
			return {"success": False, "verified": False}
		
		session = frappe.cache().get_value(f"customer_session:{session_token}")
		if not session:
			# Redis may have been flushed (deploy `clear-cache`, eviction, or restart).
			# Fall back to the durable DB session (Customer Session) so a valid user
			# isn't logged out just because the cache was cleared. This also repopulates
			# Redis for subsequent reads.
			from flamezo_backend.flamezo.utils.customer_helpers import _restore_session_from_db
			session = _restore_session_from_db(session_token)
		if not session:
			# Return successful response but verified=False so frontend handles it cleanly
			return {"success": True, "verified": False}
		
		# Confirm customer still exists
		customer_id = session.get("customer_id")
		if not customer_id or not frappe.db.exists("Customer", customer_id):
			frappe.cache().delete_value(f"customer_session:{session_token}")
			return {"success": True, "verified": False}

		# Fetch customer name — strip auto-generated placeholder so frontend
		# shows the profile completion step for users who haven't set their name.
		customer_name = frappe.db.get_value("Customer", customer_id, "customer_name") or ""
		phone_normalized = session.get("phone") or ""
		if customer_name == f"Customer {phone_normalized}":
			customer_name = ""

		# Token rotation DISABLED: rotating (and hard-revoking) the token on every
		# check_session raced with concurrent API calls — an in-flight request
		# (e.g. UGC get_claimable_orders firing at page load) would use the token
		# that check_session had just revoked, get SESSION_REQUIRED, and force a
		# spurious re-login. Keep ONE stable token for the whole session so a
		# single login works across every feature. The token is still revoked on
		# explicit logout and bounded by its TTL.
		new_token = session_token

		return {
			"success": True,
			"verified": True,
			"customer_id": customer_id,
			"customer_name": customer_name,
			"phone": phone_normalized,
			"new_token": new_token,
		}
	except Exception as e:
		frappe.log_error(f"check_session error: {e}", "OTP_Check_Error")
		return {"success": False, "verified": False}


@frappe.whitelist(allow_guest=True)
def list_customer_sessions(session_token):
	"""
	Return all active sessions for the customer who owns session_token.
	Used by the customer profile to show/revoke devices.
	"""
	try:
		from flamezo_backend.flamezo.utils.customer_helpers import (
			_SESSION_DOCTYPE, _session_doctype_exists, get_customer_from_token
		)
		customer_id = get_customer_from_token(session_token)
		if not customer_id:
			return {"success": False, "error": "UNAUTHORIZED"}
		if not _session_doctype_exists():
			return {"success": True, "sessions": []}
		sessions = frappe.get_all(
			_SESSION_DOCTYPE,
			filters={"customer": customer_id, "revoked": 0},
			fields=["name", "session_token", "device_info", "ip_address", "last_used_at", "creation"],
			order_by="last_used_at desc",
			limit=20,
		)
		# Mask the token — expose only last 8 chars for display
		for s in sessions:
			raw = s.get("session_token") or ""
			s["token_hint"] = f"...{raw[-8:]}" if len(raw) >= 8 else raw
			s["is_current"] = raw == session_token
			del s["session_token"]
		return {"success": True, "sessions": sessions}
	except Exception as e:
		frappe.log_error(f"list_customer_sessions error: {e}", "OTP_Sessions")
		return {"success": False, "error": "INTERNAL_ERROR"}


@frappe.whitelist(allow_guest=True)
def revoke_customer_session_by_hint(session_token, target_session_name):
	"""
	Revoke a specific session (by its doc name) for the authenticated customer.
	Prevents one user from revoking another user's sessions.
	"""
	try:
		from flamezo_backend.flamezo.utils.customer_helpers import (
			_SESSION_DOCTYPE, _session_doctype_exists, get_customer_from_token, _hard_revoke
		)
		customer_id = get_customer_from_token(session_token)
		if not customer_id:
			return {"success": False, "error": "UNAUTHORIZED"}
		if not _session_doctype_exists():
			return {"success": False, "error": "NOT_SUPPORTED"}
		rec = frappe.db.get_value(
			_SESSION_DOCTYPE,
			{"name": target_session_name, "customer": customer_id, "revoked": 0},
			["session_token"],
			as_dict=True,
		)
		if not rec:
			return {"success": False, "error": "SESSION_NOT_FOUND"}
		_hard_revoke(rec.session_token)
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"revoke_customer_session_by_hint error: {e}", "OTP_Sessions")
		return {"success": False, "error": "INTERNAL_ERROR"}


@frappe.whitelist(allow_guest=True)
def check_verified(phone):
	"""
	Check if phone number exists in DB.
	NOTE: This no longer suffices for login/ordering; use check_session instead.
	"""
	try:
		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "verified": False}
		return {"success": True, "verified": is_phone_verified(phone)}
	except Exception as e:
		frappe.log_error(f"check_verified error: {e}", "OTP_Check_Error")
		return {"success": False, "verified": False}


# ─── WhatsApp Auto-Login Magic Tokens ────────────────────────────────────────

_WA_AUTH_TOKEN_TTL = 24 * 60 * 60  # 24-hour window — enough for "grab it before you leave"


def generate_whatsapp_auth_token(phone: str, customer_id: str) -> str:
	"""
	Generate a one-time-use token for WhatsApp button deep links.

	Stored in Redis for 24 hours. Call from task functions when building
	the button URL so the user is auto-logged-in when they click from
	WhatsApp's in-app browser (which has no shared session with Chrome/Safari).

	Returns an empty string on failure so callers can safely append it
	(a missing ?wt= just means the user will see the normal login prompt).
	"""
	import secrets
	try:
		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return ""
		# Orders placed at pay-bill sometimes have no platform_customer linked, but
		# the payer is (or becomes) a known customer. Resolve — or create — the
		# Customer by phone so the auto-login token is still issued (otherwise
		# "Check My Offer" would fall back to a manual login prompt).
		if not customer_id:
			customer_id = _find_customer_by_normalized_phone(normalized) or ""
		if not customer_id:
			cust = get_or_create_customer(phone=normalized)
			customer_id = cust.name if cust else ""
		if not customer_id:
			return ""
		import time
		token = secrets.token_urlsafe(32)
		# NOTE: set_value(..., expires_in_sec=...) is unreliable on this Frappe
		# build (it silently drops the key in some contexts — same class of bug
		# as the RQ set_value nx= issue). Store WITHOUT a TTL and enforce expiry
		# via an embedded timestamp that verify_whatsapp_token checks.
		frappe.cache().set_value(
			f"wa_auth:{token}",
			{"phone": normalized, "customer_id": customer_id,
			 "exp": int(time.time()) + _WA_AUTH_TOKEN_TTL},
		)
		return token
	except Exception as e:
		frappe.log_error(f"generate_whatsapp_auth_token: {e}", "WA_Auth")
		return ""


@frappe.whitelist(allow_guest=True)
def verify_whatsapp_token(token):
	"""
	Validate a WhatsApp auto-login token and return a fresh session.

	One-time use — token is deleted from Redis immediately on first call
	so it cannot be replayed via bookmarks or link sharing.

	On success returns:
	  { success: true, session_token, phone, customer_id, customer_name }

	On failure returns:
	  { success: false, error: TOKEN_EXPIRED | INVALID_TOKEN | CUSTOMER_NOT_FOUND }
	"""
	try:
		if not token or not isinstance(token, str) or len(token) > 200:
			return {"success": False, "error": "INVALID_TOKEN"}

		payload = frappe.cache().get_value(f"wa_auth:{token}")
		if not payload:
			return {"success": False, "error": "TOKEN_EXPIRED"}

		# Delete immediately — one-time use
		frappe.cache().delete_value(f"wa_auth:{token}")

		# Expiry is enforced in-value (see generate_whatsapp_auth_token — the TTL
		# is embedded because set_value's expires_in_sec is unreliable here).
		import time
		if int(payload.get("exp", 0) or 0) < int(time.time()):
			return {"success": False, "error": "TOKEN_EXPIRED"}

		phone = payload.get("phone", "")
		customer_id = payload.get("customer_id", "")

		if not phone or not customer_id:
			return {"success": False, "error": "INVALID_TOKEN"}

		if not frappe.db.exists("Customer", customer_id):
			return {"success": False, "error": "CUSTOMER_NOT_FOUND"}

		session_token = create_customer_session(phone=phone, customer_id=customer_id)

		raw_name = frappe.db.get_value("Customer", customer_id, "customer_name") or ""
		display_name = "" if raw_name == f"Customer {phone}" else raw_name

		return {
			"success": True,
			"session_token": session_token,
			"phone": phone,
			"customer_id": customer_id,
			"customer_name": display_name,
		}
	except Exception as e:
		frappe.log_error(f"verify_whatsapp_token: {e}", "WA_Auth")
		return {"success": False, "error": "INTERNAL_ERROR"}


@frappe.whitelist(allow_guest=True)
def get_my_profile():
	"""
	Return the authenticated customer's profile fields.
	Reads X-Customer-Token / Authorization: Bearer from request headers.
	Returns: { success, customer_id, customer_name, phone, email, date_of_birth, profile_photo }
	"""
	try:
		from flamezo_backend.flamezo.utils.customer_helpers import (
			get_customer_token, get_customer_from_token
		)
		token = get_customer_token()
		if not token:
			return {"success": False, "error": "AUTH_REQUIRED"}

		customer_id = get_customer_from_token(token)
		if not customer_id:
			return {"success": False, "error": "INVALID_SESSION"}

		fields = ["customer_name", "email", "phone", "image"]
		if frappe.db.has_column("Customer", "date_of_birth"):
			fields.append("date_of_birth")

		c = frappe.db.get_value("Customer", customer_id, fields, as_dict=True)
		if not c:
			return {"success": False, "error": "CUSTOMER_NOT_FOUND"}

		display_name = c.get("customer_name") or ""
		phone_val = c.get("phone") or ""
		if display_name == f"Customer {phone_val}":
			display_name = ""

		from flamezo_backend.flamezo.api.addresses import get_addresses_for_customer
		saved_addresses = get_addresses_for_customer(customer_id)

		return {
			"success": True,
			"customer_id": customer_id,
			"customer_name": display_name,
			"phone": phone_val,
			"email": c.get("email") or "",
			"date_of_birth": str(c.get("date_of_birth")) if c.get("date_of_birth") else None,
			"profile_photo": c.get("image") or None,
			"saved_addresses": saved_addresses,
		}
	except Exception as e:
		frappe.log_error(f"get_my_profile error: {e}", "Customer_Profile")
		return {"success": False, "error": "INTERNAL_ERROR"}


def _resolve_customer_from_token() -> str:
    """
    Read X-Customer-Token / Authorization Bearer from request headers,
    validate the session, and return the customer_id string.
    Raises frappe.AuthenticationError on failure so callers get a clean 401.
    """
    from flamezo_backend.flamezo.utils.customer_helpers import (
        get_customer_token, get_customer_from_token
    )
    token = get_customer_token()
    if not token:
        frappe.throw("Authentication required.", frappe.AuthenticationError)

    customer_id = get_customer_from_token(token)
    if not customer_id:
        frappe.throw("Invalid or expired session.", frappe.AuthenticationError)

    return customer_id


def _create_otp_log(outlet_id, phone, channel, verified, purpose, error_message):
	try:
		frappe.get_doc({
			"doctype": "OTP Verification Log",
			"outlet": outlet_id,
			"phone": phone,
			"channel": channel,
			"verified": verified,
			"purpose": purpose or "verification",
			"error_message": error_message
		}).insert(ignore_permissions=True)
	except Exception:
		pass
