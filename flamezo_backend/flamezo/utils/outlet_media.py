# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Shared, batched outlet media resolver — used by both the discovery/feed card
formatter (flamezo.py) and outlet detail (outlet.py) so a feed of N outlets
costs a fixed 2 SQL queries total, never N+1 per-card round trips.

Priority per outlet, first non-empty wins:
  1. Curated Gallery — Restaurant Gallery Item, is_selected=1. Within this
     tier, Google Places photos rank first (real, recognisable shots of the
     actual place — the strongest signal we have), then everything else by
     sort_order. This is what a merchant explicitly picked to show off via
     Gallery Management's Active Showcase, plus anything synced from Google.
  2. Food/product photos — Product Media on the outlet's active Menu
     Products, display_order asc. "The food images we use right now" —
     kept as the fallback exactly as before, just resolved in the same
     batched pass instead of a separate code path.
  3. Outlet logo — passed in by the caller (already fetched as part of
     the outlet's own row query, so no extra query needed here).
"""

import frappe


def batch_resolve_outlet_media(outlet_ids, limit_per_outlet=4, logos=None):
    """
    Returns {outlet_id: [{"url", "type", "title"}, ...]}, each list capped at
    limit_per_outlet, ordered by the priority above. Outlets with nothing at
    all (no gallery, no food photos, no logo) map to an empty list — callers
    decide their own final fallback (e.g. a placeholder asset).
    """
    if not outlet_ids:
        return {}

    logos = logos or {}
    result = {oid: [] for oid in outlet_ids}
    placeholders = ",".join(["%s"] * len(outlet_ids))

    # 1. Curated gallery — single query across every outlet. Google Places
    # photos rank first within this tier (source_rank 0), everything else
    # after (source_rank 1), then sort_order — so a merchant's pre-existing
    # menu-photo gallery rows never bury the real Google photos.
    gallery_rows = frappe.db.sql(
        f"""
        SELECT restaurant, url, media_type as type, title, sort_order,
               (source != 'Google Places') as source_rank
        FROM `tabRestaurant Gallery Item`
        WHERE restaurant IN ({placeholders}) AND is_selected = 1
        ORDER BY restaurant, source_rank ASC, sort_order ASC
        """,
        outlet_ids,
        as_dict=True,
    )
    for row in gallery_rows:
        bucket = result[row.restaurant]
        if len(bucket) < limit_per_outlet and row.url:
            bucket.append({"url": row.url, "type": row.type or "Image", "title": row.title or ""})

    # 2. Food/product photos — only queried for outlets still short of the cap,
    # so a fully-curated feed pays zero extra cost for this join.
    needing = [oid for oid in outlet_ids if len(result[oid]) < limit_per_outlet]
    if needing:
        need_placeholders = ",".join(["%s"] * len(needing))
        food_rows = frappe.db.sql(
            f"""
            SELECT p.restaurant as restaurant, pm.media_url as url, pm.media_type as type,
                   p.product_name as title
            FROM `tabProduct Media` pm
            JOIN `tabMenu Product` p ON pm.parent = p.name
            WHERE p.restaurant IN ({need_placeholders}) AND p.is_active = 1
            ORDER BY p.restaurant, p.display_order ASC, pm.display_order ASC
            """,
            needing,
            as_dict=True,
        )
        for row in food_rows:
            bucket = result[row.restaurant]
            if len(bucket) < limit_per_outlet and row.url:
                bucket.append({"url": row.url, "type": row.type or "Image", "title": row.title or ""})

    # 3. Logo — final fallback, no query (caller already has it).
    for oid in outlet_ids:
        bucket = result[oid]
        if not bucket and logos.get(oid):
            bucket.append({"url": logos[oid], "type": "Image", "title": "Logo"})

    return result
