# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MonthlyRevenueLedger(Document):
	def validate(self):
		"""Validate the monthly revenue ledger entry."""
		# Ensure unique combination of restaurant and month
		existing = frappe.db.exists("Monthly Revenue Ledger", {
			"outlet": self.outlet,
			"month": self.month,
			"name": ("!=", self.name)
		})

		if existing:
			frappe.throw(f"Monthly Revenue Ledger already exists for outlet {self.outlet} in {self.month}")
	
