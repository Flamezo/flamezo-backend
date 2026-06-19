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

import json
import frappe
from frappe import _
from frappe.utils import get_url, cint
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.media.utils import format_media_field


def invalidate_category_cache(doc=None, method=None, restaurant_id=None):
	"""Invalidate the categories cache for a restaurant. Callable as a hook (doc, method) or directly."""
	import time
	rid = restaurant_id
	if rid is None and doc is not None:
		rid = doc.get("restaurant") or doc.get("restaurant_id")
	if rid:
		frappe.cache().set_value(f"cats_v:{rid}", str(int(time.time())), expires_in_sec=7200)


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

		# ── Redis cache ────────────────────────────────────────────────────
		cache_version = frappe.cache().get_value(f"cats_v:{restaurant}") or "0"
		cache_key = f"categories_v2:{restaurant}:{cint(include_inactive)}:{cache_version}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return json.loads(cached)

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

		# ── Bulk-load image data (eliminates N+1) ─────────────────────────
		# 1. Category own Media Assets — full data (URL + variants) in 2 queries
		all_cat_ids = [c["id"] for c in all_cats]
		cat_ma_rows = frappe.get_all(
			"Media Asset",
			filters={
				"owner_doctype": "Menu Category",
				"owner_name": ["in", all_cat_ids] if all_cat_ids else ["__no_match__"],
				"media_role": "category_image",
				"status": "ready",
			},
			fields=["name", "owner_name", "primary_url", "blur_placeholder", "media_kind"],
		)
		# Bulk-load variants for category media assets
		cat_ma_asset_names = [r["name"] for r in cat_ma_rows if r.get("media_kind") == "image"]
		cat_variants_by_asset = {}
		if cat_ma_asset_names:
			cat_variant_rows = frappe.get_all(
				"Media Variant",
				filters={"parent": ["in", cat_ma_asset_names]},
				fields=["parent", "variant_name", "file_url as url", "width", "height"],
				order_by="width asc",
			)
			for v in cat_variant_rows:
				cat_variants_by_asset.setdefault(v["parent"], []).append(v)

		# Build {cat_id: full_media_data} map
		from flamezo_backend.flamezo.media.utils import normalize_variant_name
		category_media_data = {}
		for row in cat_ma_rows:
			variants_list = cat_variants_by_asset.get(row["name"], [])
			variants_dict = {}
			srcset_parts = []
			for v in variants_list:
				vname = normalize_variant_name(v.get("variant_name", ""))
				variants_dict[vname] = {"url": v["url"], "width": v.get("width"), "height": v.get("height")}
				if v.get("url") and v.get("width"):
					srcset_parts.append(f"{v['url']} {v['width']}w")
			category_media_data[row["owner_name"]] = {
				"url": row.get("primary_url") or "",
				"blur_placeholder": row.get("blur_placeholder"),
				"media_id": row["name"],
				"variants": variants_dict,
				"srcset": ", ".join(srcset_parts) or None,
			}
		cats_with_media_asset = set(category_media_data.keys())

		# 2. First product image per category docname — bulk SQL + Media Asset data in 2 more queries
		product_image_by_catname = {}
		if all_cat_names:
			pm_rows = frappe.db.sql(
				"""
				SELECT mp.category AS cat_docname, pm.name AS media_name, pm.media_url
				FROM `tabMenu Product` mp
				INNER JOIN `tabProduct Media` pm
					ON pm.parent = mp.name
					AND pm.parenttype = 'Menu Product'
					AND pm.parentfield = 'product_media'
					AND pm.media_type = 'image'
				WHERE mp.restaurant = %s AND mp.is_active = 1 AND mp.category IN %s
				ORDER BY mp.category ASC, pm.idx ASC
				""",
				(restaurant, tuple(all_cat_names)),
				as_dict=True,
			)
			# Take first per category
			pm_items_by_catname = {}
			for row in pm_rows:
				if row.cat_docname not in pm_items_by_catname:
					pm_items_by_catname[row.cat_docname] = row

			# Bulk-load Media Asset data for these fallback product images
			if pm_items_by_catname:
				pm_media_items = [{"name": r["media_name"], "media_url": r.get("media_url")} for r in pm_items_by_catname.values()]
				from flamezo_backend.flamezo.media.utils import bulk_get_media_asset_data
				pm_asset_map = bulk_get_media_asset_data("Product Media", pm_media_items)
				for cat_docname, pm_row in pm_items_by_catname.items():
					product_image_by_catname[cat_docname] = {
						**pm_row,
						"asset_data": pm_asset_map.get(pm_row["media_name"]),
					}

		# ── Format helper ───────────────────────────────────────────────────
		def _format_category(cat, children=None, parent_id=None):
			frappe_name = cat["docname"]
			cat_id = cat["id"]
			own_count = direct_count.get(frappe_name, 0)

			# Product count on a parent = own + all children's counts
			child_count = sum(direct_count.get(c["docname"], 0) for c in (children or []))
			total_count = own_count + child_count

			data = {
				"id": cat_id,
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

			# ── Image resolution — O(1) dict lookups, zero DB queries ───
			has_media_asset = cat_id in cats_with_media_asset

			# Find first product image: check this category then each child
			catnames_to_check = [frappe_name] + ([c["docname"] for c in children] if children else [])
			first_product_media = next(
				(product_image_by_catname[cn] for cn in catnames_to_check if cn in product_image_by_catname),
				None,
			)

			def _apply_media(media_data):
				"""Write pre-loaded CDN media data fields into `data`."""
				data["category_image"] = media_data["url"]
				if media_data.get("blur_placeholder"):
					data["categoryImageBlurPlaceholder"] = media_data["blur_placeholder"]
				if media_data.get("media_id"):
					data["mediaId"] = media_data["media_id"]
				if media_data.get("variants"):
					data["categoryImageVariants"] = media_data["variants"]
				if media_data.get("srcset"):
					data["categoryImageSrcset"] = media_data["srcset"]

			if has_media_asset:
				_apply_media(category_media_data[cat_id])
			elif first_product_media and first_product_media.get("asset_data"):
				_apply_media(first_product_media["asset_data"])
				if not data.get("category_image"):
					data["category_image"] = first_product_media.get("media_url") or ""
			elif first_product_media:
				data["category_image"] = first_product_media.get("media_url") or ""
			elif cat.get("category_image"):
				data["category_image"] = cat.get("category_image")
			else:
				data["image"] = "/images/icons/burger.png"

			# Attach subcategories
			if children:
				data["subcategories"] = [
					_format_category(child, parent_id=cat_id)
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

		result = {
			"success": True,
			"data": {
				"categories": formatted_categories,
			},
		}
		frappe.cache().set_value(cache_key, json.dumps(result), expires_in_sec=300)
		return result

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
