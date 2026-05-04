# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

"""
Shared test utilities, factories, and cleanup helpers.

All test restaurants use a TEST- prefix so bulk cleanup is safe and reliable.
Since many billing functions call frappe.db.commit() internally, tests must
explicitly delete records in tearDown rather than relying on rollback.
"""

import frappe
from frappe.utils import today, add_days


# ─── Factory helpers ──────────────────────────────────────────────────────────

def make_restaurant(name, plan="GOLD", balance=5000.0, **kwargs):
    """
    Create or reset a test Restaurant to a known state.

    Required Frappe fields are supplied with safe defaults. Pass any Restaurant
    field as a keyword argument to override the default.
    """
    defaults = {
        "plan_type": plan,
        "coins_balance": balance,
        "is_active": 1,
        "monthly_minimum": (
            999.0 if plan == "GOLD" else
            399.0 if plan == "DIAMOND" else
            0.0
        ),
        "enable_floor_recovery": 1,
        "auto_recharge_enabled": 0,
        "auto_recharge_threshold": 200.0,
        "auto_recharge_amount": 1000.0,
        "daily_auto_recharge_count": 0.0,
        "platform_fee_percent": 1.5,
        "timezone": "Asia/Kolkata",
        "mandate_status": "inactive",
    }
    defaults.update(kwargs)

    if frappe.db.exists("Restaurant", name):
        frappe.db.set_value("Restaurant", name, defaults)
        frappe.db.commit()
    else:
        frappe.get_doc({
            "doctype": "Restaurant",
            "restaurant_id": name,
            "restaurant_name": f"Test Restaurant {name}",
            **defaults,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

    return frappe.get_doc("Restaurant", name)


def make_restaurant_config(restaurant, **kwargs):
    """Create or reset a Restaurant Config for a test restaurant."""
    defaults = {
        "menu_theme_background_enabled": 0,
        "menu_theme_paid_until": None,
        "verify_my_user": 0,
    }
    defaults.update(kwargs)

    existing = frappe.db.get_value("Restaurant Config", {"restaurant": restaurant}, "name")
    if existing:
        frappe.db.set_value("Restaurant Config", existing, defaults)
        frappe.db.commit()
        return frappe.get_doc("Restaurant Config", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Restaurant Config",
            "restaurant": restaurant,
            **defaults,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc


def make_loyalty_config(restaurant, **kwargs):
    """Create an active Restaurant Loyalty Config and enable loyalty on the Restaurant."""
    defaults = {
        "program_name": f"Test Loyalty – {restaurant}",
        "is_active": 1,
        "points_per_inr": 0.1,        # 1 coin per ₹10 spent
        "loyalty_expiry_months": 12,
        "coin_value_in_inr": 1.0,
        "earn_on_status": "Completed",
        "min_redemption_threshold": 10,
        "referral_order_reward_coins": 50,
    }
    defaults.update(kwargs)

    # Enable loyalty on the restaurant itself (required for is_loyalty_enabled() check)
    frappe.db.set_value("Restaurant", restaurant, "enable_loyalty", 1)

    # Remove any stale config
    frappe.db.delete("Restaurant Loyalty Config", {"restaurant": restaurant})
    frappe.db.commit()

    doc = frappe.get_doc({
        "doctype": "Restaurant Loyalty Config",
        "restaurant": restaurant,
        **defaults,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def make_customer(phone="9000000001", name="Test Customer"):
    """Get or create a Frappe Customer for loyalty tests."""
    normalized_phone = phone.lstrip("+91").lstrip("0")[-10:]
    existing = frappe.db.get_value("Customer", {"mobile_no": normalized_phone}, "name")
    if existing:
        return frappe.get_doc("Customer", existing)

    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": name,
        "customer_type": "Individual",
        "mobile_no": normalized_phone,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def make_menu_product(restaurant, product_id, price=100.0, **kwargs):
    """Create a Menu Product for order tests."""
    defaults = {
        "product_name": f"Test Product {product_id}",
        "product_id": product_id,
        "price": price,
        "is_active": 1,
        "is_vegetarian": 0,
    }
    defaults.update(kwargs)

    existing = frappe.db.get_value("Menu Product", {"product_id": product_id, "restaurant": restaurant}, "name")
    if existing:
        return frappe.get_doc("Menu Product", existing)

    doc = frappe.get_doc({
        "doctype": "Menu Product",
        "restaurant": restaurant,
        **defaults,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def make_coin_transaction(restaurant, txn_type, amount, description="Test txn"):
    """
    Directly insert a Coin Transaction and update restaurant balance.
    Use this to set up preconditions without going through record_transaction().
    """
    current = frappe.db.get_value("Restaurant", restaurant, "coins_balance") or 0.0
    is_deduction = txn_type in [
        "AI Deduction", "Commission Deduction",
        "Daily SILVER Floor", "Daily GOLD Floor", "Daily DIAMOND Floor",
        "Daily GOLD Subscription", "Daily DIAMOND Subscription",
        "Lead Unlock", "Delivery Fee",
    ]
    if is_deduction:
        new_balance = float(current) - abs(float(amount))
        signed_amount = -abs(float(amount))
    else:
        new_balance = float(current) + abs(float(amount))
        signed_amount = abs(float(amount))

    frappe.db.set_value("Restaurant", restaurant, "coins_balance", new_balance)

    doc = frappe.get_doc({
        "doctype": "Coin Transaction",
        "restaurant": restaurant,
        "transaction_type": txn_type,
        "amount": signed_amount,
        "balance_after": new_balance,
        "description": description,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def make_loyalty_entry(customer, restaurant, coins, txn_type="Earn",
                       reason="Order", is_settled=1, days_until_expiry=30):
    """Directly insert a Restaurant Loyalty Entry."""
    doc = frappe.get_doc({
        "doctype": "Restaurant Loyalty Entry",
        "customer": customer,
        "restaurant": restaurant,
        "coins": coins,
        "transaction_type": txn_type,
        "reason": reason,
        "posting_date": today(),
        "expiry_date": add_days(today(), days_until_expiry),
        "is_settled": is_settled,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


# ─── Cleanup helpers ──────────────────────────────────────────────────────────

def cleanup_restaurant(name):
    """
    Delete ALL test records for a restaurant name.
    Safe to call even if the restaurant does not exist.
    """
    if not name:
        return
    frappe.db.delete("Coin Transaction", {"restaurant": name})
    frappe.db.delete("Restaurant Loyalty Entry", {"restaurant": name})
    frappe.db.delete("Coupon Usage", {"restaurant": name})
    frappe.db.delete("Order", {"restaurant": name})

    config = frappe.db.get_value("Restaurant Config", {"restaurant": name}, "name")
    if config:
        frappe.db.delete("Restaurant Config", {"name": config})

    loyalty_configs = frappe.db.get_list(
        "Restaurant Loyalty Config", filters={"restaurant": name}, pluck="name"
    )
    for lc in loyalty_configs:
        frappe.db.delete("Restaurant Loyalty Config", {"name": lc})

    frappe.db.delete("Restaurant", {"name": name})
    frappe.db.commit()


def cleanup_restaurants_by_prefix(prefix):
    """Bulk-delete all test restaurants (and their child records) matching a prefix."""
    names = frappe.db.sql(
        "SELECT name FROM `tabRestaurant` WHERE name LIKE %s",
        (f"{prefix}%",),
        as_list=True,
    )
    for (name,) in names:
        cleanup_restaurant(name)


def reset_restaurant_balance(restaurant, balance):
    """Helper: atomically reset a restaurant's coin balance."""
    frappe.db.set_value("Restaurant", restaurant, "coins_balance", balance)
    frappe.db.commit()


def clear_transactions(restaurant):
    """Delete all Coin Transactions for a restaurant."""
    frappe.db.delete("Coin Transaction", {"restaurant": restaurant})
    frappe.db.commit()


def get_latest_transaction(restaurant, txn_type=None):
    """Fetch the most recently created Coin Transaction for a restaurant."""
    filters = {"restaurant": restaurant}
    if txn_type:
        filters["transaction_type"] = txn_type
    result = frappe.db.get_list(
        "Coin Transaction",
        filters=filters,
        fields=["name", "transaction_type", "amount", "balance_after", "payment_id"],
        order_by="creation desc",
        limit=1,
    )
    return result[0] if result else None
