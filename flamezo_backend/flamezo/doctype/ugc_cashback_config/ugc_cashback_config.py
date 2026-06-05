# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class UGCCashbackConfig(Document):
	def validate(self):
		if cint(self.cashback_percent_cap) <= 0 or cint(self.cashback_percent_cap) > 100:
			frappe.throw(_("Cashback Percent Cap must be between 1 and 100."))

		if flt(self.ai_confidence_threshold) < 0 or flt(self.ai_confidence_threshold) > 1:
			frappe.throw(_("AI Confidence Threshold must be between 0.0 and 1.0."))

		if cint(self.proof_window_hours) <= 0:
			frappe.throw(_("Proof Window Hours must be greater than 0."))

		if cint(self.max_per_customer_per_month) < 0:
			frappe.throw(_("Max Claims Per Customer must be 0 or greater."))

		if cint(self.absolute_cap_coins) < 0:
			frappe.throw(_("Absolute Cashback Cap must be 0 (disabled) or a positive amount."))

		# Linked coupons must belong to this restaurant.
		for field in ("coupon_for_viewers", "next_visit_coupon"):
			coupon = self.get(field)
			if coupon:
				coupon_restaurant = frappe.db.get_value("Coupon", coupon, "restaurant")
				if coupon_restaurant != self.restaurant:
					frappe.throw(
						_("Coupon {0} does not belong to this restaurant.").format(coupon)
					)
