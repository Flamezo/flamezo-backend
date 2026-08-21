import frappe


# Stage 3a of the Restaurant -> Outlet internal rename: the 3 merchant-facing
# Roles. Renaming a Role via frappe.rename_doc is a standard, safe Frappe
# operation — it's just a Role document rename, which cascades to every
# `Has Role` assignment (real staff/merchant logins) and every DocPerm.role
# reference automatically, no separate migration needed for those.
_RENAMES = [
	("Restaurant Admin", "Outlet Admin"),
	("Restaurant Manager", "Outlet Manager"),
	("Restaurant Staff", "Outlet Staff"),
]


def execute():
	"""Runs in [pre_model_sync], before the renamed doctype JSONs (with their
	updated "role": "Outlet Admin" etc. permission blocks) are synced — same
	ordering reason as the doctype-rename patches: rename the live Role first
	so sync reconciles against the already-correct name instead of creating a
	stray unused "Outlet Admin" Role while real users are still assigned the
	old "Restaurant Admin" one.

	Each rename is independently guarded (no-op if already applied or if the
	old Role doesn't exist), safe to re-run.
	"""
	for old, new in _RENAMES:
		if not frappe.db.exists("Role", old):
			frappe.logger().info(f"[rename_restaurant_roles_to_outlet] Role '{old}' not found — already renamed, skipping")
			continue
		if frappe.db.exists("Role", new):
			frappe.logger().info(f"[rename_restaurant_roles_to_outlet] Role '{new}' already exists — skipping")
			continue
		frappe.rename_doc("Role", old, new, force=True)
		frappe.db.commit()
		frappe.logger().info(f"[rename_restaurant_roles_to_outlet] Role '{old}' -> '{new}' renamed")
