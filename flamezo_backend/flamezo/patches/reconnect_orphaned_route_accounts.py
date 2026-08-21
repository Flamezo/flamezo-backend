"""
Reconnect orphaned Razorpay Route linked accounts.
==================================================

Background: linked-account creation used to be non-atomic — an account could be
created on Razorpay (reference_id = restaurant id) while a mid-flow failure
prevented us from saving `razorpay_account_id` locally. That left the account
"orphaned": Razorpay has it, our DB doesn't, and every re-submit hit Razorpay's
"reference_id already in use" error ("This code is already in use").

The code fix (persist the id immediately after creation) prevents NEW orphans;
this one-time patch heals the known EXISTING one so no manual bench-console step
is needed on production.

Idempotent + safe:
  • only writes when the restaurant exists AND its razorpay_account_id is blank,
  • no-op on environments that don't have the restaurant (local / test).

The account id below was read from the Razorpay Route dashboard
(Route → Linked Accounts → search the restaurant's reference_id).
"""

import frappe

# restaurant_name (LIKE match) → orphaned Razorpay linked account id
ORPHANS = {
    "%Roller%": "acc_T520xuhcesjzs7",   # Roller Coaster Cafe (apfastfoodsurat@gmail.com)
}


def execute():
    for name_like, account_id in ORPHANS.items():
        rname = frappe.db.get_value("Outlet", {"restaurant_name": ["like", name_like]}, "name")
        if not rname:
            continue  # restaurant not on this site
        if frappe.db.get_value("Outlet", rname, "razorpay_account_id"):
            continue  # already linked — never overwrite a real value
        frappe.db.set_value("Outlet", rname, {
            "razorpay_account_id": account_id,
            "razorpay_kyc_status": "under_review",
            "route_mode": "flamezo_hold",
        })
        print(f"reconnect_orphaned_route_accounts: {rname} -> {account_id}")
    frappe.db.commit()
