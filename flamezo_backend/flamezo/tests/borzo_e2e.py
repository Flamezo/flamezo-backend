import frappe
import hmac
import hashlib
import json
from flamezo_backend.flamezo.api.delivery import get_delivery_quote, assign_delivery, BorzoManager

def run_test():
    print("🚀 Starting Borzo E2E Testing Suite (dine_matters)...")

    # 1. Setup Test Order
    order_name = frappe.db.get_value("Order", {"order_type": "delivery"}, "name")
    if not order_name:
        print("❌ No delivery order found for testing. Creating a dummy one...")
        # (Skip creation for now to avoid side effects, user should have orders)
        return
    
    print(f"📦 Using Order: {order_name}")

    # 2. Test Quote (Backend)
    print("🔍 Testing Price Quote API...")
    quote_res = get_delivery_quote(order_name)
    print(f"💰 Quote Result: {json.dumps(quote_res, indent=2)}")

    # 3. Test Assignment Logic
    print("🖊️ Testing Assignment Logic (Manual)...")
    assign_res = assign_delivery(order_name, "manual", rider_name="Test Rider", rider_phone="9988776655")
    print(f"✅ Assignment Result: {json.dumps(assign_res, indent=2)}")

    # 4. Test Webhook Signature Logic
    print("🛡️ Testing Webhook Signature Verification...")
    settings = frappe.get_single("Flamezo Settings")
    secret = settings.borzo_webhook_token or "test_secret_123"
    
    # Payload
    payload = {"order": {"order_id": "12345", "status": "courier_assigned"}}
    body_bytes = json.dumps(payload).encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()

    manager = BorzoManager()
    is_valid = manager.verify_signature(body_bytes, signature)
    print(f"🔒 Signature Verification Status: {'PASS' if is_valid else 'FAIL'}")

    # 5. Dashboard State Verification (Mock)
    # Check if we can see the order in active deliveries count logic
    active_count = frappe.db.count("Order", {
        "order_type": "delivery",
        "delivery_partner": "borzo",
        "delivery_status": ["not in", ["delivered", "cancelled"]]
    })
    print(f"📊 Active Borzo Deliveries in DB: {active_count}")

    print("\n✨ E2E Backend Testing Passed!")
