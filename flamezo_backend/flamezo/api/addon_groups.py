"""
Addon Groups API — CRUD for managing addon groups at the restaurant level.

Endpoints:
  GET    /api/v1/addon-groups           — List addon groups for a restaurant
  POST   /api/v1/addon-groups           — Create addon group
  GET    /api/v1/addon-groups/:id       — Get single addon group
  PUT    /api/v1/addon-groups/:id       — Update addon group
  DELETE /api/v1/addon-groups/:id       — Delete addon group
  POST   /api/v1/addon-groups/:id/link  — Link addon group to products
"""
import frappe
import json
from frappe import _
from frappe.utils import flt, cint

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api


@frappe.whitelist()
def get_addon_groups(restaurant_id, status=None, group_type=None, include_items=1):
    """GET /api/v1/addon-groups — List all addon groups for a restaurant."""
    try:
        restaurant = validate_restaurant_for_api(restaurant_id)

        filters = {"restaurant": restaurant}
        if status:
            filters["status"] = status
        if group_type:
            filters["group_type"] = group_type

        groups = frappe.get_all(
            "Addon Group",
            filters=filters,
            fields=[
                "name", "group_id", "group_name", "group_type", "status",
                "is_required", "min_selections", "max_selections",
                "display_order", "pos_addon_group_id"
            ],
            order_by="display_order asc, group_name asc"
        )

        if cint(include_items) and groups:
            group_names = [g.name for g in groups]
            items = frappe.get_all(
                "Addon Item",
                filters={"parent": ["in", group_names], "parenttype": "Addon Group"},
                fields=[
                    "parent", "name", "item_id", "item_name", "price",
                    "is_default", "is_vegetarian", "in_stock", "display_order",
                    "pos_addon_item_id"
                ],
                order_by="display_order asc"
            )
            items_by_group = {}
            for item in items:
                items_by_group.setdefault(item.parent, []).append(_format_item(item))
            for g in groups:
                g["items"] = items_by_group.get(g.name, [])

        # Count linked products for each group
        for g in groups:
            g["linked_product_count"] = frappe.db.count(
                "Product Addon Group",
                {"addon_group": g.name, "parenttype": "Menu Product", "is_enabled": 1}
            )

        return {"success": True, "data": [_format_group(g) for g in groups]}

    except Exception as e:
        frappe.log_error(f"get_addon_groups error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def create_addon_group(restaurant_id, group_name, group_type="addon", items=None,
                       is_required=0, min_selections=0, max_selections=0,
                       display_order=0, status="Active"):
    """POST /api/v1/addon-groups — Create a new addon group."""
    try:
        restaurant = validate_restaurant_for_api(restaurant_id)

        if isinstance(items, str):
            items = json.loads(items)

        if not items or not isinstance(items, list):
            return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "At least one item is required"}}

        doc = frappe.get_doc({
            "doctype": "Addon Group",
            "group_name": group_name,
            "group_type": group_type,
            "restaurant": restaurant,
            "is_required": cint(is_required),
            "min_selections": cint(min_selections),
            "max_selections": cint(max_selections),
            "display_order": cint(display_order),
            "status": status,
            "items": [_parse_item_input(item, idx) for idx, item in enumerate(items)]
        })
        doc.insert(ignore_permissions=True)

        return {"success": True, "data": _get_full_group(doc.name)}

    except frappe.ValidationError as e:
        return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(e)}}
    except Exception as e:
        frappe.log_error(f"create_addon_group error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def get_addon_group(restaurant_id, group_id):
    """GET /api/v1/addon-groups/:id — Get single addon group with items and linked products."""
    try:
        restaurant = validate_restaurant_for_api(restaurant_id)
        group_name = _resolve_group(group_id, restaurant)
        if not group_name:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not found"}}

        data = _get_full_group(group_name)

        # Include linked products
        links = frappe.get_all(
            "Product Addon Group",
            filters={"addon_group": group_name, "parenttype": "Menu Product"},
            fields=["parent", "is_enabled", "display_order"]
        )
        linked_products = []
        for link in links:
            product = frappe.db.get_value(
                "Menu Product", link.parent,
                ["product_name", "product_id", "price", "is_active"], as_dict=True
            )
            if product:
                linked_products.append({
                    "id": link.parent,
                    "productName": product.product_name,
                    "productId": product.product_id,
                    "price": flt(product.price),
                    "isActive": bool(product.is_active),
                    "isEnabled": bool(link.is_enabled),
                    "displayOrder": cint(link.display_order)
                })
        data["linkedProducts"] = linked_products

        return {"success": True, "data": data}

    except Exception as e:
        frappe.log_error(f"get_addon_group error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def update_addon_group(restaurant_id, group_id, **kwargs):
    """PUT /api/v1/addon-groups/:id — Update addon group."""
    try:
        restaurant = validate_restaurant_for_api(restaurant_id)
        group_name = _resolve_group(group_id, restaurant)
        if not group_name:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not found"}}

        doc = frappe.get_doc("Addon Group", group_name)

        # Update scalar fields
        for field in ["group_name", "group_type", "is_required", "min_selections",
                      "max_selections", "display_order", "status"]:
            if field in kwargs and kwargs[field] is not None:
                val = kwargs[field]
                if field in ("is_required", "min_selections", "max_selections", "display_order"):
                    val = cint(val)
                setattr(doc, field, val)

        # Update items if provided
        items = kwargs.get("items")
        if items is not None:
            if isinstance(items, str):
                items = json.loads(items)
            doc.items = []
            for idx, item in enumerate(items):
                doc.append("items", _parse_item_input(item, idx))

        doc.save(ignore_permissions=True)
        return {"success": True, "data": _get_full_group(doc.name)}

    except frappe.ValidationError as e:
        return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(e)}}
    except Exception as e:
        frappe.log_error(f"update_addon_group error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def delete_addon_group(restaurant_id, group_id):
    """DELETE /api/v1/addon-groups/:id — Delete addon group (unlinks from all products)."""
    try:
        restaurant = validate_restaurant_for_api(restaurant_id)
        group_name = _resolve_group(group_id, restaurant)
        if not group_name:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not found"}}

        # Remove all product links first
        frappe.db.delete("Product Addon Group", {"addon_group": group_name})
        frappe.delete_doc("Addon Group", group_name, ignore_permissions=True)

        return {"success": True, "message": "Addon group deleted"}

    except Exception as e:
        frappe.log_error(f"delete_addon_group error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def link_addon_group_to_products(restaurant_id, group_id, product_ids, display_order=0):
    """POST /api/v1/addon-groups/:id/link — Link/unlink addon group to products."""
    try:
        restaurant = validate_restaurant_for_api(restaurant_id)
        group_name = _resolve_group(group_id, restaurant)
        if not group_name:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not found"}}

        if isinstance(product_ids, str):
            product_ids = json.loads(product_ids)

        linked = []
        for product_id in product_ids:
            product_name = frappe.db.get_value(
                "Menu Product",
                {"product_id": product_id, "restaurant": restaurant}
            ) or frappe.db.get_value("Menu Product", product_id)

            if not product_name:
                continue

            product_doc = frappe.get_doc("Menu Product", product_name)

            # Check if already linked
            already_linked = any(
                link.addon_group == group_name
                for link in (product_doc.addon_groups or [])
            )
            if already_linked:
                linked.append(product_name)
                continue

            product_doc.append("addon_groups", {
                "addon_group": group_name,
                "is_enabled": 1,
                "display_order": cint(display_order)
            })
            product_doc.save(ignore_permissions=True)
            linked.append(product_name)

        return {"success": True, "data": {"linked_products": len(linked)}}

    except Exception as e:
        frappe.log_error(f"link_addon_group error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def toggle_addon_item_stock(restaurant_id, group_id, item_id, in_stock):
    """POST /api/v1/addon-groups/:groupId/items/:itemId/stock — Toggle item stock."""
    try:
        restaurant = validate_restaurant_for_api(restaurant_id)
        group_name = _resolve_group(group_id, restaurant)
        if not group_name:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not found"}}

        doc = frappe.get_doc("Addon Group", group_name)
        found = False
        for item in doc.items:
            if item.item_id == item_id or item.name == item_id:
                item.in_stock = cint(in_stock)
                found = True
                break

        if not found:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": f"Item '{item_id}' not found"}}

        doc.save(ignore_permissions=True)
        return {"success": True, "message": f"Stock updated to {'in stock' if cint(in_stock) else 'out of stock'}"}

    except Exception as e:
        frappe.log_error(f"toggle_addon_item_stock error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


# ─── Internal Helpers ────────────────────────────────────────────────────────

def _resolve_group(group_id, restaurant):
    """Resolve group_id or name to Frappe document name."""
    # Try direct name first
    if frappe.db.exists("Addon Group", {"name": group_id, "restaurant": restaurant}):
        return group_id
    # Try by group_id
    return frappe.db.get_value(
        "Addon Group", {"group_id": group_id, "restaurant": restaurant}
    )


def _get_full_group(group_name):
    """Get formatted addon group with items."""
    doc = frappe.get_doc("Addon Group", group_name)
    result = _format_group(doc)
    result["items"] = [_format_item(item) for item in doc.items]
    return result


def _format_group(g):
    """Format group for API response."""
    return {
        "id": g.get("name") or g.name,
        "groupId": g.get("group_id") or "",
        "groupName": g.get("group_name") or "",
        "groupType": g.get("group_type") or "addon",
        "type": g.get("group_type") or "addon",
        "status": g.get("status") or "Active",
        "isRequired": bool(g.get("is_required")),
        "minSelections": cint(g.get("min_selections")),
        "maxSelections": cint(g.get("max_selections")),
        "displayOrder": cint(g.get("display_order")),
        "posAddonGroupId": g.get("pos_addon_group_id") or None,
        "linkedProductCount": g.get("linked_product_count", 0),
        "items": g.get("items") or []
    }


def _format_item(item):
    """Format addon item for API response."""
    return {
        "id": item.get("item_id") or str(item.get("name", "")),
        "itemId": item.get("item_id") or str(item.get("name", "")),
        "name": item.get("item_name") or "",
        "itemName": item.get("item_name") or "",
        "price": flt(item.get("price", 0)),
        "isDefault": bool(item.get("is_default")),
        "isVegetarian": bool(item.get("is_vegetarian", 1)),
        "inStock": bool(item.get("in_stock", 1)),
        "displayOrder": cint(item.get("display_order", 0)),
        "posAddonItemId": item.get("pos_addon_item_id") or None
    }


def _parse_item_input(item, idx=0):
    """Parse item input from API request to DocType fields."""
    return {
        "item_name": item.get("name") or item.get("itemName") or item.get("item_name", ""),
        "item_id": item.get("id") or item.get("itemId") or item.get("item_id") or "",
        "price": flt(item.get("price", 0)),
        "is_default": cint(item.get("isDefault") or item.get("is_default", 0)),
        "is_vegetarian": cint(item.get("isVegetarian") if item.get("isVegetarian") is not None else item.get("is_vegetarian", 1)),
        "in_stock": cint(item.get("inStock") if item.get("inStock") is not None else item.get("in_stock", 1)),
        "display_order": cint(item.get("displayOrder") or item.get("display_order", idx))
    }
