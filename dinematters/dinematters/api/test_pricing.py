import frappe
from dinematters.dinematters.tasks.subscription_tasks import process_daily_subscription_floors, process_silver_feature_renewals
from frappe.utils import getdate, now_datetime, add_days, today

def test_it():
    print("--- 🚀 STARTING SUBSCRIPTION E2E TESTING ---")
    
    # 1. SETUP MOCK DATA
    product_id_search = "test-e2e-product"
    
    # Needs a parent restaurant for the product
    temp_res_name = "test-temp-res"
    if not frappe.db.exists("Restaurant", temp_res_name):
        frappe.get_doc({
            "doctype": "Restaurant",
            "restaurant_id": temp_res_name,
            "restaurant_name": "Temp Restaurant",
            "plan_type": "SILVER",
            "is_active": 1
        }).insert(ignore_permissions=True)

    existing_product = frappe.db.get_value("Menu Product", {"product_id": product_id_search}, "name")
    if not existing_product:
        p = frappe.get_doc({
            "doctype": "Menu Product",
            "restaurant": temp_res_name,
            "product_name": "Test Product",
            "product_id": product_id_search,
            "price": 1000.0,
            "calories": 0,
            "is_vegetarian": 0,
            "is_active": 1
        }).insert(ignore_permissions=True)
        product_link = p.name
    else:
        product_link = existing_product

    gold_name = "test-gold-res-e2e"
    if not frappe.db.exists("Restaurant", gold_name):
        gold_res = frappe.get_doc({
            "doctype": "Restaurant",
            "restaurant_id": gold_name,
            "restaurant_name": "Test Gold Restaurant E2E",
            "plan_type": "GOLD",
            "is_active": 1,
            "coins_balance": 5000,
            "timezone": "UTC",
            "monthly_minimum": 999,
            "tax_rate": 0.0
        }).insert(ignore_permissions=True)
    else:
        frappe.db.set_value("Restaurant", gold_name, {"plan_type": "GOLD", "coins_balance": 5000, "monthly_minimum": 999, "tax_rate": 0.0})
    
    diamond_name = "test-diamond-res-e2e"
    if not frappe.db.exists("Restaurant", diamond_name):
        diamond_res = frappe.get_doc({
            "doctype": "Restaurant",
            "restaurant_id": diamond_name,
            "restaurant_name": "Test Diamond Restaurant E2E",
            "plan_type": "DIAMOND",
            "is_active": 1,
            "coins_balance": 5000,
            "timezone": "UTC",
            "monthly_minimum": 399,
            "tax_rate": 0.0
        }).insert(ignore_permissions=True)
    else:
        frappe.db.set_value("Restaurant", diamond_name, {"plan_type": "DIAMOND", "coins_balance": 5000, "monthly_minimum": 399, "tax_rate": 0.0})

    # Clear today's data to start fresh
    today_start = getdate().strftime("%Y-%m-%d 00:00:00")
    frappe.db.delete("Coin Transaction", {"restaurant": ["in", [gold_name, diamond_name]], "creation": [">=", today_start]})
    frappe.db.delete("Order", {"restaurant": ["in", [gold_name, diamond_name]], "creation": [">=", today_start]})

    print("\n[SCENARIO 1: DIAMOND ORDER COMMISSION]")
    # Create DIAMOND order for ₹3000. Commission should be ₹45 (1.5%)
    diamond_order = frappe.get_doc({
        "doctype": "Order",
        "restaurant": diamond_name,
        "order_id": f"TEST-DIAMOND-{frappe.generate_hash(length=8)}",
        "order_number": f"DIAMOND-{frappe.generate_hash(length=4)}",
        "total": 3000.0,
        "subtotal": 3000.0,
        "status": "Accepted",
        "payment_status": "pending",
        "order_items": [{
            "product": product_link,
            "item_name": "Test Item",
            "quantity": 1,
            "unit_price": 3000.0,
            "total_price": 3000.0
        }]
    }).insert(ignore_permissions=True)
    
    # Complete/Bill it to trigger commission
    diamond_order.status = "billed"
    diamond_order.save() # Triggers on_update -> commission deduction
    
    commission = frappe.db.get_value("Coin Transaction", {
        "restaurant": diamond_name,
        "transaction_type": "Commission Deduction",
        "reference_name": diamond_order.name
    }, "amount") or 0.0
    
    print(f"DIAMOND Order (₹3000) Commission: ₹{abs(commission)} (Expected: 45.0)")
    assert abs(abs(commission) - 45.0) < 0.01, f"DIAMOND Commission mismatch! Got {abs(commission)}"

    print("\n[SCENARIO 2: GOLD ORDER COMMISSION]")
    # Create GOLD order for ₹1000. Commission should be ₹0 (Fixed Tier)
    gold_order = frappe.get_doc({
        "doctype": "Order",
        "restaurant": gold_name,
        "order_id": f"TEST-GOLD-{frappe.generate_hash(length=8)}",
        "order_number": f"GOLD-{frappe.generate_hash(length=4)}",
        "total": 1000.0,
        "subtotal": 1000.0,
        "status": "Accepted",
        "payment_status": "pending",
        "order_items": [{
            "product": product_link,
            "item_name": "Test Item",
            "quantity": 1,
            "unit_price": 1000.0,
            "total_price": 1000.0
        }]
    }).insert(ignore_permissions=True)
    
    gold_order.status = "billed"
    gold_order.save()
    
    gold_comm = frappe.db.get_value("Coin Transaction", {
        "restaurant": gold_name,
        "transaction_type": "Commission Deduction",
        "reference_name": gold_order.name
    }, "amount") or 0.0
    
    print(f"GOLD Order (₹1000) Commission: ₹{abs(gold_comm)} (Expected: 0.0)")
    assert abs(gold_comm) < 0.01, f"GOLD should not pay order commission! Got {abs(gold_comm)}"

    print("\n[SCENARIO 3: DAILY FLOOR RECOVERY]")
    # DIAMOND has paid ₹45 commission. Daily target is ₹13.30 (399/30). 
    # Floor Recovery should be 13.30 - 45.00 = 0 (No negative recovery)
    # GOLD daily target is flat ₹33.30 (999/30). 
    
    process_daily_subscription_floors()
    
    diamond_floor = frappe.db.get_value("Coin Transaction", {
        "restaurant": diamond_name,
        "transaction_type": "Daily DIAMOND Floor"
    }, "amount") or 0.0
    
    gold_floor = frappe.db.get_value("Coin Transaction", {
        "restaurant": gold_name,
        "transaction_type": "Daily GOLD Floor"
    }, "amount") or 0.0
    
    print(f"DIAMOND Floor Recovery: ₹{abs(diamond_floor)} (Expected: 0.0)")
    print(f"GOLD Fixed Fee: ₹{abs(gold_floor)} (Expected: 33.30)")
    
    assert abs(diamond_floor) < 0.01, f"DIAMOND Floor calculation wrong! Got {diamond_floor}"
    assert abs(abs(gold_floor) - 33.30) < 0.01, f"GOLD Flat fee calculation wrong! Got {gold_floor}"

    print("\n[SCENARIO 4: DYNAMIC SETTINGS TEST]")
    # Change global GOLD fee to ₹450 (Daily: ₹15)
    settings = frappe.get_single("Dinematters Settings")
    original_gold_fee = settings.gold_monthly_fee
    settings.gold_monthly_fee = 450.0
    settings.save()
    
    # Also update the restaurant record as if an admin just saved it (triggering the new controller logic)
    res_gold = frappe.get_doc("Restaurant", gold_name)
    res_gold.plan_type = "SILVER" # Change and then change back to trigger validate_plan_change
    res_gold.save()
    res_gold.plan_type = "GOLD"
    res_gold.save()
    
    # Clear previous GOLD floor for today
    frappe.db.delete("Coin Transaction", {"restaurant": gold_name, "transaction_type": "Daily GOLD Floor", "creation": [">=", today_start]})
    
    # Process again
    process_daily_subscription_floors()
    
    new_gold_floor = frappe.db.get_value("Coin Transaction", {
        "restaurant": gold_name,
        "transaction_type": "Daily GOLD Floor",
        "creation": [">=", today_start]
    }, "amount") or 0.0
    
    print(f"New GOLD Fixed Fee (after settings change to ₹450): ₹{abs(new_gold_floor)} (Expected: 15.0)")
    assert abs(abs(new_gold_floor) - 15.0) < 0.01, f"Dynamic GOLD fee failed! Got {abs(new_gold_floor)}"

    # RESTORE ORIGINAL SETTINGS (though we rollback eventually, it's good practice)
    settings.gold_monthly_fee = original_gold_fee
    settings.save()

    print("\n[SCENARIO 5: FEATURE FEE TIER GATING TEST]")
    # 1. Setup SILVER restaurant with menu theme enabled
    res_silver_name = "test-fee-silver"
    if not frappe.db.exists("Restaurant", res_silver_name):
        frappe.get_doc({"doctype": "Restaurant", "restaurant_id": res_silver_name, "restaurant_name": "SILVER Fee Test", "plan_type": "SILVER", "coins_balance": 500, "is_active": 1}).insert(ignore_permissions=True)
    
    # Reset balance and clear transactions for isolation
    frappe.db.set_value("Restaurant", res_silver_name, "coins_balance", 500.0)
    frappe.db.delete("Coin Transaction", {"restaurant": res_silver_name})
    
    config_silver = frappe.get_doc("Restaurant Config", {"restaurant": res_silver_name})
    config_silver.menu_theme_background_enabled = 1
    config_silver.menu_theme_paid_until = None
    config_silver.save()

    # 2. Setup GOLD restaurant test (transition from SILVER to GOLD)
    res_gold_name = "test-fee-gold"
    if not frappe.db.exists("Restaurant", res_gold_name):
        frappe.get_doc({"doctype": "Restaurant", "restaurant_id": res_gold_name, "restaurant_name": "GOLD Fee Test", "plan_type": "SILVER", "coins_balance": 500, "is_active": 1}).insert(ignore_permissions=True)
    
    # Reset to SILVER first
    res_gold = frappe.get_doc("Restaurant", res_gold_name)
    res_gold.plan_type = "SILVER"
    res_gold.coins_balance = 500.0
    res_gold.save()
    frappe.db.delete("Coin Transaction", {"restaurant": res_gold_name})
    
    config_gold = frappe.get_doc("Restaurant Config", {"restaurant": res_gold_name})
    config_gold.menu_theme_background_enabled = 1
    config_gold.menu_theme_paid_until = add_days(today(), -5) # Expired 5 days ago
    config_gold.save()

    # Now upgrade to GOLD - this should trigger the cleanup in restaurant.py
    res_gold.plan_type = "GOLD"
    res_gold.save()

    # 3. Run renewal task
    process_silver_feature_renewals()

    # 4. Verify results
    silver_bal = frappe.db.get_value("Restaurant", res_silver_name, "coins_balance")
    gold_bal = frappe.db.get_value("Restaurant", res_gold_name, "coins_balance")
    
    print(f"SILVER Balance after renewal task: {silver_bal} (Expected: 400)")
    print(f"GOLD Balance after renewal task: {gold_bal} (Expected: 500)")
    
    assert abs(silver_bal - 400.0) < 0.01, f"SILVER was not charged or charged wrong! Bal: {silver_bal}"
    assert abs(gold_bal - 500.0) < 0.01, f"GOLD was incorrectly charged! Bal: {gold_bal}"
    
    # Also verify GOLD's paid_until is cleared (due to our fix)
    new_gold_paid_until = frappe.db.get_value("Restaurant Config", {"restaurant": res_gold_name}, "menu_theme_paid_until")
    print(f"GOLD Paid Until after task: {new_gold_paid_until} (Expected: None)")
    assert new_gold_paid_until is None, "GOLD paid_until was not cleared!"

    print("\n✅ ALL DYNAMIC SUBSCRIPTION & FEATURE GATING E2E TESTS PASSED!")
    frappe.db.rollback()
