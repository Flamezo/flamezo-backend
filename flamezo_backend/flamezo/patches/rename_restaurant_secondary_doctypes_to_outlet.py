import frappe


# Stage 2 of the Restaurant -> Outlet internal rename: the 7 secondary
# doctypes. Same mechanism as rename_restaurant_doctype_to_outlet (Stage 1)
# — frappe.rename_doc against "DocType" does a real RENAME TABLE, not
# drop-and-recreate, cascading to dependent Link fields automatically.
_RENAMES = [
	("Restaurant Config", "Outlet Config"),
	("Restaurant Onboarding", "Outlet Onboarding"),
	("Restaurant Table", "Outlet Table"),
	("Restaurant User", "Outlet User"),
	("Restaurant Gallery Item", "Outlet Gallery Item"),
	("Restaurant Loyalty Entry", "Outlet Loyalty Entry"),
	("Restaurant Loyalty Config", "Outlet Loyalty Config"),
]


def execute():
	"""Runs in [pre_model_sync], before the renamed doctype JSONs are synced —
	same ordering reason as Stage 1: rename first so sync reconciles fields on
	the already-correctly-named (data-intact) table, instead of creating a
	fresh empty table and orphaning the real one.

	Each rename is independently guarded (no-op if already applied), so this
	is safe to re-run and safe even if only some of the 7 have been renamed
	yet (e.g. a partial/interrupted previous run).
	"""
	for old, new in _RENAMES:
		if not frappe.db.exists("DocType", old):
			frappe.logger().info(f"[rename_restaurant_secondary_doctypes_to_outlet] {old} not found — already renamed, skipping")
			continue
		if frappe.db.exists("DocType", new):
			frappe.logger().info(f"[rename_restaurant_secondary_doctypes_to_outlet] {new} already exists — skipping")
			continue
		frappe.rename_doc("DocType", old, new, force=True)
		frappe.db.commit()
		frappe.logger().info(f"[rename_restaurant_secondary_doctypes_to_outlet] {old} -> {new} renamed")
