# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RestaurantTable(Document):
	def validate(self):
		"""Validate table data"""
		# Ensure table_number is unique per restaurant
		if self.is_new():
			existing = frappe.db.exists("Restaurant Table", {
				"restaurant": self.restaurant,
				"table_number": self.table_number,
				"name": ["!=", self.name]
			})
			if existing:
				frappe.throw(f"Table number {self.table_number} already exists for this restaurant")
		
		# Validate capacity
		if self.capacity < 1:
			frappe.throw("Table capacity must be at least 1")
	
	def before_save(self):
		"""Update table name if not set"""
		if not self.table_name:
			self.table_name = f"Table {self.table_number}"
