import frappe
from frappe.model.document import Document


class CreatorClub(Document):
    def before_save(self):
        if self.creator:
            tier = frappe.db.get_value("Flamezo Creator", self.creator, "creator_tier")
            if tier:
                self.tier = tier
