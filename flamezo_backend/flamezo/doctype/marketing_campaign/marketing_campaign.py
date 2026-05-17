# Copyright (c) 2026, Flamezo and contributors

import frappe
from frappe.model.document import Document
from frappe import _


class MarketingCampaign(Document):

    def validate(self):
        """Pre-flight checks before saving."""
        self._check_plan()
        self._check_segment_match()
        self._check_coin_balance()

    def _check_plan(self):
        plan = frappe.db.get_value("Restaurant", self.restaurant, "plan_type")
        if plan != "GOLD":
            frappe.throw(_("Marketing Studio requires a GOLD subscription."))

    def _check_segment_match(self):
        seg_restaurant = frappe.db.get_value("Marketing Segment", self.target_segment, "restaurant")
        if seg_restaurant != self.restaurant:
            frappe.throw(_("The selected segment does not belong to this restaurant."))

    def _check_coin_balance(self):
        """Warn (not hard-block) if coins may be insufficient for the full reach."""
        try:
            settings = frappe.get_single("Flamezo Settings")
            coins_per_msg = self._get_coins_per_msg(settings)
            seg_doc = frappe.get_doc("Marketing Segment", self.target_segment)
            reach = seg_doc.estimated_reach or 0
            estimated_cost = reach * coins_per_msg
            balance = float(frappe.db.get_value("Restaurant", self.restaurant, "coins_balance") or 0)
            if balance < estimated_cost:
                frappe.msgprint(
                    _(f"⚠️ Low Balance: Estimated cost is {estimated_cost:.2f} Coins for ~{reach} recipients, "
                      f"but current balance is {balance:.2f} Coins. Auto-recharge may trigger.")
                )
        except Exception:
            pass  # Non-blocking warning

    def _get_coins_per_msg(self, settings):
        channel = self.channel
        if channel == "WhatsApp":
            return float(getattr(settings, "marketing_whatsapp_coins_per_msg", None) or 1.20)
        elif channel == "SMS":
            return float(getattr(settings, "marketing_sms_coins_per_msg", None) or 0.25)
        elif channel == "Email":
            return float(getattr(settings, "marketing_email_coins_per_msg", None) or 0.05)
        return 0.25
