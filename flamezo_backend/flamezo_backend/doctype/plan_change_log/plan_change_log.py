# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PlanChangeLog(Document):
	def before_insert(self):
		"""Set changed_by and IP address before insert"""
		if not self.changed_by:
			self.changed_by = frappe.session.user
		
		if not self.ip_address:
			self.ip_address = frappe.local.request_ip or "Unknown"
	
	def validate(self):
		"""Validate plan change log entry"""
		# Ensure changed_on is set
		if not self.changed_on:
			self.changed_on = frappe.utils.now()
		
		# Validate restaurant exists
		if self.restaurant and not frappe.db.exists("Restaurant", self.restaurant):
			frappe.throw(f"Restaurant {self.restaurant} does not exist")
