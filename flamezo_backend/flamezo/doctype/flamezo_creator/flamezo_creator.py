import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class FlamezoCreator(Document):
    def before_save(self):
        if self.status == "approved" and not self.approved_at:
            self.approved_at = now_datetime()
