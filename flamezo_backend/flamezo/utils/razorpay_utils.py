import frappe
import razorpay
from frappe import _

def get_razorpay_config(restaurant_id=None):
	"""
	Universal Razorpay configuration fetcher.

	Under the May 2026 Razorpay Route hybrid model, *all* customer payments
	flow through Flamezo's master account and are split via Route. There
	are no per-restaurant Razorpay keys any more — every call returns the
	platform live/test triple based on `razorpay_live_mode` in
	site_config.json.

	The `restaurant_id` parameter is retained on the signature so existing
	callers (`get_razorpay_client(restaurant_id)`) keep working unchanged;
	it is simply ignored.
	"""
	# `restaurant_id` is no longer used — kept on the signature for callers.
	del restaurant_id

	# Use `in (True, 1)` so that an explicit `false` in site_config.json is never
	# swallowed by the `or` fallback (False or <next> would incorrectly flip to live).
	_cfg = frappe.conf if "razorpay_live_mode" in frappe.conf else frappe.get_conf()
	is_live = _cfg.get("razorpay_live_mode") in (True, 1)

	if is_live:
		return {
			"key_id": frappe.conf.get("razorpay_live_key_id") or frappe.get_conf().get("razorpay_live_key_id"),
			"key_secret": frappe.conf.get("razorpay_live_key_secret") or frappe.get_conf().get("razorpay_live_key_secret"),
			"webhook_secret": frappe.conf.get("razorpay_live_webhook_secret") or frappe.conf.get("razorpay_webhook_secret"),
			"is_merchant_direct": False,
		}

	# Test mode (includes backward compatibility for the older `razorpay_key_id` keys).
	return {
		"key_id": frappe.conf.get("razorpay_test_key_id") or frappe.conf.get("razorpay_key_id") or frappe.get_conf().get("razorpay_key_id"),
		"key_secret": frappe.conf.get("razorpay_test_key_secret") or frappe.conf.get("razorpay_key_secret") or frappe.get_conf().get("razorpay_key_secret"),
		"webhook_secret": frappe.conf.get("razorpay_test_webhook_secret") or frappe.conf.get("razorpay_webhook_secret"),
		"is_merchant_direct": False,
	}


def get_razorpay_client(restaurant_id=None):
	"""Returns a razorpay.Client instance built from platform keys."""
	cfg = get_razorpay_config(restaurant_id)

	if not cfg["key_id"] or not cfg["key_secret"]:
		frappe.throw(_("Razorpay API keys not configured. Please check site_config.json."))

	return razorpay.Client(auth=(cfg["key_id"], cfg["key_secret"]))


def get_or_create_razorpay_customer(restaurant_id):
	"""Get or create a Razorpay Customer ID for a restaurant to enable recurring mandates."""
	try:
		rest = frappe.get_doc("Outlet", restaurant_id)
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
		
		frappe.db.set_value("Outlet", restaurant_id, "razorpay_customer_id", customer_id)
		frappe.db.commit()
		
		return customer_id
	except Exception as e:
		frappe.log_error(f"Failed to get/create Razorpay Customer for {restaurant_id}: {str(e)}", "razorpay.get_or_create_customer")
		return None
