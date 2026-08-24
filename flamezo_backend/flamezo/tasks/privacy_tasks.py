# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
DPDP Act 2023 compliance — scheduled data retention enforcement.
Runs daily at 04:00 IST via hooks.py scheduler_events.
"""

import frappe
from frappe.utils import add_days, today


def purge_old_otp_logs():
	"""
	Delete OTP Verification Log records older than 90 days.
	Privacy Policy retention: 90 days from generation (DPDP Act 2023).
	"""
	try:
		cutoff = add_days(today(), -90)
		old_logs = frappe.get_all(
			"OTP Verification Log",
			filters={"creation": ["<", cutoff]},
			fields=["name"],
			limit=5000,
		)
		if not old_logs:
			return

		for log in old_logs:
			frappe.delete_doc("OTP Verification Log", log.name, ignore_permissions=True, force=True)

		frappe.db.commit()
		frappe.logger().info(f"[DPDP] Purged {len(old_logs)} OTP logs older than 90 days")
	except Exception as e:
		frappe.log_error(f"purge_old_otp_logs: {e}", "DPDP_Privacy_Tasks")
