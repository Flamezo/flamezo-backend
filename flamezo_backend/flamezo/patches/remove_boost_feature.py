import frappe


def execute():
	"""Remove the Boost (Meta ads) feature entirely.

	Zero Boost Campaigns were ever created in production since it shipped
	(May 2026) — dropped in favor of the creator marketplace. The doctype
	JSON/Python files are already deleted from the app; this patch cleans up
	what bench migrate's doctype sync doesn't do on its own (it never deletes
	a DocType whose source files were removed, it just leaves it orphaned).

	frappe.delete_doc("DocType", ...) drops the table and cleans up the
	associated meta (permissions, reports, etc.) properly. Safe to re-run —
	skips any doctype that's already gone.
	"""
	for doctype in ("Boost Campaign", "Boost Coupon Redemption", "Boost Prerequisite Check", "Boost Template"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=True)
			frappe.logger().info(f"[remove_boost_feature] deleted DocType {doctype}")

		# delete_doc() removes the DocType meta record but does not itself drop
		# the underlying table — do that explicitly so no orphaned table lingers.
		table = f"tab{doctype}"
		if frappe.db.table_exists(doctype):
			frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")
			frappe.logger().info(f"[remove_boost_feature] dropped table {table}")

	frappe.db.commit()
