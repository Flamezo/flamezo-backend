import frappe


def _add_unique_index(table, index_name, columns, dedupe_group_by):
	"""Add a unique composite index, deduplicating existing rows first (keeps
	the oldest row per group). Idempotent: checks for the index before
	attempting to create it. Mirrors add_referral_visit_unique_index.py.
	"""
	try:
		existing = frappe.db.sql(
			"""
			SELECT INDEX_NAME
			FROM INFORMATION_SCHEMA.STATISTICS
			WHERE TABLE_SCHEMA = DATABASE()
			  AND TABLE_NAME = %s
			  AND INDEX_NAME = %s
			""",
			[table, index_name],
		)
		if existing:
			return  # Already applied

		columns_sql = ", ".join(columns)
		frappe.db.sql(
			f"""
			DELETE t FROM `{table}` t
			INNER JOIN (
				SELECT {columns_sql}, MIN(creation) AS keep_creation
				FROM `{table}`
				GROUP BY {columns_sql}
				HAVING COUNT(*) > 1
			) dups ON {dedupe_group_by}
			         AND t.creation > dups.keep_creation
			"""
		)
		frappe.db.commit()
		# ALTER TABLE causes an implicit commit in MariaDB — frappe.db.sql()
		# rejects DDL while there are uncommitted writes in the transaction
		# (ImplicitCommitError). sql_ddl() commits first, then runs it.
		columns_ddl = ", ".join(f"`{c}`" for c in columns)
		frappe.db.sql_ddl(f"ALTER TABLE `{table}` ADD UNIQUE INDEX `{index_name}` ({columns_ddl})")
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Failed to add unique index {index_name} on {table}: {str(e)}", "Migration")


def execute():
	"""Enforce (request/club/outlet, customer_phone) uniqueness at the DB layer
	for the three "join/follow" membership doctypes behind Crowd & Clubs and
	Chills — previously dedup was only an application-level `exists()` check
	before insert, which is itself non-atomic and can race under concurrent
	join/follow calls.
	"""
	_add_unique_index(
		"tabCrowd Request Member",
		"uq_crowd_request_member_request_phone",
		["request", "customer_phone"],
		"t.request = dups.request AND t.customer_phone = dups.customer_phone",
	)
	_add_unique_index(
		"tabCreator Club Member",
		"uq_creator_club_member_club_phone",
		["club", "customer_phone"],
		"t.club = dups.club AND t.customer_phone = dups.customer_phone",
	)
	_add_unique_index(
		"tabChills Outlet Follow",
		"uq_chills_outlet_follow_outlet_phone",
		["outlet", "customer_phone"],
		"t.outlet = dups.outlet AND t.customer_phone = dups.customer_phone",
	)
