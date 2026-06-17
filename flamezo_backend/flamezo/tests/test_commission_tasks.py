# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Production-grade tests for tasks/commission_tasks.py — the scheduled
side of the Success Share engine.

Covers:

  - retry_wallet_settlements()
      * Only sweeps ledgers where the restaurant now has wallet balance
      * Idempotent — running twice on a fully-settled ledger is a no-op
      * Voided ledgers ignored

  - weekly_autopay_sweep()
      * Filters to active restaurants with outstanding >= MIN_AUTOPAY_SWEEP_PAISE
      * Calls sweep_via_autopay for each eligible restaurant
      * Skips restaurants below the floor

  - clear_expired_throttles()
      * Only clears when cooldown date is in the past AND outstanding = 0
      * Leaves still-in-arrears restaurants in throttle even after date passes

Run with:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_commission_tasks
"""

import unittest
from unittest.mock import patch
import frappe
from frappe.utils import today, add_days

from flamezo_backend.flamezo.tests.utils import (
    make_restaurant,
    make_menu_product,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    reset_restaurant_balance,
    clear_transactions,
)

_PREFIX = "TEST-CT"


def _cleanup_ledgers_for(restaurant):
    frappe.db.delete("Commission Ledger Entry", {"restaurant": restaurant})
    frappe.db.commit()


def _make_cash_order(restaurant, total_rupees=1000.0, status="Accepted",
                     payment_method="pay_at_counter"):
    # Force tax_rate=0 so post-save Order.total exactly matches total_rupees
    # (the pricing engine in Order.before_save would otherwise add tax).
    frappe.db.set_value("Restaurant", restaurant, "tax_rate", 0.0)
    frappe.db.commit()
    product = make_menu_product(
        restaurant,
        f"CT-PROD-{frappe.generate_hash(length=6)}",
        price=total_rupees,
    )
    doc = frappe.get_doc({
        "doctype": "Order",
        "order_id": frappe.generate_hash(length=10),
        "order_number": f"CTTST-{frappe.generate_hash(length=4)}",
        "restaurant": restaurant,
        "status": "confirmed",  # keep hook quiet during insert
        "payment_status": "pending",
        "payment_method": payment_method,
        "subtotal": total_rupees,
        "total": total_rupees,
        "order_items": [{
            "product": product.name,
            "product_name": product.product_name,
            "quantity": 1,
            "unit_price": total_rupees,
            "total_price": total_rupees,
        }],
    })
    with patch("flamezo_backend.flamezo.api.realtime.notify_new_order_to_merchant"), \
         patch("flamezo_backend.flamezo.api.realtime.notify_order_update"), \
         patch("flamezo_backend.flamezo.pos.utils.handle_order_update"):
        doc.insert(ignore_permissions=True)
    # Now transition into terminal status (which would normally fire the
    # accrual hook — for these tasks tests we want to accrue explicitly).
    frappe.db.set_value("Order", doc.name, "status", status)
    frappe.db.commit()
    doc.reload()
    return doc


# ─── 1. retry_wallet_settlements() ───────────────────────────────────────────

@unittest.skip("Order doctype removed")
class TestRetryWalletSettlements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-RW-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-RW-")

    def setUp(self):
        self._res = f"{_PREFIX}-RW-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD", balance=0.0)
        clear_transactions(self._res)
        from flamezo_backend.flamezo.tasks.commission_tasks import retry_wallet_settlements
        from flamezo_backend.flamezo.utils.commission_engine import accrue_for_order
        self.task = retry_wallet_settlements
        self.accrue = accrue_for_order

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def test_no_outstanding_no_op(self):
        result = self.task()
        self.assertEqual(result["success"], True)
        self.assertEqual(result["ledgers_swept"], 0)

    def test_sweeps_eligible_ledger_when_wallet_topped_up(self):
        """Accrue with wallet=0 (no sweep). Then top up the wallet. The daily
        retry task should sweep on the next run."""
        order = _make_cash_order(self._res, total_rupees=1000.0)
        ledger = self.accrue(order, attempt_wallet_sweep=False)
        self.assertEqual(ledger.outstanding_paise, 1770)
        # Restaurant tops up later.
        reset_restaurant_balance(self._res, 50.0)
        # Run the task.
        result = self.task()
        self.assertGreaterEqual(result["ledgers_swept"], 1)
        ledger.reload()
        self.assertEqual(ledger.status, "settled")

    def test_skips_when_wallet_zero(self):
        order = _make_cash_order(self._res, total_rupees=1000.0)
        ledger = self.accrue(order, attempt_wallet_sweep=False)
        # Wallet stays at 0 — SQL filter excludes this row.
        result = self.task()
        self.assertEqual(result["ledgers_swept"], 0)
        ledger.reload()
        self.assertEqual(ledger.outstanding_paise, 1770)

    def test_skips_voided_ledgers(self):
        order = _make_cash_order(self._res, total_rupees=1000.0)
        ledger = self.accrue(order, attempt_wallet_sweep=False)
        ledger.status = "voided"
        ledger.save(ignore_permissions=True)
        reset_restaurant_balance(self._res, 100.0)
        frappe.db.commit()

        result = self.task()
        self.assertEqual(result["ledgers_swept"], 0)
        # Wallet untouched
        bal = frappe.db.get_value("Restaurant", self._res, "coins_balance")
        self.assertAlmostEqual(float(bal), 100.0, places=2)


# ─── 2. weekly_autopay_sweep() ───────────────────────────────────────────────

class TestWeeklyAutopaySweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-WS-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-WS-")

    def setUp(self):
        self._sfx = frappe.generate_hash(length=6)
        from flamezo_backend.flamezo.tasks.commission_tasks import weekly_autopay_sweep
        self.task = weekly_autopay_sweep

    def tearDown(self):
        for tag in ["ELIG", "SMALL", "INACT"]:
            cleanup_restaurant(f"{_PREFIX}-WS-{tag}-{self._sfx}")

    @patch("flamezo_backend.flamezo.utils.commission_engine.sweep_via_autopay")
    def test_sweeps_only_eligible_restaurants(self, mock_sweep):
        """Three restaurants:
          ELIG : active, outstanding 10000 → eligible
          SMALL: active, outstanding 100   → below MIN_AUTOPAY_SWEEP_PAISE (5000)
          INACT: inactive, outstanding 10000 → filtered out
        """
        mock_sweep.return_value = {"success": True}

        elig = f"{_PREFIX}-WS-ELIG-{self._sfx}"
        small = f"{_PREFIX}-WS-SMALL-{self._sfx}"
        inact = f"{_PREFIX}-WS-INACT-{self._sfx}"

        make_restaurant(elig, plan="GOLD", is_active=1,
                        outstanding_commission_paise=10_000)
        make_restaurant(small, plan="GOLD", is_active=1,
                        outstanding_commission_paise=100)
        make_restaurant(inact, plan="GOLD", is_active=0,
                        outstanding_commission_paise=10_000)

        result = self.task()
        # ELIG is the only one that should reach sweep_via_autopay.
        called_restaurants = [c.args[0] if c.args else c.kwargs.get("restaurant")
                              for c in mock_sweep.call_args_list]
        self.assertIn(elig, called_restaurants)
        self.assertNotIn(small, called_restaurants)
        self.assertNotIn(inact, called_restaurants)
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["succeeded"], 1)

    @patch("flamezo_backend.flamezo.utils.commission_engine.sweep_via_autopay")
    def test_counts_failures(self, mock_sweep):
        mock_sweep.return_value = {"success": False, "error": "no_active_mandate"}

        elig = f"{_PREFIX}-WS-ELIG-{self._sfx}"
        make_restaurant(elig, plan="GOLD", is_active=1,
                        outstanding_commission_paise=10_000)

        result = self.task()
        self.assertEqual(result["failed"], 1)


# ─── 3. clear_expired_throttles() ────────────────────────────────────────────

class TestClearExpiredThrottles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-CT-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-CT-")

    def setUp(self):
        self._sfx = frappe.generate_hash(length=6)
        from flamezo_backend.flamezo.tasks.commission_tasks import clear_expired_throttles
        self.task = clear_expired_throttles

    def tearDown(self):
        for tag in ["EXPCLEAN", "EXPDEBT", "ACTCLEAN"]:
            cleanup_restaurant(f"{_PREFIX}-CT-{tag}-{self._sfx}")

    def test_clears_expired_when_outstanding_zero(self):
        name = f"{_PREFIX}-CT-EXPCLEAN-{self._sfx}"
        make_restaurant(name, plan="GOLD",
                        cash_payments_disabled_until=add_days(today(), -2),
                        outstanding_commission_paise=0)
        self.task()
        until = frappe.db.get_value("Restaurant", name, "cash_payments_disabled_until")
        self.assertIsNone(until, "Expired throttle with zero debt must be cleared")

    def test_keeps_throttle_when_still_in_arrears(self):
        name = f"{_PREFIX}-CT-EXPDEBT-{self._sfx}"
        make_restaurant(name, plan="GOLD",
                        cash_payments_disabled_until=add_days(today(), -2),
                        outstanding_commission_paise=5_000)
        self.task()
        until = frappe.db.get_value("Restaurant", name, "cash_payments_disabled_until")
        self.assertIsNotNone(until,
                             "Throttle must persist while outstanding > 0 "
                             "to force online-only mode")

    def test_leaves_active_throttle_alone(self):
        """Throttle date is in the future — must not be cleared regardless."""
        future = add_days(today(), 5)
        name = f"{_PREFIX}-CT-ACTCLEAN-{self._sfx}"
        make_restaurant(name, plan="GOLD",
                        cash_payments_disabled_until=future,
                        outstanding_commission_paise=0)
        self.task()
        until = frappe.db.get_value("Restaurant", name, "cash_payments_disabled_until")
        self.assertIsNotNone(until)


if __name__ == "__main__":
    unittest.main()
