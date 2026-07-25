import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


def _to_minutes(t):
	parts = str(t).split(":")
	return int(parts[0]) * 60 + int(parts[1])


class CourtBooking(Document):
	def validate(self):
		if self.start_time and self.end_time:
			if _to_minutes(self.end_time) <= _to_minutes(self.start_time):
				frappe.throw("End time must be after start time.")

	def on_update(self):
		if self.status == "Completed" and not self.completed_at:
			frappe.db.set_value("Court Booking", self.name, "completed_at", now_datetime(), update_modified=False)
