import frappe


def execute():
	"""Backfill the Google-review offer for EXISTING restaurants on deploy.

	New restaurants get their default coupons from Restaurant.after_insert, but
	existing ones never ran that hook. This runs once on `bench migrate` and:
	  1. Renames the legacy REVIEW50 code → GOOGLEREVIEW (autoname is
	     {restaurant}-{code}, so we rename the doc, which also cascades the code
	     onto its Offer Claim links).
	  2. Creates the default coupons (incl. GOOGLEREVIEW) for any restaurant
	     missing them — create_default_coupons is idempotent.
	  3. Normalises review coupons: a reward type + a loss-safe minimum bill.

	Runs in [post_model_sync] so the Coupon doctype (incl. review_reward_type) is
	already synced. Safe to re-run.
	"""
	from flamezo_backend.flamezo.doctype.outlet.default_coupons import create_default_coupons

	# 1. Rename legacy REVIEW50 → GOOGLEREVIEW
	for c in frappe.get_all(
		"Coupon", filters={"code": "REVIEW50", "offer_type": "google_review"}, fields=["name", "outlet"]
	):
		new_name = f"{c.outlet}-GOOGLEREVIEW"
		if frappe.db.exists("Coupon", new_name):
			continue
		try:
			frappe.rename_doc("Coupon", c.name, new_name, force=True)
			frappe.db.set_value("Coupon", new_name, "code", "GOOGLEREVIEW", update_modified=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Review coupon rename failed for {c.name}")

	# 2. Create the default coupons for restaurants missing them
	created = 0
	for name in frappe.get_all("Outlet", pluck="name"):
		try:
			created += create_default_coupons(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Default coupon backfill failed for {name}")

	# 3. Normalise existing review coupons: reward type + loss-safe min bill
	frappe.db.sql(
		"UPDATE `tabCoupon` SET review_reward_type='cashback' "
		"WHERE offer_type='google_review' AND (review_reward_type IS NULL OR review_reward_type='')"
	)
	frappe.db.sql(
		"UPDATE `tabCoupon` SET min_order_amount = discount_value*4 "
		"WHERE offer_type='google_review' AND review_reward_type='cashback' AND min_order_amount < discount_value*3"
	)

	frappe.db.commit()
	frappe.logger().info(f"[backfill_google_review_coupons] created {created} default coupons")
