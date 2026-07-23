import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class FlamezoCreator(Document):
    def before_save(self):
        if self.status == "approved" and not self.approved_at:
            self.approved_at = now_datetime()
        if self.meta_followers >= 100000:
            self.creator_tier = "Blaze"
        elif self.meta_followers >= 10000:
            self.creator_tier = "Flame"
        else:
            self.creator_tier = "Spark"
