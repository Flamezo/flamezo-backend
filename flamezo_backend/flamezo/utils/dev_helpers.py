import frappe

def set_test_razorpay_customer(restaurant_name, customer_id, token_id=None):
    \"\"\"Development helper: set a fake razorpay_customer_id/token on a restaurant.\"\"\"
    frappe.db.set_value("Restaurant", restaurant_name, "razorpay_customer_id", customer_id)
    if token_id:
        frappe.db.set_value("Restaurant", restaurant_name, "razorpay_token_id", token_id)
        frappe.db.set_value("Restaurant", restaurant_name, "mandate_status", "active")
    frappe.db.commit()
    print(f"Set razorpay_customer_id={customer_id} for {restaurant_name}")

