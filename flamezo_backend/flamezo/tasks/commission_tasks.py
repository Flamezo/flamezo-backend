"""
Flamezo Commission Engine — Scheduled Tasks
============================================

Three cadences:

  • Daily   — `retry_wallet_settlements` sweeps outstanding ledger entries
              that wallet balance now covers (e.g. restaurant topped up
              after a busy cash day).
  • Weekly  — `weekly_autopay_sweep` is Tier 2: triggers a Razorpay
              mandate charge for any restaurant whose outstanding balance
              exceeds the minimum sweep floor (₹50).
  • Daily   — `clear_expired_throttles` unsets `cash_payments_disabled_until`
              when the cooldown window has passed.

Each task is idempotent and individually scoped — a failure on one
restaurant never blocks the next. All errors are logged via
`frappe.log_error` for ops review.
"""

import frappe
from frappe.utils import getdate

from flamezo_backend.flamezo.utils import commission_engine


def retry_wallet_settlements():
    """Daily: walk every open ledger entry where the restaurant now has
    wallet balance, and apply Tier 0 settlement. Catches the case where a
    restaurant topped up their wallet after cash orders accrued.

    Cheap enough to run daily because we filter by `outstanding > 0` in SQL
    and the typical open-ledger count per restaurant is small."""
    rows = frappe.db.sql(
        """
        SELECT cle.name AS ledger_name
        FROM `tabCommission Ledger Entry` cle
        JOIN `tabOutlet` r ON r.name = cle.restaurant
        WHERE cle.status IN ('outstanding', 'partial')
          AND cle.outstanding_paise > 0
          AND r.coins_balance > 0
        ORDER BY cle.creation ASC
        """,
        as_dict=True,
    )
    swept = 0
    for row in rows:
        try:
            ledger = frappe.get_doc("Commission Ledger Entry", row["ledger_name"])
            applied = commission_engine.try_wallet_settlement(ledger)
            if applied > 0:
                swept += 1
        except Exception as e:
            frappe.log_error(
                f"Daily wallet retry failed for {row['ledger_name']}: {e}"[:140],
                "commission_tasks.retry_wallet",
            )
    return {"success": True, "ledgers_swept": swept}


def weekly_autopay_sweep():
    """Tier 2: for every restaurant with outstanding cash commission above
    the autopay floor, trigger a Razorpay recurring charge via their
    mandate. Settlement is recorded asynchronously when the
    `payment.captured` webhook fires (notes.type == 'cash_sweep').

    Restaurants without an active mandate get a failure recorded — three
    consecutive failures triggers Tier 3 (cash payments disabled, forcing
    online-only mode to drain the balance via Tier 1 net-off)."""
    restaurants = frappe.db.sql(
        """
        SELECT name FROM `tabOutlet`
        WHERE COALESCE(outstanding_commission_paise, 0) >= %s
          AND is_active = 1
        """,
        (commission_engine.MIN_AUTOPAY_SWEEP_PAISE,),
        as_dict=True,
    )

    results = {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    for row in restaurants:
        results["attempted"] += 1
        try:
            res = commission_engine.sweep_via_autopay(row["name"])
            if res.get("success"):
                if res.get("skipped"):
                    results["skipped"] += 1
                else:
                    results["succeeded"] += 1
            else:
                results["failed"] += 1
        except Exception as e:
            results["failed"] += 1
            frappe.log_error(
                f"Weekly sweep crashed for {row['name']}: {e}"[:140],
                "commission_tasks.weekly_sweep",
            )

    return {"success": True, **results}


def clear_expired_throttles():
    """Daily: unset `cash_payments_disabled_until` on restaurants whose
    cooldown has passed AND whose outstanding balance is now zero. If the
    cooldown ended but they're still in arrears, leave it set so the next
    sweep cycle decides — calling Tier 2 here would short-circuit the
    weekly cadence."""
    today = getdate()
    frappe.db.sql(
        """
        UPDATE `tabOutlet`
        SET cash_payments_disabled_until = NULL
        WHERE cash_payments_disabled_until IS NOT NULL
          AND cash_payments_disabled_until < %s
          AND COALESCE(outstanding_commission_paise, 0) = 0
        """,
        (today,),
    )
    frappe.db.commit()
    return {"success": True}
