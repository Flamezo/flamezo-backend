"""
Monthly reconciliation tasks for Razorpay integration
"""

import frappe
import razorpay
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client


# (Local Razorpay helper moved to utils.razorpay_utils)


@frappe.whitelist()
def process_monthly_minimums():
	"""Process monthly minimum fees for all restaurants (run on 1st of each month)"""
	try:
		# Get previous month
		today = datetime.now()
		previous_month = (today - relativedelta(months=1)).strftime("%Y-%m")
		
		frappe.log_error(f"Processing monthly minimums for {previous_month}", "razorpay.monthly_reconciliation")
		
		# Get all active restaurants
		restaurants = frappe.get_all("Restaurant",
			filters={"is_active": 1},
			fields=["name", "restaurant_name", "razorpay_customer_id", "monthly_minimum", "owner_email"]
		)
		
		processed_count = 0
		
		for restaurant in restaurants:
			try:
				process_restaurant_monthly_minimum(restaurant, previous_month)
				processed_count += 1
			except Exception as e:
				frappe.log_error(f"Failed to process monthly minimum for {restaurant.name}: {str(e)}", "razorpay.monthly_minimum_error")
		
		frappe.log_error(f"Processed monthly minimums for {processed_count} restaurants", "razorpay.monthly_reconciliation")
		return {"success": True, "processed": processed_count}
		
	except Exception as e:
		frappe.log_error(f"Monthly reconciliation failed: {str(e)}", "razorpay.monthly_reconciliation_error")
		return {"success": False, "error": str(e)}


def process_restaurant_monthly_minimum(restaurant, month):
	"""Process monthly minimum for a single restaurant"""
	restaurant_id = restaurant.name
	ledger_name = f"MRL-{restaurant_id}-{month}"
	
	# Get or create monthly ledger
	if frappe.db.exists("Monthly Revenue Ledger", ledger_name):
		ledger = frappe.get_doc("Monthly Revenue Ledger", ledger_name)
	else:
		# Create ledger for restaurants with no orders in the month
		ledger = frappe.get_doc({
			"doctype": "Monthly Revenue Ledger",
			"restaurant": restaurant_id,
			"month": month,
			"total_gmv": 0,
			"total_platform_fee": 0,
			"minimum_due": 0,
			"status": "pending"
		})
		ledger.insert()
	
	# Calculate minimum due
	monthly_minimum_paise = int(float(restaurant.monthly_minimum if restaurant.monthly_minimum is not None else 399.0) * 100)
	total_platform_fee = ledger.total_platform_fee or 0
	
	if total_platform_fee < monthly_minimum_paise:
		minimum_due = monthly_minimum_paise - total_platform_fee
		
		# Create Razorpay payment link for the shortfall
		payment_link = create_minimum_fee_payment_link(restaurant, minimum_due, month)
		
		# Update ledger
		ledger.minimum_due = minimum_due
		ledger.payment_link_id = payment_link.get("id")
		ledger.payment_link_url = payment_link.get("short_url")
		ledger.status = "pending"
		ledger.save()
		
		# Send notification email
		send_minimum_fee_notification(restaurant, minimum_due / 100, payment_link.get("short_url"), month)
		
	else:
		# No minimum due
		ledger.minimum_due = 0
		ledger.status = "paid"
		ledger.save()


def create_minimum_fee_payment_link(restaurant, amount_paise, month):
	"""Create Razorpay payment link for monthly minimum fee"""
	try:
		client = get_razorpay_client()
		
		payment_link_data = {
			"amount": amount_paise,
			"currency": "INR",
			"accept_partial": False,
			"description": f"Monthly minimum platform fee for {month}",
			"customer": {
				"name": restaurant.restaurant_name,
				"email": restaurant.owner_email
			},
			"notify": {
				"sms": False,
				"email": True
			},
			"reminder_enable": True,
			"notes": {
				"restaurant_id": restaurant.name,
				"month": month,
				"type": "monthly_minimum"
			},
			"callback_url": f"https://flamezo_backend.com/payment-success",
			"callback_method": "get"
		}
		
		payment_link = client.payment_link.create(payment_link_data)
		
		frappe.log_error(f"Created payment link for {restaurant.name}: {payment_link.get('id')}", "razorpay.payment_link_created")
		
		return payment_link
		
	except Exception as e:
		frappe.log_error(f"Payment link creation failed for {restaurant.name}: {str(e)}", "razorpay.payment_link_error")
		raise


def send_minimum_fee_notification(restaurant, amount, payment_url, month):
	"""Send email notification for monthly minimum fee"""
	try:
		if not restaurant.owner_email:
			return
		
		subject = f"Monthly Platform Fee Due - {restaurant.restaurant_name}"
		
		message = f"""
		<h3>Monthly Platform Fee Due</h3>
		<p>Dear {restaurant.restaurant_name} Team,</p>
		
		<p>Your monthly platform fee for <strong>{month}</strong> is due:</p>
		
		<ul>
			<li><strong>Amount Due:</strong> ₹{amount:.2f}</li>
			<li><strong>Restaurant:</strong> {restaurant.restaurant_name}</li>
			<li><strong>Month:</strong> {month}</li>
		</ul>
		
		<p>Please complete the payment using the link below:</p>
		<p><a href="{payment_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Pay Now</a></p>
		
		<p>If you have any questions, please contact our support team.</p>
		
		<p>Best regards,<br>Flamezo Team</p>
		"""
		
		frappe.sendmail(
			recipients=[restaurant.owner_email],
			subject=subject,
			message=message,
			now=True
		)
		
	except Exception as e:
		frappe.log_error(f"Failed to send minimum fee notification to {restaurant.owner_email}: {str(e)}", "razorpay.notification_error")


@frappe.whitelist()
def reconcile_transfers():
	"""Transfer reconciliation removed for SaaS billing (no Route/transfers)."""
	return {"success": False, "error": "transfer reconciliation is deprecated in SaaS billing mode"}