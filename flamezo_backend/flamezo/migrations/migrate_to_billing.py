import frappe
import math

def run_migration():
	"""Backfill Monthly Billing Ledger from Monthly Revenue Ledger (best-effort).

	Also creates a DB unique index on Razorpay Webhook Log.event_id if not present.
	"""
	settings = frappe.get_single("Flamezo Settings")
	floor_amt = (settings.gold_monthly_fee or 399) * 100
	gst_percent = settings.gst_percent or 18.0
	charge_gst = settings.charge_gst

	# Backfill ledgers
	rows = frappe.get_all("Monthly Revenue Ledger", fields=["name", "restaurant", "month", "total_platform_fee", "total_gmv", "minimum_due"]) or []
	created = 0
	for r in rows:
		billing_month = r.get("month")
		restaurant = r.get("restaurant")
		total_gmv = int(r.get("total_gmv") or 0)
		total_commissions = int(r.get("total_platform_fee") or 0)
		
		# Shortfall logic: if commissions < floor, we charge the difference.
		# If Monthly Revenue Ledger already has minimum_due, we use it.
		final_amount = int(r.get("minimum_due") or 0)
		if not final_amount:
			final_amount = max(0, floor_amt - total_commissions)

		# create ledger if not exists
		if not frappe.db.exists("Monthly Billing Ledger", {"restaurant": restaurant, "billing_month": billing_month}):
			gst_amount = 0
			if charge_gst and final_amount > 0:
				gst_amount = int(math.floor(final_amount * (gst_percent / 100.0)))

			doc = frappe.get_doc({
				"doctype": "Monthly Billing Ledger",
				"restaurant": restaurant,
				"billing_month": billing_month,
				"total_gmv": total_gmv,
				"calculated_fee": total_commissions,
				"final_amount": final_amount,
				"gst_amount": gst_amount,
				"tax_percent": gst_percent,
				"payment_status": "pending"
			})
			doc.insert(ignore_permissions=True)
			created += 1

	# Create unique index on Razorpay Webhook Log.event_id
	try:
		frappe.db.sql("ALTER TABLE `tabRazorpay Webhook Log` ADD UNIQUE INDEX ux_rzp_event_id (event_id(191))")
	except Exception:
		pass

	return {"created_ledgers": created}
