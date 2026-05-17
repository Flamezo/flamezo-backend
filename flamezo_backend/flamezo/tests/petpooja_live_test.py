"""
Petpooja LIVE Sandbox Test — fires a real HTTP order to Petpooja staging
Run: bench --site dine_matters execute flamezo_backend.flamezo.tests.petpooja_live_test.run

Prerequisites:
- Unvind restaurant doc must have sandbox credentials saved via POS Integration UI
- Sandbox IPs must be whitelisted with Petpooja
"""
import frappe
import json
import time
import requests
from frappe.utils import get_datetime


def run():
    print("\n" + "="*60)
    print("  🔴 PETPOOJA LIVE SANDBOX TEST")
    print("="*60)

    # ── 1. Find Unvind restaurant ──────────────────────────────
    restaurants = frappe.db.get_all(
        "Restaurant",
        filters=[["restaurant_name", "like", "%nvind%"]],
        fields=["name", "restaurant_name", "pos_provider", "pos_enabled",
                "pos_app_key", "pos_merchant_id", "plan_type"]
    )

    if not restaurants:
        # Try broader search
        restaurants = frappe.db.get_all(
            "Restaurant",
            filters={"pos_merchant_id": "ghvua4js"},
            fields=["name", "restaurant_name", "pos_provider", "pos_enabled",
                    "pos_app_key", "pos_merchant_id", "plan_type"]
        )

    if not restaurants:
        print("  ❌ No restaurant found with name '%nvind%' or pos_merchant_id=ghvua4js")
        print("  Available restaurants with POS configured:")
        all_pos = frappe.db.get_all("Restaurant", filters={"pos_enabled": 1},
                                     fields=["name", "restaurant_name", "pos_merchant_id"])
        for r in all_pos:
            print(f"     {r.name} | {r.restaurant_name} | merchant={r.pos_merchant_id}")
        return

    rest_row = restaurants[0]
    print(f"\n  Restaurant : {rest_row.restaurant_name} ({rest_row.name})")
    print(f"  Plan       : {rest_row.plan_type}")
    print(f"  POS        : {rest_row.pos_provider} | enabled={rest_row.pos_enabled}")
    print(f"  App Key    : {rest_row.pos_app_key}")
    print(f"  Merchant   : {rest_row.pos_merchant_id}")

    # ── 2. Validate credentials are present ───────────────────
    rest = frappe.get_doc("Restaurant", rest_row.name)
    app_key    = rest.pos_app_key
    app_secret = rest.get_password("pos_app_secret") if rest.pos_app_secret else None
    access_tok = rest.get_password("pos_access_token") if rest.pos_access_token else None
    merchant   = rest.pos_merchant_id

    missing = [k for k, v in [("app_key", app_key), ("app_secret", app_secret),
                                ("access_token", access_tok), ("merchant_id", merchant)] if not v]
    if missing:
        print(f"\n  ❌ Missing credentials: {missing}")
        print("  Go to POS Integration page and save all fields first.")
        return

    print(f"\n  ✅ All 4 credentials present")
    print(f"  app_key     : {app_key}")
    print(f"  app_secret  : {'*' * len(app_secret)}")
    print(f"  access_token: {'*' * len(access_tok)}")
    print(f"  merchant_id : {merchant}")

    # ── 3. Check GOLD plan ────────────────────────────────────
    if rest.plan_type != "GOLD":
        print(f"\n  ❌ Restaurant is on {rest.plan_type} plan — POS requires GOLD")
        return
    print(f"  ✅ GOLD plan confirmed")

    # ── 4. Fetch menu to get real item IDs ───────────────────
    print("\n  📋 Fetching menu from Petpooja to get real item IDs...")
    fetch_url = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/mapped_restaurant_menus"
    menu_resp = requests.post(
        fetch_url,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"app_key": app_key, "app_secret": app_secret, "access_token": access_tok, "restID": merchant}),
        timeout=20
    )
    print(f"  Menu HTTP   : {menu_resp.status_code}")
    real_item_id = None
    real_item_name = "Test Item"
    real_item_price = "100.00"
    try:
        menu_data = menu_resp.json()
        items = menu_data.get("items", []) or menu_data.get("restaurants", [{}])[0].get("items", [])
        if items:
            first = items[0]
            real_item_id   = str(first.get("itemid") or first.get("item_id") or "")
            real_item_name = first.get("itemname") or first.get("item_name") or "Test Item"
            real_item_price = str(first.get("itemprice") or first.get("price") or "100")
            print(f"  First item  : id={real_item_id} name={real_item_name} price={real_item_price}")
        else:
            print(f"  Menu raw    : {menu_resp.text[:600]}")

        # Pull tax IDs from menu to use in order
        taxes = menu_data.get("taxes", []) or menu_data.get("restaurants", [{}])[0].get("taxes", [])
        ordertypes = menu_data.get("ordertypes") or menu_data.get("restaurants", [{}])[0].get("ordertypes", {})
        print(f"  Order types : {ordertypes}")
        print(f"  Menu taxes  : {json.dumps(taxes[:3], indent=2) if taxes else 'none found'}")
        if items:
            # Find an in-stock item (in_stock != "0")
            for candidate in items:
                if str(candidate.get("in_stock", "1")) != "0":
                    real_item_id    = str(candidate.get("itemid", real_item_id))
                    real_item_name  = candidate.get("itemname", real_item_name)
                    real_item_price = str(candidate.get("price", real_item_price))
                    tax_inclusive_flag = str(candidate.get("item_tax_inclusive", candidate.get("tax_inclusive", "0")))
                    print(f"  In-stock item: id={real_item_id} name={real_item_name} price={real_item_price} in_stock={candidate.get('in_stock')} tax_inclusive={tax_inclusive_flag}")
                    break
    except Exception as e:
        print(f"  Menu parse error: {e} | raw: {menu_resp.text[:300]}")

    if not real_item_id:
        real_item_id = "1"  # fallback

    # ── 5. Build tax structure from real menu taxes ───────────
    try:
        taxes = menu_data.get("taxes", []) or menu_data.get("restaurants", [{}])[0].get("taxes", [])
    except Exception:
        taxes = []

    price_float = float(real_item_price)
    item_tax_list = []
    total_tax = 0.0
    for t in taxes[:2]:  # CGST + SGST
        rate = float(t.get("tax", 0))
        amt  = round(price_float * rate / 100, 2)
        total_tax += amt
        item_tax_list.append({
            "id": str(t.get("taxid", "1")),
            "name": t.get("taxname", "GST"),
            "tax_percentage": str(rate),
            "amount": str(amt)
        })
    if not item_tax_list:
        # Fallback: 2.5 CGST + 2.5 SGST
        item_tax_list = [
            {"id": "2201", "name": "CGST", "tax_percentage": "2.5", "amount": str(round(price_float * 0.025, 2))},
            {"id": "2202", "name": "SGST", "tax_percentage": "2.5", "amount": str(round(price_float * 0.025, 2))},
        ]
        total_tax = round(price_float * 0.05, 2)

    order_total = str(round(price_float + total_tax, 2))
    tax_total   = str(round(total_tax, 2))
    print(f"  Tax calc    : item={real_item_price} tax={tax_total} total={order_total}")

    # ── 6. Build a minimal live order payload ─────────────────
    ts = int(time.time())
    test_order_id = f"DM_LIVE_TEST_{ts}"

    from frappe.utils import get_url
    raw_url = get_url("/api/method/flamezo_backend.flamezo.api.pos.petpooja_callback")
    # Petpooja requires a public HTTPS callback URL — localhost won't work in sandbox
    # Override with production domain if localhost is detected
    if "localhost" in raw_url or "127.0.0.1" in raw_url:
        callback_url = "https://backend.flamezo_backend.com/api/method/flamezo_backend.flamezo.api.pos.petpooja_callback"
        print(f"  ⚠️  localhost detected — using prod callback: {callback_url}")
    else:
        callback_url = raw_url

    payload = {
        "app_key": app_key,
        "app_secret": app_secret,
        "access_token": access_tok,
        "restID": merchant,
        "res_name": rest.restaurant_name or rest.name,
        "address": getattr(rest, "address", "") or "",
        "Contact_information": getattr(rest, "contact_number", "") or "",
        "device_type": "Web",
        "OrderInfo": {
            "customer": {
                "name": "Flamezo Test",
                "phone": "9999999999",
                "email": "test@flamezo_backend.com",
                "address": "Test Address, Mumbai",
                "city": "Mumbai",
                "zip": "400001",
                "latitude": "19.0760",
                "longitude": "72.8777"
            },
            "order": {
                "orderID": test_order_id,
                "preorder_date": frappe.utils.today(),
                "preorder_time": frappe.utils.now_datetime().strftime("%H:%M:%S"),
                "created_on": frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
                "advanced_order": "N",
                "order_type": "P",  # Try Parcel — sandbox may not have Home Delivery enabled
                "total": order_total,
                "tax_total": tax_total,
                "payment_type": "ONLINE",
                "delivery_charges": "0",
                "packing_charges": "0",
                "discount_total": "0",
                "discount_type": "F",
                "description": "Flamezo sandbox live test order",
                "callback_url": callback_url,
                "urgent_order": "N",
                "urgent_time": "",
                "enable_delivery": "1",
                "dc_tax_percentage": "0",
                "pc_tax_percentage": "0"
            },
            "orderItem": [
                {
                    "id": real_item_id,
                    "name": real_item_name,
                    "quantity": "1",
                    "price": real_item_price,
                    "final_price": real_item_price,
                    "item_discount": "",
                    "tax_inclusive": False,
                    "gst_liability": "restaurant",
                    "item_tax": item_tax_list,
                    "variation_name": "",
                    "variation_id": "",
                    "addon_items": []
                }
            ],
            "tax_details": [
                {"id": "2201", "title": "CGST", "type": "P", "price": "2.5%", "tax": str(round(float(real_item_price)*0.025,2)), "restaurant_liable_amt": str(round(float(real_item_price)*0.025,2))},
                {"id": "2202", "title": "SGST", "type": "P", "price": "2.5%", "tax": str(round(float(real_item_price)*0.025,2)), "restaurant_liable_amt": str(round(float(real_item_price)*0.025,2))}
            ]
        }
    }

    # ── 5. Minimal payload probe (strip all optional fields) ──
    # Petpooja uses a different domain for order APIs vs menu APIs
    save_order_url = "https://47pfzh5sf2.execute-api.ap-southeast-1.amazonaws.com/V1/save_order"

    # Try multiple order_type values to find which one sandbox accepts
    # Petpooja ordertypes from menu: 1=Delivery, 2=Pick Up, 3=Dine In
    for ot_label, ot_val in [("Delivery(1)", "1"), ("PickUp(2)", "2"), ("DineIn(3)", "3")]:
        minimal_payload = {
            "app_key": app_key,
            "app_secret": app_secret,
            "access_token": access_tok,
            "restID": merchant,
            "res_name": rest.restaurant_name,
            "device_type": "Web",
            "OrderInfo": {
                "customer": {"name": "Test User", "phone": "9999999999", "address": "123 Test St"},
                "order": {
                    "orderID": f"DM_MIN_{ts}_{ot_val}",
                    "preorder_date": frappe.utils.today(),
                    "preorder_time": frappe.utils.now_datetime().strftime("%H:%M:%S"),
                    "created_on": frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
                    "advanced_order": "N",
                    "order_type": ot_val,
                    "total": real_item_price,
                    "tax_total": "0",
                    "payment_type": "COD",
                    "delivery_charges": "0",
                    "packing_charges": "0",
                    "discount_total": "0",
                    "discount_type": "F",
                    "description": "",
                    "callback_url": callback_url,
                    "urgent_order": "N",
                    "urgent_time": "",
                    "enable_delivery": "1",
                    "dc_tax_percentage": "0",
                    "pc_tax_percentage": "0"
                },
                "orderItem": [{
                    "id": real_item_id,
                    "name": real_item_name,
                    "quantity": "1",
                    "price": real_item_price,
                    "final_price": real_item_price,
                    "item_discount": "",
                    "tax_inclusive": False,
                    "gst_liability": "restaurant",
                    "item_tax": [],
                    "variation_name": "",
                    "variation_id": "",
                    "addon_items": []
                }]
            }
        }
        print(f"\n  🧪 Trying MINIMAL payload order_type={ot_label} COD no-tax...")
        min_resp = requests.post(save_order_url, headers={"Content-Type": "application/json"},
                                  data=json.dumps(minimal_payload), timeout=20)
        print(f"  Minimal {ot_label}: {min_resp.status_code} | {min_resp.text}")
        try:
            if str(min_resp.json().get("success")) == "1":
                print(f"  ✅ SUCCESS with order_type={ot_val}!")
                break
        except Exception:
            pass

    # ── 6. Fire the full live request ─────────────────────────

    print(f"\n  🚀 Firing live order to Petpooja sandbox...")
    print(f"  URL         : {save_order_url}")
    print(f"  Order ID    : {test_order_id}")
    print(f"  Callback URL: {callback_url}")
    print(f"  Payload     :\n{json.dumps(payload, indent=4)}")

    try:
        response = requests.post(
            save_order_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20
        )
        print(f"\n  HTTP Status : {response.status_code}")
        print(f"  Raw Response: {response.text}")

        result = response.json()
        print(f"\n  Parsed Response:")
        print(json.dumps(result, indent=4))

        if str(result.get("success")) == "1":
            pos_order_id = result.get("orderID") or result.get("order_id")
            print(f"\n  ✅ ORDER RELAYED SUCCESSFULLY!")
            print(f"  Petpooja Order ID : {pos_order_id}")
            print(f"  → Check Petpooja sandbox dashboard → Order Listing to confirm")
            print(f"  → Wait for callback on: {callback_url}")
        else:
            print(f"\n  ❌ Order relay FAILED")
            print(f"  Error: {result.get('message') or result.get('error') or 'Unknown'}")
            print(f"  Validation errors: {result.get('validation_errors', {})}")

    except requests.exceptions.Timeout:
        print("\n  ❌ Request timed out (20s)")
    except requests.exceptions.ConnectionError as e:
        print(f"\n  ❌ Connection error: {e}")
    except Exception as e:
        print(f"\n  ❌ Unexpected error: {e}")
        import traceback
        print(traceback.format_exc())

    print("\n" + "="*60)
