# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

import frappe
import re
import phonenumbers

SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
_SESSION_DOCTYPE = "Customer Session"


def get_customer_token():
	"""
	Centralized utility to extract customer session token from request headers.
	Checks: X-Customer-Token, x-customer-token, and Authorization (Bearer).
	"""
	if not frappe.request:
		return None
	
	headers = frappe.request.headers
	token = headers.get("X-Customer-Token") or headers.get("x-customer-token")
	
	if not token and headers.get("Authorization"):
		auth_val = headers.get("Authorization")
		if auth_val.startswith("Bearer "):
			token = auth_val.replace("Bearer ", "", 1)
			
	return token


def normalize_phone(phone: str) -> str:
	if not phone:
		return ""
	try:
		parsed = phonenumbers.parse(str(phone), "IN")
		if phonenumbers.is_valid_number(parsed):
			# Extract the national number, which is 10 digits for India
			national_num = str(parsed.national_number)
			if len(national_num) == 10:
				return national_num
	except phonenumbers.NumberParseException:
		pass
	
	# Fallback: strip non-numeric and take last 10
	digits = re.sub(r"\D", "", str(phone))
	return digits[-10:] if len(digits) >= 10 else digits


def _phone_variants(normalized: str):
	return [normalized, f"0{normalized}", f"+91{normalized}", f"+91 {normalized}", f"91{normalized}"]


def get_phone_variants_for_lookup(normalized: str):
	return _phone_variants(normalized)


def _find_customer_by_normalized_phone(normalized: str):
	if not frappe.db.has_column("Customer", "phone"):
		return None
	existing = frappe.db.get_value("Customer", {"phone": normalized}, "name")
	if existing:
		return existing
	res = frappe.db.sql("""
		SELECT name FROM `tabCustomer`
		WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone, ' ', ''), '+ ', ''), '-', ''), '(', '') LIKE %s
		LIMIT 1
	""", (f"%{normalized}",), as_dict=True)
	return res[0].name if res else None


def get_or_create_customer(phone: str, name: str = None, email: str = None):
	normalized = normalize_phone(phone)
	if not normalized or len(normalized) != 10:
		return None
	existing = _find_customer_by_normalized_phone(normalized)
	if existing:
		if name:
			frappe.db.set_value("Customer", existing, "customer_name", name)
		if email is not None:
			frappe.db.set_value("Customer", existing, "email", email or "")
		frappe.db.set_value("Customer", existing, "phone", normalized)
		frappe.db.commit()
		current = _find_customer_by_normalized_phone(normalized)
		return frappe.get_doc("Customer", current or existing)
	try:
		return frappe.get_doc({
			"doctype": "Customer",
			"phone": normalized,
			"customer_name": name or f"Customer {normalized}",
			"email": email or ""
		}).insert(ignore_permissions=True)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		existing = _find_customer_by_normalized_phone(normalized)
		if existing:
			if name:
				frappe.db.set_value("Customer", existing, "customer_name", name)
			if email is not None:
				frappe.db.set_value("Customer", existing, "email", email or "")
			frappe.db.commit()
			current = _find_customer_by_normalized_phone(normalized)
			return frappe.get_doc("Customer", current or existing)
		raise


def is_phone_verified(phone: str) -> bool:
	normalized = normalize_phone(phone)
	if not normalized or len(normalized) != 10:
		return False
	if not frappe.db.has_column("Customer", "verified_at"):
		return False
	for v in _phone_variants(normalized):
		if frappe.db.get_value("Customer", {"phone": v}, "verified_at"):
			return True
	return False


def _session_doctype_exists() -> bool:
	try:
		return bool(frappe.db.table_exists(f"tab{_SESSION_DOCTYPE}"))
	except Exception:
		return False


def create_customer_session(phone: str, customer_id: str, session_token: str = None) -> str:
	normalized = normalize_phone(phone)
	if not normalized or len(normalized) != 10:
		raise ValueError(f"Invalid phone: {phone!r}")
	if not session_token:
		session_token = frappe.generate_hash(length=48)
	session_data = {"customer_id": customer_id, "phone": normalized}
	try:
		frappe.cache().set_value(
			f"customer_session:{session_token}",
			session_data,
			expires_in_sec=SESSION_TTL_SECONDS
		)
	except Exception as e:
		frappe.log_error(f"Redis session write failed: {e}", "Session_Redis")
	if _session_doctype_exists():
		try:
			expires_at = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=SESSION_TTL_SECONDS)
			frappe.get_doc({
				"doctype": _SESSION_DOCTYPE,
				"session_token": session_token,
				"customer": customer_id,
				"phone": normalized,
				"revoked": 0,
				"expires_at": expires_at,
				"last_used_at": frappe.utils.now_datetime(),
			}).insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"DB session write failed: {e}", "Session_DB")
	return session_token


def _restore_session_from_db(session_token: str):
	if not _session_doctype_exists():
		return None
	try:
		rec = frappe.db.get_value(
			_SESSION_DOCTYPE,
			{"session_token": session_token, "revoked": 0},
			["customer", "phone", "expires_at"],
			as_dict=True
		)
		if not rec:
			return None
		if rec.expires_at and frappe.utils.now_datetime() > rec.expires_at:
			frappe.db.set_value(_SESSION_DOCTYPE, {"session_token": session_token}, "revoked", 1)
			frappe.db.commit()
			return None
		session_data = {"customer_id": rec.customer, "phone": rec.phone}
		try:
			remaining = int((rec.expires_at - frappe.utils.now_datetime()).total_seconds())
			frappe.cache().set_value(
				f"customer_session:{session_token}", session_data,
				expires_in_sec=max(remaining, 3600)
			)
		except Exception:
			pass
		return session_data
	except Exception as e:
		frappe.log_error(f"DB session restore failed: {e}", "Session_DB_Restore")
		return None


def validate_customer_session(phone: str, session_token: str, slide_expiry: bool = True) -> bool:
	try:
		if not session_token or not phone:
			return False
		normalized = normalize_phone(phone)
		if not normalized:
			return False
		session = frappe.cache().get_value(f"customer_session:{session_token}")
		if not session:
			session = _restore_session_from_db(session_token)
			if not session:
				frappe.log_error(title="Session Validation Failed", message=f"No session found for token: {session_token[:10]}...")
				return False
		
		if session.get("phone") != normalized:
			return False
		
		customer_id = session.get("customer_id")
		if not customer_id or not frappe.db.exists("Customer", customer_id):
			_hard_revoke(session_token)
			return False
		if slide_expiry:
			try:
				frappe.cache().set_value(
					f"customer_session:{session_token}", session,
					expires_in_sec=SESSION_TTL_SECONDS
				)
				# Skip DB update for now to avoid performance bottlenecks
				# if _session_doctype_exists():
				# 	new_exp = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=SESSION_TTL_SECONDS)
				# 	frappe.db.set_value(
				# 		_SESSION_DOCTYPE, {"session_token": session_token},
				# 		{"expires_at": new_exp, "last_used_at": frappe.utils.now_datetime()}
				# 	)
				# 	frappe.db.commit()
			except Exception:
				pass
		return True
	except Exception:
		return False


def get_customer_from_token(session_token: str) -> str:
	"""
	Securely retrieves the customer_id associated with a session token.
	Verifies against Cache/DB and ensures session is NOT revoked.
	"""
	if not session_token:
		return None
		
	# 1. Check Cache
	session = frappe.cache().get_value(f"customer_session:{session_token}")
	if not session:
		# 2. Try DB Restore
		session = _restore_session_from_db(session_token)
	
	if not session:
		return None
		
	customer_id = session.get("customer_id")
	if not customer_id or not frappe.db.exists("Customer", customer_id):
		return None
		
	return customer_id


def _hard_revoke(session_token: str):
	try:
		frappe.cache().delete_value(f"customer_session:{session_token}")
	except Exception:
		pass
	if _session_doctype_exists():
		try:
			frappe.db.set_value(_SESSION_DOCTYPE, {"session_token": session_token}, "revoked", 1)
			frappe.db.commit()
		except Exception:
			pass


def revoke_customer_session(session_token: str) -> bool:
	"""Hard logout: clears Redis and marks DB session as revoked."""
	if not session_token:
		return False
	
	existed = False
	# 1. Clear from Memory (Redis)
	try:
		if frappe.cache().get_value(f"customer_session:{session_token}"):
			existed = True
			frappe.cache().delete_value(f"customer_session:{session_token}")
	except Exception as e:
		frappe.log_error(f"Redis revoke failed: {e}", "Session_Revoke")
	
	# 2. Mark as Revoked in DB
	if _session_doctype_exists():
		try:
			# Check if it exists and isn't already revoked
			session_id = frappe.db.get_value(_SESSION_DOCTYPE, {"session_token": session_token, "revoked": 0}, "name")
			if session_id:
				existed = True
				frappe.db.set_value(
					_SESSION_DOCTYPE, session_id,
					{"revoked": 1, "last_used_at": frappe.utils.now_datetime()}
				)
				frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"DB revoke failed: {e}", "Session_Revoke_DB")
	
	return existed


def require_verified_phone(restaurant_id: str, phone: str) -> bool:
	plan_type = frappe.db.get_value("Restaurant", restaurant_id, "plan_type")
	if plan_type != "GOLD":
		return True
	config = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant_id}, "verify_my_user")
	if not config:
		return True
	return is_phone_verified(phone)


def get_platform_customer_from_user(user_email: str):
	if not user_email or user_email == "Guest":
		return None
	return frappe.db.get_value("Customer", {"email": user_email}, "name")


def mask_name(name):
	"""Mask name for SILVER restaurants: 'Priya Sharma' -> 'Pr*** Sh***'"""
	if not name: return "***"
	parts = str(name).split()
	masked_parts = []
	for p in parts:
		if len(p) <= 2:
			masked_parts.append(p[0] + "*" * (len(p) - 1) if p else "*")
		else:
			masked_parts.append(p[:2] + "*" * (len(p) - 2))
	return " ".join(masked_parts)


def mask_phone(phone):
	"""Mask phone: '9876543210' -> '98********'"""
	if not phone: return "**********"
	phone_str = str(phone)
	if len(phone_str) < 2: return "**********"
	return f"{phone_str[:2]}********"
