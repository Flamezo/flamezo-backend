import frappe
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime


class CrowdRequest(Document):
    def before_insert(self):
        if self.date and not self.expires_at:
            event_dt = get_datetime(str(self.date) + " 00:00:00")
            self.expires_at = add_days(event_dt, 2)
