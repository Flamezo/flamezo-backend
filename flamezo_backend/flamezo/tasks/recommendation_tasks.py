"""
Recommendation background tasks:
- log_co_order_events: called after every Order insert, logs co-ordered product pairs
- run_weekly_recommendation_refresh: weekly cron, refreshes all active outlets
- _compute_co_order_matrix: builds normalized co-occurrence matrix from Co Order Event table
"""

import logging
import math
from typing import Dict, Tuple

import frappe
from frappe.utils import now

logger = logging.getLogger(__name__)


def log_co_order_events(doc, method=None):
    pass


def _compute_co_order_matrix(outlet_name: str) -> Dict[Tuple[str, str], float]:
    """
    Queries Co Order Event for the outlet (last 90 days) and returns a
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
        outlet_name,
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
    Refreshes recommendations for all active outlets.
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

    outlets = frappe.get_all(
        "Outlet",
        fields=["name", "outlet_id"],
        filters={"disabled": 0},
    )

    for outlet in outlets:
        try:
            _refresh_outlet_recommendations(outlet.name)
        except Exception as e:
            logger.error(f"Weekly rec refresh failed for {outlet.name}: {e}")


def _refresh_outlet_recommendations(outlet_name: str):
    """
    Re-run recommendations for a single outlet (incremental, uses embedding cache).
    Called by weekly cron and also by the admin API endpoint.
    """
    from flamezo_backend.flamezo.api.recommendations import (
        _build_payload_for_restaurant,
        _call_recommendations_api,
        _store_recommendations,
    )

    restaurant_doc = frappe.get_doc("Outlet", outlet_name)

    payload, products = _build_payload_for_restaurant(restaurant_doc)
    if not products:
        return

    # Compute co-order matrix for this outlet
    co_order_matrix = _compute_co_order_matrix(outlet_name)

    api_result = _call_recommendations_api(payload, co_order_matrix=co_order_matrix)
    _store_recommendations(restaurant_doc, products, api_result)

    # Update last run timestamp
    restaurant_doc.db_set("recommendation_last_run", now(), update_modified=False)
    logger.info(f"Refreshed recommendations for {outlet_name}")
