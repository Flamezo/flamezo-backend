"""
Recommendation background tasks:
- log_co_order_events: called after every Order insert, logs co-ordered product pairs
- run_weekly_recommendation_refresh: weekly cron, refreshes all active restaurants
- _compute_co_order_matrix: builds normalized co-occurrence matrix from Co Order Event table
"""

import logging
import math
from itertools import combinations
from typing import Dict, Tuple

import frappe
from frappe.utils import now

logger = logging.getLogger(__name__)


def log_co_order_events(doc, method=None):
    """
    Called via Order.after_insert hook.
    Logs every unique pair of products in the order as a Co Order Event.
    Wrapped in try/except so it NEVER blocks order placement on failure.
    """
    try:
        if not doc or not doc.restaurant:
            return

        # Only log for non-cancelled orders
        if getattr(doc, "status", "") == "cancelled":
            return

        items = doc.order_items or []
        product_ids = []
        for item in items:
            pid = None
            # Get product_id from linked Menu Product
            if item.get("product"):
                pid = frappe.db.get_value("Menu Product", item.product, "product_id")
            if pid:
                product_ids.append(pid)

        # Need at least 2 items to form a pair
        if len(product_ids) < 2:
            return

        ts = now()
        # Generate all unique pairs (lexically ordered to avoid duplicates)
        for a, b in combinations(sorted(set(product_ids)), 2):
            try:
                frappe.get_doc({
                    "doctype": "Co Order Event",
                    "restaurant": doc.restaurant,
                    "order": doc.name,
                    "product_a_id": a,
                    "product_b_id": b,
                    "timestamp": ts,
                }).insert(ignore_permissions=True)
            except Exception:
                pass  # Non-critical; don't let one bad pair block others

        frappe.db.commit()
    except Exception as e:
        logger.warning(f"log_co_order_events failed (non-critical): {e}")


def _compute_co_order_matrix(restaurant_name: str) -> Dict[Tuple[str, str], float]:
    """
    Queries Co Order Event for the restaurant (last 90 days) and returns a
    normalized co-occurrence dict: {(product_a_id, product_b_id): score 0-1}

    Normalization: log(1 + count) / log(1 + p95_count) capped at 1.0
    """
    rows = frappe.db.sql(
        """
        SELECT product_a_id, product_b_id, COUNT(*) as cnt
        FROM `tabCo Order Event`
        WHERE restaurant = %s
          AND timestamp >= DATE_SUB(NOW(), INTERVAL 90 DAY)
        GROUP BY product_a_id, product_b_id
        """,
        restaurant_name,
        as_dict=True,
    )

    if not rows:
        return {}

    counts = {(r.product_a_id, r.product_b_id): r.cnt for r in rows}

    # Use 95th-percentile for normalization (outlier-resistant)
    sorted_counts = sorted(counts.values())
    p95_idx = max(0, int(len(sorted_counts) * 0.95) - 1)
    p95 = sorted_counts[p95_idx] if sorted_counts else 1

    log_p95 = math.log(1 + p95)
    normalized = {}
    for pair, cnt in counts.items():
        normalized[pair] = min(1.0, math.log(1 + cnt) / log_p95) if log_p95 > 0 else 0.0

    return normalized


def run_weekly_recommendation_refresh():
    """
    Scheduled weekly cron job (Sunday 02:00).
    Refreshes recommendations for all active restaurants.
    Purges Co Order Events older than 90 days first.
    """
    try:
        # Purge stale co-order events (keep last 90 days only)
        frappe.db.sql(
            "DELETE FROM `tabCo Order Event` WHERE timestamp < DATE_SUB(NOW(), INTERVAL 90 DAY)"
        )
        frappe.db.commit()
    except Exception as e:
        logger.warning(f"Failed to purge stale co-order events: {e}")

    restaurants = frappe.get_all(
        "Restaurant",
        fields=["name", "restaurant_id"],
        filters={"disabled": 0},
    )

    for restaurant in restaurants:
        try:
            _refresh_restaurant_recommendations(restaurant.name)
        except Exception as e:
            logger.error(f"Weekly rec refresh failed for {restaurant.name}: {e}")


def _refresh_restaurant_recommendations(restaurant_name: str):
    """
    Re-run recommendations for a single restaurant (incremental, uses embedding cache).
    Called by weekly cron and also by the admin API endpoint.
    """
    from dinematters.dinematters.api.recommendations import (
        _build_payload_for_restaurant,
        _call_recommendations_api,
        _store_recommendations,
    )

    restaurant_doc = frappe.get_doc("Restaurant", restaurant_name)

    payload, products = _build_payload_for_restaurant(restaurant_doc)
    if not products:
        return

    # Compute co-order matrix for this restaurant
    co_order_matrix = _compute_co_order_matrix(restaurant_name)

    api_result = _call_recommendations_api(payload, co_order_matrix=co_order_matrix)
    _store_recommendations(restaurant_doc, products, api_result)

    # Update last run timestamp
    restaurant_doc.db_set("recommendation_last_run", now(), update_modified=False)
    logger.info(f"Refreshed recommendations for {restaurant_name}")
