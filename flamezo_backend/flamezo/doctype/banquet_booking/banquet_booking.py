# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class BanquetBooking(Document):
	def before_insert(self):
		"""Generate booking number"""
		if not self.booking_number:
			self.booking_number = self.generate_booking_number()
	
	def generate_booking_number(self):
		"""Generate unique booking number: BQ-YYYY-NNN"""
		from datetime import datetime
		year = datetime.now().year
		count = frappe.db.count("Banquet Booking", filters={
			"creation": [">=", f"{year}-01-01"],
			"creation": ["<=", f"{year}-12-31"],
			"restaurant": self.restaurant
		})
		sequence = str(count + 1).zfill(3)
		return f"BQ-{year}-{sequence}"


