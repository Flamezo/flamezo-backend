import frappe


def execute():
	"""Stage 1 of the Restaurant -> Outlet internal rename: the core doctype
	itself. Uses Frappe's built-in doctype rename (frappe.rename_doc against
	the "DocType" doctype), which performs a real `RENAME TABLE` — not a
	drop-and-recreate — so every existing row (every merchant's real data) is
	preserved, and cascades the rename to every dependent Link/Table field
	across the app automatically.

	Runs in [pre_model_sync], i.e. BEFORE the new `Outlet` doctype JSON is
	synced into the DB. This ordering matters: if the doctype sync ran first,
	it would just create a brand-new empty `Outlet` table and leave the real
	`tabRestaurant` table orphaned with all its data stranded. Running the
	rename first means the table/meta are already `Outlet` by the time sync
	runs, so sync just reconciles field differences on the (correctly
	renamed, data-intact) table.

	Guarded to be a no-op if `Restaurant` doesn't exist (already renamed) or
	`Outlet` already exists (rename already happened). Safe to re-run.
	"""
	if not frappe.db.exists("DocType", "Restaurant"):
		frappe.logger().info("[rename_restaurant_doctype_to_outlet] Restaurant doctype not found — already renamed, skipping")
		return

	if frappe.db.exists("DocType", "Outlet"):
		frappe.logger().info("[rename_restaurant_doctype_to_outlet] Outlet doctype already exists — skipping")
		return

	frappe.rename_doc("DocType", "Restaurant", "Outlet", force=True)
	frappe.db.commit()
	frappe.logger().info("[rename_restaurant_doctype_to_outlet] Restaurant -> Outlet renamed (table + meta + dependent Link fields)")
