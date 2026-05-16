import frappe

def execute():
	"""
	Standardize the platform to Asia/Kolkata (IST).
	1. Sets System Settings timezone to Asia/Kolkata.
	2. Sets Date Format to dd-mm-yyyy.
	3. Sets Number Format to Indian style (#,##,###.##).
	"""
	frappe.db.set_single_value("System Settings", "time_zone", "Asia/Kolkata")
	frappe.db.set_single_value("System Settings", "date_format", "dd-mm-yyyy")
	frappe.db.set_single_value("System Settings", "number_format", "#,##,###.##")
	
	# Commit to ensure changes are applied immediately
	frappe.db.commit()
