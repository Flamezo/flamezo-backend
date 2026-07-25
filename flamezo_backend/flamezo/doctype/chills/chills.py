# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Chills(Document):
    def before_save(self):
        if self.status == "published" and not self.published_at:
            self.published_at = frappe.utils.now_datetime()
