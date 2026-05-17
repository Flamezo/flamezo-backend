import frappe
import requests
import json

def send_direct_text(phone="917487871213", message="Test"):
    settings = frappe.get_single('Flamezo Settings')
    token = settings.get_password('whatsapp_cloud_api_token')
    phone_id = settings.whatsapp_cloud_api_phone_id
    
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"preview_url": False, "body": message}
    }
    
    print(f"Sending direct text to {phone}...")
    res = requests.post(url, headers=headers, json=payload)
    print(res.text)

if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "917487871213"
    m = sys.argv[2] if len(sys.argv) > 2 else "Test message from Flamezo"
    send_direct_text(p, m)
