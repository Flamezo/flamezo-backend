# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

MAX_LIVE_HOT_DROPS_PER_OUTLET = 3


class HotDrop(Document):
	def validate(self):
		if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
			frappe.throw("Hot Drop end time must be after its start time.")

		# Backstop cap enforcement — the API layer (create_hot_drop) is the
		# primary place this is checked (better error messaging for the
		# merchant app), but this validate() catches anything that bypasses
		# the API (Desk UI, data import, etc.) so the cap can never be
		# silently violated. "Occupies a slot" = active and not yet ended,
		# whether it's live right now or still upcoming.
		if self.is_active and self.ends_at and self.ends_at > now_datetime():
			count = frappe.db.count(
				"Hot Drop",
				{
					"restaurant": self.restaurant,
					"is_active": 1,
					"ends_at": [">", now_datetime()],
					"name": ["!=", self.name or ""],
				},
			)
			if count >= MAX_LIVE_HOT_DROPS_PER_OUTLET:
				frappe.throw(
					f"This outlet already has {MAX_LIVE_HOT_DROPS_PER_OUTLET} active/upcoming Hot Drops — "
					"end or wait for one to finish before posting another."
				)
