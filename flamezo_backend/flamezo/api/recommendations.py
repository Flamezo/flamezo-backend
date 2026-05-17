import json
from typing import Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import now

from flamezo_backend.flamezo.media.utils import get_media_asset_data
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.services.ai.recommendations import get_recommendations

MAX_RECOMMENDATIONS_PER_PRODUCT = 8


def _get_restaurant_doc(restaurant_id: str):
    """Validate and load Restaurant doc."""
    restaurant_name = validate_restaurant_for_api(restaurant_id)
    return frappe.get_doc("Restaurant", restaurant_name)


def _build_payload_for_restaurant(restaurant_doc) -> tuple:
    """Build payload from Menu Product and Menu Category data."""
    products = frappe.get_all(
        "Menu Product",
        fields=[
            "product_id", "product_name", "category_name", "main_category",
            "price", "description", "is_vegetarian", "name",
        ],
        filters={"restaurant": restaurant_doc.name, "is_active": 1},
    )

    if not products:
        frappe.throw(_("No active menu products found for this restaurant."))

    categories = frappe.get_all(
        "Menu Category",
        fields=["category_id", "category_name"],
        filters={"restaurant": restaurant_doc.name},
    )

    dishes: List[Dict] = []
    for product in products:
        dishes.append({
            "id": product.product_id,
            "name": product.product_name,
            "category": product.category_name or "",
            "mainCategory": product.main_category or "food",
            "price": float(product.price or 0),
            "description": product.description or "",
            "isVegetarian": bool(product.is_vegetarian),
        })

    categories_data: List[Dict] = []
    for cat in categories:
        categories_data.append({
            "id": cat.category_id or (cat.category_name or "").lower().replace(" ", "-"),
            "name": cat.category_name,
        })

    return {
        "dishes": dishes,
        "categories": categories_data,
        "restaurant_name": restaurant_doc.restaurant_name or restaurant_doc.name,
        "min_recommendations": MAX_RECOMMENDATIONS_PER_PRODUCT,
    }, products


# Keep old name as alias for backward compat
_build_payload = _build_payload_for_restaurant


def _call_recommendations_api(payload: Dict, co_order_matrix: Optional[Dict] = None) -> Dict:
    """Call internal recommendations service."""
    data = get_recommendations(
        dishes=payload.get("dishes", []),
        categories=payload.get("categories", []),
        min_recommendations=payload.get("min_recommendations", 9),
        co_order_matrix=co_order_matrix,
        restaurant=payload.get("restaurant_name"),
    )

    if not data.get("success"):
        frappe.throw(_("Recommendations Service failed: {0}").format(data.get("error", "Unknown error")))

    return data


def _store_recommendations(restaurant_doc, products: List[Dict], api_result: Dict) -> Dict:
    """Persist recommendations into Menu Recommendation doctype and Menu Product.recommendations JSON."""
    recommendations_data = api_result.get("data", {}).get("recommendations", []) or []
    product_map = {p.product_id: p for p in products}

    # Clear existing recommendations for this restaurant
    frappe.db.delete("Menu Recommendation", {"restaurant": restaurant_doc.name})

    updated_products = 0
    total_relations = 0

    for rec_item in recommendations_data:
        product_id = rec_item.get("id")
        if not product_id or product_id not in product_map:
            continue

        product_row = product_map[product_id]
        product_doc = frappe.get_doc("Menu Product", product_row.name)

        recs = rec_item.get("recommendations") or []
        if not isinstance(recs, list) or not recs:
            continue

        recs = recs[:MAX_RECOMMENDATIONS_PER_PRODUCT]
        formatted_recs: List[Dict] = []

        for rank, rec in enumerate(recs, start=1):
            rec_id = rec.get("id")
            if not rec_id:
                continue

            rec_doc_name = frappe.db.get_value(
                "Menu Product",
                {"product_id": rec_id, "restaurant": restaurant_doc.name},
                "name",
            )

            reason = rec.get("reason", "")
            score = rec.get("score", 0)
            co_order_freq = rec.get("co_order_freq", 0)

            menu_rec = frappe.get_doc({
                "doctype": "Menu Recommendation",
                "restaurant": restaurant_doc.name,
                "source_product": product_doc.name,
                "source_product_id": product_doc.product_id,
                "source_product_name": product_doc.product_name,
                "recommended_product": rec_doc_name,
                "recommended_product_id": rec_id,
                "recommended_product_name": rec.get("name"),
                "rank": rank,
                "score": score,
                "category": rec.get("category", ""),
                "main_category": rec.get("mainCategory", ""),
                "is_vegetarian": bool(rec.get("isVegetarian", False)),
                "price": rec.get("price", 0),
                "reason": reason,
            })
            menu_rec.insert(ignore_permissions=True)
            total_relations += 1

            formatted_recs.append({
                "id": rec_id,
                "name": rec.get("name"),
                "category": rec.get("category", ""),
                "mainCategory": rec.get("mainCategory", ""),
                "isVegetarian": bool(rec.get("isVegetarian", False)),
                "price": rec.get("price", 0),
                "reason": reason,
                "score": score,
                "co_order_freq": co_order_freq,
            })

        if not formatted_recs:
            continue

        product_doc.recommendations = json.dumps(formatted_recs)
        product_doc.save(ignore_permissions=True)
        updated_products += 1

    frappe.db.commit()

    return {
        "products_updated": updated_products,
        "total_relations": total_relations,
        "products_with_no_recommendations": len(products) - updated_products,
    }


@frappe.whitelist()
def run_recommendation_engine(restaurant_id: str):
    """
    Run the AI recommendation engine for a restaurant.
    Can be run multiple times (no longer locked after first run).
    Includes co-order signals and uses embedding cache for speed.
    """
    if not restaurant_id:
        frappe.throw(_("restaurant_id is required"))

    restaurant_doc = _get_restaurant_doc(restaurant_id)

    from flamezo_backend.flamezo.tasks.recommendation_tasks import _compute_co_order_matrix
    co_order_matrix = _compute_co_order_matrix(restaurant_doc.name)

    payload, products = _build_payload_for_restaurant(restaurant_doc)
    api_result = _call_recommendations_api(payload, co_order_matrix=co_order_matrix)
    stats = _store_recommendations(restaurant_doc, products, api_result)

    restaurant_doc.db_set("recommendation_run", 1, update_modified=False)
    restaurant_doc.db_set("recommendation_last_run", now(), update_modified=False)

    return {
        "success": True,
        "message": _("Successfully generated recommendations for {0} products.").format(
            stats["products_updated"]
        ),
        "stats": stats,
        "last_run": now(),
    }


@frappe.whitelist()
def get_recommendations_tree(restaurant_id: str):
    """
    Return tree-friendly structure for Recommendations Engine page.
    Includes recommendation_last_run timestamp and per-product CTR if available.
    """
    if not restaurant_id:
        frappe.throw(_("restaurant_id is required"))

    restaurant_doc = _get_restaurant_doc(restaurant_id)

    products = frappe.get_all(
        "Menu Product",
        fields=[
            "product_id", "product_name", "category_name", "main_category",
            "recommendations", "name",
        ],
        filters={"restaurant": restaurant_doc.name, "is_active": 1},
        order_by="display_order, product_name",
    )

    product_names = [p.name for p in products]
    image_by_parent: Dict[str, str] = {}

    if product_names:
        media_rows = frappe.get_all(
            "Product Media",
            fields=["name", "parent", "media_url", "media_type"],
            filters={
                "parent": ["in", product_names],
                "parenttype": "Menu Product",
                "parentfield": "product_media",
            },
            order_by="parent, idx asc",
        )

        for row in media_rows:
            parent = row.parent
            if parent in image_by_parent:
                continue
            if (row.media_type or "image") != "image":
                continue
            media_asset_data = get_media_asset_data(
                "Product Media",
                row.name,
                f"product_{row.media_type or 'image'}",
                row.media_url,
            )
            media_url = media_asset_data.get("url")
            if media_url and isinstance(media_url, str):
                image_by_parent[parent] = media_url

    image_by_product_id: Dict[str, str] = {}
    for p in products:
        image = image_by_parent.get(p.name)
        if image:
            image_by_product_id[p.product_id] = image

    # Load CTR stats for all products in one query
    ctr_by_product: Dict[str, Dict] = _get_ctr_stats_bulk(restaurant_doc.name)

    tree = []
    for p in products:
        recs_raw = p.recommendations
        recs: List[Dict] = []
        if recs_raw:
            try:
                parsed = json.loads(recs_raw) if isinstance(recs_raw, str) else recs_raw
                if isinstance(parsed, list):
                    recs = parsed[:MAX_RECOMMENDATIONS_PER_PRODUCT]
            except Exception:
                recs = []

        for rec in recs:
            rec_id = rec.get("id")
            if rec_id and rec_id in image_by_product_id:
                rec["image"] = image_by_product_id[rec_id]
            # Attach CTR for this specific rec pair
            pair_key = f"{p.product_id}:{rec_id}"
            pair_stats = ctr_by_product.get(pair_key, {})
            rec["clicks"] = pair_stats.get("clicks", 0)
            rec["add_to_cart"] = pair_stats.get("add_to_cart", 0)

        root_image = image_by_product_id.get(p.product_id)
        product_stats = ctr_by_product.get(p.product_id, {})

        tree.append({
            "id": p.product_id,
            "name": p.product_name,
            "category": p.category_name,
            "mainCategory": p.main_category,
            "image": root_image,
            "recommendations": recs,
            "total_rec_clicks": product_stats.get("total_clicks", 0),
            "total_rec_add_to_cart": product_stats.get("total_add_to_cart", 0),
        })

    return {
        "success": True,
        "data": {
            "recommendation_run": int(getattr(restaurant_doc, "recommendation_run", 0) or 0),
            "recommendation_last_run": str(getattr(restaurant_doc, "recommendation_last_run", "") or ""),
            "products": tree,
        },
    }


def _get_ctr_stats_bulk(restaurant_name: str) -> Dict[str, Dict]:
    """
    Returns CTR stats indexed by:
    - "{source_product_id}:{recommended_product_id}" → {clicks, add_to_cart}
    - "{source_product_id}" → {total_clicks, total_add_to_cart}
    """
    try:
        rows = frappe.db.sql(
            """
            SELECT source_product_id, recommended_product_id, action, COUNT(*) as cnt
            FROM `tabRecommendation Interaction`
            WHERE restaurant = %s
            GROUP BY source_product_id, recommended_product_id, action
            """,
            restaurant_name,
            as_dict=True,
        )
    except Exception:
        return {}

    result: Dict[str, Dict] = {}
    for row in rows:
        pair_key = f"{row.source_product_id}:{row.recommended_product_id}"
        if pair_key not in result:
            result[pair_key] = {"clicks": 0, "add_to_cart": 0}
        result[pair_key][row.action] = result[pair_key].get(row.action, 0) + row.cnt

        # Aggregate by source product
        src_key = row.source_product_id
        if src_key not in result:
            result[src_key] = {"total_clicks": 0, "total_add_to_cart": 0}
        if row.action == "click":
            result[src_key]["total_clicks"] = result[src_key].get("total_clicks", 0) + row.cnt
        elif row.action == "add_to_cart":
            result[src_key]["total_add_to_cart"] = result[src_key].get("total_add_to_cart", 0) + row.cnt

    return result


@frappe.whitelist(allow_guest=True)
def log_recommendation_interaction(
    restaurant_id: str,
    source_product_id: str,
    recommended_product_id: str,
    action: str,
    session_id: str = "",
):
    """
    Log a recommendation interaction (click or add_to_cart) from the customer app.
    allow_guest=True since ono-menu customers are unauthenticated.
    TODO: at high volume, consider frappe.enqueue() to dequeue from request thread.
    """
    if not restaurant_id or not source_product_id or not recommended_product_id:
        return {"success": False, "error": "Missing required fields"}

    if action not in ("click", "add_to_cart"):
        return {"success": False, "error": "Invalid action"}

    try:
        restaurant_name = frappe.db.get_value(
            "Restaurant",
            {"restaurant_id": restaurant_id},
            "name",
        )
        if not restaurant_name:
            return {"success": False, "error": "Restaurant not found"}

        frappe.get_doc({
            "doctype": "Recommendation Interaction",
            "restaurant": restaurant_name,
            "source_product_id": source_product_id,
            "recommended_product_id": recommended_product_id,
            "action": action,
            "session_id": session_id or "",
            "timestamp": now(),
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_recommendation_stats(restaurant_id: str):
    """Return per-product recommendation CTR stats for the admin dashboard."""
    if not restaurant_id:
        frappe.throw(_("restaurant_id is required"))

    restaurant_doc = _get_restaurant_doc(restaurant_id)
    stats = _get_ctr_stats_bulk(restaurant_doc.name)
    return {"success": True, "data": stats}


@frappe.whitelist()
def update_product_recommendations(restaurant_id: str, source_product_id: str, recommendation_ids=None):
    """
    Manually update recommendations for a single product.
    Validates restaurant and product ownership.
    Max 8 unique recommendations.
    """
    if not restaurant_id:
        frappe.throw(_("restaurant_id is required"))
    if not source_product_id:
        frappe.throw(_("source_product_id is required"))

    restaurant_doc = _get_restaurant_doc(restaurant_id)

    raw_list = frappe.parse_json(recommendation_ids) if recommendation_ids is not None else []
    if not isinstance(raw_list, list):
        frappe.throw(_("recommendation_ids must be a list of product IDs."))

    seen = set()
    clean_ids: List[str] = []
    for pid in raw_list:
        if not pid or not isinstance(pid, str):
            continue
        if pid in seen:
            continue
        seen.add(pid)
        clean_ids.append(pid)

    if len(clean_ids) > MAX_RECOMMENDATIONS_PER_PRODUCT:
        frappe.throw(
            _("You can only keep up to {0} recommendations per product.").format(MAX_RECOMMENDATIONS_PER_PRODUCT)
        )

    source_rows = frappe.get_all(
        "Menu Product",
        fields=["name", "product_id", "product_name", "category_name", "main_category", "price", "description", "is_vegetarian"],
        filters={"restaurant": restaurant_doc.name, "product_id": source_product_id, "is_active": 1},
        limit=1,
    )
    if not source_rows:
        frappe.throw(_("Source product {0} not found for this restaurant.").format(source_product_id))

    source_row = source_rows[0]

    target_rows = []
    if clean_ids:
        target_rows = frappe.get_all(
            "Menu Product",
            fields=["name", "product_id", "product_name", "category_name", "main_category", "price", "description", "is_vegetarian"],
            filters={"restaurant": restaurant_doc.name, "product_id": ["in", clean_ids], "is_active": 1},
        )

    target_by_id = {row.product_id: row for row in target_rows}

    frappe.db.delete("Menu Recommendation", {"restaurant": restaurant_doc.name, "source_product_id": source_product_id})

    formatted_recs: List[Dict] = []
    rank = 0
    for pid in clean_ids:
        target = target_by_id.get(pid)
        if not target:
            continue
        rank += 1
        reason = _("Manually selected recommendation")
        score = 0

        menu_rec = frappe.get_doc({
            "doctype": "Menu Recommendation",
            "restaurant": restaurant_doc.name,
            "source_product": source_row.name,
            "source_product_id": source_row.product_id,
            "source_product_name": source_row.product_name,
            "recommended_product": target.name,
            "recommended_product_id": target.product_id,
            "recommended_product_name": target.product_name,
            "rank": rank,
            "score": score,
            "category": target.category_name,
            "main_category": target.main_category,
            "is_vegetarian": bool(target.is_vegetarian),
            "price": target.price,
            "reason": reason,
        })
        menu_rec.insert(ignore_permissions=True)

        formatted_recs.append({
            "id": target.product_id,
            "name": target.product_name,
            "category": target.category_name or "",
            "mainCategory": target.main_category or "",
            "isVegetarian": bool(target.is_vegetarian),
            "price": float(target.price or 0),
            "reason": reason,
            "score": score,
            "co_order_freq": 0,
        })

    source_doc = frappe.get_doc("Menu Product", source_row.name)
    source_doc.recommendations = json.dumps(formatted_recs)
    source_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "message": _("Recommendations updated for product {0}.").format(source_product_id),
        "count": len(formatted_recs),
    }
