# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class EscrowTransaction(Document):
	def validate(self):
		self._validate_amounts()
		self._stamp_state_timestamp()

	def _validate_amounts(self):
		if flt(self.platform_fee_inr) + flt(self.creator_net_inr) - flt(self.amount_inr) > 0.01:
			frappe.throw(
				_("platform_fee_inr + creator_net_inr must equal amount_inr."),
				frappe.ValidationError,
			)
		if flt(self.amount_inr) <= 0:
			frappe.throw(_("amount_inr must be positive."), frappe.ValidationError)

	def _stamp_state_timestamp(self):
		if self.state == "held" and not self.held_at:
			self.held_at = now_datetime()
		if self.state == "released" and not self.released_at:
			self.released_at = now_datetime()
