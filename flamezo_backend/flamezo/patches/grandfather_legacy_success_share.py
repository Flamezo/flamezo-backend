"""
Grandfather Legacy Restaurants at 1.5% Success Share
====================================================

Context: in May 2026 we raised the default Success Share from 1.5% to 3.0%
for *new* restaurants. Existing restaurants must keep their old rate (or
they'd silently see a 2x charge on their next bill).

This patch locks in 1.5% on every Restaurant whose `platform_fee_percent`
is currently NULL or 1.5 (i.e. they were created under the old default).
Restaurants that have been explicitly customised to any other value
(0, 2.0, 5.0, …) are left untouched.

Idempotent: re-running is a no-op once the field is populated.

Run order in patches.txt: must run AFTER `init_commission_engine`
(which creates the column) and AFTER doctype sync (which loads the new
3.0 default for fresh inserts).
"""

import frappe


def execute():
    # The set of `current_value` interpretations we treat as "the old
    # default":
    #   • NULL  — never set, would fall back to whatever the global default
    #             is *today* (now 3.0). Must lock in 1.5.
    #   • 1.5   — explicitly stored. The user is on the old rate, keep it.
    #
    # Anything else (a custom 2.0 negotiated for a partner, etc.) is left
    # alone — that's a deliberate override, not a default-inherited value.
    rows = frappe.db.sql(
        """
        SELECT name, platform_fee_percent
        FROM `tabOutlet`
        WHERE platform_fee_percent IS NULL
           OR ABS(platform_fee_percent - 1.5) < 0.001
        """,
        as_dict=True,
    )

    grandfathered = 0
    for r in rows:
        # Only WRITE for rows that don't already store 1.5 — saves the audit
        # log noise of a no-op update on the (probably much larger) set of
        # already-1.5 restaurants.
        if r["platform_fee_percent"] is None:
            frappe.db.set_value(
                "Outlet",
                r["name"],
                "platform_fee_percent",
                1.5,
                update_modified=False,
            )
            grandfathered += 1

    frappe.db.commit()
    print(
        f"✅ grandfathered {grandfathered} restaurants at 1.5% Success Share "
        f"(of {len(rows)} eligible). New restaurants will use the 3.0% default."
    )
