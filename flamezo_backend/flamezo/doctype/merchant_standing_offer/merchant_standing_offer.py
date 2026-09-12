# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Merchant Standing Offer — creator-marketplace-blueprint.html §17. Pure
validation, no network IO — money/deal creation lives in
api/standing_offers.py, same discipline as every other doctype
controller in this module (collab_deal.py, collab_dispute.py).
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document

VALID_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class MerchantStandingOffer(Document):
	def validate(self):
		self._validate_reward()
		self._validate_days()
		self._validate_time_window()

	def _validate_reward(self):
		if self.reward_type in ("free_item", "both") and not self.reward_item:
			frappe.throw(_("reward_item is required when reward_type includes a free item."), frappe.ValidationError)
		if self.reward_value_inr is None or self.reward_value_inr <= 0:
			frappe.throw(_("reward_value_inr must be positive — it's what feeds 194R barter tracking."), frappe.ValidationError)

	def _validate_days(self):
		if not self.valid_days_of_week:
			return
		days = [d.strip() for d in self.valid_days_of_week.split(",") if d.strip()]
		bad = [d for d in days if d not in VALID_DAYS]
		if bad:
			frappe.throw(_("Invalid day(s) in valid_days_of_week: {0}. Use Mon/Tue/Wed/Thu/Fri/Sat/Sun.").format(", ".join(bad)), frappe.ValidationError)

	def _validate_time_window(self):
		for label, value in (("valid_time_start", self.valid_time_start), ("valid_time_end", self.valid_time_end)):
			if value and not _HHMM.match(value):
				frappe.throw(_("{0} must be \"HH:MM\" 24h format, got {1!r}.").format(label, value), frappe.ValidationError)
		if self.valid_time_start and self.valid_time_end and self.valid_time_start == self.valid_time_end:
			frappe.throw(_("valid_time_start and valid_time_end can't be identical — that's a zero-width window."), frappe.ValidationError)
