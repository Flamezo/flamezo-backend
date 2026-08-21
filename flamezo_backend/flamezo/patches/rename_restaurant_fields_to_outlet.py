import frappe
from frappe.model.utils.rename_field import rename_field


# Stage 4 of the Restaurant -> Outlet internal rename: the individual
# DocField-level fieldnames. Every doctype that links to Outlet (or has a
# restaurant-derived field) still names that field "restaurant"/
# "restaurant_name" etc. — the last remaining internal surface using the
# old word.
#
# IMPORTANT ordering note: unlike the doctype/table rename patches (which
# use frappe.rename_doc and run in [pre_model_sync]), Frappe's rename_field()
# util assumes the doctype is ALREADY SYNCED to the new field name — it looks
# up the new fieldname in the doctype's meta and COPIES data from the old
# column into it (`UPDATE tabX SET new=old`); it does not itself do a
# rename/ALTER TABLE and does not drop the old column. So this patch MUST run
# in [post_model_sync] (after doctype sync has already created the new,
# empty "outlet" columns) — running it in pre_model_sync would silently
# no-op (rename_field prints "not found" and returns early since the new
# field doesn't exist in meta yet), leaving every renamed column EMPTY while
# the real data sits stranded in the old column.
#
# SAFETY: we never drop the old column without first VERIFYING the copy
# actually succeeded (row-count match between old-non-null and new-non-null,
# checked with a live SHOW COLUMNS query, not cached meta). A prior manual
# test on dev caught rename_field() silently no-op'ing and a naive drop
# wiping real data before this verification existed — this patch is written
# specifically to make that class of mistake impossible.
_RESTAURANT_FIELD_DOCTYPES = [
	"Addon Group", "AI Image Generation", "Analytics Event", "Banquet Booking",
	"Boost Campaign", "Boost Coupon Redemption", "Boost Prerequisite Check",
	"Catalogue Category", "Catalogue Item", "Coin Transaction",
	"Commission Ledger Entry", "Coupon", "Coupon Usage", "Court", "Court Booking",
	"Customer Data Unlock", "Event", "Game", "Home Feature", "Hot Drop",
	"Legacy Content", "Marketing Campaign", "Marketing Event", "Marketing Segment",
	"Marketing Trigger", "Media Asset", "Media Upload Session", "Menu Category",
	"Menu Image Extractor", "Menu Product", "Menu Product Embedding Cache",
	"Menu Recommendation", "Monthly Billing Ledger", "Monthly Revenue Ledger",
	"Offer", "Offer Claim", "Order", "OTP Verification Log", "Outlet Config",
	"Outlet Gallery Item", "Outlet Loyalty Config", "Outlet Loyalty Entry",
	"Outlet Media Section", "Outlet Table", "Outlet User", "Plan Change Log",
	"Recommendation Interaction", "Referral Link", "Service Appointment",
	"Table Booking", "Tokenization Attempt", "UGC Cashback Config",
	"UGC Fraud Flag", "UGC Story Submission", "UGC Voucher",
	"UGC Voucher Redemption", "WhatsApp Lead Unlock",
]

# (doctype, old_fieldname, new_fieldname) for fields with a non-default name
_SPECIAL_RENAMES = [
	("Boost Campaign", "restaurant_lat", "outlet_lat"),
	("Boost Campaign", "restaurant_lng", "outlet_lng"),
	("Menu Image Extractor", "restaurant_name", "outlet_name"),
	("Order", "restaurant_transfer_amount", "outlet_transfer_amount"),
	("Outlet", "restaurant_id", "outlet_id"),
	("Outlet", "restaurant_name", "outlet_name"),
	("Outlet Config", "restaurant_name", "outlet_name"),
	("Outlet Onboarding", "restaurant_name", "outlet_name"),
]


def _live_columns(doctype):
	"""Raw SHOW COLUMNS — never trust frappe.db.has_column()'s cache for this;
	a prior mistake was caused by exactly that cache going stale mid-script."""
	return {r[0] for r in frappe.db.sql(f"SHOW COLUMNS FROM `tab{doctype}`")}


def _safe_rename_field(doctype, old_fieldname, new_fieldname):
	if not frappe.db.exists("DocType", doctype):
		frappe.logger().info(f"[rename_restaurant_fields_to_outlet] doctype '{doctype}' not found, skipping")
		return

	cols = _live_columns(doctype)
	if old_fieldname not in cols:
		frappe.logger().info(f"[rename_restaurant_fields_to_outlet] {doctype}.{old_fieldname} column not found — already renamed, skipping")
		return
	if new_fieldname not in cols:
		frappe.logger().info(f"[rename_restaurant_fields_to_outlet] {doctype}.{new_fieldname} column doesn't exist yet — doctype sync hasn't created it, skipping this run")
		return

	old_nonnull = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tab{doctype}` WHERE `{old_fieldname}` IS NOT NULL AND `{old_fieldname}` != ''"
	)[0][0]

	rename_field(doctype, old_fieldname, new_fieldname)

	new_nonnull = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tab{doctype}` WHERE `{new_fieldname}` IS NOT NULL AND `{new_fieldname}` != ''"
	)[0][0]
	mismatched = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tab{doctype}`
		WHERE `{old_fieldname}` IS NOT NULL AND `{old_fieldname}` != ''
		AND (`{new_fieldname}` IS NULL OR `{new_fieldname}` != `{old_fieldname}`)"""
	)[0][0]

	if new_nonnull < old_nonnull or mismatched > 0:
		raise frappe.ValidationError(
			f"[rename_restaurant_fields_to_outlet] SAFETY ABORT for {doctype}: "
			f"old '{old_fieldname}' had {old_nonnull} non-empty values, new '{new_fieldname}' "
			f"has {new_nonnull} ({mismatched} mismatched) after copy — NOT dropping the old "
			f"column. Data is untouched (old column still intact); investigate before re-running."
		)

	frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{old_fieldname}`")
	frappe.db.commit()
	frappe.logger().info(
		f"[rename_restaurant_fields_to_outlet] {doctype}.{old_fieldname} -> {new_fieldname} renamed "
		f"and verified ({old_nonnull} values copied, old column dropped)"
	)


def execute():
	"""Runs in [post_model_sync] — see the module docstring above for why this
	ordering is required. Every rename is independently guarded and
	verify-before-drop, safe to re-run, safe mid-way through a partial
	previous run. Raises (aborting migrate) rather than silently continuing
	if any single field's copy doesn't verify — a partial failure here should
	stop the deploy, not paper over it."""
	for doctype in _RESTAURANT_FIELD_DOCTYPES:
		_safe_rename_field(doctype, "restaurant", "outlet")

	for doctype, old, new in _SPECIAL_RENAMES:
		_safe_rename_field(doctype, old, new)
