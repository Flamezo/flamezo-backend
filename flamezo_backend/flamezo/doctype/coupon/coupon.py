import frappe
from frappe.model.document import Document


class Coupon(Document):
	def validate(self):
		self.code = self.code.upper().strip() if self.code else self.code
		self._validate_code_unique_per_restaurant()
		self._sanitize_json_fields()
		self._validate_discount_values()

	def before_insert(self):
		self._sanitize_json_fields()
		self._validate_discount_values()

	def before_save(self):
		self._sanitize_json_fields()
		self._validate_discount_values()

	def on_trash(self):
		"""Offer Claim.coupon is a required Link, so any claim on this coupon blocks
		deletion. Remove the claim records first so a merchant can delete the offer.
		Runs before Frappe's link-integrity check, so the delete then succeeds."""
		frappe.db.delete("Offer Claim", {"coupon": self.name})

	def _sanitize_json_fields(self):
		"""Ensure JSON fields are None (not empty string) — MariaDB JSON CHECK constraint rejects ''."""
		for field in ("required_items", "valid_days_of_week", "item_pool"):
			val = getattr(self, field, None)
			if val == "" or val == "null" or val == "[]":
				setattr(self, field, None)
		# Frappe unconditionally auto-fills every Time field with nowtime() for new docs.
		# Clear them so the time-of-day gate only fires when explicitly provided.
		if self.is_new():
			submitted_doc = frappe.local.form_dict.get("doc") if frappe.local.form_dict else None
			if isinstance(submitted_doc, str):
				import json as _json
				try: submitted_doc = _json.loads(submitted_doc)
				except Exception: submitted_doc = {}
			for field in ("valid_time_start", "valid_time_end"):
				explicitly_set = submitted_doc.get(field) if submitted_doc else None
				if not explicitly_set:
					setattr(self, field, None)

	def _validate_code_unique_per_restaurant(self):
		"""Ensure the coupon code is unique within the same restaurant (not globally)."""
		filters = {
			"outlet": self.outlet,
			"code": self.code,
		}
		if not self.is_new():
			filters["name"] = ("!=", self.name)

		existing = frappe.db.exists("Coupon", filters)
		if existing:
			frappe.throw(
				f"Coupon code <b>{self.code}</b> already exists for this outlet.",
				title="Duplicate Coupon Code"
			)

	def _validate_discount_values(self):
		from frappe.utils import flt
		# A google-review free-dish is served physically (no ₹ off the bill), so it
		# legitimately has a zero discount value — skip the > 0 requirement for it.
		is_free_dish = self.offer_type == "google_review" and (self.review_reward_type or "cashback") == "free_dish"
		if self.offer_type != "combo":
			if not is_free_dish and flt(self.discount_value) <= 0:
				frappe.throw(
					frappe._("Discount Value must be greater than zero for flat or percentage discounts."),
					title=frappe._("Invalid Discount Value")
				)
		else:
			self.discount_type = "flat"

