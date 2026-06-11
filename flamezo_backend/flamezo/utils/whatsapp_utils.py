# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
import requests
import re
from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone

def send_whatsapp_message(phone, message, settings=None):
    """
    Generic function to send WhatsApp messages via Evolution API.
    Supports both free-text and template-based sending.
    Returns: (bool success, str error_message)
    """
    if not settings:
        settings = frappe.get_single("Flamezo Settings")

    url = getattr(settings, "evolution_api_url", None)
    api_key = settings.get_password("evolution_api_key")
    instance = getattr(settings, "evolution_api_instance", None) or "Flamezo"
    marketing_template = getattr(settings, "marketing_wa_template_name", None)

    if not url or not api_key:
        return False, "Evolution API not configured in Flamezo Settings"

    # Clean phone number (Evolution API expects digits only)
    phone_clean = normalize_phone(phone)
    if len(phone_clean) == 10 and not phone_clean.startswith("91"):
        phone_clean = "91" + phone_clean

    if marketing_template:
        # ✅ Template-based (Meta compliant for marketing window)
        endpoint = f"{url.rstrip('/')}/message/sendWhatsAppBusinessTemplate/{instance}"
        payload = {
            "number": phone_clean,
            "template": {
                "name": marketing_template,
                "language": {"code": "en"},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": message}]}]
            }
        }
    else:
        # Free-text (compliant within 24h customer-initiated window only)
        endpoint = f"{url.rstrip('/')}/message/sendText/{instance}"
        payload = {"number": phone_clean, "text": message}

    try:
        res = requests.post(
            endpoint,
            headers={
                "apikey": api_key,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=15
        )
        if res.status_code in [200, 201]:
            return True, None
        
        error_info = res.text[:200]
        frappe.log_error(f"Evolution API HTTP {res.status_code}: {error_info}", "WhatsApp Send Failed")
        return False, f"Evolution API Error: {res.status_code}"
    
    except Exception as e:
        frappe.log_error(f"WhatsApp send exception: {str(e)}", "WhatsApp Send Exception")
        return False, str(e)


def send_whatsapp_cloud_message(to_phone, template_name, body_params, settings=None, language="en", button_url_param=None):
    """
    Send a WhatsApp message via the OFFICIAL Meta WhatsApp Cloud API (Graph API).
    Used for business-initiated, reliable order delivery to restaurants.

    Args:
        to_phone: recipient phone (10-digit or 91XXXXXXXXXX)
        template_name: name of an APPROVED Meta utility template
        body_params: list mapped in order to the template body params {{1}}, {{2}}, ...
        language: template language code (default 'en')
        button_url_param: if the template has a dynamic URL button, the value substituted
            into its {{1}} (e.g. the receipt token appended to flamezo.in/o/)

    Returns: (bool success, str message_id_or_error)
    """
    if not settings:
        settings = frappe.get_single("Flamezo Settings")

    # Prefer the platform Meta Cloud creds in site_config — these are the same ones
    # OTP uses and are proven working on prod. Fall back to Flamezo Settings.
    site_config = frappe.get_site_config() or {}
    token = site_config.get("whatsapp_access_token") or settings.get_password("whatsapp_cloud_api_token")
    phone_id = site_config.get("whatsapp_phone_number_id") or getattr(settings, "whatsapp_cloud_api_phone_id", None)

    if not token or not phone_id:
        return False, "WhatsApp Cloud API not configured (site_config or Flamezo Settings)"
    if not template_name:
        return False, "No WhatsApp order template configured"

    to_clean = normalize_phone(to_phone)
    if len(to_clean) == 10 and not to_clean.startswith("91"):
        to_clean = "91" + to_clean

    components = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in (body_params or [])],
        }
    ]
    if button_url_param:
        components.append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": str(button_url_param)}],
        })

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components,
        },
    }

    try:
        res = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if res.status_code in (200, 201):
            data = res.json()
            msg_id = (data.get("messages") or [{}])[0].get("id")
            return True, msg_id
        frappe.log_error(f"Meta Cloud API HTTP {res.status_code}: {res.text[:300]}", "WhatsApp Cloud Send Failed")
        return False, f"Meta Cloud API Error {res.status_code}: {res.text[:150]}"
    except Exception as e:
        frappe.log_error(f"WhatsApp Cloud send exception: {str(e)}", "WhatsApp Cloud Send Exception")
        return False, str(e)
