# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import json
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


def _try_fast_path(restaurant_id, restaurant):
	"""
	Serve bootstrap entirely from Redis — zero thread overhead.
	Returns assembled data dict when all 4 caches are warm, else None.
	"""
	# 1. Config cache (60s TTL, keyed by restaurant_id)
	config_raw = frappe.cache().get_value(f"restaurant_config:{restaurant_id}")
	if not config_raw:
		return None

	# 2. Categories cache (5-min, version-keyed)
	cats_version = frappe.cache().get_value(f"cats_v:{restaurant}") or "0"
	cats_raw = frappe.cache().get_value(f"categories_v2:{restaurant}:0:{cats_version}")
	if not cats_raw:
		return None

	# 3. Products cache (5-min, version-keyed, page=1 limit=100 no filters)
	prods_version = frappe.cache().get_value(f"products_v:{restaurant}") or "0"
	prods_raw = frappe.cache().get_value(f"products_v2:{restaurant}:{prods_version}::::p1:l100")
	if not prods_raw:
		return None

	# 4. Filters cache (5-min)
	filters_raw = frappe.cache().get_value(f"filters_cache:{restaurant}")
	if not filters_raw:
		return None

	config_resp  = json.loads(config_raw)
	cats_resp    = json.loads(cats_raw)
	prods_resp   = json.loads(prods_raw)
	filters_resp = json.loads(filters_raw)

	return {
		"config":               config_resp.get("data"),
		"categories":           cats_resp.get("data", {}).get("categories", []),
		"filters":              filters_resp.get("data", {}).get("filters", []),
		"products":             prods_resp.get("data", {}).get("products", []),
		"pagination":           prods_resp.get("data", {}).get("pagination", {}),
		"currency":             prods_resp.get("data", {}).get("currency", "INR"),
		"currencySymbol":       prods_resp.get("data", {}).get("currencySymbol", "₹"),
		"currencySymbolOnRight": prods_resp.get("data", {}).get("currencySymbolOnRight", False),
	}


@frappe.whitelist(allow_guest=True)
def get_restaurant_bootstrap(restaurant_id):
	"""
	Consolidated API to fetch all initial data for ONO Menu in one request.

	Fast path  (all 4 caches warm): pure Redis reads, zero threads — ~40ms server-side.
	Slow path  (any cache cold):     parallel ThreadPoolExecutor(4) — ~265ms server-side.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		# ── Fast path ──────────────────────────────────────────────────────
		fast = _try_fast_path(restaurant_id, restaurant)
		if fast is not None:
			return {"success": True, "data": {**fast, "site": frappe.local.site}}

		# ── Slow path: parallel threads ─────────────────────────────────────
		site = frappe.local.site
		task_map = {
			"config":     (get_restaurant_config, [restaurant_id], {}),
			"categories": (get_categories,        [restaurant_id], {}),
			"filters":    (get_filters,            [restaurant_id], {}),
			"products":   (get_products,           [restaurant_id], {"limit": 100}),
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

		for resp in results.values():
			if not resp.get("success"):
				return resp

		return {
			"success": True,
			"data": {
				"config":               results["config"].get("data"),
				"categories":           results["categories"].get("data", {}).get("categories", []),
				"filters":              results["filters"].get("data", {}).get("filters", []),
				"products":             results["products"].get("data", {}).get("products", []),
				"pagination":           results["products"].get("data", {}).get("pagination", {}),
				"currency":             results["products"].get("data", {}).get("currency", "INR"),
				"currencySymbol":       results["products"].get("data", {}).get("currencySymbol", "₹"),
				"currencySymbolOnRight": results["products"].get("data", {}).get("currencySymbolOnRight", False),
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
