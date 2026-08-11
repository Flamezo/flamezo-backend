"""
Catalogue API — non-dining merchant catalogue (wellness, fitness, sports_venue, fashion, etc.)

Consumer endpoints (public):
  get_catalogue(outlet_id)
  get_catalogue_item(item_id, outlet_id)

Merchant endpoints (auth required, restaurant permission enforced):
  get_catalogue_categories(outlet_id)
  save_catalogue_category(outlet_id, ...)
  delete_catalogue_category(outlet_id, name)
  save_catalogue_item(outlet_id, ...)
  delete_catalogue_item(outlet_id, name)
  reorder_catalogue_items(outlet_id, item_orders)
"""

import json
import frappe
from frappe import _
from frappe.utils import cint, flt, now


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_price(price, price_prefix=""):
	"""Format a numeric price as Indian locale string with optional prefix."""
	if price is None:
		return ""
	formatted = "₹{:,.0f}".format(flt(price)).replace(",", ",")
	# Indian number formatting
	formatted = _indian_format(flt(price))
	if price_prefix:
		return f"{price_prefix} {formatted}"
	return formatted


def _indian_format(amount):
	"""Format number in Indian numbering system (e.g. ₹1,00,000)."""
	amount = int(flt(amount))
	s = str(amount)
	if len(s) <= 3:
		return f"₹{s}"
	last3 = s[-3:]
	rest = s[:-3]
	parts = []
	while len(rest) > 2:
		parts.append(rest[-2:])
		rest = rest[:-2]
	if rest:
		parts.append(rest)
	parts.reverse()
	return "₹" + ",".join(parts) + "," + last3


def _resolve_restaurant_name(outlet_id):
	"""Resolve outlet_id (external ID or internal name) to internal Frappe name."""
	name = frappe.db.get_value("Restaurant", {"restaurant_id": outlet_id}, "name")
	if not name:
		# Try direct name match
		name = frappe.db.get_value("Restaurant", outlet_id, "name")
	return name


def _assert_restaurant_access(restaurant_name):
	"""Raise PermissionError if current user doesn't manage this restaurant."""
	if frappe.session.user in ("Administrator", "Guest"):
		return
	has_access = frappe.db.exists(
		"Restaurant User",
		{"restaurant": restaurant_name, "user": frappe.session.user, "is_active": 1},
	)
	if not has_access:
		frappe.throw(_("Access denied to this outlet."), frappe.PermissionError)


# ── Consumer: get_catalogue ───────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_catalogue(outlet_id=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.catalogue.get_catalogue

	Returns the full catalogue for a non-dining merchant.
	Cached in Redis — invalidated on any category/item change.

	Response:
	  {
	    success: true,
	    data: {
	      outlet_type: "wellness",
	      categories: [
	        {
	          id, name, sort_order,
	          items: [
	            {
	              id, name, price, price_prefix, price_display,
	              original_price, is_popular, badge, description,
	              media: [{url, type, is_primary}],
	              sub_items: [{id, name, price, price_display, is_available}]
	            }
	          ]
	        }
	      ]
	    }
	  }
	"""
	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}

	try:
		restaurant_name = _resolve_restaurant_name(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}

		# Cache check
		cache_key = f"flamezo:catalogue:{restaurant_name}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return json.loads(cached)

		# Fetch outlet_type
		outlet_type = frappe.db.get_value("Restaurant", restaurant_name, "outlet_type") or "dining"

		# ── 4-query batch fetch (no N+1) ─────────────────────────────────────

		# Query 1: categories
		categories = frappe.get_all(
			"Catalogue Category",
			filters={"restaurant": restaurant_name, "is_active": 1},
			fields=["name", "category_name", "sort_order"],
			order_by="sort_order asc, creation asc",
		)

		if not categories:
			response = {"success": True, "data": {"outlet_type": outlet_type, "categories": []}}
			frappe.cache().set_value(cache_key, json.dumps(response))
			return response

		category_names = [c.name for c in categories]

		# Query 2: all items for this restaurant
		items = frappe.get_all(
			"Catalogue Item",
			filters={"restaurant": restaurant_name, "is_active": 1, "category": ["in", category_names]},
			fields=[
				"name", "item_name", "category", "price", "price_prefix",
				"original_price", "is_popular", "badge", "description", "sort_order",
			],
			order_by="sort_order asc, creation asc",
		)

		if not items:
			cat_list = [
				{"id": c.name, "name": c.category_name, "sort_order": c.sort_order, "items": []}
				for c in categories
			]
			response = {"success": True, "data": {"outlet_type": outlet_type, "categories": cat_list}}
			frappe.cache().set_value(cache_key, json.dumps(response))
			return response

		item_names = [i.name for i in items]

		# Query 3: all media for all items at once
		all_media = frappe.get_all(
			"Catalogue Item Media",
			filters={"parent": ["in", item_names], "parenttype": "Catalogue Item"},
			fields=["parent", "media_url", "media_type", "is_primary", "display_order"],
			order_by="display_order asc",
		)

		# Query 4: all sub-items for all items at once
		all_sub_items = frappe.get_all(
			"Catalogue Sub-item",
			filters={"parent": ["in", item_names], "parenttype": "Catalogue Item", "is_available": 1},
			fields=["name", "parent", "item_name", "price", "sort_order"],
			order_by="sort_order asc",
		)

		# ── Merge in Python (no more DB calls) ───────────────────────────────

		# Group media by item
		media_map = {}
		for m in all_media:
			media_map.setdefault(m.parent, []).append({
				"url": m.media_url or "",
				"type": m.media_type or "image",
				"is_primary": bool(m.is_primary),
			})

		# Group sub-items by item
		sub_items_map = {}
		for s in all_sub_items:
			sub_items_map.setdefault(s.parent, []).append({
				"id": s.name,
				"name": s.item_name,
				"price": flt(s.price),
				"price_display": _indian_format(flt(s.price)),
				"is_available": True,
			})

		# Group items by category
		items_by_category = {}
		for item in items:
			media = media_map.get(item.name, [])
			# Ensure primary image first
			media.sort(key=lambda m: (0 if m["is_primary"] else 1))

			price = flt(item.price)
			original_price = flt(item.original_price) if item.original_price else None
			prefix = (item.price_prefix or "").strip()

			items_by_category.setdefault(item.category, []).append({
				"id": item.name,
				"name": item.item_name,
				"price": price,
				"price_prefix": prefix,
				"price_display": _format_price(price, prefix),
				"original_price": original_price,
				"original_price_display": _indian_format(original_price) if original_price else None,
				"is_popular": bool(item.is_popular),
				"badge": item.badge or None,
				"description": item.description or "",
				"media": media,
				"sub_items": sub_items_map.get(item.name, []),
			})

		# Build final categories list (preserve sort order)
		cat_list = []
		for cat in categories:
			cat_list.append({
				"id": cat.name,
				"name": cat.category_name,
				"sort_order": cat.sort_order,
				"items": items_by_category.get(cat.name, []),
			})

		response = {
			"success": True,
			"data": {
				"outlet_type": outlet_type,
				"categories": cat_list,
			},
		}

		# Cache — no TTL, invalidated on update
		frappe.cache().set_value(cache_key, json.dumps(response))
		return response

	except Exception as e:
		frappe.log_error(f"catalogue.get_catalogue error for {outlet_id}: {e}")
		return {"success": False, "error": {"code": "CATALOGUE_FETCH_ERROR", "message": str(e)}}


# ── Consumer: get_catalogue_item ──────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_catalogue_item(item_id=None, outlet_id=None):
	"""
	GET /api/method/flamezo_backend.flamezo.api.catalogue.get_catalogue_item

	Returns a single catalogue item with full detail.
	Used by the item detail page.
	"""
	if not item_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "item_id is required"}}

	try:
		doc = frappe.get_doc("Catalogue Item", item_id)

		# Security: confirm item belongs to the given restaurant (or resolve via item)
		if outlet_id:
			rest_name = _resolve_restaurant_name(outlet_id)
			if rest_name and doc.restaurant != rest_name:
				return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not found"}}

		if not doc.is_active:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not available"}}

		price = flt(doc.price)
		original_price = flt(doc.original_price) if doc.original_price else None
		prefix = (doc.price_prefix or "").strip()

		media = sorted(
			[
				{"url": m.media_url or "", "type": m.media_type or "image", "is_primary": bool(m.is_primary)}
				for m in (doc.item_media or [])
			],
			key=lambda m: (0 if m["is_primary"] else 1, (doc.item_media or []).index(
				next((x for x in (doc.item_media or []) if x.media_url == m["url"]), None)
			) if any(x.media_url == m["url"] for x in (doc.item_media or [])) else 99),
		)

		sub_items = [
			{
				"id": s.name,
				"name": s.item_name,
				"price": flt(s.price),
				"price_display": _indian_format(flt(s.price)),
				"is_available": bool(s.is_available),
			}
			for s in sorted(doc.sub_items or [], key=lambda x: x.sort_order)
		]

		# Fetch linked addon groups with options
		linked_addons = []
		for link in (doc.addon_groups or []):
			if not link.is_enabled:
				continue
			try:
				grp = frappe.get_doc("Addon Group", link.addon_group)
				linked_addons.append({
					"id": grp.name,
					"group_name": grp.group_name,
					"group_type": grp.group_type,
					"is_required": bool(grp.is_required),
					"min_selections": grp.min_selections or 0,
					"max_selections": grp.max_selections or 1,
					"display_order": link.display_order or 0,
					"options": [
						{
							"id": opt.name,
							"name": opt.item_name,
							"price": flt(opt.price),
							"is_default": bool(opt.is_default),
							"in_stock": bool(opt.in_stock),
							"display_order": opt.display_order or 0,
						}
						for opt in sorted(grp.items or [], key=lambda x: x.display_order or 0)
						if opt.in_stock or True  # show all options
					]
				})
			except Exception:
				pass
		linked_addons.sort(key=lambda x: x["display_order"])

		# Fetch category name
		category_name = frappe.db.get_value("Catalogue Category", doc.category, "category_name") or ""

		# Fetch outlet info for CTA
		outlet_type, whatsapp_number, contact_phone = frappe.db.get_value(
			"Restaurant", doc.restaurant,
			["outlet_type", "whatsapp_number", "contact_phone"]
		) or ("dining", "", "")

		response = {
			"success": True,
			"data": {
				"id": doc.name,
				"name": doc.item_name,
				"category_id": doc.category,
				"category_name": category_name,
				"price": price,
				"price_prefix": prefix,
				"price_display": _format_price(price, prefix),
				"original_price": original_price,
				"original_price_display": _indian_format(original_price) if original_price else None,
				"is_popular": bool(doc.is_popular),
				"badge": doc.badge or None,
				"description": doc.description or "",
				"media": media,
				"sub_items": sub_items,
				"addon_groups": linked_addons,
				"outlet_type": outlet_type or "dining",
				"whatsapp_number": whatsapp_number or "",
				"contact_phone": contact_phone or "",
			},
		}

		return response

	except frappe.DoesNotExistError:
		return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not found"}}
	except Exception as e:
		frappe.log_error(f"catalogue.get_catalogue_item error for {item_id}: {e}")
		return {"success": False, "error": {"code": "ITEM_FETCH_ERROR", "message": str(e)}}


# ── Merchant: Categories ──────────────────────────────────────────────────────

@frappe.whitelist()
def get_catalogue_categories(outlet_id=None):
	"""List all catalogue categories for a restaurant (merchant use)."""
	if not outlet_id:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id is required"}}
	try:
		restaurant_name = _resolve_restaurant_name(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		categories = frappe.get_all(
			"Catalogue Category",
			filters={"restaurant": restaurant_name},
			fields=["name", "category_name", "is_active", "sort_order"],
			order_by="sort_order asc, creation asc",
		)
		return {"success": True, "data": categories}
	except Exception as e:
		frappe.log_error(f"catalogue.get_catalogue_categories error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def save_catalogue_category(outlet_id=None, name=None, category_name=None, sort_order=0, is_active=1):
	"""Create or update a catalogue category."""
	if not outlet_id or not category_name:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id and category_name are required"}}
	try:
		restaurant_name = _resolve_restaurant_name(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		if name:
			doc = frappe.get_doc("Catalogue Category", name)
			if doc.restaurant != restaurant_name:
				frappe.throw(_("Access denied."), frappe.PermissionError)
			doc.category_name = category_name
			doc.sort_order = cint(sort_order)
			doc.is_active = cint(is_active)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({
				"doctype": "Catalogue Category",
				"restaurant": restaurant_name,
				"category_name": category_name,
				"sort_order": cint(sort_order),
				"is_active": cint(is_active),
			})
			doc.insert(ignore_permissions=True)

		frappe.cache().delete_value(f"flamezo:catalogue:{restaurant_name}")
		return {"success": True, "data": {"name": doc.name, "category_name": doc.category_name}}
	except Exception as e:
		frappe.log_error(f"catalogue.save_catalogue_category error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def delete_catalogue_category(outlet_id=None, name=None):
	"""Delete a catalogue category (and orphan its items — they keep the category link but category is gone)."""
	if not outlet_id or not name:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id and name are required"}}
	try:
		restaurant_name = _resolve_restaurant_name(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		doc = frappe.get_doc("Catalogue Category", name)
		if doc.restaurant != restaurant_name:
			frappe.throw(_("Access denied."), frappe.PermissionError)

		frappe.delete_doc("Catalogue Category", name, ignore_permissions=True)
		frappe.cache().delete_value(f"flamezo:catalogue:{restaurant_name}")
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"catalogue.delete_catalogue_category error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


# ── Merchant: Items ───────────────────────────────────────────────────────────

@frappe.whitelist()
def save_catalogue_item(outlet_id=None, name=None, item_data=None):
	"""
	Create or update a catalogue item.

	item_data (JSON string or dict):
	  {
	    item_name, category, price, price_prefix, original_price,
	    description, is_popular, badge, sort_order, is_active,
	    item_media: [{media_url, media_type, is_primary, display_order, media_asset?}],
	    sub_items:  [{item_name, price, is_available, sort_order}]
	  }
	"""
	if not outlet_id or not item_data:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id and item_data are required"}}
	try:
		restaurant_name = _resolve_restaurant_name(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		if isinstance(item_data, str):
			item_data = json.loads(item_data)

		if not item_data.get("item_name"):
			return {"success": False, "error": {"code": "MISSING_PARAM", "message": "item_name is required"}}
		if not item_data.get("category"):
			return {"success": False, "error": {"code": "MISSING_PARAM", "message": "category is required"}}
		if not item_data.get("price"):
			return {"success": False, "error": {"code": "MISSING_PARAM", "message": "price is required"}}

		# Verify category belongs to restaurant
		cat_restaurant = frappe.db.get_value("Catalogue Category", item_data["category"], "restaurant")
		if cat_restaurant != restaurant_name:
			return {"success": False, "error": {"code": "INVALID_CATEGORY", "message": "Category does not belong to this restaurant"}}

		# Build child table rows
		media_rows = [
			{
				"doctype": "Catalogue Item Media",
				"media_url": m.get("media_url", ""),
				"media_type": m.get("media_type", "image"),
				"is_primary": cint(m.get("is_primary", 0)),
				"display_order": cint(m.get("display_order", 0)),
				"media_asset": m.get("media_asset"),
			}
			for m in (item_data.get("item_media") or [])
		]

		sub_item_rows = [
			{
				"doctype": "Catalogue Sub-item",
				"item_name": s.get("item_name", ""),
				"price": flt(s.get("price", 0)),
				"is_available": cint(s.get("is_available", 1)),
				"sort_order": cint(s.get("sort_order", 0)),
			}
			for s in (item_data.get("sub_items") or [])
			if s.get("item_name") and flt(s.get("price", 0)) > 0
		]

		if name:
			doc = frappe.get_doc("Catalogue Item", name)
			if doc.restaurant != restaurant_name:
				frappe.throw(_("Access denied."), frappe.PermissionError)

			doc.item_name = item_data["item_name"]
			doc.category = item_data["category"]
			doc.price = flt(item_data["price"])
			doc.price_prefix = item_data.get("price_prefix", "")
			doc.original_price = flt(item_data.get("original_price") or 0) or None
			doc.description = item_data.get("description", "")
			doc.is_popular = cint(item_data.get("is_popular", 0))
			doc.badge = item_data.get("badge", "")
			doc.sort_order = cint(item_data.get("sort_order", 0))
			doc.is_active = cint(item_data.get("is_active", 1))
			# Only replace media if explicitly sent; preserve existing rows otherwise
			if "item_media" in item_data:
				doc.item_media = media_rows
			doc.sub_items = sub_item_rows
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({
				"doctype": "Catalogue Item",
				"restaurant": restaurant_name,
				"item_name": item_data["item_name"],
				"category": item_data["category"],
				"price": flt(item_data["price"]),
				"price_prefix": item_data.get("price_prefix", ""),
				"original_price": flt(item_data.get("original_price") or 0) or None,
				"description": item_data.get("description", ""),
				"is_popular": cint(item_data.get("is_popular", 0)),
				"badge": item_data.get("badge", ""),
				"sort_order": cint(item_data.get("sort_order", 0)),
				"is_active": cint(item_data.get("is_active", 1)),
				"item_media": media_rows,
				"sub_items": sub_item_rows,
			})
			doc.insert(ignore_permissions=True)

		frappe.cache().delete_value(f"flamezo:catalogue:{restaurant_name}")
		return {"success": True, "data": {"name": doc.name}}
	except Exception as e:
		frappe.log_error(f"catalogue.save_catalogue_item error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def delete_catalogue_item(outlet_id=None, name=None):
	"""Delete a catalogue item."""
	if not outlet_id or not name:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id and name are required"}}
	try:
		restaurant_name = _resolve_restaurant_name(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		doc = frappe.get_doc("Catalogue Item", name)
		if doc.restaurant != restaurant_name:
			frappe.throw(_("Access denied."), frappe.PermissionError)

		frappe.delete_doc("Catalogue Item", name, ignore_permissions=True)
		frappe.cache().delete_value(f"flamezo:catalogue:{restaurant_name}")
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"catalogue.delete_catalogue_item error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}


@frappe.whitelist()
def reorder_catalogue_items(outlet_id=None, item_orders=None):
	"""
	Bulk-update sort_order for catalogue items.

	item_orders: [{"name": "CITEM-xxx", "sort_order": 0}, ...]
	"""
	if not outlet_id or not item_orders:
		return {"success": False, "error": {"code": "MISSING_PARAM", "message": "outlet_id and item_orders are required"}}
	try:
		restaurant_name = _resolve_restaurant_name(outlet_id)
		if not restaurant_name:
			return {"success": False, "error": {"code": "NOT_FOUND", "message": "Restaurant not found"}}
		_assert_restaurant_access(restaurant_name)

		if isinstance(item_orders, str):
			item_orders = json.loads(item_orders)

		for entry in item_orders:
			item_name = entry.get("name")
			sort_order = cint(entry.get("sort_order", 0))
			if not item_name:
				continue
			# Verify ownership before writing
			owner = frappe.db.get_value("Catalogue Item", item_name, "restaurant")
			if owner != restaurant_name:
				continue
			frappe.db.set_value("Catalogue Item", item_name, "sort_order", sort_order, update_modified=False)

		frappe.cache().delete_value(f"flamezo:catalogue:{restaurant_name}")
		return {"success": True}
	except Exception as e:
		frappe.log_error(f"catalogue.reorder_catalogue_items error: {e}")
		return {"success": False, "error": {"code": "ERROR", "message": str(e)}}
