# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
OTP delivery services:
  1. Meta Cloud API (WhatsApp Business) — primary, production-grade
  2. Fast2SMS (SMS) — fallback
"""

import re
import requests
import frappe
from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone

FAST2SMS_SMS_URL = "https://www.fast2sms.com/dev/bulkV2"
META_GRAPH_API_URL = "https://graph.facebook.com/v21.0"
OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 5
OTP_RESEND_COOLDOWN = 30
OTP_MAX_PER_HOUR = 3


def send_otp_via_whatsapp(phone: str, otp: str, restaurant_name: str = None) -> bool:
	"""
	Send OTP via Meta Cloud API (WhatsApp Business).
	Uses the 'verify_code_1' authentication template: "{{code}} is your verification code."

	Config (site_config.json or Flamezo Settings):
	  - whatsapp_phone_number_id: Phone number ID from Meta Business Manager
	  - whatsapp_access_token: Permanent system user token
	  - whatsapp_otp_template: Template name (default: verify_code_1)
	"""
	try:
		site_config = frappe.get_site_config()

		phone_number_id = site_config.get("whatsapp_phone_number_id")
		access_token = site_config.get("whatsapp_access_token")
		template_name = site_config.get("whatsapp_otp_template") or "otp_verify"

		if not phone_number_id or not access_token:
			return False

		to = normalize_phone(phone)
		if not to or len(to) != 10:
			return False
		to = f"91{to}"

		endpoint = f"{META_GRAPH_API_URL}/{phone_number_id}/messages"

		headers = {
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json",
		}

		payload = {
			"messaging_product": "whatsapp",
			"to": to,
			"type": "template",
			"template": {
				"name": template_name,
				"language": {"code": "en_US"},
				"components": [
					{
						"type": "body",
						"parameters": [
							{"type": "text", "text": str(otp)}
						]
					},
					{
						"type": "button",
						"sub_type": "url",
						"index": "0",
						"parameters": [
							{"type": "text", "text": str(otp)}
						]
					}
				]
			}
		}

		# Short timeout: OTP delivery is on the login critical path, so a slow
		# Meta Graph endpoint must not stall the request (was 15s → ~25s total
		# with the SMS fallback, leaving the app stuck on "Sending...").
		resp = requests.post(endpoint, json=payload, headers=headers, timeout=8)
		data = resp.json() if resp.text else {}

		if resp.status_code in [200, 201] and data.get("messages"):
			return True

		frappe.log_error(
			message=f"status={resp.status_code} body={resp.text[:500]}",
			title="OTP_WhatsApp_Failed"
		)
		return False

	except Exception as e:
		frappe.log_error(message=str(e)[:500], title="OTP_WhatsApp_Error")
		return False


def send_otp_via_sms(api_key: str, numbers: str, otp: str, restaurant_name: str = None) -> bool:
	"""Send OTP via Fast2SMS. Returns True if successful."""
	try:
		# DLT config: prefer site_config.json (secure, server-side, not in git);
		# fall back to Flamezo Settings for backwards compatibility.
		conf = frappe.conf
		settings = frappe.get_single("Flamezo Settings")
		sender_id = conf.get("fast2sms_sender_id") or getattr(settings, "fast2sms_sender_id", None)
		dlt_template_id = conf.get("fast2sms_dlt_template_id") or getattr(settings, "fast2sms_dlt_template_id", None)
		route = "dlt" if (sender_id and dlt_template_id) else "q"

		headers = {"authorization": api_key, "Content-Type": "application/json"}

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
				"sender_id": sender_id,
				"message": str(dlt_template_id),
				"variables_values": otp,
				"numbers": numbers
			}

		resp = requests.post(FAST2SMS_SMS_URL, json=payload, headers=headers, timeout=7)
		data = resp.json() if resp.text else {}
		return resp.status_code == 200 and data.get("return", False)
	except Exception as e:
		frappe.log_error(f"Fast2SMS SMS failed: {e}", "OTP_SMS_Failed")
		return False


# Legacy — kept for backwards compatibility during migration
def send_otp_via_evolution_api(url: str, api_key: str, instance: str, phone: str, otp: str, restaurant_name: str = None) -> bool:
	"""DEPRECATED: Use send_otp_via_whatsapp (Meta Cloud API) instead."""
	try:
		if not url or not api_key or not instance:
			return False

		to = normalize_phone(phone)
		if len(to) == 10 and not to.startswith("91"):
			to = "91" + to

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
