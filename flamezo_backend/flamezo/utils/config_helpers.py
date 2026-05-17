# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import os
import frappe

def get_app_base_url():
    """
    Production-ready URL resolution.
    Priority:
    1. frappe.conf.app_base_url (Site configuration)
    2. os.environ.get("APP_BASE_URL") (Environment variable)
    3. Fallback: https://app.flamezo_backend.com/
    """
    # 1. Check site config (common_site_config.json or site_config.json)
    base_url = frappe.conf.get("app_base_url")
    
    # 2. Check environment variable
    if not base_url:
        base_url = os.environ.get("APP_BASE_URL")
        
    # 3. Final Fallback
    if not base_url:
        base_url = "https://app.flamezo_backend.com/"
        
    return base_url.rstrip("/") + "/"

@frappe.whitelist(allow_guest=True)
def get_app_settings():
    """
    Exposes global app settings to the frontend.
    """
    return {
        "app_base_url": get_app_base_url(),
        "platform_name": "Flamezo",
        "support_email": "support@flamezo_backend.com"
    }
