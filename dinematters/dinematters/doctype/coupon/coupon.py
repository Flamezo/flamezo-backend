import frappe
from frappe.model.document import Document


class Coupon(Document):
	def validate(self):
		self.code = self.code.upper().strip() if self.code else self.code
		self._validate_code_unique_per_restaurant()
		self._sanitize_json_fields()

	def before_insert(self):
		self._sanitize_json_fields()

	def before_save(self):
		self._sanitize_json_fields()

	def _sanitize_json_fields(self):
		"""Ensure JSON fields are None (not empty string) — MariaDB JSON CHECK constraint rejects ''."""
		for field in ("required_items", "valid_days_of_week"):
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
			"restaurant": self.restaurant,
			"code": self.code,
		}
		if not self.is_new():
			filters["name"] = ("!=", self.name)

		existing = frappe.db.exists("Coupon", filters)
		if existing:
			frappe.throw(
				f"Coupon code <b>{self.code}</b> already exists for this restaurant.",
				title="Duplicate Coupon Code"
			)
