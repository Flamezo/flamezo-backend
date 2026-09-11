# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Legal status transitions only — a signature is never allowed to move
# "backwards" (e.g. Signed -> Draft) through this doctype. The only way past
# a Signed row is to supersede it with a brand-new Signed Agreement pointing
# back via `supersedes`; the old row itself is never re-opened for editing,
# it only ever flips once to Superseded (metadata-only: `superseded_by`).
_ALLOWED_TRANSITIONS = {
	# Draft -> Signed direct is clickwrap only (record_clickwrap_acceptance)
	# — there's no provider round-trip, no Link Sent/Viewed phase, it's
	# recorded and immediately final.
	"Draft": {"Link Sent", "Signed", "Failed"},
	"Link Sent": {"Viewed", "Signed", "Failed", "Expired"},
	"Viewed": {"Signed", "Failed", "Expired"},
	"Signed": {"Superseded"},
	"Failed": set(),
	"Expired": set(),
	"Superseded": set(),
}

# Once a row has ever reached Signed, only these fields may still change on
# a later save (the Superseded transition + linking to the row that
# replaced it). Everything else — the signed PDF, hashes, signer details,
# the commercial-terms snapshot — is frozen forever from that point on.
_MUTABLE_AFTER_SIGNED = {"status", "superseded_by", "modified", "modified_by"}


class SignedAgreement(Document):
	def before_save(self):
		if not self.is_new():
			self._enforce_transition()

	def _enforce_transition(self):
		before = frappe.db.get_value("Signed Agreement", self.name, "status")
		if before == "Signed":
			self._enforce_immutable_after_signed()
		if before == self.status:
			return
		allowed = _ALLOWED_TRANSITIONS.get(before, set())
		if self.status not in allowed:
			frappe.throw(
				_("Signed Agreement {0} cannot move from {1} to {2}.").format(
					self.name, before, self.status
				)
			)

	def _enforce_immutable_after_signed(self):
		before_doc = frappe.get_doc("Signed Agreement", self.name)
		for fieldname in before_doc.as_dict():
			if fieldname in _MUTABLE_AFTER_SIGNED or fieldname.startswith("_"):
				continue
			if self.get(fieldname) != before_doc.get(fieldname):
				frappe.throw(
					_(
						"Signed Agreement {0} is already Signed and its content is "
						"immutable. Field '{1}' cannot change. Create a new Signed "
						"Agreement with `supersedes` set to this one instead."
					).format(self.name, fieldname)
				)
