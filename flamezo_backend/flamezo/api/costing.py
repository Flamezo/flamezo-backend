# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Menu Costing API
================
Lets a restaurant owner set the food cost (COGS) of every menu item — per item,
per category, or as a blanket % across the whole menu — and surfaces margin
metrics. This powers the Offer Simulator so owners can design BOGO / combo /
flat offers that never eat into real profit.

Food cost is stored as an absolute amount on Menu Product.food_cost. When the
owner sets it as a %, we compute food_cost = price * pct / 100 and persist the
absolute value (single source of truth, survives later % changes).

All endpoints are merchant-only and scoped to a restaurant the session user owns.
"""

import frappe
from frappe import _
from frappe.utils import flt, cint

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
import json


def _require_restaurant(outlet_id):
	"""Validate the restaurant AND that the logged-in user has access to it."""
	return validate_restaurant_for_api(outlet_id, user=frappe.session.user)


def _has_food_cost_col():
	"""True once `bench migrate` has added the food_cost column to Menu Product."""
	try:
		return "food_cost" in frappe.db.get_table_columns("Menu Product")
	except Exception:
		return False


def _product_metrics(price, food_cost):
	"""Compute per-item margin metrics. Returns a dict of derived numbers."""
	price = flt(price)
	food_cost = flt(food_cost)
	has_cost = food_cost > 0
	margin = price - food_cost if has_cost else 0
	margin_pct = (margin / price * 100) if (has_cost and price > 0) else 0
	food_cost_pct = (food_cost / price * 100) if (has_cost and price > 0) else 0
	return {
		"hasCost": has_cost,
		"margin": round(margin, 2),
		"marginPct": round(margin_pct, 1),
		"foodCostPct": round(food_cost_pct, 1),
	}


@frappe.whitelist()
def get_menu_costing(outlet_id):
	"""
	GET menu items + food cost + margin metrics for the costing page.
	Returns products grouped flat (frontend groups by category), the category
	list, and a menu-wide summary (coverage, avg food cost %, avg margin %).
	"""
	try:
		restaurant = _require_restaurant(outlet_id)
		has_cost_col = _has_food_cost_col()

		fields = [
			"name as docname",
			"product_name as name",
			"category_name as category",
			"price",
			"is_active",
			"is_vegetarian",
		]
		if has_cost_col:
			fields.append("food_cost")

		products = frappe.get_all(
			"Menu Product",
			fields=fields,
			filters={"restaurant": restaurant},
			order_by="category_name asc, display_order asc, product_name asc",
			limit_page_length=0,
		)
		# Pre-migrate fallback: column not added yet → treat every cost as unset
		if not has_cost_col:
			for p in products:
				p["food_cost"] = 0

		categories = frappe.get_all(
			"Menu Category",
			fields=["name", "category_name", "display_name"],
			filters={"restaurant": restaurant},
			order_by="display_order asc",
			limit_page_length=0,
		)

		# Enrich products with derived metrics
		cost_pcts = []
		margin_pcts = []
		items_with_cost = 0
		for p in products:
			m = _product_metrics(p.get("price"), p.get("food_cost"))
			p.update(m)
			if m["hasCost"]:
				items_with_cost += 1
				if flt(p.get("price")) > 0:
					cost_pcts.append(m["foodCostPct"])
					margin_pcts.append(m["marginPct"])

		total = len(products)

		def _avg(arr):
			return round(sum(arr) / len(arr), 1) if arr else 0

		summary = {
			"totalItems": total,
			"itemsWithCost": items_with_cost,
			"itemsWithoutCost": total - items_with_cost,
			"coveragePct": round(items_with_cost / total * 100, 0) if total else 0,
			"avgFoodCostPct": _avg(cost_pcts),
			"avgMarginPct": _avg(margin_pcts),
			"migrationPending": not has_cost_col,
		}

		return {
			"success": True,
			"data": {
				"products": products,
				"categories": categories,
				"summary": summary,
			},
		}
	except (frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as e:
		return {"success": False, "error": {"message": str(e)}}
	except Exception as e:
		frappe.log_error(f"Error in get_menu_costing: {str(e)}")
		return {"success": False, "error": {"message": str(e)}}


@frappe.whitelist()
def bulk_set_costs(outlet_id, items):
	"""
	Set food_cost on multiple products at once.
	items: JSON list of {"docname": "...", "food_cost": <number>}
	Used for inline single edits (one item) and saved batches.
	"""
	try:
		restaurant = _require_restaurant(outlet_id)
		if not _has_food_cost_col():
			return {"success": False, "error": {"message": "Food cost is not enabled yet. Please run 'bench migrate' to finish setup."}}
		if isinstance(items, str):
			items = json.loads(items)

		updated = 0
		for it in items or []:
			docname = it.get("docname")
			if not docname:
				continue
			# Scope guard: only touch products that belong to this restaurant
			owner = frappe.db.get_value("Menu Product", docname, "restaurant")
			if owner != restaurant:
				continue
			frappe.db.set_value(
				"Menu Product", docname, "food_cost", flt(it.get("food_cost")), update_modified=True
			)
			updated += 1

		frappe.db.commit()
		return {"success": True, "data": {"updated": updated}}
	except (frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as e:
		return {"success": False, "error": {"message": str(e)}}
	except Exception as e:
		frappe.log_error(f"Error in bulk_set_costs: {str(e)}")
		return {"success": False, "error": {"message": str(e)}}


def _apply_pct(restaurant, pct, category_name=None):
	"""Set food_cost = price * pct/100 for matching active-or-inactive products."""
	if not _has_food_cost_col():
		frappe.throw(_("Food cost is not enabled yet. Please run 'bench migrate' to finish setup."))
	pct = flt(pct)
	filters = {"restaurant": restaurant}
	if category_name:
		filters["category_name"] = category_name
	rows = frappe.get_all(
		"Menu Product", fields=["name", "price"], filters=filters, limit_page_length=0
	)
	updated = 0
	for r in rows:
		price = flt(r.get("price"))
		if price <= 0:
			continue
		frappe.db.set_value(
			"Menu Product", r["name"], "food_cost", round(price * pct / 100.0, 2), update_modified=True
		)
		updated += 1
	frappe.db.commit()
	return updated


@frappe.whitelist()
def apply_category_cost_pct(outlet_id, category, pct):
	"""Set food cost = pct% of price for every item in one category."""
	try:
		restaurant = _require_restaurant(outlet_id)
		if not _has_food_cost_col():
			return {"success": False, "error": {"message": "Food cost is not enabled yet. Please run 'bench migrate' to finish setup."}}
		updated = _apply_pct(restaurant, pct, category_name=category)
		return {"success": True, "data": {"updated": updated}}
	except (frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as e:
		return {"success": False, "error": {"message": str(e)}}
	except Exception as e:
		frappe.log_error(f"Error in apply_category_cost_pct: {str(e)}")
		return {"success": False, "error": {"message": str(e)}}


@frappe.whitelist()
def apply_global_cost_pct(outlet_id, pct):
	"""Set food cost = pct% of price for the entire menu (one-tap baseline)."""
	try:
		restaurant = _require_restaurant(outlet_id)
		if not _has_food_cost_col():
			return {"success": False, "error": {"message": "Food cost is not enabled yet. Please run 'bench migrate' to finish setup."}}
		updated = _apply_pct(restaurant, pct)
		return {"success": True, "data": {"updated": updated}}
	except (frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as e:
		return {"success": False, "error": {"message": str(e)}}
	except Exception as e:
		frappe.log_error(f"Error in apply_global_cost_pct: {str(e)}")
		return {"success": False, "error": {"message": str(e)}}


@frappe.whitelist()
def check_food_cost_coverage(outlet_id):
	"""
	Check whether all active menu items have food cost set.
	Used to gate AI coupon generation — AI needs cost data on every item to
	generate profit-safe, margin-aware offers.
	"""
	try:
		restaurant = _require_restaurant(outlet_id)

		total = frappe.db.count("Menu Product", {"restaurant": restaurant, "is_active": 1})

		if total == 0:
			return {
				"success": True,
				"data": {
					"all_covered": False,
					"total_items": 0,
					"items_with_cost": 0,
					"items_without_cost": 0,
					"coverage_pct": 0,
				},
			}

		if not _has_food_cost_col():
			return {
				"success": True,
				"data": {
					"all_covered": False,
					"total_items": total,
					"items_with_cost": 0,
					"items_without_cost": total,
					"coverage_pct": 0,
				},
			}

		costed = frappe.db.count(
			"Menu Product",
			{"restaurant": restaurant, "is_active": 1, "food_cost": [">", 0]},
		)
		without_cost = total - costed

		return {
			"success": True,
			"data": {
				"all_covered": without_cost == 0,
				"total_items": total,
				"items_with_cost": costed,
				"items_without_cost": without_cost,
				"coverage_pct": round(costed / total * 100, 0),
			},
		}
	except (frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError) as e:
		return {"success": False, "error": {"message": str(e)}}
	except Exception as e:
		frappe.log_error(f"Error in check_food_cost_coverage: {str(e)}")
		return {"success": False, "error": {"message": str(e)}}
