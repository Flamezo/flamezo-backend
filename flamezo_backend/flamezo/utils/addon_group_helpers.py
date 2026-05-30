"""
Addon Group Helpers — loading, validation, price calculation.

Replaces the old customization_helpers.py pattern with the new
Addon Group → Addon Item model (Petpooja/Swiggy/Zomato-style).
"""
import frappe
import json
from frappe import _
from frappe.utils import flt, cint
from collections import defaultdict


# ─── Loading ─────────────────────────────────────────────────────────────────

def load_product_addon_groups(product_doc):
    """
    Load all addon groups and their items for a product.
    Returns list of addon group dicts with nested items.
    Optimized: 2 queries total regardless of product count.
    """
    if not product_doc.get("addon_groups"):
        return []

    group_links = [
        link for link in product_doc.addon_groups
        if link.is_enabled and link.addon_group
    ]
    if not group_links:
        return []

    group_names = [link.addon_group for link in group_links]
    display_order_map = {link.addon_group: cint(link.display_order) for link in group_links}

    # Query 1: Get addon groups
    groups = frappe.get_all(
        "Addon Group",
        filters={"name": ["in", group_names], "status": "Active"},
        fields=[
            "name", "group_id", "group_name", "group_type", "restaurant",
            "is_required", "min_selections", "max_selections", "display_order",
            "pos_addon_group_id"
        ]
    )

    if not groups:
        return []

    # Query 2: Get all addon items for these groups
    items = frappe.get_all(
        "Addon Item",
        filters={
            "parent": ["in", [g.name for g in groups]],
            "parenttype": "Addon Group"
        },
        fields=[
            "parent", "name", "item_id", "item_name", "price",
            "is_default", "is_vegetarian", "in_stock", "display_order",
            "pos_addon_item_id"
        ],
        order_by="display_order asc"
    )

    items_by_group = defaultdict(list)
    for item in items:
        items_by_group[item.parent].append(item)

    result = []
    for group in groups:
        group_items = items_by_group.get(group.name, [])
        result.append({
            "name": group.name,
            "group_id": group.group_id,
            "group_name": group.group_name,
            "group_type": group.group_type,
            "is_required": bool(group.is_required),
            "min_selections": cint(group.min_selections),
            "max_selections": cint(group.max_selections),
            "display_order": display_order_map.get(group.name, cint(group.display_order)),
            "pos_addon_group_id": group.pos_addon_group_id,
            "items": group_items
        })

    result.sort(key=lambda g: g["display_order"])
    return result


def bulk_load_addon_groups(product_names):
    """
    Bulk load addon groups for multiple products (listing APIs).
    Returns: dict mapping product_name → list of addon group dicts.
    """
    if not product_names:
        return {}

    # Get all product→group links
    links = frappe.get_all(
        "Product Addon Group",
        filters={
            "parent": ["in", product_names],
            "parenttype": "Menu Product",
            "parentfield": "addon_groups",
            "is_enabled": 1
        },
        fields=["parent", "addon_group", "display_order"]
    )

    if not links:
        return {}

    group_names = list({link.addon_group for link in links})

    # Get groups
    groups = frappe.get_all(
        "Addon Group",
        filters={"name": ["in", group_names], "status": "Active"},
        fields=[
            "name", "group_id", "group_name", "group_type",
            "is_required", "min_selections", "max_selections",
            "display_order", "pos_addon_group_id"
        ]
    )
    groups_by_name = {g.name: g for g in groups}

    # Get all items
    items = frappe.get_all(
        "Addon Item",
        filters={
            "parent": ["in", group_names],
            "parenttype": "Addon Group"
        },
        fields=[
            "parent", "name", "item_id", "item_name", "price",
            "is_default", "is_vegetarian", "in_stock", "display_order",
            "pos_addon_item_id"
        ],
        order_by="display_order asc"
    )
    items_by_group = defaultdict(list)
    for item in items:
        items_by_group[item.parent].append(item)

    # Build product → groups mapping
    result = defaultdict(list)
    for link in links:
        group = groups_by_name.get(link.addon_group)
        if not group:
            continue
        result[link.parent].append({
            "name": group.name,
            "group_id": group.group_id,
            "group_name": group.group_name,
            "group_type": group.group_type,
            "is_required": bool(group.is_required),
            "min_selections": cint(group.min_selections),
            "max_selections": cint(group.max_selections),
            "display_order": cint(link.display_order) or cint(group.display_order),
            "pos_addon_group_id": group.pos_addon_group_id,
            "items": items_by_group.get(group.name, [])
        })

    # Sort each product's groups
    for product_name in result:
        result[product_name].sort(key=lambda g: g["display_order"])

    return result


# ─── Validation ──────────────────────────────────────────────────────────────

def validate_addon_selections(addon_groups, selections):
    """
    Validate customer's addon selections against addon group constraints.

    selections format:
    {
        "group_id_or_name": ["item_id_1", "item_id_2"],
        ...
    }

    Also supports legacy format:
    {
        "question_id": "option_id"   (single)
        "question_id": ["opt1", "opt2"]  (multiple)
    }
    """
    if not addon_groups:
        if selections:
            frappe.throw(_("This product does not have addon groups"), frappe.ValidationError)
        return

    # Build lookup by group_id and group name
    group_lookup = {}
    for g in addon_groups:
        group_lookup[g["group_id"]] = g
        group_lookup[g["name"]] = g

    for group in addon_groups:
        gid = group["group_id"]
        selected = selections.get(gid, selections.get(group["name"], []))

        if isinstance(selected, (str, int)):
            selected = [selected] if selected else []
        if selected is None:
            selected = []

        # Required check
        if group["is_required"] and not selected:
            frappe.throw(
                _("'{0}' is required").format(group["group_name"]),
                frappe.ValidationError
            )

        if not selected:
            continue

        # Min selections
        min_sel = group["min_selections"]
        if min_sel > 0 and len(selected) < min_sel:
            frappe.throw(
                _("Select at least {0} option(s) for '{1}'").format(min_sel, group["group_name"]),
                frappe.ValidationError
            )

        # Max selections
        max_sel = group["max_selections"]
        if max_sel > 0 and len(selected) > max_sel:
            frappe.throw(
                _("Select at most {0} option(s) for '{1}'").format(max_sel, group["group_name"]),
                frappe.ValidationError
            )

        # Validate item IDs exist and are in stock
        valid_items = {str(item.get("item_id", item.get("name", ""))): item for item in group["items"]}
        for item_id in selected:
            item_id_str = str(item_id)
            if item_id_str not in valid_items:
                frappe.throw(
                    _("Invalid addon item '{0}' for group '{1}'").format(item_id, group["group_name"]),
                    frappe.ValidationError
                )
            item = valid_items[item_id_str]
            if not item.get("in_stock", 1):
                frappe.throw(
                    _("'{0}' is currently out of stock").format(item.get("item_name", item_id)),
                    frappe.ValidationError
                )


# ─── Price Calculation ───────────────────────────────────────────────────────

def calculate_addon_price(addon_groups, selections, base_price):
    """
    Calculate total unit price including addon selections.

    For variation groups (group_type == "variation"):
        - The selected item's price REPLACES the base price
    For addon groups:
        - The selected items' prices are ADDED to the base price

    Returns: (unit_price, price_breakdown)
    """
    unit_price = flt(base_price)
    variation_applied = False
    breakdown = []

    if not addon_groups or not selections:
        return unit_price, breakdown

    for group in addon_groups:
        gid = group["group_id"]
        selected = selections.get(gid, selections.get(group["name"], []))

        if isinstance(selected, (str, int)):
            selected = [selected] if selected else []
        if not selected:
            continue

        items_lookup = {str(item.get("item_id", item.get("name", ""))): item for item in group["items"]}

        for item_id in selected:
            item = items_lookup.get(str(item_id))
            if not item:
                continue

            item_price = flt(item.get("price", 0))

            if group["group_type"] == "variation" and not variation_applied:
                # Variation replaces base price
                if item_price > 0:
                    unit_price = item_price
                    variation_applied = True
                    breakdown.append({
                        "group": group["group_name"],
                        "item": item.get("item_name"),
                        "type": "variation",
                        "price": item_price
                    })
            else:
                # Addon adds to price
                unit_price += item_price
                if item_price > 0:
                    breakdown.append({
                        "group": group["group_name"],
                        "item": item.get("item_name"),
                        "type": "addon",
                        "price": item_price
                    })

    return unit_price, breakdown


# ─── Serialization for cart/order storage ────────────────────────────────────

def serialize_addon_selections(addon_groups, selections):
    """
    Convert addon selections to a JSON-safe dict for storage in cart/order.
    Includes full details for display and POS mapping.

    Returns dict:
    {
        "version": 2,
        "groups": [
            {
                "group_id": "choice-of-size",
                "group_name": "Choice of Size",
                "group_type": "variation",
                "pos_addon_group_id": "9675",
                "selected_items": [
                    {
                        "item_id": "large",
                        "item_name": "Large",
                        "price": 50.0,
                        "pos_addon_item_id": "41110"
                    }
                ]
            }
        ]
    }
    """
    if not addon_groups or not selections:
        return None

    groups_data = []
    for group in addon_groups:
        gid = group["group_id"]
        selected = selections.get(gid, selections.get(group["name"], []))

        if isinstance(selected, (str, int)):
            selected = [selected] if selected else []
        if not selected:
            continue

        items_lookup = {str(item.get("item_id", item.get("name", ""))): item for item in group["items"]}
        selected_items = []
        for item_id in selected:
            item = items_lookup.get(str(item_id))
            if item:
                selected_items.append({
                    "item_id": item.get("item_id") or str(item.get("name", "")),
                    "item_name": item.get("item_name", ""),
                    "price": flt(item.get("price", 0)),
                    "pos_addon_item_id": item.get("pos_addon_item_id") or ""
                })

        if selected_items:
            groups_data.append({
                "group_id": gid,
                "group_name": group["group_name"],
                "group_type": group["group_type"],
                "pos_addon_group_id": group.get("pos_addon_group_id") or "",
                "selected_items": selected_items
            })

    if not groups_data:
        return None

    return {"version": 2, "groups": groups_data}


def deserialize_addon_selections(customizations_json):
    """
    Parse stored customizations JSON — handles both v2 (addon groups) and legacy format.

    Returns:
        (version, data) where:
        - v2: (2, {"groups": [...]})
        - legacy: (1, {"question_id": "option_id", ...})
    """
    if not customizations_json:
        return 0, {}

    if isinstance(customizations_json, str):
        try:
            data = json.loads(customizations_json)
        except (json.JSONDecodeError, TypeError):
            return 0, {}
    else:
        data = customizations_json

    if isinstance(data, dict) and data.get("version") == 2:
        return 2, data

    # Legacy format
    return 1, data


# ─── API Response Formatting ────────────────────────────────────────────────

def format_addon_groups_for_api(addon_groups):
    """Format addon groups for product API response."""
    result = []
    for group in addon_groups:
        items = []
        for item in group.get("items", []):
            items.append({
                "id": item.get("item_id") or str(item.get("name", "")),
                "itemId": item.get("item_id") or str(item.get("name", "")),
                "name": item.get("item_name", ""),
                "label": item.get("item_name", ""),
                "price": flt(item.get("price", 0)),
                "isDefault": bool(item.get("is_default")),
                "isVegetarian": bool(item.get("is_vegetarian", 1)),
                "inStock": bool(item.get("in_stock", 1)),
                "displayOrder": cint(item.get("display_order", 0)),
                "posAddonItemId": item.get("pos_addon_item_id") or None
            })

        result.append({
            "id": str(group.get("name", "")) or group.get("group_id", ""),
            "groupId": group.get("group_id") or str(group.get("name", "")),
            "name": group.get("group_name", ""),
            "groupName": group.get("group_name", ""),
            "type": group.get("group_type", "addon"),
            "groupType": group.get("group_type", "addon"),
            "isRequired": group.get("is_required", False),
            "minSelections": group.get("min_selections", 0),
            "maxSelections": group.get("max_selections", 0),
            "displayOrder": group.get("display_order", 0),
            "posAddonGroupId": group.get("pos_addon_group_id") or None,
            "items": items
        })

    return result
