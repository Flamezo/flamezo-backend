import frappe


def execute():
	"""Drop the stale has_no_media column and backfill orphaned media links.

	Background: has_no_media was a stored flag on Menu Product / Extracted Dish
	that could go stale (e.g. after an AI Image Generation silently failed to
	auto-apply). Both doctypes' APIs now compute "has media" live from the
	actual resolved media list instead of trusting this column, so it's dead
	weight — drop it outright.

	Also backfills two real incidents found via prod investigation:
	  1. Madhuram Garden Restaurant: 118 AI Image Generation records stuck in
	     Pending_Upload since the Azure -> AWS migration — reset + re-enqueued
	     via the existing retry_failed_image_generations() worker path.
	  2. Platform-wide: AI Image Generation records marked Completed whose
	     auto-apply-to-product step failed silently (status was set to
	     Completed before the fragile apply_to_product() call), leaving the
	     enhanced image generated but never linked to the product. Re-applies
	     any such orphan whose Menu Product still exists.

	Safe to re-run: column drops are guarded by existence checks, and the
	backfill only touches Completed generations with zero linked Product Media
	rows (already-linked ones are untouched).
	"""
	from flamezo_backend.flamezo.api.ai_media import apply_to_product, retry_failed_image_generations

	# 1. Drop the has_no_media column from both doctypes, if present.
	for doctype, table in (("Menu Product", "tabMenu Product"), ("Extracted Dish", "tabExtracted Dish")):
		if frappe.db.has_column(table, "has_no_media"):
			frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `has_no_media`")
			frappe.logger().info(f"[remove_has_no_media_and_backfill_media] dropped has_no_media from {table}")

	# 2. Madhuram: reset + re-enqueue the Pending_Upload backlog stuck since the
	# Azure -> AWS migration.
	if frappe.db.exists("Outlet", "madhuram-garden-restaurant"):
		try:
			result = retry_failed_image_generations("madhuram-garden-restaurant")
			frappe.logger().info(
				f"[remove_has_no_media_and_backfill_media] Madhuram retry: "
				f"{result.get('total_retried', 0)} retried, {result.get('total_skipped', 0)} skipped"
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Madhuram media retry failed")

	# 3. Platform-wide: re-apply any Completed generation whose auto-apply
	# silently failed and never linked a Product Media row.
	candidates = frappe.get_all(
		"AI Image Generation",
		filters={
			"status": "Completed",
			"owner_doctype": "Menu Product",
			"enhanced_image_url": ["is", "set"],
		},
		fields=["name", "owner_name"],
	)

	fixed, failed, skipped = 0, 0, 0
	for c in candidates:
		if frappe.db.exists("Product Media", {"parent": c.owner_name}):
			continue
		if not frappe.db.exists("Menu Product", c.owner_name):
			skipped += 1
			continue
		try:
			apply_to_product(c.name)
			fixed += 1
		except Exception:
			failed += 1
			frappe.log_error(frappe.get_traceback(), f"Orphaned media backfill failed for {c.name}")

	frappe.db.commit()
	frappe.logger().info(
		f"[remove_has_no_media_and_backfill_media] platform backfill: "
		f"{fixed} fixed, {failed} failed, {skipped} skipped (product deleted)"
	)
