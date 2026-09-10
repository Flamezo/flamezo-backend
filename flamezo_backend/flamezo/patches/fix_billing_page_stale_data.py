import frappe


def execute():
	"""Fix two real bugs found on the merchant Billing & Subscription page.

	1. deferred_plan_type / plan_change_date: leftover from before the
	   single-tier model (update_subscription_plan is now a retired no-op —
	   nothing in the codebase writes these fields anymore). 65/65 outlets that
	   had any value here were stuck on deferred_plan_type='GOLD' with
	   plan_change_date=NULL, and the frontend rendered `new Date(null)` for
	   that null date — the Unix epoch, shown to merchants as
	   "Effective 01/01/1970". The whole "plan switch scheduled" banner (both
	   on this page and the global notification bar) is dead-feature UI and
	   has been removed; this patch drops the columns entirely.

	2. auto_recharge_threshold: the doctype default was 200, but the UI (and
	   webhooks.py's fallback) has always assumed a 300 minimum — every one of
	   71 outlets, having never touched this setting, sat below the platform's
	   own stated minimum. Bumps any value below the new minimum up to it.
	"""
	for doctype, column in (("Outlet", "deferred_plan_type"), ("Outlet", "plan_change_date")):
		if frappe.db.has_column(doctype, column):
			frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{column}`")
			frappe.logger().info(f"[fix_billing_page_stale_data] dropped {doctype}.{column}")

	updated = frappe.db.sql(
		"UPDATE `tabOutlet` SET auto_recharge_threshold = 300 WHERE auto_recharge_threshold < 300"
	)
	frappe.db.commit()
	frappe.logger().info(
		f"[fix_billing_page_stale_data] bumped auto_recharge_threshold to 300 where below minimum"
	)
