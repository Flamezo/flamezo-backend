import frappe
from frappe.model.document import Document


class Court(Document):
	def validate(self):
		if self.opening_time and self.closing_time:
			if str(self.closing_time) <= str(self.opening_time):
				frappe.throw("Closing time must be after opening time.")
		if self.slot_duration_minutes and self.slot_duration_minutes < 15:
			frappe.throw("Slot duration must be at least 15 minutes.")
