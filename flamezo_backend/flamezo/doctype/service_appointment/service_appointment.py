import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class ServiceAppointment(Document):
	def validate(self):
		if self.outlet and not self.outlet_type:
			self.outlet_type = frappe.db.get_value("Outlet", self.outlet, "outlet_type") or ""

	def on_update(self):
		if self.status == "Confirmed" and not self.confirmed_at:
			frappe.db.set_value("Service Appointment", self.name, "confirmed_at", now_datetime(), update_modified=False)
		elif self.status == "Completed" and not self.completed_at:
			frappe.db.set_value("Service Appointment", self.name, "completed_at", now_datetime(), update_modified=False)
