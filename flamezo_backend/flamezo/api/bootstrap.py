# Copyright (c) 2025, Flamezo and contributors
# For license information, please see license.txt

import frappe
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.api.config import get_restaurant_config, get_filters
from flamezo_backend.flamezo.api.categories import get_categories
from flamezo_backend.flamezo.api.products import get_products

@frappe.whitelist(allow_guest=True)
def get_restaurant_bootstrap(restaurant_id):
    """
    Consolidated API to fetch all initial data for ONO Menu in one request.
    Reduces waterfall requests and improves perceived performance.
    """
    try:
        # Validate restaurant exists
        validate_restaurant_for_api(restaurant_id)
        
        # 1. Get Restaurant Config
        config_resp = get_restaurant_config(restaurant_id)
        if not config_resp.get("success"):
            return config_resp
            
        # 2. Get Categories
        categories_resp = get_categories(restaurant_id)
        if not categories_resp.get("success"):
            return categories_resp
            
        # 3. Get Filters
        filters_resp = get_filters(restaurant_id)
        if not filters_resp.get("success"):
            return filters_resp
            
        # 4. Get Initial Products (Top 100 to avoid immediate sequential calls)
        products_resp = get_products(restaurant_id, limit=100)
        if not products_resp.get("success"):
            return products_resp
            
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
                "site": frappe.local.site
            }
        }
    except (frappe.DoesNotExistError, frappe.ValidationError) as e:
        return {
            "success": False,
            "error": {
                "code": "RESTAURANT_NOT_FOUND" if isinstance(e, frappe.DoesNotExistError) else "VALIDATION_ERROR",
                "message": str(e)
            }
        }
    except Exception as e:
        frappe.log_error(f"Error in get_restaurant_bootstrap: {str(e)}")
        return {
            "success": False,
            "error": {
                "code": "BOOTSTRAP_ERROR",
                "message": str(e)
            }
        }
