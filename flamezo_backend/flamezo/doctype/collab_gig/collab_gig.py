# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, get_datetime

VALID_DELIVERABLE_TYPES = {
	"native_chills", "native_club_post", "instagram_reel", "instagram_story", "bundle",
}


class CollabGig(Document):
	def validate(self):
		self._default_city_and_category_from_outlet()
		self._validate_reward()
		self._validate_deliverables()
		self._validate_expiry()

	def _default_city_and_category_from_outlet(self):
		outlet_city, outlet_type = frappe.db.get_value(
			"Outlet", self.outlet, ["city", "outlet_type"]
		) or (None, None)
		if not self.city:
			self.city = outlet_city
		if not self.category:
			self.category = outlet_type
		# A gig's city is a search-index shortcut, not something the
		# merchant should be able to spoof to appear in a city they aren't
		# actually in — always trust the outlet's real city over whatever
		# was passed in.
		if outlet_city:
			self.city = outlet_city

	def _validate_reward(self):
		if not self.barter_allowed and not flt(self.budget_inr):
			frappe.throw(
				_("A gig must offer something — set a budget, allow barter, or both."),
				frappe.ValidationError,
			)
		if flt(self.budget_inr) < 0:
			frappe.throw(_("Budget can't be negative."), frappe.ValidationError)
		if self.barter_allowed and not (self.barter_details or "").strip():
			frappe.throw(_("Describe what's offered for barter."), frappe.ValidationError)

	def _validate_deliverables(self):
		try:
			items = json.loads(self.deliverables_json or "[]")
		except (TypeError, ValueError):
			frappe.throw(_("Deliverables must be valid JSON."), frappe.ValidationError)

		if not isinstance(items, list) or not items:
			frappe.throw(_("List at least one deliverable."), frappe.ValidationError)

		for item in items:
			if not isinstance(item, dict):
				frappe.throw(_("Each deliverable must be an object with type and count."), frappe.ValidationError)
			d_type = item.get("type")
			count = item.get("count")
			if d_type not in VALID_DELIVERABLE_TYPES:
				frappe.throw(_("Unknown deliverable type: {0}").format(d_type), frappe.ValidationError)
			if not isinstance(count, int) or count < 1:
				frappe.throw(_("Deliverable count must be a positive integer."), frappe.ValidationError)

	def _validate_expiry(self):
		if not self.expires_at:
			# Default: 14 days out, matches the API spec's default
			self.expires_at = frappe.utils.add_days(now_datetime(), 14)
			return
		if self.is_new() and get_datetime(self.expires_at) <= now_datetime():
			frappe.throw(_("Expiry must be in the future."), frappe.ValidationError)
