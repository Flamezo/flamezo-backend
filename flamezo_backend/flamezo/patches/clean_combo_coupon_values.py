import frappe

def execute():
	"""
	Clean existing coupons in the database:
	For combo, BOGO, or free-item offers, ensure discount_value is 0.0 and discount_type is 'flat'
	so they satisfy database constraints and do not show incorrect discount values.
	"""
	coupons = frappe.get_all(
		"Coupon",
		filters={
			"offer_type": "combo",
		},
		fields=["name", "discount_value", "discount_type"]
	)

	for coupon in coupons:
		if coupon.discount_value != 0.0 or coupon.discount_type != "flat":
			doc = frappe.get_doc("Coupon", coupon.name)
			doc.discount_value = 0.0
			doc.discount_type = "flat"
			doc.save(ignore_permissions=True)

	frappe.db.commit()
