import frappe
from frappe.model.document import Document
import math


class MonthlyBillingLedger(Document):
    def validate(self):
        # Ensure uniqueness per restaurant + month
        existing = frappe.db.exists("Monthly Billing Ledger", {
            "restaurant": self.restaurant,
            "billing_month": self.billing_month,
            "name": ("!=", self.name)
        })
        if existing:
            frappe.throw(f"Monthly Billing Ledger already exists for {self.restaurant} in {self.billing_month}")

    def before_save(self):
        # Calculate fee and final amount if totals are present
        try:
            total_gmv = int(self.total_gmv or 0)
            
            platform_fee_percent = 3.0
            if self.restaurant:
                res_fee = frappe.db.get_value("Restaurant", self.restaurant, "platform_fee_percent")
                if res_fee is not None:
                    platform_fee_percent = float(res_fee)

            # 1. Calculate Base Commission based on Success Share
            calculated_fee = int(math.floor(total_gmv * (platform_fee_percent / 100.0)))
            base_commission = calculated_fee
            self.notes = f"Commission: ₹{calculated_fee/100:.2f} ({platform_fee_percent}%)"
            
            # 2. GST Compliance (Global Setting)
            settings = frappe.get_single("Flamezo Settings")
            charge_gst = bool(settings.charge_gst)
            default_rate = float(settings.gst_percent or 18.0) if charge_gst else 0.0
            
            tax_rate = float(self.tax_percent if self.tax_percent is not None else default_rate)
            gst_amount = int(math.floor(base_commission * (tax_rate / 100.0)))
            
            # 3. Final Amount
            final_total = base_commission + gst_amount

            self.calculated_fee = base_commission
            self.gst_amount = gst_amount
            self.tax_percent = tax_rate
            self.final_amount = final_total
            self.notes += f" | GST ({tax_rate}%): ₹{gst_amount/100:.2f}"
        except Exception as e:
            frappe.log_error(f"Failed to calculate billing: {str(e)}", "monthly_billing_ledger.before_save")

