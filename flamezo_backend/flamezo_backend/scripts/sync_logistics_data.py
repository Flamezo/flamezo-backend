import frappe
from frappe.utils import flt

def execute():
    """
    Ensures all restaurants with 'Self' delivery provider have their flat fee
    moved to the standard 'default_delivery_fee' field.
    """
    frappe.connect()
    try:
        # Find all Self delivery restaurants
        restaurants = frappe.get_all("Restaurant", 
            filters={
                "preferred_logistics_provider": "Self"
            },
            fields=["name", "delivery_markup_value", "default_delivery_fee"]
        )
        
        updated_count = 0
        for res in restaurants:
            markup = flt(res.delivery_markup_value)
            current_fee = flt(res.default_delivery_fee)
            
            # If markup exists but fee is 0, migrate it
            if markup > 0 and current_fee == 0:
                frappe.db.set_value("Restaurant", res.name, {
                    "default_delivery_fee": markup,
                    "delivery_markup_value": 0 # Clear markup for clean state
                }, update_modified=False)
                updated_count += 1
                print(f"Migrated {res.name}: {markup} -> default_delivery_fee")
            
            # If both exist and differ, log it (manual check needed if ambiguous)
            elif markup > 0 and current_fee > 0 and markup != current_fee:
                print(f"Warning: {res.name} has both markup ({markup}) and fee ({current_fee}). Using existing fee.")

        frappe.db.commit()
        print(f"Logistics Migration Complete. Updated {updated_count} restaurants.")
        
    except Exception as e:
        frappe.db.rollback()
        print(f"Migration Failed: {str(e)}")
    finally:
        frappe.destroy()

if __name__ == "__main__":
    execute()
