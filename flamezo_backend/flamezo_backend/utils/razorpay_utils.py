import frappe
import razorpay
from frappe import _

def get_razorpay_config(restaurant_id=None):
	"""
	Universal Razorpay configuration fetcher.
	Priority:
	1. Merchant-specific keys on Restaurant doc (if restaurant_id provided).
	2. Platform Dual-Mode keys (Live/Test) based on razorpay_live_mode toggle.
	"""
	config = {
		"key_id": None,
		"key_secret": None,
		"webhook_secret": None,
		"is_merchant_direct": False
	}

	# 1. Check for Merchant-specific credentials override
	if restaurant_id:
		try:
			rest = frappe.get_doc("Restaurant", restaurant_id)
			# Look for merchant's own Razorpay account details
			m_key_id = rest.get("razorpay_merchant_key_id")
			try:
				m_key_secret = rest.get_password("razorpay_merchant_key_secret")
			except Exception:
				m_key_secret = rest.get("razorpay_merchant_key_secret")
			
			m_webhook_secret = None
			try:
				m_webhook_secret = rest.get_password("razorpay_webhook_secret")
			except Exception:
				m_webhook_secret = rest.get("razorpay_webhook_secret")

			if m_key_id and m_key_secret:
				config["key_id"] = m_key_id
				config["key_secret"] = m_key_secret
				config["webhook_secret"] = m_webhook_secret
				config["is_merchant_direct"] = True
				return config
		except Exception:
			pass

	# 2. Fallback to Platform Dual-Mode keys
	is_live = frappe.conf.get("razorpay_live_mode") or frappe.get_conf().get("razorpay_live_mode")
	
	if is_live:
		config["key_id"] = frappe.conf.get("razorpay_live_key_id") or frappe.get_conf().get("razorpay_live_key_id")
		config["key_secret"] = frappe.conf.get("razorpay_live_key_secret") or frappe.get_conf().get("razorpay_live_key_secret")
		config["webhook_secret"] = frappe.conf.get("razorpay_live_webhook_secret") or frappe.conf.get("razorpay_webhook_secret")
	else:
		# Test mode fallback (includes backward compatibility for razorpay_key_id)
		config["key_id"] = frappe.conf.get("razorpay_test_key_id") or frappe.conf.get("razorpay_key_id") or frappe.get_conf().get("razorpay_key_id")
		config["key_secret"] = frappe.conf.get("razorpay_test_key_secret") or frappe.conf.get("razorpay_key_secret") or frappe.get_conf().get("razorpay_key_secret")
		config["webhook_secret"] = frappe.conf.get("razorpay_test_webhook_secret") or frappe.conf.get("razorpay_webhook_secret")

	return config


def get_razorpay_client(restaurant_id=None):
	"""Returns a razorpay.Client instance based on the above config logic."""
	cfg = get_razorpay_config(restaurant_id)
	
	if not cfg["key_id"] or not cfg["key_secret"]:
		frappe.throw(_("Razorpay API keys not configured. Please check site_config.json."))
		
	return razorpay.Client(auth=(cfg["key_id"], cfg["key_secret"]))


def get_or_create_razorpay_customer(restaurant_id):
	"""Get or create a Razorpay Customer ID for a restaurant to enable recurring mandates."""
	try:
		rest = frappe.get_doc("Restaurant", restaurant_id)
		client = get_razorpay_client()
		
		# If we already have an ID, verify it exists in the current Razorpay account
		if rest.razorpay_customer_id:
			try:
				client.customer.fetch(rest.razorpay_customer_id)
				return rest.razorpay_customer_id
			except Exception:
				# Customer doesn't exist in THIS Razorpay account (e.g. key switch)
				pass

		customer_data = {
			"name": rest.name,
			"email": rest.get("owner_email") or rest.owner or f"admin@{restaurant_id}.com",
			"notes": {
				"restaurant_id": restaurant_id,
				"source": "saas_billing_setup"
			}
		}
		
		customer = client.customer.create(data=customer_data)
		customer_id = customer.get("id")
		
		frappe.db.set_value("Restaurant", restaurant_id, "razorpay_customer_id", customer_id)
		frappe.db.commit()
		
		return customer_id
	except Exception as e:
		frappe.log_error(f"Failed to get/create Razorpay Customer for {restaurant_id}: {str(e)}", "razorpay.get_or_create_customer")
		return None
