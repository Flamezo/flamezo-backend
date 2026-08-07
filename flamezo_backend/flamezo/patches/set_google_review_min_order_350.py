import frappe


def execute():
	"""Raise the Google-review coupon minimum bill to ₹350 for EXISTING merchants.

	The Google-review reward (GOOGLEREVIEW, ₹50 cashback) previously required a
	₹200 minimum bill. New merchants now default to ₹350 (see default_coupons.py);
	this brings existing merchants in line automatically on `bench migrate`.

	Only raises the floor — merchants who deliberately set a HIGHER minimum keep
	it (a review-cashback coupon is meant to be loss-safe, so we never lower it).
	Runs in [post_model_sync]. Safe to re-run.
	"""
	frappe.db.sql(
		"UPDATE `tabCoupon` SET min_order_amount = 350 "
		"WHERE offer_type = 'google_review' AND COALESCE(min_order_amount, 0) < 350"
	)
	frappe.db.commit()
	frappe.logger().info("[set_google_review_min_order_350] bumped review coupons to ₹350 min bill")
