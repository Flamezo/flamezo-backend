# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document


class AgreementTemplate(Document):
	def validate(self):
		self._enforce_single_active()
		self._compute_file_hash()

	def _enforce_single_active(self):
		"""Only one active template per agreement_type — the signing flow
		always resolves "the active template for this type" with no
		ambiguity. Activating a new version does NOT retroactively touch
		Signed Agreement rows already tied to the previous version; it only
		changes what NEW signing requests render."""
		if not self.is_active:
			return
		others = frappe.get_all(
			"Agreement Template",
			filters={
				"agreement_type": self.agreement_type,
				"is_active": 1,
				"name": ["!=", self.name],
			},
			pluck="name",
		)
		for other in others:
			frappe.db.set_value("Agreement Template", other, "is_active", 0)
			frappe.db.set_value("Agreement Template", other, "superseded_by", self.name)

	def _compute_file_hash(self):
		if not self.template_file:
			return
		try:
			file_doc = frappe.get_doc("File", {"file_url": self.template_file})
			content = file_doc.get_content()
			if isinstance(content, str):
				content = content.encode("utf-8")
			self.template_file_hash = hashlib.sha256(content).hexdigest()
		except Exception:
			# Non-fatal — hash is a defence-in-depth integrity check, not a
			# gate on saving the template itself.
			frappe.log_error(
				f"Could not hash Agreement Template file for {self.name}",
				"agreement_template.hash",
			)
