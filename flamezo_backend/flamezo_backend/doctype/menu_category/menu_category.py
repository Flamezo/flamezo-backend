# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
import re


class MenuCategory(Document):
	def validate(self):
		# Auto-generate category_id if missing
		if not self.category_id and self.category_name:
			self.category_id = self.generate_id_from_name(self.category_name)

		# Unify Display Name with Category Name always
		if self.category_name:
			self.display_name = self.category_name

		if self.category_id and self.restaurant:
			# Auto-resolve duplicates for category_id
			original_id = self.category_id
			counter = 1
			while frappe.db.exists("Menu Category", {"category_id": self.category_id, "restaurant": self.restaurant, "name": ["!=", self.name]}):
				self.category_id = f"{original_id}-{counter}"
				counter += 1

		# Validate parent_category constraints
		if self.parent_category:
			self._validate_parent_category()

	def _validate_parent_category(self):
		"""Enforce 2-level max depth and prevent circular references."""
		# Cannot be its own parent
		if self.parent_category == self.name:
			frappe.throw(_("A category cannot be its own parent."))

		# Verify the parent belongs to the same restaurant
		parent_restaurant = frappe.db.get_value("Menu Category", self.parent_category, "restaurant")
		if parent_restaurant != self.restaurant:
			frappe.throw(_("Parent category must belong to the same restaurant."))

		# The parent itself must NOT already have a parent (max 2 levels: parent → sub)
		grandparent = frappe.db.get_value("Menu Category", self.parent_category, "parent_category")
		if grandparent:
			frappe.throw(_(
				"Sub-categories cannot be nested more than one level deep. "
				"The selected parent is already a sub-category."
			))

		# Circular reference: make sure the chosen parent is not already a child of this category
		self._check_circular_reference(self.parent_category)

	def _check_circular_reference(self, candidate_parent):
		"""Raises if candidate_parent is a descendant of self (would create a cycle)."""
		visited = set()
		current = candidate_parent
		while current:
			if current == self.name:
				frappe.throw(_("Circular reference detected in category hierarchy."))
			if current in visited:
				break  # break to avoid infinite loop on corrupt data
			visited.add(current)
			current = frappe.db.get_value("Menu Category", current, "parent_category")

	def on_trash(self):
		"""
		Cascade delete:
		1. If this is a parent category, delete all subcategories first (which cascades their products).
		2. Delete all products directly in this category.
		"""
		# Delete subcategories (they will cascade-delete their own products via their on_trash)
		subcategories = frappe.get_all(
			"Menu Category",
			filters={"parent_category": self.name},
			pluck="name"
		)
		for sub_name in subcategories:
			frappe.delete_doc("Menu Category", sub_name, force=True, ignore_permissions=True)

		# Delete products directly in this category
		products = frappe.get_all("Menu Product", filters={"category": self.name}, pluck="name")
		for product in products:
			frappe.delete_doc("Menu Product", product, force=True, ignore_permissions=True)

	def generate_id_from_name(self, name):
		"""Generate a slug-like ID from name"""
		if not name:
			return None

		# Convert to lowercase
		id_str = name.lower()

		# Replace spaces and special characters with hyphens
		id_str = re.sub(r'[^\w\s-]', '', id_str)  # Remove special chars
		id_str = re.sub(r'[-\s]+', '-', id_str)  # Replace spaces and multiple hyphens with single hyphen
		id_str = id_str.strip('-')  # Remove leading/trailing hyphens

		return id_str
