# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
The Collab Dispute state machine (creator-marketplace-blueprint.html
section 08). One active dispute per deal at a time — a second raise
against a deal that already has an open dispute is rejected at the API
layer (api/collab_disputes.py), not here; this controller only enforces
the state machine and SLA timestamps once a dispute record exists.

Like collab_deal.py, this controller does NOT talk to Razorpay or move
money — that's api/collab_disputes.py's job (resolve_dispute). A
doctype controller doing network IO on save is the anti-pattern
collab_deal.py's own docstring already flags; this file follows the
same discipline.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime

EVIDENCE_WINDOW_HOURS = 24
RESOLUTION_WINDOW_HOURS = 48  # from the close of the evidence window, per blueprint §08's SLA table

ALLOWED_TRANSITIONS = {
	"raised": {"evidence", "closed"},
	"evidence": {"review"},
	"review": {"resolved"},
	"resolved": {"appealed", "closed"},
	"appealed": {"closed"},
	"closed": set(),
}


class CollabDispute(Document):
	def validate(self):
		self._validate_deal()
		self._validate_status_transition()
		self._stamp_lifecycle_timestamps()
		self._validate_resolution_fields()
		self._validate_appeal_fields()

	# ── deal linkage ─────────────────────────────────────────────────────

	def _validate_deal(self):
		if not frappe.db.exists("Collab Deal", self.deal):
			frappe.throw(_("Deal not found."), frappe.DoesNotExistError)

	# ── state machine ────────────────────────────────────────────────────

	def _validate_status_transition(self):
		if self.is_new():
			if self.status and self.status != "raised":
				frappe.throw(_("A new dispute must start as 'raised'."), frappe.ValidationError)
			self.status = "raised"
			return

		previous_status = frappe.db.get_value("Collab Dispute", self.name, "status")
		if previous_status == self.status:
			return  # not a transition, some other field changed

		allowed = ALLOWED_TRANSITIONS.get(previous_status, set())
		if self.status not in allowed:
			frappe.throw(
				_("Can't move a dispute from '{0}' to '{1}'.").format(previous_status, self.status),
				frappe.ValidationError,
			)

	def _stamp_lifecycle_timestamps(self):
		now = now_datetime()
		if self.status == "raised" and not self.raised_at:
			self.raised_at = now
			self.evidence_due_at = add_to_date(now, hours=EVIDENCE_WINDOW_HOURS)
		if self.status == "review" and not self.resolution_due_at:
			self.resolution_due_at = add_to_date(now, hours=RESOLUTION_WINDOW_HOURS)
		if self.status == "resolved" and not self.resolved_at:
			self.resolved_at = now
		if self.status == "closed" and not self.closed_at:
			self.closed_at = now
		if self.appeal_requested and not self.appeal_requested_at:
			self.appeal_requested_at = now
		if self.appeal_outcome and not self.appeal_resolved_at:
			self.appeal_resolved_at = now

	# ── resolution consistency ───────────────────────────────────────────

	def _validate_resolution_fields(self):
		if self.status not in ("resolved", "appealed", "closed"):
			return
		if not self.resolution_outcome:
			frappe.throw(_("A resolved dispute needs a resolution_outcome."), frappe.ValidationError)
		if not self.at_fault:
			frappe.throw(_("A resolved dispute needs an at_fault verdict."), frappe.ValidationError)
		if self.resolution_outcome == "split_partial":
			if self.split_creator_pct is None or not (0 < float(self.split_creator_pct) < 100):
				frappe.throw(
					_("split_partial needs split_creator_pct strictly between 0 and 100 — use release_full/refund_full for the 0/100 cases."),
					frappe.ValidationError,
				)
		elif self.split_creator_pct:
			frappe.throw(_("split_creator_pct is only meaningful when resolution_outcome = split_partial."), frappe.ValidationError)

	def _validate_appeal_fields(self):
		if self.status == "appealed" and not self.appeal_requested:
			frappe.throw(_("A dispute can't be 'appealed' without appeal_requested being set first."), frappe.ValidationError)
		if self.appeal_outcome and self.status not in ("appealed", "closed"):
			frappe.throw(_("appeal_outcome can only be set once the dispute is in 'appealed'."), frappe.ValidationError)
