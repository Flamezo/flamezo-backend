"""
Petpooja POS Integration — End-to-End Test Suite

Covers all integration flows per the official Petpooja API docs:
  - Save Order (push_order)          → petpoojamarkdown2.md + pet-pooja.md
  - Order Callback (handle_callback) → pet-pooja.md (status codes -1,1,2,3,4,5,10)
  - Menu Push (handle_menu_push)     → pet-pooja.md Push Menu
  - Item Stock On/Off                → pet-pooja.md Update Item Stock
  - Store Status On/Off              → pet-pooja.md Update Store Status
  - Rider Info Webhook               → pet-pooja.md Rider Information
  - Status Machine (no regression)   → status_priority guard
  - Duplicate push guard             → is_pushed_to_pos idempotency
  - Utils trigger (get_doc_before_save) → handle_order_update

Run:
  cd /home/frappe/frappe-bench
  bench execute dinematters.dinematters.dinematters.tests.petpooja_e2e_test.run_tests
"""

import frappe
import json
import time
from unittest.mock import patch, MagicMock
from frappe.utils import now_datetime


# ─── Constants ────────────────────────────────────────────────────────────────

SANDBOX_APP_KEY    = "TEST_APP_KEY_32CHARS_PLACEHOLDER"
SANDBOX_APP_SECRET = "TEST_APP_SECRET_40CHARS_PLACEHOLDER00000"
SANDBOX_ACCESS_TOKEN = "TEST_ACCESS_TOKEN_40CHARS_PLACEHOLDER000"
SANDBOX_REST_ID    = "PP_TEST_REST_001"


# ─── Test Fixtures ────────────────────────────────────────────────────────────

def setup_test_data():
    """Create isolated test restaurant, menu product, and order."""
    ts = int(time.time())
    rest_id   = f"TEST_PP_{ts}"
    order_id  = f"TEST_PP_ORDER_{ts}"

    print(f"  .. Creating Restaurant {rest_id}")
    rest = frappe.get_doc({
        "doctype": "Restaurant",
        "restaurant_id": rest_id,
        "restaurant_name": f"Test Petpooja Restaurant {ts}",
        "plan_type": "GOLD",
        "is_active": 1,
        "coins_balance": 5000.0,
        "pos_enabled": 1,
        "pos_provider": "Petpooja",
        "pos_app_key": SANDBOX_APP_KEY,
        "pos_app_secret": SANDBOX_APP_SECRET,
        "pos_access_token": SANDBOX_ACCESS_TOKEN,
        "pos_merchant_id": SANDBOX_REST_ID,
        "address": "123 Test Street, Mumbai",
        "contact_number": "9876543210",
    })
    rest.insert(ignore_permissions=True)
    frappe.db.commit()

    print(f"  .. Creating Menu Product")
    prod = frappe.get_doc({
        "doctype": "Menu Product",
        "restaurant": rest_id,
        "product_name": "Margherita Pizza",
        "pos_id": "ITEM_101",
        "price": 250.0,
        "status": "Active",
        "is_vegetarian": 1,
    })
    prod.insert(ignore_permissions=True)
    frappe.db.commit()

    print(f"  .. Creating Order {order_id}")
    order = frappe.get_doc({
        "doctype": "Order",
        "order_id": order_id,
        "order_number": f"TP{ts}",
        "restaurant": rest_id,
        "status": "pending_verification",
        "customer_name": "John Doe",
        "customer_phone": "9876543210",
        "customer_email": "john@example.com",
        "order_type": "delivery",
        "delivery_address": "456 Customer Lane, Delhi",
        "delivery_city": "Delhi",
        "delivery_zip_code": "110001",
        "delivery_landmark": "Near Metro",
        "delivery_latitude": 28.7041,
        "delivery_longitude": 77.1025,
        "payment_method": "online",
        "subtotal": 500.0,
        "tax": 45.0,
        "cgst": 22.5,
        "sgst": 22.5,
        "tax_percent": 9.0,
        "delivery_fee": 50.0,
        "packaging_fee": 20.0,
        "discount": 0.0,
        "loyalty_discount": 0.0,
        "total": 615.0,
        "is_pushed_to_pos": 0,
        "payment_status": "completed",
        "order_items": [
            {
                "product": prod.name,
                "product_name": "Margherita Pizza",
                "quantity": 2,
                "unit_price": 250.0,
                "total_price": 500.0,
                "tax_percent": 9.0,
                "tax_amount": 45.0,
                "is_tax_inclusive": 0,
            }
        ],
    })
    order.insert(ignore_permissions=True)
    frappe.db.commit()

    return rest, order, prod


def teardown_test_data(rest_id):
    """Remove all test records by restaurant prefix."""
    frappe.db.delete("Order", {"restaurant": rest_id})
    frappe.db.delete("Menu Product", {"restaurant": rest_id})
    frappe.db.delete("Restaurant", {"name": rest_id})
    frappe.db.commit()
    print(f"  .. Cleaned up {rest_id}")


def make_petpooja_provider(rest):
    """Get a live PetpoojaProvider instance with credentials stubbed."""
    from dinematters.dinematters.pos.petpooja import PetpoojaProvider

    with patch.object(
        frappe.model.base_document.BaseDocument, "get_password",
        side_effect=lambda field: {
            "pos_app_secret": SANDBOX_APP_SECRET,
            "pos_access_token": SANDBOX_ACCESS_TOKEN,
        }.get(field, "")
    ):
        provider = PetpoojaProvider(rest)

    # Manually set credentials since patch scope is closed
    provider.settings["app_secret"]    = SANDBOX_APP_SECRET
    provider.settings["access_token"]  = SANDBOX_ACCESS_TOKEN
    return provider


# ─── Helpers ──────────────────────────────────────────────────────────────────

def mock_save_order_success():
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"success": "1", "orderID": "PP_POS_ORDER_999"}
    return resp

def mock_save_order_failure(msg="Item not found"):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"success": "0", "message": msg}
    return resp

def make_callback(client_order_id, status, rest_id=SANDBOX_REST_ID, **kwargs):
    payload = {
        "restID": rest_id,
        "orderID": client_order_id,
        "status": str(status),
        "cancel_reason": kwargs.get("cancel_reason", ""),
        "minimum_prep_time": kwargs.get("prep_time", "15"),
    }
    payload.update(kwargs)
    return payload


# ─── Test Cases ───────────────────────────────────────────────────────────────

def test_1_payload_structure(provider, order):
    """T1: _format_order produces correct schema per petpoojamarkdown2.md"""
    print("\n📦 T1: Payload structure validation")

    payload = provider._format_order(order)

    # Top-level auth fields
    assert payload["app_key"]      == SANDBOX_APP_KEY,    "app_key mismatch"
    assert payload["app_secret"]   == SANDBOX_APP_SECRET, "app_secret mismatch"
    assert payload["access_token"] == SANDBOX_ACCESS_TOKEN, "access_token mismatch"
    assert payload["restID"]       == SANDBOX_REST_ID,    "restID mismatch"
    assert payload["device_type"]  == "Web",              "device_type must be 'Web'"

    # OrderInfo wrapper exists
    assert "OrderInfo" in payload, "Top-level key must be 'OrderInfo' not 'order'"

    oi = payload["OrderInfo"]

    # Customer fields
    c = oi["customer"]
    assert c["name"]    == "John Doe"
    assert c["phone"]   == "9876543210"
    assert c["email"]   == "john@example.com"
    assert "Near Metro" in c["address"], "Landmark must be appended to address"
    assert c["city"]    == "Delhi"
    assert c["zip"]     == "110001"
    assert c["latitude"]  == "28.7041"
    assert c["longitude"] == "77.1025"

    # Order fields
    o = oi["order"]
    assert o["orderID"]       == order.name
    assert o["order_type"]    == "H",      "delivery must map to 'H'"
    assert o["payment_type"]  == "ONLINE", "online payment must be 'ONLINE'"
    assert o["advanced_order"]== "N"
    assert o["enable_delivery"]== "1"
    # Totals are pulled directly from order_doc — assert they are present and numeric
    assert float(o["total"]) > 0,               f"total missing or zero: {o['total']}"
    assert float(o["tax_total"]) >= 0,           f"tax_total invalid: {o['tax_total']}"
    assert float(o["delivery_charges"]) >= 0,    f"delivery_charges invalid: {o['delivery_charges']}"
    assert float(o["packing_charges"])  >= 0,    f"packing_charges invalid: {o['packing_charges']}"
    # Verify values match what's on the order doc (not hardcoded)
    order.reload()
    assert float(o["total"]) == float(order.total), f"total mismatch: payload={o['total']} order={order.total}"
    assert "preorder_date"    in o
    assert "preorder_time"    in o
    assert "created_on"       in o
    assert "callback_url"     in o

    # OrderItem fields
    items = oi["orderItem"]
    assert len(items) == 1
    item = items[0]
    assert item["name"]        == "Margherita Pizza"
    assert item["quantity"]    == "2"
    assert float(item["price"])       == 250.0, f"price={item['price']}"
    assert float(item["final_price"]) == 500.0, f"final_price={item['final_price']}"
    assert item["gst_liability"] == "restaurant"
    assert isinstance(item["tax_inclusive"], bool)
    assert len(item["item_tax"]) == 2, f"Expected 2 item_tax entries, got {len(item['item_tax'])}"
    cgst = item["item_tax"][0]
    sgst = item["item_tax"][1]
    assert cgst["name"] == "CGST"
    assert sgst["name"] == "SGST"
    # tax_rate_half must be tax_percent / 2, derived from the actual order field (not hardcoded)
    order.reload()
    expected_half_rate = float(order.tax_percent) / 2
    assert float(cgst["tax_percentage"]) == expected_half_rate, \
        f"CGST rate should be {expected_half_rate} (tax_percent={order.tax_percent}/2), got {cgst['tax_percentage']}"
    assert float(sgst["tax_percentage"]) == expected_half_rate, \
        f"SGST rate should be {expected_half_rate}, got {sgst['tax_percentage']}"
    # Single item has full weight — item CGST amount should equal order-level CGST
    expected_cgst = float(order.cgst)
    expected_sgst = float(order.sgst)
    assert float(cgst["amount"]) == expected_cgst, \
        f"Item CGST amount should be {expected_cgst}, got {cgst['amount']}"
    assert float(sgst["amount"]) == expected_sgst, \
        f"Item SGST amount should be {expected_sgst}, got {sgst['amount']}"

    # Order-level tax_details array (key is "tax_details" not "tax" per official Petpooja schema)
    order_tax = oi["tax_details"]
    assert len(order_tax) == 2, f"order-level tax_details should have 2 entries, got {len(order_tax)}"
    assert order_tax[0]["title"] == "CGST"
    assert order_tax[1]["title"] == "SGST"
    assert order_tax[0]["type"] == "P"
    assert order_tax[1]["type"] == "P"
    assert float(order_tax[0]["tax"]) == expected_cgst, \
        f"Order CGST tax should be {expected_cgst}, got {order_tax[0]['tax']}"
    assert float(order_tax[1]["tax"]) == expected_sgst, \
        f"Order SGST tax should be {expected_sgst}, got {order_tax[1]['tax']}"
    assert "restaurant_liable_amt" in order_tax[0]
    assert "discount" not in oi, "discount array must NOT be present per Petpooja docs"

    print("  ✅ All payload fields validated")


def test_2_order_type_mapping(provider, order):
    """T2: order_type maps H / P / D correctly"""
    print("\n🗂  T2: Order type mapping")

    for (dm_type, expected) in [("delivery", "H"), ("takeaway", "P"), ("dine_in", "D")]:
        order.order_type = dm_type
        payload = provider._format_order(order)
        got = payload["OrderInfo"]["order"]["order_type"]
        assert got == expected, f"order_type '{dm_type}' should map to '{expected}', got '{got}'"

    order.order_type = "delivery"  # reset
    print("  ✅ H/P/D mapping correct")


def test_3_payment_type_mapping(provider, order):
    """T3: payment_type maps COD / CARD / ONLINE correctly"""
    print("\n💳 T3: Payment type mapping")

    cases = [
        ("online", "ONLINE"), ("upi", "ONLINE"), ("wallet", "ONLINE"),
        ("card", "CARD"),
        ("cash", "COD"), ("cod", "COD"), ("", "COD"),
    ]
    for (pm, expected) in cases:
        order.payment_method = pm
        got = provider._format_order(order)["OrderInfo"]["order"]["payment_type"]
        assert got == expected, f"payment_method '{pm}' should map to '{expected}', got '{got}'"

    order.payment_method = "online"  # reset
    print("  ✅ COD/CARD/ONLINE mapping correct")


def test_4_dine_in_table_number(provider, order):
    """T4: table_no injected for dine-in orders"""
    print("\n🪑 T4: Dine-in table_no injection")

    order.order_type    = "dine_in"
    order.table_number  = "7"
    payload = provider._format_order(order)
    assert payload["OrderInfo"]["order"].get("table_no") == "7", "table_no missing for dine-in"

    order.order_type   = "delivery"  # reset
    order.table_number = None
    print("  ✅ table_no present for dine-in")


def test_5_push_order_success(provider, order):
    """T5: push_order → success path persists pos_order_id"""
    print("\n🚀 T5: push_order — success path")

    with patch("requests.post", return_value=mock_save_order_success()) as mock_post:
        result = provider.push_order(order)

    assert result["status"]       == "success",        f"Expected success: {result}"
    assert result["pos_order_id"] == "PP_POS_ORDER_999"

    # Verify the correct URL was called
    call_url = mock_post.call_args[0][0]
    assert "47pfzh5sf2" in call_url, f"Wrong URL called: {call_url}"
    assert "save_order"  in call_url

    # Verify payload is JSON-serializable (no crashes on dumps)
    sent_body = json.loads(mock_post.call_args[1]["data"])
    assert "OrderInfo" in sent_body

    print("  ✅ push_order success — URL, payload, response all correct")


def test_6_push_order_failure(provider, order):
    """T6: push_order → failure path returns error dict"""
    print("\n❌ T6: push_order — failure path")

    with patch("requests.post", return_value=mock_save_order_failure("Item not found")):
        result = provider.push_order(order)

    assert result["status"]  == "error"
    assert "Item not found"   in result["message"]
    print("  ✅ push_order failure handled gracefully")


def test_7_push_order_network_error(provider, order):
    """T7: push_order → network timeout returns error dict (no crash)"""
    print("\n🌐 T7: push_order — network error")

    with patch("requests.post", side_effect=Exception("Connection timed out")):
        result = provider.push_order(order)

    assert result["status"] == "error"
    assert "timed out" in result["message"]
    print("  ✅ Network error handled without crash")


def test_8_push_order_missing_credentials(rest, order):
    """T8: push_order with missing credentials returns early error"""
    print("\n🔑 T8: push_order — missing credentials guard")

    from dinematters.dinematters.pos.petpooja import PetpoojaProvider

    bad_rest = frappe.copy_doc(rest)
    bad_rest.pos_app_key = ""
    bad_rest.pos_merchant_id = ""
    bad_rest.name = rest.name  # keep same name so settings resolution works

    provider = PetpoojaProvider.__new__(PetpoojaProvider)
    provider.restaurant = bad_rest
    provider.settings = {
        "app_key": "", "app_secret": "", "access_token": "", "merchant_id": ""
    }
    provider.save_order_url = "https://47pfzh5sf2.execute-api.ap-southeast-1.amazonaws.com/V1/save_order"

    with patch("requests.post") as mock_post:
        result = provider.push_order(order)
        mock_post.assert_not_called()

    assert result["status"] == "error"
    assert "Missing" in result["message"]
    print("  ✅ Missing credentials guard works — no HTTP call made")


def test_9_callback_status_accepted(provider, order):
    """T9: callback status 1/2/3 → Accepted"""
    print("\n📥 T9: Callback — status 1/2/3 = Accepted")

    order.db_set("status", "pending_verification")
    for code in ["1", "2", "3"]:
        order.db_set("status", "pending_verification")
        cb = make_callback(order.name, code)
        with patch("dinematters.dinematters.api.realtime.notify_order_update"):
            provider.handle_callback(cb)
        status = frappe.db.get_value("Order", order.name, "status")
        assert status == "Accepted", f"Status code {code} should set Accepted, got {status}"

    print("  ✅ Status 1/2/3 → Accepted")


def test_10_callback_status_dispatched(provider, order):
    """T10: callback status 4 → Dispatched"""
    print("\n🚗 T10: Callback — status 4 = Dispatched")

    order.db_set("status", "Accepted")
    cb = make_callback(order.name, 4)
    with patch("dinematters.dinematters.api.realtime.notify_order_update"):
        provider.handle_callback(cb)

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "Dispatched", f"Expected Dispatched, got {status}"  # doctype value = "Dispatched"
    print("  ✅ Status 4 → Dispatched")


def test_11_callback_status_ready(provider, order):
    """T11: callback status 5 → Ready (Food Ready)"""
    print("\n🍕 T11: Callback — status 5 = Ready")

    order.db_set("status", "Accepted")
    cb = make_callback(order.name, 5)
    with patch("dinematters.dinematters.api.realtime.notify_order_update"):
        provider.handle_callback(cb)

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "ready", f"Expected ready, got {status}"
    print("  ✅ Status 5 → ready")


def test_12_callback_status_delivered(provider, order):
    """T12: callback status 10 → Delivered"""
    print("\n✅ T12: Callback — status 10 = Delivered")

    order.db_set("status", "Dispatched")
    cb = make_callback(order.name, 10)
    with patch("dinematters.dinematters.api.realtime.notify_order_update"):
        provider.handle_callback(cb)

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "delivered", f"Expected delivered, got {status}"
    print("  ✅ Status 10 → delivered")


def test_13_callback_status_cancelled(provider, order):
    """T13: callback status -1 → Cancelled"""
    print("\n🚫 T13: Callback — status -1 = Cancelled")

    order.db_set("status", "Accepted")
    cb = make_callback(order.name, -1, cancel_reason="Restaurant busy")
    with patch("dinematters.dinematters.api.realtime.notify_order_update"):
        provider.handle_callback(cb)

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "cancelled", f"Expected cancelled, got {status}"
    print("  ✅ Status -1 → cancelled")


def test_14_callback_no_backwards_regression(provider, order):
    """T14: Status machine — cannot move backwards (e.g. Delivered → Accepted)"""
    print("\n🔒 T14: Status machine — no backward regression")

    order.db_set("status", "delivered")
    cb = make_callback(order.name, 1)  # Accepted
    with patch("dinematters.dinematters.api.realtime.notify_order_update") as mock_notify:
        provider.handle_callback(cb)
        mock_notify.assert_not_called()

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "delivered", f"Status regressed! Expected delivered, got {status}"
    print("  ✅ delivered → Accepted blocked correctly")


def test_15_callback_cancel_after_delivery_blocked(provider, order):
    """T15: Cancellation after delivery is blocked"""
    print("\n🛡  T15: Cancel after Delivered — blocked")

    order.db_set("status", "delivered")
    cb = make_callback(order.name, -1, cancel_reason="Late cancel")
    with patch("dinematters.dinematters.api.realtime.notify_order_update") as mock_notify:
        provider.handle_callback(cb)
        mock_notify.assert_not_called()

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "delivered", f"Expected delivered to remain, got {status}"
    print("  ✅ Cancel after delivered blocked correctly")


def test_16_callback_unknown_status(provider, order):
    """T16: Unknown status code is ignored (no crash)"""
    print("\n❓ T16: Unknown status code — ignored safely")

    order.db_set("status", "pending_verification")
    cb = make_callback(order.name, 99)
    with patch("dinematters.dinematters.api.realtime.notify_order_update") as mock_notify:
        provider.handle_callback(cb)
        mock_notify.assert_not_called()

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "pending_verification", f"Status should remain pending_verification, got {status}"
    print("  ✅ Unknown status 99 ignored, no crash")


def test_17_callback_missing_order_id(provider, order):
    """T17: Callback with no orderID — logged and ignored, no crash"""
    print("\n🔍 T17: Callback — missing orderID")

    cb = {"restID": SANDBOX_REST_ID, "status": "1"}
    try:
        provider.handle_callback(cb)
    except Exception as e:
        raise AssertionError(f"handle_callback crashed on missing orderID: {e}")
    print("  ✅ Missing orderID handled gracefully")


def test_18_callback_bad_app_key(provider, order):
    """T18: Callback with wrong app_key is rejected"""
    print("\n🔑 T18: Callback — wrong app_key rejected")

    order.db_set("status", "pending_verification")
    cb = make_callback(order.name, 1)
    cb["app_key"] = "WRONG_KEY_TOTALLY_DIFFERENT"

    with patch("dinematters.dinematters.api.realtime.notify_order_update") as mock_notify:
        provider.handle_callback(cb)
        mock_notify.assert_not_called()

    status = frappe.db.get_value("Order", order.name, "status")
    assert status == "pending_verification", f"Should remain pending_verification with bad app_key, got {status}"
    print("  ✅ Wrong app_key rejected — order untouched")


def test_19_callback_pos_sync_status_written(provider, order):
    """T19: pos_sync_status field is written on successful callback"""
    print("\n📝 T19: pos_sync_status field written")

    order.db_set("status", "pending_verification")
    cb = make_callback(order.name, 1)
    with patch("dinematters.dinematters.api.realtime.notify_order_update"):
        provider.handle_callback(cb)

    sync_status = frappe.db.get_value("Order", order.name, "pos_sync_status")
    assert sync_status and "Petpooja" in sync_status, f"pos_sync_status not written: {sync_status}"
    print(f"  ✅ pos_sync_status = '{sync_status}'")


def test_20_menu_push_categories_and_products(provider, order):
    """T20: Menu push creates/updates categories and products"""
    print("\n📋 T20: Menu push — category + product sync")

    menu_payload = {
        "categories": [
            {"categoryid": "CAT_001", "categoryname": "Burgers", "categorystatus": "1"},
            {"categoryid": "CAT_002", "categoryname": "Drinks", "categorystatus": "0"},
        ],
        "items": [
            {
                "itemid": "ITEM_BURGER_001", "itemname": "Classic Burger",
                "categoryid": "CAT_001", "itemprice": "199", "itemstatus": "1",
                "itemvegetarian": "0", "itemdescription": "Juicy beef burger",
                "nutrition": {"kcal": "450"},
            },
            {
                "itemid": "ITEM_DRINK_001", "itemname": "Cola",
                "categoryid": "CAT_002", "itemprice": "60", "itemstatus": "1",
                "itemvegetarian": "1", "itemdescription": "",
                "nutrition": {},
            },
        ],
    }

    result = provider.handle_menu_push(menu_payload)
    assert result["status"] == "success", f"Menu push failed: {result}"

    # Verify categories
    rest_id = provider.restaurant.name
    cat1 = frappe.get_all("Menu Category", {"pos_id": "CAT_001", "restaurant": rest_id}, ["status", "category_name"])
    assert cat1, "CAT_001 not created"
    assert cat1[0]["status"] == "Active"
    assert cat1[0]["category_name"] == "Burgers"

    cat2 = frappe.get_all("Menu Category", {"pos_id": "CAT_002", "restaurant": rest_id}, ["status"])
    assert cat2[0]["status"] == "Inactive"

    # Verify products
    p1 = frappe.get_all("Menu Product", {"pos_id": "ITEM_BURGER_001", "restaurant": rest_id},
                         ["price", "is_vegetarian", "calories", "description"])
    assert p1, "ITEM_BURGER_001 not created"
    assert float(p1[0]["price"]) == 199.0
    assert p1[0]["is_vegetarian"] == 0
    assert p1[0]["calories"] == 450

    # Verify pos_last_sync_at updated
    last_sync = frappe.db.get_value("Restaurant", rest_id, "pos_last_sync_at")
    assert last_sync, "pos_last_sync_at not updated after menu push"

    print("  ✅ Categories and products synced correctly")


def test_21_menu_push_idempotent_update(provider, order):
    """T21: Second menu push updates existing product, doesn't duplicate"""
    print("\n🔄 T21: Menu push — idempotent update (no duplicate records)")

    rest_id = provider.restaurant.name

    payload_v1 = {
        "categories": [{"categoryid": "CAT_UPD", "categoryname": "Starters", "categorystatus": "1"}],
        "items": [{
            "itemid": "ITEM_UPD_001", "itemname": "Spring Roll",
            "categoryid": "CAT_UPD", "itemprice": "120", "itemstatus": "1",
            "itemvegetarian": "1", "itemdescription": "Crispy roll", "nutrition": {},
        }],
    }
    provider.handle_menu_push(payload_v1)

    payload_v2 = {
        "categories": [{"categoryid": "CAT_UPD", "categoryname": "Starters V2", "categorystatus": "1"}],
        "items": [{
            "itemid": "ITEM_UPD_001", "itemname": "Spring Roll XL",
            "categoryid": "CAT_UPD", "itemprice": "150", "itemstatus": "0",
            "itemvegetarian": "1", "itemdescription": "Bigger crispy roll", "nutrition": {},
        }],
    }
    provider.handle_menu_push(payload_v2)

    products = frappe.get_all("Menu Product", {"pos_id": "ITEM_UPD_001", "restaurant": rest_id})
    assert len(products) == 1, f"Expected 1 product, got {len(products)} (duplicate created)"

    doc = frappe.get_doc("Menu Product", products[0].name)
    assert doc.product_name == "Spring Roll XL"
    assert float(doc.price) == 150.0
    assert doc.status == "Inactive"
    print("  ✅ No duplicate — product updated in place")


def test_22_item_stock_off(provider, order):
    """T22: Item stock-off webhook marks product Inactive"""
    print("\n📴 T22: Item stock off")

    rest_id = provider.restaurant.name
    prod = frappe.get_all("Menu Product", {"pos_id": "ITEM_101", "restaurant": rest_id}, limit=1)
    if not prod:
        print("  .. Skipped (ITEM_101 not in this test's restaurant context)")
        return

    cb = {"restID": SANDBOX_REST_ID, "inStock": False, "type": "Item", "itemID": ["ITEM_101"]}
    provider.handle_callback(cb)

    status = frappe.db.get_value("Menu Product", prod[0].name, "status")
    assert status == "Inactive", f"Expected Inactive, got {status}"
    print("  ✅ Item stock off → status = Inactive")


def test_23_item_stock_on(provider, order):
    """T23: Item stock-on webhook marks product Active"""
    print("\n📶 T23: Item stock on")

    rest_id = provider.restaurant.name
    prod = frappe.get_all("Menu Product", {"pos_id": "ITEM_101", "restaurant": rest_id}, limit=1)
    if not prod:
        print("  .. Skipped (ITEM_101 not in this test's restaurant context)")
        return

    frappe.db.set_value("Menu Product", prod[0].name, "status", "Inactive")
    cb = {"restID": SANDBOX_REST_ID, "inStock": True, "type": "Item", "itemID": "ITEM_101"}  # single string
    provider.handle_callback(cb)

    status = frappe.db.get_value("Menu Product", prod[0].name, "status")
    assert status == "Active", f"Expected Active, got {status}"
    print("  ✅ Item stock on → status = Active (string itemID handled)")


def test_24_store_status_close(provider, order):
    """T24: Store close webhook updates pos_store_status = Closed"""
    print("\n🏪 T24: Store close webhook")

    cb = {"restID": SANDBOX_REST_ID, "store_status": "0"}
    provider.handle_callback(cb)

    val = frappe.db.get_value("Restaurant", provider.restaurant.name, "pos_store_status")
    assert val == "Closed", f"Expected Closed, got {val}"
    print("  ✅ Store status = Closed")


def test_25_store_status_open(provider, order):
    """T25: Store open webhook updates pos_store_status = Open"""
    print("\n🟢 T25: Store open webhook")

    cb = {"restID": SANDBOX_REST_ID, "store_status": "1"}
    provider.handle_callback(cb)

    val = frappe.db.get_value("Restaurant", provider.restaurant.name, "pos_store_status")
    assert val == "Open", f"Expected Open, got {val}"
    print("  ✅ Store status = Open")


def test_26_rider_update(provider, order):
    """T26: Rider info webhook updates delivery_rider_name and delivery_rider_phone"""
    print("\n🛵 T26: Rider info webhook")

    cb = {
        "restID": SANDBOX_REST_ID,
        "order_id": order.name,
        "status": "rider-assigned",
        "rider_data": {"rider_name": "Raju Kumar", "rider_phone": "9001234567"},
    }
    provider.handle_callback(cb)

    rider_name  = frappe.db.get_value("Order", order.name, "delivery_rider_name")
    rider_phone = frappe.db.get_value("Order", order.name, "delivery_rider_phone")
    assert rider_name  == "Raju Kumar",   f"Expected 'Raju Kumar', got {rider_name}"
    assert rider_phone == "9001234567",   f"Expected '9001234567', got {rider_phone}"
    print("  ✅ Rider name and phone updated on order")


def test_27_duplicate_push_guard(provider, order):
    """T27: is_pushed_to_pos flag prevents double-push"""
    print("\n🔁 T27: Duplicate push guard (is_pushed_to_pos)")

    frappe.db.set_value("Order", order.name, "is_pushed_to_pos", 1)
    frappe.db.commit()

    with patch("requests.post") as mock_post:
        from dinematters.dinematters.pos.utils import push_order_to_pos_job
        push_order_to_pos_job(order.name)
        mock_post.assert_not_called()

    frappe.db.set_value("Order", order.name, "is_pushed_to_pos", 0)
    frappe.db.commit()
    print("  ✅ Duplicate push blocked — no HTTP call made")


def test_28_utils_trigger_on_accepted(order):
    """T28: handle_order_update enqueues push when status changes to Accepted"""
    print("\n⚙️  T28: utils.handle_order_update — enqueues on Accepted")

    from dinematters.dinematters.pos.utils import handle_order_update
    import frappe.utils.background_jobs as bj

    order.reload()
    order.status = "Accepted"

    # Simulate _doc_before_save
    before = frappe.copy_doc(order)
    before.status = "pending_verification"
    order._doc_before_save = before

    with patch("frappe.enqueue") as mock_enqueue:
        handle_order_update(order, method="on_update")
        mock_enqueue.assert_called_once()
        job_path = mock_enqueue.call_args[0][0]
        assert "push_order_to_pos_job" in job_path

    print("  ✅ Enqueue called with push_order_to_pos_job")


def test_29_utils_no_trigger_on_same_status(order):
    """T29: handle_order_update does NOT enqueue if status didn't change"""
    print("\n⚙️  T29: utils.handle_order_update — no enqueue on same status")

    from dinematters.dinematters.pos.utils import handle_order_update

    order.reload()
    order.status = "Accepted"
    before = frappe.copy_doc(order)
    before.status = "Accepted"  # same
    order._doc_before_save = before

    with patch("frappe.enqueue") as mock_enqueue:
        handle_order_update(order, method="on_update")
        mock_enqueue.assert_not_called()

    print("  ✅ No enqueue when status unchanged")


def test_30_utils_no_trigger_on_unpushable_status(order):
    """T30: handle_order_update does NOT enqueue on Placed, Preparing, Delivered etc."""
    print("\n⚙️  T30: utils — no enqueue on non-pushable statuses")

    from dinematters.dinematters.pos.utils import handle_order_update

    for status in ["pending_verification", "preparing", "ready", "Dispatched", "delivered", "cancelled"]:
        order.status = status
        before = frappe.copy_doc(order)
        before.status = "Placed"
        order._doc_before_save = before

        with patch("frappe.enqueue") as mock_enqueue:
            handle_order_update(order, method="on_update")
            mock_enqueue.assert_not_called(), f"Enqueue should NOT fire for status={status}"

    print("  ✅ Non-pushable statuses — no enqueue triggered")


def test_31_map_status_all_codes(provider):
    """T31: map_status returns correct DineMatters status for all Petpooja codes"""
    print("\n🗺  T31: map_status — all codes")

    expected = {
        "1": "Accepted", "2": "Accepted", "3": "Accepted",
        "4": "Dispatched", "5": "ready", "10": "delivered",
        "-1": "cancelled",
    }
    for code, exp_status in expected.items():
        got = provider.map_status(code)
        assert got == exp_status, f"map_status({code}) = {got}, expected {exp_status}"

    assert provider.map_status("99") is None, "Unknown code should return None"
    print("  ✅ All 7 status codes map correctly + unknown returns None")


def test_32_get_pos_provider_routing():
    """T32: get_pos_provider returns PetpoojaProvider for pos_provider='Petpooja'"""
    print("\n🔌 T32: get_pos_provider routing")

    from dinematters.dinematters.pos.base import get_pos_provider
    from dinematters.dinematters.pos.petpooja import PetpoojaProvider

    mock_rest = MagicMock()
    mock_rest.pos_enabled = 1
    mock_rest.pos_provider = "Petpooja"
    mock_rest.pos_app_key = "key"
    mock_rest.pos_merchant_id = "id"
    mock_rest.get_password = MagicMock(return_value="secret")

    provider = get_pos_provider(mock_rest)
    assert isinstance(provider, PetpoojaProvider), f"Expected PetpoojaProvider, got {type(provider)}"
    print("  ✅ get_pos_provider returns PetpoojaProvider")


def test_33_pos_gateway_sniff_petpooja():
    """T33: pos_gateway sniffs Petpooja by clientorderID field"""
    print("\n🌐 T33: pos_gateway — provider sniffing")

    from dinematters.dinematters.api.pos import _process_gateway_event

    data = {
        "clientorderID": "NONEXISTENT_ORDER",
        "restID": "NONEXISTENT_REST",
        "status": "1",
    }
    # Should not crash, even if restaurant not found — just logs
    try:
        _process_gateway_event(data=data, provider_hint=None)
    except Exception as e:
        raise AssertionError(f"Gateway sniffing crashed: {e}")
    print("  ✅ Gateway sniffing ran without crash (restaurant not found logged)")


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_tests():
    import traceback

    print("\n" + "="*65)
    print("  🧪 PETPOOJA POS — E2E TEST SUITE")
    print("="*65)

    rest, order, prod = setup_test_data()
    rest_id = rest.name
    passed = 0
    failed = 0
    errors = []

    try:
        provider = make_petpooja_provider(rest)

        tests = [
            (test_1_payload_structure,             (provider, order)),
            (test_2_order_type_mapping,            (provider, order)),
            (test_3_payment_type_mapping,          (provider, order)),
            (test_4_dine_in_table_number,          (provider, order)),
            (test_5_push_order_success,            (provider, order)),
            (test_6_push_order_failure,            (provider, order)),
            (test_7_push_order_network_error,      (provider, order)),
            (test_8_push_order_missing_credentials,(rest, order)),
            (test_9_callback_status_accepted,      (provider, order)),
            (test_10_callback_status_dispatched,   (provider, order)),
            (test_11_callback_status_ready,        (provider, order)),
            (test_12_callback_status_delivered,    (provider, order)),
            (test_13_callback_status_cancelled,    (provider, order)),
            (test_14_callback_no_backwards_regression, (provider, order)),
            (test_15_callback_cancel_after_delivery_blocked, (provider, order)),
            (test_16_callback_unknown_status,      (provider, order)),
            (test_17_callback_missing_order_id,    (provider, order)),
            (test_18_callback_bad_app_key,         (provider, order)),
            (test_19_callback_pos_sync_status_written, (provider, order)),
            (test_20_menu_push_categories_and_products, (provider, order)),
            (test_21_menu_push_idempotent_update,  (provider, order)),
            (test_22_item_stock_off,               (provider, order)),
            (test_23_item_stock_on,                (provider, order)),
            (test_24_store_status_close,           (provider, order)),
            (test_25_store_status_open,            (provider, order)),
            (test_26_rider_update,                 (provider, order)),
            (test_27_duplicate_push_guard,         (provider, order)),
            (test_28_utils_trigger_on_accepted,    (order,)),
            (test_29_utils_no_trigger_on_same_status, (order,)),
            (test_30_utils_no_trigger_on_unpushable_status, (order,)),
            (test_31_map_status_all_codes,         (provider,)),
            (test_32_get_pos_provider_routing,     ()),
            (test_33_pos_gateway_sniff_petpooja,   ()),
        ]

        for fn, args in tests:
            try:
                fn(*args)
                passed += 1
            except Exception as e:
                failed += 1
                err_msg = f"FAILED: {fn.__name__}\n  {e}\n  {traceback.format_exc()}"
                errors.append(err_msg)
                print(f"\n  ❌ {fn.__name__} FAILED: {e}")

    finally:
        print(f"\n{'='*65}")
        print(f"  Results: {passed} passed, {failed} failed out of {passed + failed} tests")
        if errors:
            print("\n  Failures:")
            for err in errors:
                print(f"\n  {err}")
        teardown_test_data(rest_id)
        print("="*65)

    if failed:
        raise Exception(f"{failed} test(s) failed. See output above.")

    print("\n  🎉 All Petpooja E2E tests passed!\n")
