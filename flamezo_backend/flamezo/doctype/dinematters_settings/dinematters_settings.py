# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FlamezoSettings(Document):
	"""Site-wide settings for Flamezo (OTP, etc.). Single doc."""

	def on_update(self):
		"""Only sync SMTP config when Hostinger credentials actually changed."""
		doc_before = self.get_doc_before_save()
		
		email_changed = not doc_before or doc_before.get("hostinger_email") != self.hostinger_email
		password_changed = not doc_before or self.has_value_changed("hostinger_password")

		if email_changed or password_changed:
			from flamezo_backend.flamezo.utils.email_setup import setup_hostinger_email
			setup_hostinger_email()

