# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

"""
Utility functions for Restaurant User Permissions
"""

import frappe
from frappe import _
from flamezo_backend.flamezo.utils.roles import GLOBAL_ADMIN_ROLES, SUPERVISOR_ROLES


def create_restaurant_user_permission(user, restaurant, is_default=0):
	"""Create User Permission for restaurant"""
	try:
		# Check if permission already exists
		if frappe.db.exists("User Permission", {
			"user": user,
			"allow": "Restaurant",
			"for_value": restaurant
		}):
			return
		
		# Create User Permission
		frappe.permissions.add_user_permission(
			doctype="Restaurant",
			name=restaurant,
			user=user,
			is_default=is_default,
			ignore_permissions=True
		)
	except Exception as e:
		frappe.log_error(
			title="Restaurant Permission", 
			message=f"Error creating restaurant user permission: {str(e)}"
		)


def remove_restaurant_user_permission(user, restaurant):
	"""Remove User Permission for restaurant"""
	try:
		frappe.permissions.remove_user_permission(
			doctype="Restaurant",
			name=restaurant,
			user=user,
			ignore_permissions=True
		)
	except Exception as e:
		frappe.log_error(
			title="Restaurant Permission", 
			message=f"Error removing restaurant user permission: {str(e)}"
		)


def assign_user_to_restaurant(user, restaurant, role="Restaurant Staff", is_default=0):
	"""Assign user to restaurant (creates Restaurant User + User Permission)"""
	# Check if Restaurant User already exists
	if frappe.db.exists("Restaurant User", {"user": user, "restaurant": restaurant}):
		frappe.throw(_("User is already assigned to this restaurant"))
	
	# Create Restaurant User
	restaurant_user = frappe.get_doc({
		"doctype": "Restaurant User",
		"user": user,
		"restaurant": restaurant,
		"role": role,
		"is_default": is_default,
		"is_active": 1
	})
	restaurant_user.insert(ignore_permissions=True)
	
	return restaurant_user


def remove_user_from_restaurant(user, restaurant):
	"""Remove user from restaurant"""
	restaurant_user = frappe.db.get_value(
		"Restaurant User",
		{"user": user, "restaurant": restaurant},
		"name"
	)
	
	if restaurant_user:
		frappe.delete_doc("Restaurant User", restaurant_user, ignore_permissions=True)
		return True
	return False


def get_user_restaurants(user):
	"""Get all restaurants assigned to user"""
	restaurants = frappe.get_all(
		"Restaurant User",
		filters={"user": user, "is_active": 1},
		fields=["restaurant", "role", "is_default", "name"],
		order_by="is_default desc, restaurant asc"
	)
	return restaurants


def get_default_restaurant(user):
	"""Get user's default restaurant"""
	restaurant = frappe.db.get_value(
		"Restaurant User",
		{"user": user, "is_default": 1, "is_active": 1},
		"restaurant"
	)
	return restaurant


def get_user_restaurant_ids(user):
	"""Get list of restaurant IDs user has access to based on Restaurant User records
	Optimized with Request-Level Caching and Redis Caching for Production Scale.
	"""
	user_roles = frappe.get_roles(user)
	has_global_access = any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles)
	if has_global_access:
		# Administrator, System Manager, and Supervisors have access to all restaurants
		# Cache results in frappe.local to ensure it only runs once per request
		if not hasattr(frappe.local, "all_restaurant_ids"):
			# Use direct SQL to avoid any hooks when fetching the list of all restaurants
			all_res = frappe.db.sql("SELECT name FROM `tabRestaurant` WHERE is_active = 1", as_dict=True)
			frappe.local.all_restaurant_ids = [d.name for d in all_res]
		return frappe.local.all_restaurant_ids
	
	# Tier 1: Request-Level Cache (Memory)
	cache_key = f"user_restaurant_ids_{user}"
	if hasattr(frappe.local, cache_key):
		return getattr(frappe.local, cache_key)
	
	# Tier 2: Redis-Level Cache (Shared Memory) - 10 minute TTL
	redis_key = f"flamezo_backend:user_restaurants:{user}"
	cached_ids = frappe.cache().get_value(redis_key)
	if cached_ids is not None:
		setattr(frappe.local, cache_key, cached_ids)
		return cached_ids

	# Tier 3: Database Query (Direct SQL for speed and to bypass hooks)
	restaurant_users = frappe.db.sql("""
		SELECT restaurant 
		FROM `tabRestaurant User` 
		WHERE user = %s AND is_active = 1
	""", user, as_dict=True)
	
	ids = [d.restaurant for d in restaurant_users if d.restaurant]
	
	# Save to all cache tiers
	setattr(frappe.local, cache_key, ids)
	frappe.cache().set_value(redis_key, ids, expires_in_sec=600)
	
	return ids


def validate_restaurant_access(user, restaurant):
	"""Validate user has access to restaurant"""
	user_roles = frappe.get_roles(user)
	if any(role in GLOBAL_ADMIN_ROLES or role in SUPERVISOR_ROLES for role in user_roles):
		return True
	
	# Check if restaurant exists and is active
	if not frappe.db.exists("Restaurant", {"name": restaurant, "is_active": 1}):
		return False
	
	# Check user permissions
	restaurant_ids = get_user_restaurant_ids(user)
	return restaurant in restaurant_ids


