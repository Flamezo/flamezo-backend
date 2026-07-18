import frappe
from frappe.model.document import Document


class CustomerAddress(Document):
    def before_save(self):
        # Enforce single default per customer — clear others when setting new default
        if self.is_default:
            frappe.db.set_value(
                "Customer Address",
                {
                    "customer": self.customer,
                    "name": ("!=", self.name),
                    "is_default": 1,
                },
                "is_default",
                0,
            )

    def validate(self):
        if self.pincode and len(self.pincode.strip()) not in (0, 6):
            frappe.throw("Pincode must be 6 digits.")

        if self.latitude is not None and not (-90 <= self.latitude <= 90):
            frappe.throw("Latitude must be between -90 and 90.")
        if self.longitude is not None and not (-180 <= self.longitude <= 180):
            frappe.throw("Longitude must be between -180 and 180.")
