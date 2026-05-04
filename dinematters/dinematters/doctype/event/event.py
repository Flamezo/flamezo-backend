# Copyright (c) 2025, Dinematters and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Event(Document):
	"""
	Custom Event doctype for Dinematters.
	This class handles the case where Frappe/ERPNext integrations try to access
	fields that don't exist in this custom Event doctype.
	"""
	
	def validate(self):
		"""Validate event settings."""
		if not self.image_src:
			frappe.throw(_("Image is mandatory for all events."))
			
		if self.repeat_this_event:
			if not self.repeat_on:
				frappe.throw(_("Please select 'Repeat On' for recurring events."))
			
			# For weekly recurrence, at least one weekday must be selected
			if self.repeat_on == "Weekly":
				weekdays = [
					self.monday, self.tuesday, self.wednesday, 
					self.thursday, self.friday, self.saturday, self.sunday
				]
				if not any(weekdays):
					frappe.throw(_("Please select at least one weekday for weekly recurring events."))
			
			# Auto-update status to recurring if repeat_this_event is checked
			if self.status != "recurring":
				self.status = "recurring"
	
	@property
	def sync_with_google_calendar(self):
		"""Return False since this custom Event doesn't support Google Calendar sync."""
		return False
	
	@property
	def pulled_from_google_calendar(self):
		"""Return False since this custom Event doesn't support Google Calendar sync."""
		return False
	
	@property
	def google_calendar(self):
		"""Return None since this custom Event doesn't support Google Calendar sync."""
		return None
	
	@property
	def event_participants(self):
		"""Return empty list since this custom Event doesn't have event participants."""
		return []


