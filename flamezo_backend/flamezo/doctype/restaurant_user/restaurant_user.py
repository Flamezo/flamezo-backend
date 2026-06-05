# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


# Staff seat limits (excludes the one Restaurant Admin)
STAFF_SEAT_LIMIT = 6


def get_staff_seat_limit(restaurant):
	"""Return the maximum non-admin staff count allowed (default 6)."""
	return STAFF_SEAT_LIMIT


class RestaurantUser(Document):
	def validate(self):
		"""Validate Restaurant User"""
		# Ensure only one default restaurant per user
		if self.is_default:
			existing_default = frappe.db.get_value(
				"Restaurant User",
				{"user": self.user, "is_default": 1, "name": ["!=", self.name]},
				"name"
			)
			if existing_default:
				frappe.throw("User can have only one default restaurant")

		# --- Seat Limit Enforcement (only for new Staff records) ---
		if self.is_new() and self.role == "Restaurant Staff":
			self._enforce_seat_limit()

	def _enforce_seat_limit(self):
		"""Enforce staff seat limits."""
		limit = get_staff_seat_limit(self.restaurant)

		# Count existing active non-admin staff
		current_count = frappe.db.count(
			"Restaurant User",
			{
				"restaurant": self.restaurant,
				"role": "Restaurant Staff",
				"is_active": 1,
			}
		)

		if current_count >= limit:
			frappe.throw(
				f"Staff seat limit of {limit} reached. "
				f"You currently have {current_count} active staff."
			)

	def after_insert(self):
		"""Add role + User Permission when Restaurant User is created"""
		self.add_role_to_user()
		self._sync_user_permission(create=True)

	def on_update(self):
		"""Update role when Restaurant User is updated"""
		self.add_role_to_user()

	def on_trash(self):
		"""Remove User Permission when Restaurant User is deleted"""
		self._sync_user_permission(create=False)

	def add_role_to_user(self):
		"""Add Frappe role to user if not already present"""
		try:
			user_doc = frappe.get_doc("User", self.user)
			role = self.role or "Restaurant Staff"

			existing_roles = [r.role for r in user_doc.roles]
			if role not in existing_roles:
				user_doc.append("roles", {"role": role})
				user_doc.save(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(f"Error adding role to user: {str(e)}", "Restaurant User Role Assignment")

	def _sync_user_permission(self, create=True):
		"""Create or remove Frappe User Permission for restaurant access."""
		try:
			if create:
				if not frappe.db.exists("User Permission", {
					"user": self.user,
					"allow": "Restaurant",
					"for_value": self.restaurant
				}):
					frappe.permissions.add_user_permission(
						doctype="Restaurant",
						name=self.restaurant,
						user=self.user,
						is_default=self.is_default,
						ignore_permissions=True
					)
			else:
				try:
					frappe.permissions.remove_user_permission(
						doctype="Restaurant",
						name=self.restaurant,
						user=self.user,
						ignore_permissions=True
					)
				except Exception:
					pass  # Silently ignore if permission doesn't exist

			# Bust the Redis restaurant-access cache so changes reflect immediately
			redis_key = f"flamezo_backend:user_restaurants:{self.user}"
			frappe.cache().delete_value(redis_key)
		except Exception as e:
			frappe.log_error(f"Error syncing user permission: {str(e)}", "Restaurant User Permission Sync")
