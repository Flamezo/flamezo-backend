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

		# Validate inline viewer coupon fields
		if self.viewer_coupon_code:
			if not self.viewer_discount_type:
				frappe.throw(_("Discount Type is required when a viewer coupon code is set."))
			if not flt(self.viewer_discount_value) > 0:
				frappe.throw(_("Discount Value must be greater than 0."))
			if self.viewer_discount_type == "percent":
				# Max Discount Cap is OPTIONAL: leaving it blank/0 means the full
				# percentage applies to whatever the bill is (uncapped). A cap only
				# takes effect when the merchant actually sets one.
				if flt(self.viewer_discount_cap) < 0:
					frappe.throw(_("Max Discount Cap (₹) cannot be negative."))
				if flt(self.viewer_discount_value) > 100:
					frappe.throw(_("Percent discount cannot exceed 100%."))

		# Auto-generate offer label if not provided
		if self.viewer_coupon_code and not self.viewer_coupon_description:
			if self.viewer_discount_type == "flat":
				self.viewer_coupon_description = f"₹{int(flt(self.viewer_discount_value))} off on your next visit"
			elif self.viewer_discount_type == "percent":
				# Only mention a ceiling when one is actually set (cap is optional).
				cap = flt(self.viewer_discount_cap)
				self.viewer_coupon_description = (
					f"{int(flt(self.viewer_discount_value))}% off"
					+ (f" (up to ₹{int(cap)})" if cap > 0 else " on your next visit")
				)

		# next_visit_coupon must belong to this restaurant if set
		if self.next_visit_coupon:
			coupon_restaurant = frappe.db.get_value("Coupon", self.next_visit_coupon, "restaurant")
			if coupon_restaurant != self.restaurant:
				frappe.throw(_("Next-Visit Coupon does not belong to this outlet."))

	def on_update(self):
		self._sync_ugc_coupon()

	def after_insert(self):
		self._sync_ugc_coupon()

	def _sync_ugc_coupon(self):
		"""
		Create or update a hidden Coupon doc for checkout integration.
		The coupon is tagged category='ugc_exclusive' so it's filtered
		out of the general Coupon management list.
		If viewer coupon fields are cleared, deactivate the hidden doc.
		"""
		if not self.viewer_coupon_code or not self.viewer_discount_type:
			# Deactivate hidden coupon if coupon is removed
			if self._ugc_coupon_ref and frappe.db.exists("Coupon", self._ugc_coupon_ref):
				frappe.db.set_value("Coupon", self._ugc_coupon_ref, "is_active", 0)
			return

		coupon_fields = {
			"restaurant": self.restaurant,
			"offer_type": "coupon",
			"code": self.viewer_coupon_code.upper().strip(),
			"discount_type": self.viewer_discount_type,
			"discount_value": flt(self.viewer_discount_value),
			"max_discount_cap": flt(self.viewer_discount_cap or 0),
			"description": self.viewer_coupon_description or "",
			"category": "ugc_exclusive",
			"is_active": 1,
		}

		ref = self._ugc_coupon_ref
		if ref and frappe.db.exists("Coupon", ref):
			coupon = frappe.get_doc("Coupon", ref)
			for k, v in coupon_fields.items():
				coupon.set(k, v)
			coupon.save(ignore_permissions=True)
		else:
			coupon = frappe.get_doc({"doctype": "Coupon", **coupon_fields})
			coupon.insert(ignore_permissions=True)
			frappe.db.set_value(
				"UGC Cashback Config", self.name, "_ugc_coupon_ref", coupon.name, update_modified=False
			)

		frappe.db.commit()
