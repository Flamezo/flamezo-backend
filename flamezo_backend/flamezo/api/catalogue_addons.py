"""
Catalogue Addons API — link/unlink Addon Groups to Catalogue Items.

Endpoints:
  GET    get_item_addons(outlet_id, item_id)
  POST   link_addon_to_item(outlet_id, item_id, addon_group_id, display_order)
  DELETE unlink_addon_from_item(outlet_id, item_id, addon_group_id)
  POST   toggle_item_addon_enabled(outlet_id, item_id, addon_group_id, is_enabled)
  POST   reorder_item_addons(outlet_id, item_id, order)
"""
import frappe
import json
from frappe import _
from frappe.utils import flt, cint

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api


def _get_catalogue_item(item_id, restaurant):
    """Fetch Catalogue Item doc and verify it belongs to restaurant. Raises on failure."""
    doc = frappe.get_doc("Catalogue Item", item_id)
    if doc.outlet != restaurant:
        frappe.throw(_("Item not found or access denied"), exc=frappe.DoesNotExistError)
    return doc


def _build_addon_list(doc):
    """Build the sorted addon groups response list from a Catalogue Item doc."""
    linked_addons = []
    for link in (doc.addon_groups or []):
        try:
            grp = frappe.get_doc("Addon Group", link.addon_group)
            linked_addons.append({
                "id": grp.name,
                "addon_group_id": link.name,
                "group_name": grp.group_name,
                "group_type": grp.group_type,
                "is_required": bool(grp.is_required),
                "min_selections": cint(grp.min_selections),
                "max_selections": cint(grp.max_selections) or 1,
                "is_enabled": bool(link.is_enabled),
                "display_order": cint(link.display_order),
                "options": [
                    {
                        "id": opt.name,
                        "name": opt.item_name,
                        "price": flt(opt.price),
                        "is_default": bool(opt.is_default),
                        "in_stock": bool(opt.in_stock),
                        "display_order": cint(opt.display_order),
                    }
                    for opt in sorted(grp.items or [], key=lambda x: cint(x.display_order))
                ]
            })
        except Exception:
            pass
    linked_addons.sort(key=lambda x: x["display_order"])
    return linked_addons


@frappe.whitelist()
def get_item_addons(outlet_id, item_id):
    """GET — return all addon groups linked to a catalogue item."""
    try:
        restaurant = validate_restaurant_for_api(outlet_id)
        doc = _get_catalogue_item(item_id, restaurant)
        return {"success": True, "data": _build_addon_list(doc)}
    except frappe.DoesNotExistError:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not found"}}
    except Exception as e:
        frappe.log_error(f"get_item_addons error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def link_addon_to_item(outlet_id, item_id, addon_group_id, display_order=0):
    """POST — link an Addon Group to a Catalogue Item."""
    try:
        restaurant = validate_restaurant_for_api(outlet_id)
        doc = _get_catalogue_item(item_id, restaurant)

        # Validate addon group belongs to restaurant
        if not frappe.db.exists("Addon Group", {"name": addon_group_id, "outlet": restaurant}):
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not found"}}

        # Skip if already linked
        already_linked = any(
            row.addon_group == addon_group_id
            for row in (doc.addon_groups or [])
        )
        if not already_linked:
            doc.append("addon_groups", {
                "addon_group": addon_group_id,
                "is_enabled": 1,
                "display_order": cint(display_order),
            })
            doc.save(ignore_permissions=True)

        return {"success": True, "data": _build_addon_list(doc)}
    except frappe.DoesNotExistError:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not found"}}
    except Exception as e:
        frappe.log_error(f"link_addon_to_item error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def unlink_addon_from_item(outlet_id, item_id, addon_group_id):
    """DELETE — remove an Addon Group link from a Catalogue Item."""
    try:
        restaurant = validate_restaurant_for_api(outlet_id)
        doc = _get_catalogue_item(item_id, restaurant)

        rows_to_remove = [
            row for row in (doc.addon_groups or [])
            if row.addon_group == addon_group_id
        ]
        if not rows_to_remove:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not linked to this item"}}

        for row in rows_to_remove:
            doc.addon_groups.remove(row)

        doc.save(ignore_permissions=True)
        return {"success": True, "data": _build_addon_list(doc)}
    except frappe.DoesNotExistError:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not found"}}
    except Exception as e:
        frappe.log_error(f"unlink_addon_from_item error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def toggle_item_addon_enabled(outlet_id, item_id, addon_group_id, is_enabled):
    """POST — toggle is_enabled on a linked Addon Group row."""
    try:
        restaurant = validate_restaurant_for_api(outlet_id)
        doc = _get_catalogue_item(item_id, restaurant)

        found = False
        for row in (doc.addon_groups or []):
            if row.addon_group == addon_group_id:
                row.is_enabled = cint(is_enabled)
                found = True
                break

        if not found:
            return {"success": False, "error": {"code": "NOT_FOUND", "message": "Addon group not linked to this item"}}

        doc.save(ignore_permissions=True)
        return {"success": True, "data": _build_addon_list(doc)}
    except frappe.DoesNotExistError:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not found"}}
    except Exception as e:
        frappe.log_error(f"toggle_item_addon_enabled error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}


@frappe.whitelist()
def reorder_item_addons(outlet_id, item_id, order):
    """POST — bulk-update display_order on linked addon group rows.

    order: [{"addon_group_id": "<child row name>", "display_order": int}, ...]
    """
    try:
        restaurant = validate_restaurant_for_api(outlet_id)
        doc = _get_catalogue_item(item_id, restaurant)

        if isinstance(order, str):
            order = json.loads(order)

        # Build lookup: child row name → display_order
        order_map = {entry["addon_group_id"]: cint(entry["display_order"]) for entry in order}

        for row in (doc.addon_groups or []):
            if row.name in order_map:
                row.display_order = order_map[row.name]

        doc.save(ignore_permissions=True)
        return {"success": True, "data": _build_addon_list(doc)}
    except frappe.DoesNotExistError:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "Item not found"}}
    except Exception as e:
        frappe.log_error(f"reorder_item_addons error: {e}")
        return {"success": False, "error": {"code": "SERVER_ERROR", "message": str(e)}}
