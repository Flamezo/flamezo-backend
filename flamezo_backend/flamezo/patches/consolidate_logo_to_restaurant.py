import frappe


def execute():
	"""Consolidate the two competing logo fields onto Restaurant.logo (the
	single source of truth) and drop the now-removed Restaurant Config.logo
	column. Restaurant Config.logo was an older, separate write path — a real
	slice of outlets (e.g. Arabista, Sync, Pops Cafe) only ever had their logo
	written there and never got backfilled onto Restaurant.logo, which is why
	the map/discovery feed showed a blank pin for them despite the merchant
	having a real uploaded logo. See onboarding.backfill_restaurant_logo_from_config
	for the original one-off version of this backfill — this patch supersedes
	it and additionally drops the field. Only fills Restaurant.logo when it's
	currently empty; never overwrites. Safe to re-run.
	"""
	if not frappe.db.table_exists("Outlet Config") or not frappe.db.has_column("Outlet Config", "logo"):
		return

	rows = frappe.db.sql(
		"""
		SELECT r.name AS restaurant, c.logo AS config_logo
		FROM `tabOutlet` r
		JOIN `tabOutlet Config` c ON c.restaurant = r.name
		WHERE (r.logo IS NULL OR r.logo = '')
		  AND c.logo IS NOT NULL AND c.logo != ''
		""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value("Outlet", row.restaurant, "logo", row.config_logo, update_modified=False)
	frappe.db.commit()
	frappe.logger().info(f"[consolidate_logo_to_restaurant] backfilled {len(rows)} outlet(s)")

	frappe.db.sql_ddl("ALTER TABLE `tabOutlet Config` DROP COLUMN `logo`")
	frappe.db.commit()
	frappe.logger().info("[consolidate_logo_to_restaurant] dropped Restaurant Config.logo column")
