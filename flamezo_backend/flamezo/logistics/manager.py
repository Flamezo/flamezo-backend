import frappe
from frappe.utils import flt, cint
from .borzo import BorzoProvider
from .flash import FlashProvider

class LogisticsManager:
    def __init__(self, restaurant_name):
        self.restaurant = frappe.get_doc("Restaurant", restaurant_name)
        self.settings = frappe.get_single("Flamezo Settings")

        # Determine provider
        provider_name = self.restaurant.preferred_logistics_provider or "Flash"
        if provider_name == "Borzo":
            self.provider = BorzoProvider(self.settings)
        elif provider_name == "Flash":
            self.provider = FlashProvider(self.settings)
        else:
            # "Self" — restaurant manages its own riders. No external API.
            self.provider = None

    @property
    def is_self_delivery(self):
        return self.provider is None

    def get_quote(self, order_details):
        """
        Gets a combined quote including Courier Fee + Restaurant Markup + Platform Fee.
        For Self delivery: courier_fee = 0, no platform_fee coin deduction.
        """
        if self.is_self_delivery:
            # Self delivery: restaurant sets their own flat delivery charge
            delivery_fee = flt(self.restaurant.default_delivery_fee or 0)
            return {
                "success": True,
                "courier_fee": 0,
                "markup": delivery_fee, # Legacy: For self, the fee IS the markup/revenue
                "platform_fee": 0,          # No platform cut for self delivery
                "delivery_fee": delivery_fee, # What the customer pays for delivery
                "eta_mins": self.restaurant.estimated_prep_time or 30,
                "provider": "Self"
            }

        res = self.provider.calculate_quote(self.restaurant, order_details)
        if not res.get("success"):
            return res

        base_fee = flt(res.get("delivery_fee") or 0)

        # 1. Platform Convenience Fee (Flamezo Revenue)
        platform_fee = flt(self.settings.platform_delivery_convenience_fee or 0)

        # 2. Restaurant Markup (Merchant Profit)
        markup = 0
        markup_type = self.restaurant.delivery_markup_type or "Fixed"
        markup_val = flt(self.restaurant.delivery_markup_value or 0)

        if markup_type == "Percentage":
            markup = base_fee * (markup_val / 100.0)
        else:
            markup = markup_val

        total_delivery_fee = base_fee + markup + platform_fee

        return {
            "success": True,
            "courier_fee": base_fee,
            "markup": markup,
            "platform_fee": platform_fee,
            "delivery_fee": total_delivery_fee,  # Total fee charged to customer
            "eta_mins": res.get("eta_mins"),
            "provider": res.get("provider") or self.restaurant.preferred_logistics_provider
        }

    def book_delivery(self, order):
        """
        Books a delivery and persists the fee stack.

        Self delivery:   No external API call. No coins deducted. Returns immediately.
        Borzo / Flash:   Calls provider API, then deducts (courier_fee + platform_fee)
                         from the restaurant's Flamezo Coin wallet.

        The Merchant Markup is NOT deducted via coins — it's the restaurant's profit
        earned directly from the customer payment.
        """
        # ── Self / Manual Delivery ─────────────────────────────────────────────
        if self.is_self_delivery:
            delivery_charge = flt(self.restaurant.default_delivery_fee or 0)
            return {
                "success": True,
                "delivery_id": f"SELF-{order.name}",
                "status": "ACCEPTED",
                "tracking_url": None,
                "delivery_fee": delivery_charge,
                "logistics_platform_fee": 0,
                "provider": "Self",
                "note": "Self delivery — managed by restaurant's own rider."
            }

        # ── Borzo / Flash ──────────────────────────────────────────────────────
        res = self.provider.create_order(self.restaurant, order)
        if not res.get("success"):
            return res

        # Fetch the quote again to get the authoritative fee stack
        quote = self.get_quote({
            "address": order.delivery_address,
            "latitude": order.delivery_latitude,
            "longitude": order.delivery_longitude,
            "total": order.total,
            "items": order.get("order_items")
        })

        courier_fee = flt(res.get("delivery_fee") or (quote.get("courier_fee") if quote.get("success") else 0))
        platform_fee = flt(self.settings.platform_delivery_convenience_fee or 5)
        total_deduction = courier_fee + platform_fee

        if quote.get("success"):
            res["logistics_platform_fee"] = platform_fee
            res["delivery_fee"] = quote.get("delivery_fee")  # Full stacked fee

        # Deduct coins from the restaurant's wallet
        if total_deduction > 0:
            try:
                from flamezo_backend.flamezo.api.coin_billing import deduct_coins
                deduct_coins(
                    restaurant=self.restaurant.name,
                    amount=total_deduction,
                    type="Delivery Fee",
                    description=(
                        f"Delivery via {self.restaurant.preferred_logistics_provider} — "
                        f"Courier: ₹{courier_fee:.2f} + Platform: ₹{platform_fee:.2f} | "
                        f"Order: {order.name}"
                    ),
                    ref_doctype="Order",
                    ref_name=order.name
                )
            except Exception as coin_err:
                # Log but don't block the delivery — coins can be reconciled
                frappe.log_error(
                    f"Coin deduction failed for {order.name}: {str(coin_err)}",
                    "Logistics Coin Error"
                )

        return res

    def cancel_delivery(self, delivery_id):
        if self.is_self_delivery:
            return {"success": True, "message": "Self delivery cancelled."}
        return self.provider.cancel_order(delivery_id)

    def track_delivery(self, delivery_id):
        if self.is_self_delivery:
            return {"success": True, "status": "Self-Managed", "message": "Self delivery is managed locally."}
        return self.provider.track_order(delivery_id)

    def verify_webhook(self, provider_name, data, signature):
        # Allow cross-verification if provider is specified
        if provider_name == "borzo":
            return BorzoProvider(self.settings).verify_webhook(data, signature)
        elif provider_name == "flash":
            return FlashProvider(self.settings).verify_webhook(data, signature)
        return False
