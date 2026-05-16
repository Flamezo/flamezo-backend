import frappe
import requests
import json

def get_whatsapp_config():
    settings = frappe.get_single('Flamezo Settings')
    token = settings.get_password('whatsapp_cloud_api_token')
    phone_id = settings.whatsapp_cloud_api_phone_id
    business_id = settings.whatsapp_cloud_api_business_id
    return {
        "token": token,
        "phone_id": phone_id,
        "business_id": business_id
    }

def send_test_message(to_number="917487871213"):
    config = get_whatsapp_config()
    if not config['token'] or not config['phone_id']:
        print("Missing config")
        return

    url = f"https://graph.facebook.com/v21.0/{config['phone_id']}/messages"
    headers = {
        "Authorization": f"Bearer {config['token']}",
        "Content-Type": "application/json"
    }
    
    # We use the default 'hello_world' template for testing
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {
                "code": "en_US"
            }
        }
    }

    print(f"Sending test message to {to_number}...")
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        print("Test message sent successfully!")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Error sending message: {response.status_code} - {response.text}")

def verify_status():
    config = get_whatsapp_config()
    if not config['token'] or not config['phone_id']:
        print("Missing config")
        return

    url = f"https://graph.facebook.com/v21.0/{config['phone_id']}"
    headers = {
        "Authorization": f"Bearer {config['token']}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("Phone Status from Meta:")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Error fetching status: {response.status_code} - {response.text}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        send_test_message(sys.argv[1])
    else:
        verify_status()
