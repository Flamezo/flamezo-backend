import frappe
from frappe.model.document import Document


class CreatorClubPost(Document):
    def before_insert(self):
        if self.club and not self.creator:
            self.creator = frappe.db.get_value("Creator Club", self.club, "creator")
