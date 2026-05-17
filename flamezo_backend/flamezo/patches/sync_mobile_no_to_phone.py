"""One-time: Copy mobile_no to phone for Customers where phone is empty.
Use phone as single source of truth; mobile_no (ERPNext) is deprecated for our logic."""
import frappe
from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone


def execute():
	if not frappe.db.has_column("Customer", "phone") or not frappe.db.has_column("Customer", "mobile_no"):
		return
	rows = frappe.db.sql(
		"SELECT name, mobile_no FROM tabCustomer WHERE (phone IS NULL OR phone = '') AND mobile_no IS NOT NULL AND mobile_no != ''",
		as_dict=1,
	)
	for r in rows:
		normalized = normalize_phone(r.mobile_no)
		if normalized and len(normalized) == 10:
			frappe.db.set_value("Customer", r.name, "phone", normalized)
	frappe.db.commit()
