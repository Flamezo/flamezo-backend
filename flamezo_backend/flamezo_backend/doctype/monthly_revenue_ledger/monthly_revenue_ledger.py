# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MonthlyRevenueLedger(Document):
	def validate(self):
		"""Validate the monthly revenue ledger entry."""
		# Ensure unique combination of restaurant and month
		existing = frappe.db.exists("Monthly Revenue Ledger", {
			"restaurant": self.restaurant,
			"month": self.month,
			"name": ("!=", self.name)
		})
		
		if existing:
			frappe.throw(f"Monthly Revenue Ledger already exists for {self.restaurant} in {self.month}")
	
	def before_save(self):
		"""Calculate minimum due before saving."""
		if self.total_platform_fee and self.restaurant:
			restaurant_doc = frappe.get_doc("Restaurant", self.restaurant)
			monthly_minimum_paise = int(restaurant_doc.monthly_minimum * 100)  # Convert to paise
			
			if self.total_platform_fee < monthly_minimum_paise:
				self.minimum_due = monthly_minimum_paise - self.total_platform_fee
			else:
				self.minimum_due = 0
				self.status = "paid"  # No minimum due, mark as paid