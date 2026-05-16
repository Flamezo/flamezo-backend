import frappe
from frappe.model.document import Document


class TokenizationAttempt(Document):
    def validate(self):
        # ensure amount is integer paise
        try:
            self.amount = int(self.amount or 100)
        except Exception:
            self.amount = 100

    def mark_created(self, razorpay_order_id: str):
        self.razorpay_order_id = razorpay_order_id
        self.status = "created"
        self.save(ignore_permissions=True)

    def mark_captured(self, payment_id: str, customer_id: str = None, token_id: str = None):
        self.razorpay_payment_id = payment_id
        if customer_id:
            self.customer_id = customer_id
        if token_id:
            self.token_id = token_id
        self.status = "captured"
        self.processed = 1
        self.save(ignore_permissions=True)

