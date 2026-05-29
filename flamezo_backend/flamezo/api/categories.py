# Copyright (c) 2024, Hetvi Patel and contributors
# For license information, please see license.txt

"""
API endpoints for Categories
Matches format from BACKEND_API_DOCUMENTATION.md

Sub-category support
────────────────────
`get_categories` now returns a flat list that is backward-compatible
PLUS a nested representation:

  {
    "categories": [
      {
        "id": "starters",
        "name": "Starters",
        ...
        "isParent": true,          # true only when it has subcategories
        "subcategories": [         # empty [] for plain categories
          {
            "id": "veg-starters",
            "name": "Veg Starters",
            "parentId": "starters",
            ...
          }
        ]
      }
    ]
  }

Rules:
  • max 2 levels (parent → sub).  The controller enforces this on save.
  • A plain category has   isParent=False, subcategories=[]
  • A parent category has  isParent=True,  subcategories=[...]
  • Sub-categories are NOT returned at the top level — they appear only
    inside their parent's `subcategories` list.
  • Virtual categories (Top Picks, Chef Special) are always top-level and
    never have subcategories.
  • productCount on a parent = its own direct products + all sub products.
"""

import frappe
from frappe import _
from frappe.utils import get_url, cint
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.media.utils import format_media_field


@frappe.whitelist(allow_guest=True)
def get_categories(restaurant_id, include_inactive=0):
	"""
	GET /api/v1/categories
	Get all categories (with optional sub-categories) for a restaurant.
	Returns a nested structure; sub-categories live inside their parent's
	`subcategories` list and are NOT repeated at the top level.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)

		cat_filters = {"restaurant": restaurant}
		if not cint(include_inactive):
			cat_filters["is_active"] = 1

		# Single query: fetch ALL categories for this restaurant
		# Use `docname` alias for the actual Frappe name (hash) to avoid collision
		# with the `category_name as name` alias.
		all_cats = frappe.get_all(
			"Menu Category",
			fields=[
				"name as docname",
				"category_id as id",
				"category_name as name",
				"display_name as displayName",
				"description",
				"is_special as isSpecial",
				"category_image",
				"parent_category",
				"display_order",
			],
			filters=cat_filters,
			order_by="display_order asc, category_name asc",
		)

		# ── Build children map in O(n) ──────────────────────────────────────
		# children_map: parent_docname  →  [child_cat_dict, ...]
		children_map = {}
		top_level = []

		for cat in all_cats:
			parent = cat.get("parent_category")
			if parent:
				children_map.setdefault(parent, []).append(cat)
			else:
				top_level.append(cat)

		# ── Count products: one bulk query for ALL categories ───────────────
		# We need counts for every category (parent + children).
		all_cat_names = [c["docname"] for c in all_cats]  # actual Frappe hash docnames

		product_count_filters = {"restaurant": restaurant, "category": ["in", all_cat_names]}
		if not cint(include_inactive):
			product_count_filters["is_active"] = 1

		product_rows = frappe.get_all(
			"Menu Product",
			filters=product_count_filters,
			fields=["category"],
		)

		# direct_count: frappe_docname → count of products directly in that category
		direct_count = {}
		for row in product_rows:
			direct_count[row["category"]] = direct_count.get(row["category"], 0) + 1

		# ── Format helper ───────────────────────────────────────────────────
		def _format_category(cat, children=None, parent_id=None):
			frappe_name = cat["docname"]
			own_count = direct_count.get(frappe_name, 0)

			# Product count on a parent = own + all children's counts
			child_count = sum(direct_count.get(c["docname"], 0) for c in (children or []))
			total_count = own_count + child_count

			data = {
				"id": cat["id"],
				"name": cat["name"],
				"displayName": cat["displayName"],
				"description": cat.get("description") or "",
				"isSpecial": bool(cat.get("isSpecial", False)),
				"productCount": total_count,
				"isParent": bool(children),
				"subcategories": [],
			}
			if parent_id:
				data["parentId"] = parent_id

			# ── Image resolution (same logic as before) ─────────────────────
			has_media_asset = frappe.db.get_value(
				"Media Asset",
				{
					"owner_doctype": "Menu Category",
					"owner_name": cat.get("id"),
					"media_role": "category_image",
					"status": "ready",
				},
				"name",
			)

			# Find product image — check direct products first, then subcategory products
			category_names_to_search = [frappe_name]
			if children:
				category_names_to_search.extend([c.get("docname") or c.get("name") for c in children])

			product_names_with_images = frappe.get_all(
				"Menu Product",
				filters={"category": ["in", category_names_to_search], "is_active": 1, "restaurant": restaurant},
				pluck="name",
			)

			first_product_media = frappe.db.get_value(
				"Product Media",
				{
					"parenttype": "Menu Product",
					"media_type": "image",
					"parent": ["in", product_names_with_images or ["__no_match__"]],
				},
				["name", "media_url"],
				order_by="idx asc",
				as_dict=True,
			)

			if has_media_asset:
				format_media_field(data, "category_image", "Menu Category", cat.get("id"), "category_image", "image")
			elif first_product_media:
				data["category_image"] = first_product_media["media_url"]
				format_media_field(data, "category_image", "Product Media", first_product_media["name"], "media_url", "image")
			elif cat.get("category_image"):
				data["category_image"] = cat.get("category_image")
				format_media_field(data, "category_image", "Menu Category", cat.get("id"), "category_image", "image")
			else:
				data["image"] = "/images/icons/burger.png"

			# Attach subcategories
			if children:
				data["subcategories"] = [
					_format_category(child, parent_id=cat["id"])
					for child in sorted(children, key=lambda c: (c.get("display_order") or 0, c.get("name") or ""))
				]

			return data

		# ── Build final top-level list ──────────────────────────────────────
		formatted_categories = []
		for cat in top_level:
			children = children_map.get(cat["docname"], [])
			formatted_categories.append(_format_category(cat, children=children if children else None))

		# ── Virtual categories ──────────────────────────────────────────────
		top_picks_count = frappe.db.count(
			"Menu Product",
			filters={"product_type": "top-picks", "is_active": 1, "restaurant": restaurant},
		)
		if top_picks_count > 0:
			top_picks = {
				"id": "top-picks",
				"name": "Top Picks",
				"displayName": "Top Picks",
				"description": "Our most popular dishes",
				"isSpecial": True,
				"productCount": top_picks_count,
				"isParent": False,
				"subcategories": [],
			}
			first_tp_media = frappe.db.get_value(
				"Product Media",
				{
					"parenttype": "Menu Product",
					"media_type": "image",
					"parent": ["in", frappe.get_all(
						"Menu Product",
						filters={"product_type": "top-picks", "is_active": 1, "restaurant": restaurant},
						pluck="name",
					)],
				},
				["name", "media_url"],
				order_by="idx asc",
				as_dict=True,
			)
			if first_tp_media:
				top_picks["category_image"] = first_tp_media["media_url"]
				format_media_field(top_picks, "category_image", "Product Media", first_tp_media["name"], "product_image", "image")
			else:
				top_picks["image"] = "/images/icons/burger.png"
			formatted_categories.insert(0, top_picks)

		chef_special_count = frappe.db.count(
			"Menu Product",
			filters={"product_type": "chef-special", "is_active": 1, "restaurant": restaurant},
		)
		if chef_special_count > 0:
			chef_special = {
				"id": "chef-special",
				"name": "Chef Special",
				"displayName": "Chef Special",
				"description": "Chef's signature dish",
				"isSpecial": True,
				"productCount": chef_special_count,
				"isParent": False,
				"subcategories": [],
				"image": "/animations/Chef.gif",
			}
			formatted_categories.insert(1 if top_picks_count > 0 else 0, chef_special)

		return {
			"success": True,
			"data": {
				"categories": formatted_categories,
			},
		}

	except Exception as e:
		frappe.log_error(f"Error in get_categories: {str(e)}")
		return {
			"success": False,
			"error": {
				"code": "CATEGORY_FETCH_ERROR",
				"message": str(e),
			},
		}


@frappe.whitelist()
def update_category_order(category_orders):
	"""
	POST /api/method/flamezo_backend.flamezo.api.categories.update_category_order
	Update display_order for multiple categories.
	Accepts both parent and sub-categories.
	"""
	try:
		import json
		if isinstance(category_orders, str):
			category_orders = json.loads(category_orders)

		for order in category_orders:
			frappe.db.set_value("Menu Category", order["name"], "display_order", order["display_order"])

		frappe.db.commit()
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"Error in update_category_order: {str(e)}")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_parent_categories(restaurant_id):
	"""
	Helper used by the dashboard to populate the 'parent_category' Link field.
	Returns only top-level (non-sub) categories so you can't create 3-level nesting.
	"""
	try:
		restaurant = validate_restaurant_for_api(restaurant_id)
		cats = frappe.get_all(
			"Menu Category",
			filters={
				"restaurant": restaurant,
				"is_active": 1,
				"parent_category": ["is", "not set"],
			},
			fields=["name", "category_name as label", "category_id as value"],
			order_by="display_order asc, category_name asc",
		)
		return {"success": True, "data": {"categories": cats}}
	except Exception as e:
		frappe.log_error(f"Error in get_parent_categories: {str(e)}")
		return {"success": False, "error": str(e)}
