import frappe
import json
import time
from unittest.mock import patch, MagicMock
from frappe.utils import flt, now_datetime
from flamezo_backend.flamezo.logistics.manager import LogisticsManager
from flamezo_backend.flamezo.api.delivery import assign_delivery, handle_unified_webhook, sync_delivery_status

def setup_test_data():
    """Setup mock restaurant and order for testing"""
    print("  .. Setting up test data")
    timestamp = int(time.time())
    rest_id = f"TEST_LOG_{timestamp}"
    order_id = f"TEST_ORDER_{timestamp}"

    # 1. Create Mock Restaurant
    print(f"  .. Creating Restaurant {rest_id}")
    rest = frappe.get_doc({
        "doctype": "Restaurant",
        "restaurant_name": f"Test Logistics Hub {timestamp}",
        "restaurant_id": rest_id,
        "name": rest_id,
        "city": "Bangalore",
        "preferred_logistics_provider": "Flash",
        "delivery_markup_type": "Fixed",
        "delivery_markup_value": 10,
        "latitude": 12.9716,
        "longitude": 77.5946,
        "owner_phone": "9876543210"
    })
    rest.insert(ignore_permissions=True)
    frappe.db.commit()

    # 2. Update Settings (Normal fields)
    print("  .. Updating Settings")
    settings = frappe.get_single("Flamezo Settings")
    settings.flash_mode = "Sandbox"
    settings.flash_store_id = "89"
    settings.platform_delivery_convenience_fee = 5
    settings.save()
    frappe.db.commit()

    # 1.5 Create Mock Menu Product
    print("  .. Creating Menu Product")
    prod = frappe.get_doc({
        "doctype": "Menu Product",
        "product_name": "Test Pizza",
        "restaurant": rest_id,
        "price": 500,
        "calories": 0,
        "is_vegetarian": 0
    })
    prod.insert(ignore_permissions=True)
    frappe.db.commit()
    prod_name = prod.name

    # 3. Create Mock Order
    print(f"  .. Creating Order {order_id}")
    order = frappe.get_doc({
        "doctype": "Order",
        "order_id": order_id,
        "order_number": f"T{timestamp}",
        "restaurant": rest_id,
        "customer_name": "Test Customer",
        "customer_phone": "9000000000",
        "order_type": "delivery",
        "delivery_address": "Test Drop Address, Bangalore",
        "delivery_latitude": 12.9300,
        "delivery_longitude": 77.6100,
        "total": 500.0,
        "payment_status": "completed",
        "status": "confirmed",
        "order_items": [
            {
                "product": prod_name, 
                "quantity": 1, 
                "unit_price": 500,
                "total_price": 500
            }
        ]
    })
    order.insert(ignore_permissions=True)
    frappe.db.commit()
    
    return rest, order, prod_name

def mock_flash_responses(mock_post):
    """Setup mock side effects for requests.post in FlashProvider"""
    def side_effect(url, **kwargs):
        response = MagicMock()
        response.status_code = 200
        
        if "/getServiceability" in url:
            response.json.return_value = {
                "status": "200", 
                "serviceability": {"riderServiceAble": True, "locationServiceAble": True},
                "payouts": {"total": 60.0, "price": 50.0, "tax": 10.0}
            }
        elif "/createTask" in url:
            response.json.return_value = {
                "status": True, 
                "taskId": "FLASH_TASK_123", 
                "message": "Task created", 
                "Status_code": "ACCEPTED"
            }
        elif "/trackTaskStatus" in url:
            response.json.return_value = {
                "status": True,
                "status_code": "DISPATCHED",
                "data": {
                    "taskId": "FLASH_TASK_123",
                    "rider_name": "Flash Rider X",
                    "rider_contact": "9988776655",
                    "latitude": "12.9500",
                    "longitude": "77.6000",
                    "tracking_url": "https://track.flash.com/123"
                }
            }
        elif "/cancelTask" in url:
            response.json.return_value = {"status": True, "message": "Cancelled"}
            
        return response
    
    mock_post.side_effect = side_effect

def run_tests():
    print("🚀 Starting E2E Logistics Hub Tests...")
    try:
        rest, order, prod_name = setup_test_data()
        print(f"✅ Setup: Mock Restaurant '{rest.name}' and Order '{order.name}' created.")

        # Universal patch for get_password to handle Flash integration token
        with patch('frappe.model.base_document.BaseDocument.get_password', return_value="DUMMY_TOKEN"):
            with patch('requests.post') as mock_post, patch('requests.get') as mock_get:
                mock_flash_responses(mock_post)
                
                # --- TEST 1: Quoting ---
                print("\n🔍 Running TEST 1: Delivery Quoting...")
                manager = LogisticsManager(rest.name)
                quote = manager.get_quote({
                    "address": order.delivery_address,
                    "latitude": order.delivery_latitude,
                    "longitude": order.delivery_longitude,
                    "total": order.total,
                    "items": order.order_items
                })
                
                # Expected: base 60 + markup 10 + platform 5 = 75
                assert quote["success"] is True, f"Quote failed: {quote.get('error')}"
                assert flt(quote["delivery_fee"]) == 75.0, f"Expected 75.0, got {quote['delivery_fee']}"
                assert quote["provider"] == "Flash"
                print("✅ TEST 1: Quote calculation (Base + Markup + Platform) is accurate.")

                # --- TEST 2: Booking & Coins ---
                print("\n💰 Running TEST 2: Booking & Coin Deduction...")
                frappe.set_user("Administrator")
                
                booking_res = assign_delivery(order.name, "auto", partner_name="flash")
                assert booking_res.get("success") is True, f"Booking failed: {booking_res.get('error') or booking_res}"
                
                # Verify Order updates
                order.reload()
                assert order.delivery_id == "FLASH_TASK_123"
                assert order.delivery_status == "ACCEPTED"
                assert flt(order.delivery_fee) == 75.0
                assert flt(order.logistics_platform_fee) == 5.0
                
                # Verify Coin Transaction
                coins = frappe.db.get_value("Coin Transaction", {"reference_name": order.name}, "amount")
                print(f"ℹ️ Coin Transaction Deduction Found: {coins}")
                assert coins is not None, "No coin deduction transaction found for this order."
                print("✅ TEST 2: Order booked and coins deducted successfully.")

                # --- TEST 3: Webhook Simulation ---
                print("\n📡 Running TEST 3: Webhook Status Update Simulation...")
                webhook_payload = {
                    "status": True,
                    "status_code": "DISPATCHED",
                    "data": {
                        "taskId": "FLASH_TASK_123",
                        "rider_name": "Flash Rider X",
                        "rider_contact": "9988776655",
                        "latitude": "12.9540",
                        "longitude": "77.6010",
                        "tracking_url": "https://track.flash.com/123"
                    }
                }
                
                mock_request = MagicMock()
                mock_request.get_data.return_value = json.dumps(webhook_payload).encode('utf-8')
                mock_request.args = {"provider": "flash"}
                
                with patch('frappe.request', mock_request):
                    res = handle_unified_webhook()
                    assert res["status"] is True, f"Webhook failed: {res}"
                    assert res["message"] == "Webhook Processed"

                order.reload()
                assert order.delivery_status == "DISPATCHED"
                assert order.delivery_rider_name == "Flash Rider X"
                assert flt(order.rider_latitude) == 12.9540
                print("✅ TEST 3: Webhook successfully updated Order status and rider location.")

                # --- TEST 4: Sync/Tracking Fallback ---
                print("\n🔄 Running TEST 4: Manual Sync (Track Status)...")
                sync_res = sync_delivery_status(order.name)
                assert sync_res["success"] is True
                assert sync_res["status"] == "DISPATCHED"
                print("✅ TEST 4: Manual Sync successfully pulled latest provider status.")

        print("\n🏁 ALL TESTS PASSED SUCCESSFULLY!")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🧹 Cleaning up test data...")
        try:
            if 'order' in locals() and order:
                frappe.delete_doc("Order", order.name, ignore_permissions=True)
            if 'prod_name' in locals():
                frappe.delete_doc("Menu Product", prod_name, ignore_permissions=True)
            if 'rest' in locals() and rest:
                frappe.delete_doc("Restaurant", rest.name, ignore_permissions=True)
            frappe.db.commit()
            print("Done.")
        except Exception as cleanup_err:
            print(f"⚠️ Cleanup partially failed: {str(cleanup_err)}")

if __name__ == "__main__":
    run_tests()
