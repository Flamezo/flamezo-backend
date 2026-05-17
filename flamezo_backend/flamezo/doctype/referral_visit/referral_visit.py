# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReferralVisit(Document):
	def validate(self):
		if not self.timestamp:
			self.timestamp = frappe.utils.now_datetime()
