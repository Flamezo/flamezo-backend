import frappe
from frappe.utils import now_datetime, add_to_date

def run():
    twenty_four_hours_ago = add_to_date(now_datetime(), hours=-24)
    print(f"Filtering for orders created after: {twenty_four_hours_ago}")
    
    # Test without the 24h filter
    orders_all = frappe.get_all(
        "Order",
        filters=[
            ["status", "=", "pending_verification"]
        ],
        fields=["name", "creation"]
    )
    
    # Test with the 24h filter (how the API will now call it)
    orders_24h = frappe.get_all(
        "Order",
        filters=[
            ["status", "=", "pending_verification"],
            ["creation", ">=", twenty_four_hours_ago]
        ],
        fields=["name", "creation"]
    )
    
    print(f"Total pending_verification orders without time filter: {len(orders_all)}")
    print(f"Total pending_verification orders with 24h filter: {len(orders_24h)}")
    
    if len(orders_all) > 0:
        print("\nSample orders without 24h filter:")
        for o in orders_all[:3]:
            print(f"- {o.name}: {o.creation}")
            
    if len(orders_24h) > 0:
        print("\nSample orders with 24h filter:")
        for o in orders_24h[:3]:
            print(f"- {o.name}: {o.creation}")
