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
