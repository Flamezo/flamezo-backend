import frappe

def check_time_settings():
    frappe.init(site="flamezo_backend.com") # Assuming this is the site name, but let's try to find it
    # Actually, we can just use frappe.db if we are in the bench environment
    
    try:
        tz = frappe.db.get_single_value("System Settings", "time_zone")
        df = frappe.db.get_single_value("System Settings", "date_format")
        tf = frappe.db.get_single_value("System Settings", "time_format")
        
        print(f"Timezone: {tz}")
        print(f"Date Format: {df}")
        print(f"Time Format: {tf}")
        print(f"Current Time (now): {frappe.utils.now()}")
        print(f"Current Time (now_datetime): {frappe.utils.now_datetime()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Since I don't know the site name for sure, I'll try to get it from the environment or bench
    import os
    # Try to execute via bench
    print("Running check...")
