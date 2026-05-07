import frappe


def execute():
	"""Add a unique composite index on (referral_link, ip_address) in tabReferral Visit.
	This prevents duplicate coin rewards from race conditions when the same IP
	hits a referral link multiple times in rapid succession.
	Idempotent: checks for the index before attempting to create it.
	"""
	try:
		# Check if the index already exists
		existing = frappe.db.sql("""
			SELECT INDEX_NAME
			FROM INFORMATION_SCHEMA.STATISTICS
			WHERE TABLE_SCHEMA = DATABASE()
			  AND TABLE_NAME = 'tabReferral Visit'
			  AND INDEX_NAME = 'uq_referral_visit_link_ip'
		""")
		if existing:
			return  # Already applied

		# Deduplicate existing rows first (keep oldest per referral_link+ip_address pair)
		frappe.db.sql("""
			DELETE rv FROM `tabReferral Visit` rv
			INNER JOIN (
				SELECT referral_link, ip_address, MIN(creation) AS keep_creation
				FROM `tabReferral Visit`
				GROUP BY referral_link, ip_address
				HAVING COUNT(*) > 1
			) dups ON rv.referral_link = dups.referral_link
			         AND rv.ip_address = dups.ip_address
			         AND rv.creation > dups.keep_creation
		""")
		frappe.db.sql("""
			ALTER TABLE `tabReferral Visit`
			ADD UNIQUE INDEX `uq_referral_visit_link_ip` (`referral_link`, `ip_address`)
		""")
		frappe.db.commit()
	except Exception as e:
		# If index creation fails (e.g., existing duplicates in data), log and continue
		frappe.log_error(f"Failed to add referral visit unique index: {str(e)}", "Migration")
