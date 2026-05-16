# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime
from datetime import datetime, timedelta


class TableBooking(Document):
	def before_insert(self):
		"""Generate booking number"""
		if not self.booking_number:
			self.booking_number = self.generate_booking_number()

	def _get_assigned_table(self):
		return self.get("assigned_table") if hasattr(self, "get") else None

	def _get_auto_assign_table(self):
		return self.get("auto_assign_table") if hasattr(self, "get") else None
	
	def validate(self):
		"""Validate booking data"""
		# Check for anti-abuse: limit active bookings per phone
		if self.customer_phone and self.is_new():
			self.check_booking_limit()
		
		# Validate table assignment if manually set
		if self._get_assigned_table():
			self.validate_table_assignment()
	
	def on_update(self):
		"""Handle status changes"""
		if self.has_value_changed("status"):
			self.handle_status_change()
	
	def generate_booking_number(self):
		"""Generate unique booking number: TB-YYYY-NNN"""
		year = datetime.now().year
		prefix = f"TB-{year}-"
		last_booking = frappe.get_all(
			"Table Booking",
			filters={
				"booking_number": ["like", f"{prefix}%"]
			},
			fields=["booking_number"],
			order_by="creation desc",
			limit=1
		)

		last_sequence = 0
		if last_booking and last_booking[0].get("booking_number"):
			try:
				last_sequence = int(last_booking[0]["booking_number"].split("-")[-1])
			except (ValueError, TypeError):
				last_sequence = 0

		for sequence in range(last_sequence + 1, last_sequence + 1000):
			candidate = f"{prefix}{str(sequence).zfill(3)}"
			if not frappe.db.exists("Table Booking", {"booking_number": candidate}):
				return candidate

		frappe.throw("Unable to generate a unique booking number. Please try again.")
	
	def check_booking_limit(self):
		"""Anti-abuse: Check if customer has too many active bookings"""
		active_bookings = frappe.db.count("Table Booking", filters={
			"customer_phone": self.customer_phone,
			"status": ["in", ["pending", "confirmed"]],
			"date": [">=", frappe.utils.today()]
		})
		
		# Limit to 3 active bookings per phone number
		if active_bookings >= 3:
			frappe.throw("You have reached the maximum limit of 3 active bookings. Please cancel an existing booking to create a new one.")
	
	def validate_table_assignment(self):
		"""Validate that assigned table exists and belongs to restaurant"""
		assigned_table = self._get_assigned_table()
		if not assigned_table:
			return

		table = frappe.get_doc("Restaurant Table", assigned_table)
		if table.restaurant != self.restaurant:
			frappe.throw(f"Table {assigned_table} does not belong to this restaurant")
		
		# Check if table has sufficient capacity
		if table.capacity < self.number_of_diners:
			frappe.msgprint(
				f"Warning: Table {table.table_number} has capacity {table.capacity} but booking is for {self.number_of_diners} diners",
				indicator="orange"
			)
	
	def handle_status_change(self):
		"""Handle status transitions and auto-assign tables"""
		current_user = frappe.session.user
		current_time = now_datetime()
		
		if self.status == "confirmed":
			self.confirmed_at = current_time
			self.confirmed_by = current_user
			
			# Auto-assign table if enabled and not already assigned
			if self._get_auto_assign_table() and not self._get_assigned_table():
				self.auto_assign_best_table()
		
		elif self.status == "rejected":
			self.rejected_at = current_time
			self.rejected_by = current_user
			# Release table if assigned
			if self._get_assigned_table():
				self.release_table()
		
		elif self.status == "completed":
			self.completed_at = current_time
			# Release table
			if self._get_assigned_table():
				self.release_table()
		
		elif self.status == "no-show":
			self.no_show_at = current_time
			# Release table
			if self._get_assigned_table():
				self.release_table()
		
		elif self.status == "cancelled":
			self.cancelled_at = current_time
			# Release table
			if self._get_assigned_table():
				self.release_table()
	
	def auto_assign_best_table(self):
		"""Intelligently assign the best available table based on capacity and availability"""
		# Get all available tables for this restaurant
		tables = frappe.get_all(
			"Restaurant Table",
			filters={
				"restaurant": self.restaurant,
				"status": "available"
			},
			fields=["name", "table_number", "capacity", "priority", "is_combinable"],
			order_by="priority desc, capacity asc"
		)
		
		if not tables:
			frappe.msgprint("No available tables found for auto-assignment", indicator="orange")
			return
		
		# Find best matching table
		best_table = None
		
		# Strategy 1: Find smallest table that fits (exact or slightly larger)
		for table in tables:
			if table.capacity >= self.number_of_diners:
				# Check if table is available for this time slot
				if self.is_table_available(table.name):
					best_table = table
					break
		
		# Strategy 2: If no exact match, try combining tables (future enhancement)
		# For now, just pick the largest available table
		if not best_table and tables:
			for table in reversed(tables):
				if self.is_table_available(table.name):
					best_table = table
					break
		
		if best_table:
			self.set("assigned_table", best_table.name)
			self.set("table_assignment_method", "auto")
			frappe.msgprint(
				f"Table {best_table.table_number} (capacity: {best_table.capacity}) auto-assigned",
				indicator="green"
			)
		else:
			frappe.msgprint("No suitable table available for this time slot", indicator="orange")
	
	def is_table_available(self, table_name):
		"""Check if table is available for this booking's date and time slot"""
		# Get booking time slot duration (default 90 minutes)
		slot_duration = 90  # minutes
		
		# Parse time slot to get start time
		booking_datetime = self.get_booking_datetime()
		if not booking_datetime:
			return True  # If we can't parse, assume available
		
		# Check for overlapping bookings
		overlapping = frappe.db.exists("Table Booking", {
			"assigned_table": table_name,
			"date": self.date,
			"status": ["in", ["pending", "confirmed"]],
			"name": ["!=", self.name]
		})
		
		# For simplicity, if same date and table, consider it occupied
		# More sophisticated overlap detection can be added later
		return not overlapping
	
	def get_booking_datetime(self):
		"""Parse booking date and time slot to datetime"""
		try:
			# Parse time slot (e.g., "7:00 PM" or "19:00")
			from dateutil import parser
			time_str = self.time_slot
			time_obj = parser.parse(time_str).time()
			booking_dt = datetime.combine(get_datetime(self.date).date(), time_obj)
			return booking_dt
		except:
			return None
	
	def release_table(self):
		"""Release the assigned table"""
		assigned_table = self._get_assigned_table()
		if assigned_table:
			try:
				table = frappe.get_doc("Restaurant Table", assigned_table)
				if table.status == "reserved":
					table.status = "available"
					table.save(ignore_permissions=True)
			except:
				pass


