# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
OTP verification API — send, verify, check.
SMS primary, WhatsApp fallback. Platform-wide verification.
"""

import random
import string
import frappe
from flamezo_backend.flamezo.utils.customer_helpers import (
	normalize_phone,
	get_or_create_customer,
	is_phone_verified,
	create_customer_session
)
from flamezo_backend.flamezo.utils.otp_service import (
	send_otp_via_sms,
	send_otp_via_evolution_api,
	OTP_LENGTH,
	OTP_EXPIRY_MINUTES,
	OTP_RESEND_COOLDOWN,
	OTP_MAX_PER_HOUR,
)


@frappe.whitelist(allow_guest=True)
def send_otp(restaurant_id, phone, purpose="verification", restaurant_name=None, channel=None):
	"""
	Send OTP: MSG91 WhatsApp first, fallback to Fast2SMS SMS.
	Returns: { success, token, expires_in, channel }
	"""
	try:
		config = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant_id}, "verify_my_user")
		if not config:
			# verify_my_user is OFF — still issue a trust session token.
			# Without this, the frontend has no X-Customer-Token for subsequent authenticated APIs
			# (order history, loyalty balance) and will hit SECURE_SESSION_INVALID when the
			# restaurant later enables verification.
			normalized = normalize_phone(phone)
			if normalized and len(normalized) == 10:
				try:
					customer = get_or_create_customer(normalized)
					if customer:
						# Generate session token using specialized helper (ensures DB persistence)
						session_token = create_customer_session(phone=normalized, customer_id=customer.name)
						frappe.db.commit()
						return {"success": True, "skip_verification": True, "session_token": session_token}
				except Exception as e:
					frappe.log_error(f"send_otp skip_verification session error: {e}", "OTP_Skip_Session")
					# Non-fatal: fall through to return without session token
			return {"success": True, "skip_verification": True}

		normalized = normalize_phone(phone)
		if not normalized or len(normalized) != 10:
			return {"success": False, "error": "INVALID_PHONE", "message": "Invalid phone number"}

		# A user must now always have a session token or verify via OTP.

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

		# 1. Try Evolution API (Strategic Preference - Free/Dedicated)
		# site_config.json takes priority so config persists across deployments without DB changes
		if channel != "sms":
			site_config = frappe.get_site_config()
			evo_url = site_config.get("evolution_api_url") or settings.evolution_api_url
			evo_key = site_config.get("evolution_api_key") or settings.get_password("evolution_api_key")
			evo_inst = site_config.get("evolution_api_instance") or settings.evolution_api_instance
			if evo_url and evo_key and evo_inst:
				if send_otp_via_evolution_api(evo_url, evo_key, evo_inst, normalized, otp, restaurant_name=restaurant_name or restaurant_id):
					used_channel = "whatsapp"





		if not used_channel:
			_create_otp_log(restaurant_id, phone, channel or "whatsapp", 0, purpose, "All channels failed")
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

		_create_otp_log(restaurant_id, phone, used_channel, 0, purpose, None)

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
def verify_otp(restaurant_id, phone, otp, token, name=None, email=None, referral_id=None):
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
				frappe.db.set_value("Customer", customer.name, "first_verified_at_restaurant", restaurant_id)
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

		return {
			"success": True,
			"verified": True,
			"customer_id": customer.name,
			"customer_name": customer.customer_name,
			"session_token": session_token
		}
	except Exception as e:
		frappe.log_error(f"verify_otp error: {e}", "OTP_Verify_Error")
		return {"success": False, "error": "INTERNAL_ERROR", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def send_flamezo_otp(phone, purpose="verification", channel=None):
	"""
	Send a platform-level OTP for the FLAMEZO consumer super-app.
	No restaurant_id is required. Uses "Flamezo" as the brand.
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

		# Try Evolution API (WhatsApp) with default "Flamezo" brand
		if channel != "sms":
			site_config = frappe.get_site_config()
			evo_url = site_config.get("evolution_api_url") or settings.evolution_api_url
			evo_key = site_config.get("evolution_api_key") or settings.get_password("evolution_api_key")
			evo_inst = site_config.get("evolution_api_instance") or settings.evolution_api_instance
			if evo_url and evo_key and evo_inst:
				if send_otp_via_evolution_api(evo_url, evo_key, evo_inst, normalized, otp, restaurant_name="Flamezo"):
					used_channel = "whatsapp"

		# Fallback to SMS if WhatsApp fails
		if not used_channel:
			if send_otp_via_sms(normalized, otp, settings):
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

		return {
			"success": True,
			"verified": True,
			"customer_id": customer.name,
			"customer_name": customer.customer_name,
			"session_token": session_token
		}
	except Exception as e:
		frappe.log_error(f"verify_flamezo_otp error: {e}", "OTP_Flamezo_Verify_Error")
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
			# Return successful response but verified=False so frontend handles it cleanly
			return {"success": True, "verified": False}
		
		# Confirm customer still exists
		customer_id = session.get("customer_id")
		if not customer_id or not frappe.db.exists("Customer", customer_id):
			frappe.cache().delete_value(f"customer_session:{session_token}")
			return {"success": True, "verified": False}

		# Fetch customer name
		customer_name = frappe.db.get_value("Customer", customer_id, "customer_name")

		return {
			"success": True,
			"verified": True, 
			"customer_id": customer_id,
			"customer_name": customer_name,
			"phone": session.get("phone")
		}
	except Exception as e:
		frappe.log_error(f"check_session error: {e}", "OTP_Check_Error")
		return {"success": False, "verified": False}


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


def _create_otp_log(restaurant_id, phone, channel, verified, purpose, error_message):
	try:
		frappe.get_doc({
			"doctype": "OTP Verification Log",
			"restaurant": restaurant_id,
			"phone": phone,
			"channel": channel,
			"verified": verified,
			"purpose": purpose or "verification",
			"error_message": error_message
		}).insert(ignore_permissions=True)
	except Exception:
		pass
