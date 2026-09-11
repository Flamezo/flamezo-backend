# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CreatorRateCard(Document):
	def validate(self):
		self._enforce_uniqueness()
		self._enforce_pricing_makes_sense()

	def _enforce_uniqueness(self):
		"""One rate card per (creator, deliverable_type) — the API layer
		upserts against this, but the doctype itself must not allow a
		second row to slip in via any other path (desk, import, a future
		endpoint that forgets to check first)."""
		existing = frappe.db.exists(
			"Creator Rate Card",
			{
				"creator": self.creator,
				"deliverable_type": self.deliverable_type,
				"name": ["!=", self.name or ""],
			},
		)
		if existing:
			frappe.throw(
				_("A rate card for {0} already exists for this creator — update it instead of creating a new one.").format(
					self.deliverable_type
				),
				frappe.ValidationError,
			)

	def _enforce_pricing_makes_sense(self):
		"""A rate card that's neither priced nor barter-eligible is
		meaningless — it would silently disappear from every merchant-
		facing filter (price_band, barter_only) with no signal why."""
		if not self.accepts_barter and not frappe.utils.flt(self.price_inr):
			frappe.throw(
				_("Set a price, enable barter, or both — a rate card can't be neither."),
				frappe.ValidationError,
			)
		if self.accepts_barter and frappe.utils.flt(self.barter_min_value_inr) < 0:
			frappe.throw(_("Minimum barter value can't be negative."), frappe.ValidationError)
		if frappe.utils.flt(self.price_inr) < 0:
			frappe.throw(_("Price can't be negative."), frappe.ValidationError)
