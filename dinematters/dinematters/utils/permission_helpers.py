# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

"""
Permission helper functions for Restaurant-based access control
"""

import frappe
from dinematters.dinematters.utils.permissions import get_user_restaurant_ids
from dinematters.dinematters.utils.roles import GLOBAL_ADMIN_ROLES, SUPERVISOR_ROLES


def get_restaurant_permission_query_conditions(user, doctype=None, **kwargs):
	"""Get permission query conditions for restaurant-based doctypes
	Optimized with recursion guard for Enterprise stability.
	"""
	if not user:
		user = frappe.session.user
	
	user_roles = frappe.get_roles(user)
	if any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles):
		return "1=1"
	
	try:
		# Recursion Guard: Prevent loop if this function is triggered during metadata fetch
		guard_key = f"permission_hook_guard_{doctype}"
		if hasattr(frappe.local, guard_key):
			return ""
		
		setattr(frappe.local, guard_key, True)
		
		try:
			restaurant_ids = get_user_restaurant_ids(user)
			
			if not restaurant_ids:
				return "1=0"  # No access
			
			# Build condition
			restaurant_list = ",".join([f'"{r}"' for r in restaurant_ids])
			
			# For Restaurant doctype, filter by name directly
			if doctype == "Restaurant":
				return f"`tab{doctype}`.name IN ({restaurant_list})"
			
			# For other doctypes, filter by restaurant field if it exists
			if doctype:
				meta = frappe.get_meta(doctype)
			else:
				# If doctype is not passed, we can't safely assume parent/restaurant field
				return ""
			if meta.has_field("restaurant"):
				return f"`tab{doctype}`.restaurant IN ({restaurant_list})"
			
			# Skip filtering for doctypes without restaurant field (e.g. child tables)
			return ""
		finally:
			# Always clear guard
			if hasattr(frappe.local, guard_key):
				delattr(frappe.local, guard_key)
	except Exception as e:
		frappe.log_error(title="Permission Query Hook Error", message=frappe.get_traceback())
		raise


def has_restaurant_permission(doc, ptype="read", user=None, **kwargs):
	"""Check if user has permission to access restaurant-based document
	Role Permissions control what actions users can perform (read/write/create/delete)
	This function only checks if user has access to the restaurant (data filtering)
	"""
	try:
		if not user:
			user = frappe.session.user
		
		user_roles = frappe.get_roles(user)
		if any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles):
			return True
		
		# Recursion Guard
		doctype = getattr(doc, "doctype", None)
		guard_key = f"has_permission_guard_{doctype}_{getattr(doc, 'name', 'new')}"
		if hasattr(frappe.local, guard_key):
			return True # Assume OK if already checking to avoid loop
		
		setattr(frappe.local, guard_key, True)
		
		try:
			# For Restaurant doctype, check by name
			if doctype == "Restaurant":
				restaurant_ids = get_user_restaurant_ids(user)
				return doc.name in restaurant_ids
			
			# For other doctypes, check restaurant field
			if not hasattr(doc, "restaurant") or not doc.restaurant:
				return False
			
			# Check user has access to this restaurant
			restaurant_ids = get_user_restaurant_ids(user)
			return doc.restaurant in restaurant_ids
		finally:
			if hasattr(frappe.local, guard_key):
				delattr(frappe.local, guard_key)
	except Exception as e:
		frappe.log_error(title="has_restaurant_permission Error", message=frappe.get_traceback())
		raise


# Specific permission functions for each doctype

def get_menu_product_permissions(user, doctype="Menu Product"):
	"""Get permission query for Menu Product"""
	return get_restaurant_permission_query_conditions(user, doctype)


def has_menu_product_permission(doc, ptype, user, **kwargs):
	"""Check permission for Menu Product"""
	return has_restaurant_permission(doc, ptype=ptype, user=user)


def get_menu_category_permissions(user, doctype="Menu Category"):
	"""Get permission query for Menu Category"""
	return get_restaurant_permission_query_conditions(user, doctype)


def has_menu_category_permission(doc, ptype, user, **kwargs):
	"""Check permission for Menu Category"""
	return has_restaurant_permission(doc, ptype=ptype, user=user)


def get_order_permissions(user, doctype="Order"):
	"""Get permission query for Order"""
	return get_restaurant_permission_query_conditions(user, doctype)


def has_order_permission(doc, ptype, user, **kwargs):
	"""Check permission for Order"""
	return has_restaurant_permission(doc, ptype=ptype, user=user)


def get_cart_entry_permissions(user, doctype="Cart Entry"):
	"""Get permission query for Cart Entry"""
	return get_restaurant_permission_query_conditions(user, doctype)


def has_cart_entry_permission(doc, ptype, user, **kwargs):
	"""Check permission for Cart Entry"""
	return has_restaurant_permission(doc, ptype=ptype, user=user)


def get_restaurant_user_permission_query_conditions(user, doctype="Restaurant User", **kwargs):
	"""Get permission query for Restaurant User - filter by restaurants user has access to"""
	if not user:
		user = frappe.session.user
	
	user_roles = frappe.get_roles(user)
	if any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles):
		return "1=1"
	
	restaurant_ids = get_user_restaurant_ids(user)
	
	if not restaurant_ids:
		return "1=0"  # No access
	
	# Build condition - Restaurant User has a restaurant field
	restaurant_list = ",".join([f'"{r}"' for r in restaurant_ids])
	return f"`tab{doctype}`.restaurant IN ({restaurant_list})"



def has_restaurant_user_permission(doc, ptype, user, **kwargs):
	"""Check permission for Restaurant User"""
	return has_restaurant_permission(doc, ptype=ptype, user=user)


