"""
Petpooja 5-Scenario Direct Test — Correct payload structure from Shivam's sample.
Run: python3 frappe-bench/apps/flamezo_backend/flamezo_backend/flamezo/tests/petpooja_5_direct.py
"""
import json
import time
import requests
from datetime import datetime

SAVE_ORDER_URL = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/save_order"
MENU_URL = "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/mapped_restaurant_menus"

CREDS = {
    "app_key": "yk5aniupvtjgwr1839fxzds70hoe2cm6",
    "app_secret": "3c88718f646c5a808828c9f27b8775b7129323e7",
    "access_token": "b4bfad4f5c1c9568e4e76efe4f4e00c9a130cdbc",
}
REST_ID = "ghvua4js"
CALLBACK_URL = "https://backend.flamezo.in/api/method/flamezo_backend.flamezo.api.pos.pos_gateway"


def main():
    print("\n" + "=" * 70)
    print("  PETPOOJA 5-SCENARIO TEST (Correct Payload Structure)")
    print("=" * 70)

    # Fetch menu
    print("\n  Fetching menu...")
    resp = requests.post(MENU_URL, json={**CREDS, "restID": REST_ID}, timeout=20)
    data = resp.json()
    items = data.get("items", [])
    taxes = data.get("taxes", [])
    addongroups = data.get("addongroups", [])
    print(f"  Items: {len(items)}, Taxes: {len(taxes)}, AddonGroups: {len(addongroups)}")

    # Find in-stock item
    item = next((i for i in items if str(i.get("in_stock", "1")) != "0" and float(i.get("price", 0)) > 0), items[0])
    item_id = str(item["itemid"])
    item_name = item["itemname"]
    item_price = float(item["price"])
    print(f"  Base item: id={item_id} name={item_name} price={item_price}")

    # Find item with variation
    var_item, variation = None, None
    for i in items:
        if str(i.get("itemallowvariation", "0")) == "1" and i.get("variation"):
            var_item = i
            variation = i["variation"][0]
            print(f"  Variation item: {i['itemname']} | var={variation.get('name')} price={variation.get('price')}")
            break

    # Find item with addon
    addon_item, addon, addon_group = None, None, None
    ag_lookup = {str(ag["addongroupid"]): ag for ag in addongroups}
    for i in items:
        for ref in (i.get("addon") or []):
            ag = ag_lookup.get(str(ref.get("addon_group_id", "")))
            if ag and ag.get("addongroupitems"):
                addon_item = i
                addon = ag["addongroupitems"][0]
                addon_group = ag
                print(f"  Addon item: {i['itemname']} | addon={addon.get('addonitem_name')} price={addon.get('addonitemprice')}")
                break
        if addon:
            break

    # Tax IDs
    cgst = next((t for t in taxes if "cgst" in t.get("taxname", "").lower()), taxes[0] if taxes else {})
    sgst = next((t for t in taxes if "sgst" in t.get("taxname", "").lower()), taxes[1] if len(taxes) > 1 else {})
    cgst_id = str(cgst.get("taxid", "2201"))
    sgst_id = str(sgst.get("taxid", "2202"))
    cgst_rate = float(cgst.get("tax", 2.5))
    sgst_rate = float(sgst.get("tax", 2.5))

    ts = int(time.time())
    results = {}

    # ═══════════════════════════════════════════════════
    # SCENARIO 1: Items + Tax
    # ═══════════════════════════════════════════════════
    print("\n" + "-" * 50)
    print("  SCENARIO 1: Items + Tax")
    cgst_amt = round(item_price * cgst_rate / 100, 2)
    sgst_amt = round(item_price * sgst_rate / 100, 2)
    tax_total = round(cgst_amt + sgst_amt, 2)
    total = round(item_price + tax_total, 2)

    results["1. Items + Tax"] = fire(build_payload(
        order_id=f"FZ_S1_{ts}", total=total, tax_total=tax_total,
        items=[build_item(item_id, item_name, item_price, item_price, cgst_id, sgst_id, cgst_rate, sgst_rate)],
        taxes=build_taxes(cgst_id, sgst_id, cgst_rate, sgst_rate, cgst_amt, sgst_amt)
    ))

    # ═══════════════════════════════════════════════════
    # SCENARIO 2: Item with Addons + Tax
    # ═══════════════════════════════════════════════════
    print("\n" + "-" * 50)
    print("  SCENARIO 2: Item with Addons + Tax")
    if addon_item and addon:
        a_id = str(addon_item["itemid"])
        a_name = addon_item["itemname"]
        a_price = float(addon_item["price"])
        ad_id = str(addon.get("addonitemid", ""))
        ad_name = addon.get("addonitem_name", "")
        ad_price = float(addon.get("addonitemprice", 0))
        total_price = a_price + ad_price
    else:
        a_id, a_name, a_price = item_id, item_name, item_price
        ad_id, ad_name, ad_price = "999", "Extra", 50
        total_price = a_price + ad_price
        print("  (No addon in menu, using placeholder)")

    c2 = round(total_price * cgst_rate / 100, 2)
    s2 = round(total_price * sgst_rate / 100, 2)
    t2 = round(c2 + s2, 2)
    tot2 = round(total_price + t2, 2)

    addon_details = [{"id": ad_id, "name": ad_name, "group_name": addon_group.get("addongroup_name", "") if addon_group else "", "price": str(ad_price), "group_id": int(addon_group["addongroupid"]) if addon_group else 0, "quantity": "1"}]

    results["2. Item with Addons + Tax"] = fire(build_payload(
        order_id=f"FZ_S2_{ts}", total=tot2, tax_total=t2,
        items=[build_item(a_id, a_name, total_price, total_price, cgst_id, sgst_id, cgst_rate, sgst_rate, addon_items=addon_details)],
        taxes=build_taxes(cgst_id, sgst_id, cgst_rate, sgst_rate, c2, s2)
    ))

    # ═══════════════════════════════════════════════════
    # SCENARIO 3: Item with Variation + Tax
    # ═══════════════════════════════════════════════════
    print("\n" + "-" * 50)
    print("  SCENARIO 3: Item with Variation + Tax")
    if var_item and variation:
        v_id = str(var_item["itemid"])
        v_name = var_item["itemname"]
        vid = str(variation.get("variationid", variation.get("id", "")))
        vname = variation.get("name", "Regular")
        vprice = float(variation.get("price", item_price))
    else:
        v_id, v_name = item_id, item_name
        vid, vname, vprice = "110", "Regular", item_price
        print("  (No variation in menu, using placeholder)")

    c3 = round(vprice * cgst_rate / 100, 2)
    s3 = round(vprice * sgst_rate / 100, 2)
    t3 = round(c3 + s3, 2)
    tot3 = round(vprice + t3, 2)

    results["3. Item with Variation + Tax"] = fire(build_payload(
        order_id=f"FZ_S3_{ts}", total=tot3, tax_total=t3,
        items=[build_item(v_id, v_name, vprice, vprice, cgst_id, sgst_id, cgst_rate, sgst_rate, variation_name=vname, variation_id=vid)],
        taxes=build_taxes(cgst_id, sgst_id, cgst_rate, sgst_rate, c3, s3)
    ))

    # ═══════════════════════════════════════════════════
    # SCENARIO 4: Item with Discount + Tax
    # ═══════════════════════════════════════════════════
    print("\n" + "-" * 50)
    print("  SCENARIO 4: Item with Discount + Tax")
    disc = round(item_price * 0.1, 2)
    final_price = round(item_price - disc, 2)
    c4 = round(final_price * cgst_rate / 100, 2)
    s4 = round(final_price * sgst_rate / 100, 2)
    t4 = round(c4 + s4, 2)
    tot4 = round(final_price + t4, 2)

    results["4. Item with Discount + Tax"] = fire(build_payload(
        order_id=f"FZ_S4_{ts}", total=tot4, tax_total=t4, discount_total=str(disc),
        items=[build_item(item_id, item_name, item_price, final_price, cgst_id, sgst_id, cgst_rate, sgst_rate, item_discount=str(disc))],
        taxes=build_taxes(cgst_id, sgst_id, cgst_rate, sgst_rate, c4, s4)
    ))

    # ═══════════════════════════════════════════════════
    # SCENARIO 5: Item with Addon + Variation + Tax
    # ═══════════════════════════════════════════════════
    print("\n" + "-" * 50)
    print("  SCENARIO 5: Item with Addon + Variation + Tax")
    s5_vid = vid if var_item else "110"
    s5_vname = vname if var_item else "Regular"
    s5_vprice = vprice if var_item else item_price
    s5_item_id = v_id if var_item else item_id
    s5_item_name = v_name if var_item else item_name
    s5_ad_id = ad_id if addon else "999"
    s5_ad_name = ad_name if addon else "Extra"
    s5_ad_price = ad_price if addon else 50
    s5_total_item = s5_vprice + s5_ad_price
    c5 = round(s5_total_item * cgst_rate / 100, 2)
    s5 = round(s5_total_item * sgst_rate / 100, 2)
    t5 = round(c5 + s5, 2)
    tot5 = round(s5_total_item + t5, 2)

    s5_addon_details = [{"id": s5_ad_id, "name": s5_ad_name, "group_name": addon_group.get("addongroup_name", "") if addon_group else "", "price": str(s5_ad_price), "group_id": int(addon_group["addongroupid"]) if addon_group else 0, "quantity": "1"}]

    results["5. Item with Addon + Variation + Tax"] = fire(build_payload(
        order_id=f"FZ_S5_{ts}", total=tot5, tax_total=t5,
        items=[build_item(s5_item_id, s5_item_name, s5_total_item, s5_total_item, cgst_id, sgst_id, cgst_rate, sgst_rate,
                          variation_name=s5_vname, variation_id=s5_vid, addon_items=s5_addon_details)],
        taxes=build_taxes(cgst_id, sgst_id, cgst_rate, sgst_rate, c5, s5)
    ))

    # ═══════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  RESULTS — Order IDs for Petpooja Email")
    print("=" * 70)
    all_pass = True
    for scenario, r in results.items():
        if r.get("success"):
            print(f"  OK   {scenario}: {r['order_id']}")
        else:
            all_pass = False
            print(f"  FAIL {scenario}: {r.get('error', 'Unknown')}")

    if all_pass:
        print("\n  ALL 5 PASSED! Copy-paste for email:")
        print("  " + "-" * 40)
        for scenario, r in results.items():
            print(f"  {scenario}: {r['order_id']}")
    print("=" * 70)


# ─── Payload Builders (Petpooja's actual format) ─────────────────────────────

def build_payload(order_id, total, tax_total, items, taxes, discount_total="0"):
    now = datetime.now()
    return {
        "app_key": CREDS["app_key"],
        "app_secret": CREDS["app_secret"],
        "access_token": CREDS["access_token"],
        "orderinfo": {
            "OrderInfo": {
                "Restaurant": {
                    "details": {
                        "res_name": "Dinematters DEMO",
                        "address": "Shollinganallur",
                        "contact_information": "1234567890",
                        "restID": REST_ID
                    }
                },
                "Customer": {
                    "details": {
                        "email": "test@flamezo.com",
                        "name": "Flamezo Test",
                        "address": "Test Address, Mumbai",
                        "phone": "9999999999",
                        "latitude": "19.0760",
                        "longitude": "72.8777"
                    }
                },
                "Order": {
                    "details": {
                        "orderID": order_id,
                        "preorder_date": now.strftime("%Y-%m-%d"),
                        "preorder_time": now.strftime("%H:%M:%S"),
                        "service_charge": "0",
                        "sc_tax_amount": "0",
                        "delivery_charges": "0",
                        "dc_tax_percentage": "0",
                        "dc_tax_amount": "0",
                        "dc_gst_details": [],
                        "packing_charges": "0",
                        "pc_tax_amount": "0",
                        "pc_tax_percentage": "0",
                        "pc_gst_details": [],
                        "order_type": "D",
                        "ondc_bap": "",
                        "advanced_order": "N",
                        "urgent_order": False,
                        "urgent_time": 0,
                        "payment_type": "ONLINE",
                        "table_no": "1",
                        "no_of_persons": "1",
                        "discount_total": discount_total,
                        "tax_total": str(tax_total),
                        "discount_type": "F",
                        "total": str(total),
                        "description": f"Flamezo test - {order_id}",
                        "created_on": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "enable_delivery": 1,
                        "min_prep_time": 20,
                        "callback_url": CALLBACK_URL
                    }
                },
                "OrderItem": {
                    "details": items
                },
                "Tax": {
                    "details": taxes
                }
            },
            "udid": "",
            "device_type": "Web"
        }
    }


def build_item(item_id, name, price, final_price, cgst_id, sgst_id, cgst_rate, sgst_rate,
               item_discount="", variation_name="", variation_id="", addon_items=None):
    cgst_amt = round(float(final_price) * cgst_rate / 100, 2)
    sgst_amt = round(float(final_price) * sgst_rate / 100, 2)
    return {
        "id": str(item_id),
        "name": name,
        "tax_inclusive": False,
        "gst_liability": "restaurant",
        "item_tax": [
            {"id": cgst_id, "name": "CGST", "tax_percentage": str(cgst_rate), "amount": str(cgst_amt)},
            {"id": sgst_id, "name": "SGST", "tax_percentage": str(sgst_rate), "amount": str(sgst_amt)},
        ],
        "item_discount": item_discount,
        "price": str(price),
        "final_price": str(final_price),
        "quantity": "1",
        "description": "",
        "variation_name": variation_name,
        "variation_id": str(variation_id) if variation_id else "",
        "AddonItem": {
            "details": addon_items or []
        }
    }


def build_taxes(cgst_id, sgst_id, cgst_rate, sgst_rate, cgst_amt, sgst_amt):
    return [
        {"id": cgst_id, "title": "CGST", "type": "P", "price": str(cgst_rate), "tax": str(cgst_amt), "restaurant_liable_amt": str(cgst_amt)},
        {"id": sgst_id, "title": "SGST", "type": "P", "price": str(sgst_rate), "tax": str(sgst_amt), "restaurant_liable_amt": str(sgst_amt)},
    ]


def fire(payload):
    oid = payload["orderinfo"]["OrderInfo"]["Order"]["details"]["orderID"]
    print(f"  Firing: {oid}")
    try:
        resp = requests.post(SAVE_ORDER_URL, json=payload, timeout=20)
        print(f"  HTTP {resp.status_code}: {resp.text[:400]}")
        result = resp.json()
        if str(result.get("success")) == "1":
            pos_id = result.get("orderID") or result.get("order_id") or result.get("client_orderID")
            print(f"  SUCCESS: {pos_id}")
            return {"success": True, "order_id": pos_id, "our_id": oid}
        else:
            err = result.get("message") or result.get("error") or json.dumps(result)
            print(f"  FAILED: {err}")
            return {"success": False, "error": err, "our_id": oid}
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"success": False, "error": str(e), "our_id": oid}


if __name__ == "__main__":
    main()
