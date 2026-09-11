import frappe


def execute():
	"""Create the Support Agent role used by support chat.

	Additive and idempotent: creates the role only if it is missing, and never
	modifies or removes anything that already exists.
	"""
	if frappe.db.exists("Role", "Support Agent"):
		return
	frappe.get_doc({"doctype": "Role", "role_name": "Support Agent", "desk_access": 1}).insert(
		ignore_permissions=True
	)
