# Copyright (c) 2026, Flamezo and contributors

import frappe
from frappe.model.document import Document
from frappe import _


class MarketingTrigger(Document):
    def validate(self):
        plan = frappe.db.get_value("Restaurant", self.restaurant, "plan_type")
        if plan != "GOLD" and self.is_active:
            frappe.throw(_("Marketing Triggers require a GOLD subscription."))
