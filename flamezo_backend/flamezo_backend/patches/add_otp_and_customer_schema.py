"""Create Flamezo Settings single doc if not exists."""
import frappe


def execute():
	if not frappe.db.exists("DocType", "Flamezo Settings"):
		return
	# Single doctype: ensure the doc exists (Frappe auto-creates on first access, but we init explicitly)
	try:
		if not frappe.db.exists("Flamezo Settings", "Flamezo Settings"):
			frappe.get_doc({"doctype": "Flamezo Settings"}).insert(ignore_permissions=True)
			frappe.db.commit()
	except Exception:
		pass
