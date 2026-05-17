# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
Centralized role definitions for Flamezo.
Use these constants to enforce permissions uniformly across the system.
"""

# Global Administrators with root/system-wide access
GLOBAL_ADMIN_ROLES = ["Administrator", "System Manager"]

# Elevated Staff roles (can manage all restaurants via dashboard but lack global settings access)
SUPERVISOR_ROLES = ["Flamezo Supervisor"]

# Merchant-level roles (assigned via Restaurant User)
MERCHANT_ADMIN_ROLES = ["Restaurant Admin"]
MERCHANT_STAFF_ROLES = ["Restaurant Staff"]

# Roles that are explicitly locked out of the Frappe Desk (/app)
# Note: Flamezo Supervisor is NOT here, allowing them Desk access for advanced support.
DESK_RESTRICTED_ROLES = [
    "Restaurant Admin", 
    "Restaurant Staff"
]


def is_global_admin(user=None):
	"""Check if user has root/global admin roles."""
	import frappe
	if not user: user = frappe.session.user
	if user == "Administrator": return True
	
	user_roles = frappe.get_roles(user)
	return any(role in GLOBAL_ADMIN_ROLES for role in user_roles)


def is_supervisor(user=None):
	"""Check if user has supervisor/platform support roles."""
	import frappe
	if not user: user = frappe.session.user
	if is_global_admin(user): return True
	
	user_roles = frappe.get_roles(user)
	return any(role in SUPERVISOR_ROLES for role in user_roles)
