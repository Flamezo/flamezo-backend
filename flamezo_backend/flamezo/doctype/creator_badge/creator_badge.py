# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Earned-badge history (creator-marketplace-blueprint.html §07, Phase 5).
Rows are only ever written by utils/creator_badges.sync_creator_badge —
this controller enforces the "at most one is_current=1 row per creator"
invariant at the DB layer regardless of what writes here later, same
defense-in-depth discipline as collab_deal.py/collab_dispute.py.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class CreatorBadge(Document):
	def validate(self):
		if not self.earned_at:
			self.earned_at = now_datetime()
		if self.is_current:
			self._enforce_single_current()

	def _enforce_single_current(self):
		other_current = frappe.db.exists(
			"Creator Badge", {"creator": self.creator, "is_current": 1, "name": ["!=", self.name or ""]}
		)
		if other_current:
			frappe.throw(
				_("{0} already has a current badge ({1}) — supersede it first.").format(self.creator, other_current),
				frappe.ValidationError,
			)
