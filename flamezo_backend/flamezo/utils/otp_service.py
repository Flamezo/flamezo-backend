# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
Fast2SMS & Evolution API OTP service.
"""

import re
import requests
import frappe
from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone

FAST2SMS_SMS_URL = "https://www.fast2sms.com/dev/bulkV2"
OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 5
OTP_RESEND_COOLDOWN = 30
OTP_MAX_PER_HOUR = 3


def send_otp_via_sms(api_key: str, numbers: str, otp: str, restaurant_name: str = None) -> bool:
	"""Send OTP via Fast2SMS. Returns True if successful."""
	try:
		settings = frappe.get_single("Flamezo Settings")
		route = "dlt"
		if not (getattr(settings, "fast2sms_sender_id", None) and getattr(settings, "fast2sms_dlt_template_id", None)):
			route = "q"  # Quick SMS – temporary testing only (₹5/SMS), not production

		headers = {"authorization": api_key, "Content-Type": "application/json"}

		# Production message: restaurant-dynamic, single-line (newlines can affect delivery)
		label = (restaurant_name or "Flamezo").strip()[:25]
		sms_message = f"Your {label} verification code is: {otp}. Don't share this code with anyone."

		if route == "q":
			payload = {
				"route": "q",
				"message": sms_message,
				"numbers": numbers
			}
		else:
			payload = {
				"route": "dlt",
				"sender_id": settings.fast2sms_sender_id,
				"message": settings.fast2sms_dlt_template_id,
				"variables_values": otp,
				"numbers": numbers
			}

		resp = requests.post(FAST2SMS_SMS_URL, json=payload, headers=headers, timeout=10)
		data = resp.json() if resp.text else {}
		return resp.status_code == 200 and data.get("return", False)
	except Exception as e:
		frappe.log_error(f"Fast2SMS SMS failed: {e}", "OTP_SMS_Failed")
		return False








def send_otp_via_evolution_api(url: str, api_key: str, instance: str, phone: str, otp: str, restaurant_name: str = None) -> bool:
	"""Send OTP via Evolution API (WhatsApp). Returns True if successful."""
	try:
		if not url or not api_key or not instance:
			return False

		to = normalize_phone(phone)
		if len(to) == 10 and not to.startswith("91"):
			to = "91" + to

		# Ensure URL doesn't have trailing slash
		url = url.rstrip("/")
		endpoint = f"{url}/message/sendText/{instance}"
		
		headers = {
			"apikey": api_key,
			"Content-Type": "application/json"
		}

		label = (restaurant_name or "Flamezo").strip()[:25]
		payload = {
			"number": to,
			"text": f"Your {label} verification code is: {otp}. Don't share this code with anyone."
		}

		resp = requests.post(endpoint, json=payload, headers=headers, timeout=12)
		data = resp.json() if resp.text else {}
		
		success = resp.status_code in [200, 201] and data.get("key")
		if not success:
			frappe.log_error(f"Evolution API Failed: {resp.text}", "OTP_Evolution_Failed")
			
		return success
	except Exception as e:
		frappe.log_error(f"Evolution API failed: {e}", "OTP_Evolution_Error")
		return False
