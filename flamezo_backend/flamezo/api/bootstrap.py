# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from concurrent.futures import ThreadPoolExecutor, as_completed
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.api.config import get_restaurant_config, get_filters
from flamezo_backend.flamezo.api.categories import get_categories
from flamezo_backend.flamezo.api.products import get_products


def _run_in_frappe_thread(site, fn, *args, **kwargs):
	"""Run a function in a worker thread with its own Frappe DB connection."""
	frappe.init(site=site)
	frappe.connect()
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.destroy()


@frappe.whitelist(allow_guest=True)
def get_restaurant_bootstrap(restaurant_id):
	"""
	Consolidated API to fetch all initial data for ONO Menu in one request.
	Reduces waterfall requests and improves perceived performance.
	All four sub-calls run in parallel via ThreadPoolExecutor.
	"""
	try:
		validate_restaurant_for_api(restaurant_id)

		site = frappe.local.site

		task_map = {
			"config":      (get_restaurant_config, [restaurant_id], {}),
			"categories":  (get_categories,        [restaurant_id], {}),
			"filters":     (get_filters,            [restaurant_id], {}),
			"products":    (get_products,           [restaurant_id], {"limit": 100}),
		}

		results = {}
		with ThreadPoolExecutor(max_workers=4) as executor:
			future_to_key = {
				executor.submit(_run_in_frappe_thread, site, fn, *args, **kwargs): key
				for key, (fn, args, kwargs) in task_map.items()
			}
			for future in as_completed(future_to_key):
				key = future_to_key[future]
				results[key] = future.result()

		for key, resp in results.items():
			if not resp.get("success"):
				return resp

		config_resp    = results["config"]
		categories_resp = results["categories"]
		filters_resp   = results["filters"]
		products_resp  = results["products"]

		return {
			"success": True,
			"data": {
				"config": config_resp.get("data"),
				"categories": categories_resp.get("data", {}).get("categories", []),
				"filters": filters_resp.get("data", {}).get("filters", []),
				"products": products_resp.get("data", {}).get("products", []),
				"pagination": products_resp.get("data", {}).get("pagination", {}),
				"currency": products_resp.get("data", {}).get("currency", "INR"),
				"currencySymbol": products_resp.get("data", {}).get("currencySymbol", "₹"),
				"currencySymbolOnRight": products_resp.get("data", {}).get("currencySymbolOnRight", False),
				"site": frappe.local.site,
			},
		}
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		return {
			"success": False,
			"error": {
				"code": "RESTAURANT_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
				"message": str(e),
			},
		}
	except Exception as e:
		frappe.log_error(f"Error in get_restaurant_bootstrap: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "BOOTSTRAP_ERROR",
				"message": str(e),
			},
		}
