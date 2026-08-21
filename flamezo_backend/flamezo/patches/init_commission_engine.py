"""
Init Commission Engine (Razorpay Route Hybrid)
==============================================

One-shot migration to roll out the cash-commission settlement engine:

  1. Backfill `Restaurant.outstanding_commission_paise = 0` for any rows
     where it's NULL after the schema patch.
  2. Default `Restaurant.route_mode` to `flamezo_hold` so the existing
     payment flow stays untouched until per-restaurant KYC is collected.
  3. Default `Order.settlement_mode` to `flamezo_hold` for historical
     orders so analytics queries don't trip on NULLs.

Idempotent — re-running is a no-op once values are in place.
"""

import frappe


def execute():
    # Restaurants
    frappe.db.sql(
        """
        UPDATE `tabOutlet`
        SET outstanding_commission_paise = COALESCE(outstanding_commission_paise, 0),
            cash_sweep_failure_count    = COALESCE(cash_sweep_failure_count, 0),
            route_mode                  = COALESCE(NULLIF(route_mode, ''), 'flamezo_hold')
        WHERE outstanding_commission_paise IS NULL
           OR cash_sweep_failure_count IS NULL
           OR route_mode IS NULL
           OR route_mode = ''
        """
    )

    # Orders — only backfill settlement_mode where empty so we don't
    # overwrite anything `payments.create_payment_order` already stamped
    # during the rollout overlap window.
    frappe.db.sql(
        """
        UPDATE `tabOrder`
        SET settlement_mode = 'flamezo_hold',
            cash_netoff_applied_paise = COALESCE(cash_netoff_applied_paise, 0)
        WHERE settlement_mode IS NULL OR settlement_mode = ''
        """
    )

    frappe.db.commit()
    print("✅ commission engine init: defaults backfilled.")
