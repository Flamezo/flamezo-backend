import frappe
from dateutil.relativedelta import relativedelta
import math

@frappe.whitelist()
def process_monthly_minimums_by_onboarding_date():
	"""Run daily: create Monthly Billing Ledger for restaurants whose onboarding day matches today."""
	try:
		from datetime import datetime
		import calendar
		today = datetime.now().date()
		previous_month = (today - relativedelta(months=1)).strftime("%Y-%m")
		last_day_current = calendar.monthrange(today.year, today.month)[1]

		restaurants = frappe.get_all("Restaurant", 
			filters={"is_active": 1}, 
			fields=["name", "onboarding_date", "monthly_minimum", "platform_fee_percent"]
		)
		created = []
		for r in restaurants:
			try:
				od = r.get("onboarding_date")
				if not od:
					continue
				if isinstance(od, str):
					od_day = int(od.split("-")[-1])
				else:
					od_day = od.day
				match_day = od_day if od_day <= last_day_current else last_day_current
				if today.day != match_day:
					continue

				# skip if ledger already exists
				if frappe.db.exists("Monthly Billing Ledger", {"restaurant": r.get("name"), "billing_month": previous_month}):
					continue

				# Sum completed orders for the previous month
				total = frappe.db.sql("""
					SELECT COALESCE(SUM(total),0) FROM `tabOrder`
					WHERE restaurant=%s AND payment_status='completed' AND DATE_FORMAT(creation, '%%Y-%%m')=%s
				""", (r.get("name"), previous_month))[0][0] or 0
				total_paise = int(float(total) * 100)
				
				# Fetch commission settings from Restaurant
				res_fee_percent = float(r.get("platform_fee_percent") if r.get("platform_fee_percent") is not None else 1.5)
				calculated_fee = int(math.floor(total_paise * (res_fee_percent / 100.0)))
				
				res_min = float(r.get("monthly_minimum") if r.get("monthly_minimum") is not None else 399.0)
				min_amt_paise = int(res_min * 100)
				
				base_commission = max(min_amt_paise, calculated_fee)
				
				# GST Compliance (18%)
				gst_amount = int(math.floor(base_commission * 0.18))
				final_total = base_commission + gst_amount

				ledger = frappe.get_doc({
					"doctype": "Monthly Billing Ledger",
					"restaurant": r.get("name"),
					"billing_month": previous_month,
					"total_gmv": total_paise,
					"calculated_fee": base_commission,
					"final_amount": final_total,
					"payment_status": "pending",
					"notes": f"Base Commission: ₹{base_commission/100:.2f}, GST (18%): ₹{gst_amount/100:.2f} (Rate: {res_fee_percent}%)"
				})
				ledger.insert(ignore_permissions=True)
				created.append(ledger.name)
			except Exception as e:
				frappe.log_error(f"Failed onboarding monthly for {r.get('name')}: {str(e)}", "razorpay.monthly_onboarding")
		return {"success": True, "created": created}
	except Exception as e:
		frappe.log_error(f"process_monthly_minimums_by_onboarding_date failed: {str(e)}", "razorpay.monthly_onboarding_error")
		return {"success": False, "error": str(e)}

