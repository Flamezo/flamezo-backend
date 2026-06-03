# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class UGCCashbackConfig(Document):
	def validate(self):
		# Clamp sane ranges so a mis-configured form can never break the credit math.
		if cint(self.cashback_percent_cap) <= 0:
			self.cashback_percent_cap = 100
		self.cashback_percent_cap = min(cint(self.cashback_percent_cap), 100)

		if flt(self.ai_confidence_threshold) < 0 or flt(self.ai_confidence_threshold) > 1:
			self.ai_confidence_threshold = 0.85

		if cint(self.proof_window_hours) <= 0:
			self.proof_window_hours = 48

		if cint(self.max_per_customer_per_month) < 0:
			self.max_per_customer_per_month = 0

		if cint(self.absolute_cap_coins) < 0:
			self.absolute_cap_coins = 0

		# Linked coupons must belong to this restaurant.
		for field in ("coupon_for_viewers", "next_visit_coupon"):
			coupon = self.get(field)
			if coupon:
				coupon_restaurant = frappe.db.get_value("Coupon", coupon, "restaurant")
				if coupon_restaurant != self.restaurant:
					frappe.throw(
						_("Coupon {0} does not belong to this restaurant.").format(coupon)
					)
