# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OTPVerificationLog(Document):
	"""Log of OTP send/verify attempts. Read-only for auditing."""

	pass
