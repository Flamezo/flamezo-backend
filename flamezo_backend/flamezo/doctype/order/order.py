import frappe
from frappe.model.document import Document
from frappe.utils import flt
import math


class Order(Document):
    def before_save(self):
        # Use the centralized pricing engine for production-level consistency
        from flamezo_backend.flamezo.utils.pricing import calculate_cart_totals
        
        # 2. Preparation: Determine if we should recalculate
        # For WhatsApp orders, we trust the frontend's calculated totals if provided,
        # otherwise we fallback to the central pricing engine.
        if getattr(self, "is_whatsapp_order", 0) and flt(self.total) > 0:
            # Update Platform Fee only
            rate = float(frappe.db.get_value("Restaurant", self.restaurant, "platform_fee_percent") or 1.5) / 100.0
            self.platform_fee_amount = int(math.floor(float(self.total or 0) * rate * 100))
            return

        # Prepare items in the format expected by the utility
        pricing_items = []
        for item in self.get("order_items"):
            if not item.product_name and item.product:
                item.product_name = frappe.db.get_value("Menu Product", item.product, "product_name")
            
            pricing_items.append({
                "quantity": item.quantity or 1,
                "unitPrice": item.unit_price,
                "dishId": item.product
            })

        # Calculate totals
        result = calculate_cart_totals(
            restaurant=self.restaurant,
            items=pricing_items,
            coupon_code=self.coupon,
            loyalty_coins=flt(self.loyalty_coins_redeemed or 0),
            customer=self.platform_customer,
            delivery_type=self.order_type # Dine-in, Delivery, Takeaway
        )

        # Update self with calculated values
        self.subtotal = result["subtotal"]
        self.discount = result["discount"]
        self.loyalty_discount = result["loyaltyDiscount"]
        self.tax = result["tax"]
        self.cgst = result["cgst"]
        self.sgst = result["sgst"]
        self.tax_percent = result["taxRate"]
        self.delivery_fee = result["deliveryFee"]
        self.packaging_fee = result["packagingFee"]
        
        # Delivery breakdown for reporting
        details = result.get("deliveryDetails", {})
        self.delivery_courier_fee = flt(details.get("courier_fee", 0))
        self.delivery_markup = flt(details.get("markup", 0))
        self.logistics_platform_fee = flt(details.get("platform_fee", 0))
        
        self.total = result["total"]

        # 5. Update Platform Fee (Dynamic commission on GMV)
        # GMV = total amount paid by customer
        # Field is 'platform_fee_amount' (Int, Paise)
        rate = float(frappe.db.get_value("Restaurant", self.restaurant, "platform_fee_percent") or 1.5) / 100.0
        self.platform_fee_amount = int(math.floor(float(self.total or 0) * rate * 100))


    def on_update(self):
        """
        Trigger commission deduction when order is confirmed/paid.
        Only applicable for GOLD restaurants.
        """
        if self.status in ["confirmed", "completed", "billed"] or self.payment_status == "completed":
            # 1. Plan Awareness: Only GOLD restaurants pay commission per transaction
            plan_type = frappe.db.get_value("Restaurant", self.restaurant, "plan_type")
            if plan_type != "GOLD":
                return

            # Avoid duplicate deductions
            if not frappe.db.exists("Coin Transaction", {
                "reference_doctype": "Order",
                "reference_name": self.name,
                "transaction_type": "Commission Deduction"
            }):
                from flamezo_backend.flamezo.api.coin_billing import deduct_coins
                
                res_fee_percent = float(frappe.db.get_value("Restaurant", self.restaurant, "platform_fee_percent") or 1.5)
                commission_amt = float(self.total or 0) * (res_fee_percent / 100.0)
                
                if commission_amt > 0:
                    try:
                        deduct_coins(
                            restaurant=self.restaurant,
                            amount=commission_amt,
                            type="Commission Deduction",
                            description=f"{res_fee_percent}% Commission for Order {self.order_number}",
                            ref_doctype="Order",
                            ref_name=self.name
                        )
                    except Exception as e:
                        # Log error but don't block order update (to avoid blocking kitchen flow)
                        # Autopay should eventually recover this
                        frappe.log_error(f"Commission deduction failed for {self.name}: {str(e)}", "Commission Error")

            # ── 2. Loyalty Settlement ─────────────────────────────────────────────
            # Update pending loyalty entries to 'is_settled=1' so they become spendable
            frappe.db.sql("""
                UPDATE `tabRestaurant Loyalty Entry`
                SET is_settled = 1
                WHERE customer = %s AND restaurant = %s 
                  AND reference_doctype = 'Order' AND reference_name = %s
                  AND is_settled = 0
            """, (self.platform_customer, self.restaurant, self.name))

        # Handle Cancellations (Refund if already charged)
        if self.status == "cancelled":
            # ── 1. Revert Earned Loyalty Coins ───────────────────────────────────
            # If the order is cancelled, the earned coins should be removed/reverted
            frappe.db.sql("""
                DELETE FROM `tabRestaurant Loyalty Entry`
                WHERE reference_doctype = 'Order' AND reference_name = %s
                  AND transaction_type = 'Earn'
            """, (self.name,))

            # ── 2. Commission Refund ─────────────────────────────────────────────
            # Check if deduction exists
            deduction_txn = frappe.db.get_value("Coin Transaction", {
                "reference_doctype": "Order",
                "reference_name": self.name,
                "transaction_type": "Commission Deduction"
            }, ["name", "amount"], as_dict=True)

            if deduction_txn:
                # Check if refund already exists
                if not frappe.db.exists("Coin Transaction", {
                    "reference_doctype": "Order",
                    "reference_name": self.name,
                    "transaction_type": "Refund"
                }):
                    from flamezo_backend.flamezo.api.coin_billing import refund_coins
                    try:
                        refund_coins(
                            restaurant=self.restaurant,
                            amount=deduction_txn.amount,
                            description=f"Commission Refund for Cancelled Order {self.order_number}",
                            ref_doctype="Order",
                            ref_name=self.name
                        )
                    except Exception as e:
                        frappe.log_error(f"Commission refund failed for {self.name}: {str(e)}", "Refund Error")





