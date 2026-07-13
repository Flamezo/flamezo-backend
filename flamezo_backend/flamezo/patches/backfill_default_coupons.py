# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Patch: Backfill the 4 default offers on every existing restaurant.

`create_default_coupons()` already runs when a NEW restaurant is created, seeding
four default offers:
  SAVE50 / SAVE100 / SAVE200  (offer_type = auto)          — the 3 normal offers
  REVIEW50                    (offer_type = google_review)  — the Google-review offer

Restaurants created before that hook existed have none of these. This patch seeds
them for every existing restaurant so the offers show up after migrate + restart.

It is fully idempotent: create_default_coupons() checks whether each coupon code
already exists for the restaurant and skips it, so re-running migrate never
duplicates offers.
"""

import frappe
from flamezo_backend.flamezo.doctype.restaurant.default_coupons import create_default_coupons


def execute():
    restaurants = frappe.get_all("Restaurant", pluck="name")
    total_created = 0
    for name in restaurants:
        try:
            total_created += create_default_coupons(name) or 0
        except Exception as e:
            # One bad restaurant must never fail the whole migrate.
            frappe.log_error(
                f"backfill_default_coupons: {name}: {str(e)}"[:140],
                "Default Coupon Backfill",
            )
    frappe.db.commit()
    frappe.logger().info(
        f"backfill_default_coupons: seeded {total_created} default coupon(s) across {len(restaurants)} restaurant(s)"
    )
