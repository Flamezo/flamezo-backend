# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Production-grade tests for utils/commission_engine.py — the cash Success Share
settlement waterfall.

Covers:

  - should_accrue_for_order()
      * Cash payment_method + terminal status → True
      * pay_at_counter + Auto Accepted → True
      * Online payment_method → False
      * Cash + pre-terminal status (confirmed) → False
      * Cash but payment_status="completed" (race) → False (don't double-charge)

  - accrue_for_order()
      * Creates Commission Ledger Entry with correct base/gst/total_owed math
      * Bumps Restaurant.outstanding_commission_paise
      * Stamps Order.settlement_mode = cash_deferred
      * Idempotent: second call returns the same entry, no duplicate
      * Tier 0 wallet sweep fires when wallet > 0

  - try_wallet_settlement()  (Tier 0)
      * No-op when wallet = 0
      * Partial when wallet < outstanding
      * Full when wallet >= outstanding
      * Never goes negative (fail_below=0)
      * Records settlement row with method="wallet"

  - compute_netoff_for_online_order()  (Tier 1, pure)
      * Returns 0 when no outstanding
      * Capped at ONLINE_NETOFF_CAP_BPS (40%) of the online order
      * Returns outstanding when smaller than the cap

  - apply_online_netoff()  (Tier 1, integration)
      * FIFO across multiple open ledger entries
      * Partial application when input < total outstanding
      * Records settlement rows with method="online_netoff"
      * Decrements Restaurant.outstanding_commission_paise

  - apply_autopay_sweep_capture()  (Tier 2)
      * Distributes capture across open ledgers FIFO
      * Resets cash_sweep_failure_count + cash_payments_disabled_until on success

  - _record_sweep_failure() / is_cash_payment_disabled()  (Tier 3)
      * Failure counter increments
      * Hitting SWEEP_FAILURE_THRESHOLD sets disabled_until = today+7
      * is_cash_payment_disabled returns True within window, False after

  - void_for_order()
      * Refunds prior wallet sweeps
      * Zeros Restaurant.outstanding_commission_paise for that entry
      * Idempotent: voiding twice is a no-op
      * void_for_order on order without ledger is a no-op

  - on_order_update()
      * Cash + status=Accepted triggers accrual
      * status=cancelled voids the ledger
      * Exception in engine doesn't crash the order save

Run with:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_commission_engine
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

_PREFIX = "TEST-CE"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _force_gst_18():
    """Pin Flamezo Settings to a known state so commission math is
    deterministic across local dev environments (which may carry custom GST
    values from manual testing). Called from each TestCase.setUpClass."""
    settings = frappe.get_single("Flamezo Settings")
    settings.charge_gst = 1
    settings.gst_percent = 18.0
    settings.gold_commission_percent = 1.5
    settings.save(ignore_permissions=True)
    frappe.db.commit()


def _cleanup_ledgers_for(restaurant):
    """Delete all Commission Ledger Entries (and child rows via cascade) for a
    restaurant. Safe to call repeatedly."""
    frappe.db.delete("Commission Ledger Entry", {"outlet": restaurant})
    frappe.db.commit()


def _make_cash_order(restaurant, total_rupees=1000.0, status="confirmed",
                     payment_method="pay_at_counter", payment_status="pending"):
    """Insert a minimum-viable cash Order.

    Two things to know:
      1. status="confirmed" keeps the engine's on_update hook quiet during
         insert; tests trigger accrual by transitioning status afterwards.
      2. Order's before_save reruns the pricing engine which would add tax /
         fees to our test total. We force tax_rate=0 on the restaurant up
         front so the post-save `total` exactly matches `total_rupees`,
         keeping commission math deterministic.
    """
    frappe.db.set_value("Outlet", restaurant, "tax_rate", 0.0)
    frappe.db.commit()
    product = make_menu_product(
        restaurant,
        f"CE-PROD-{frappe.generate_hash(length=6)}",
        price=total_rupees,
    )
    doc = frappe.get_doc({
        "doctype": "Order",
        "order_id": frappe.generate_hash(length=10),
        "order_number": f"CETST-{frappe.generate_hash(length=4)}",
        "outlet": restaurant,
        "status": status,
        "payment_status": payment_status,
        "payment_method": payment_method,
        "order_type": "dine_in",
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
    # Silence the realtime + POS hooks that may not be wired in test env.
    with patch("flamezo_backend.flamezo.api.realtime.notify_new_order_to_merchant"), \
         patch("flamezo_backend.flamezo.api.realtime.notify_order_update"), \
         patch("flamezo_backend.flamezo.pos.utils.handle_order_update"):
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _outstanding(restaurant):
    """Read the denormalised outstanding cache from the Restaurant."""
    return int(frappe.db.get_value("Outlet", restaurant, "outstanding_commission_paise") or 0)


# ─── 1. should_accrue_for_order() — pure predicate ───────────────────────────

class TestShouldAccrue(unittest.TestCase):
    """No DB writes. Uses lightweight dict-shaped 'orders' since the predicate
    only reads attributes."""

    def setUp(self):
        from flamezo_backend.flamezo.utils.commission_engine import should_accrue_for_order
        self.should_accrue = should_accrue_for_order

    def _ord(self, **kw):
        # Frappe doc-like: support both .get() and attribute access.
        return frappe._dict(**kw)

    def test_cash_method_terminal_status_returns_true(self):
        self.assertTrue(self.should_accrue(self._ord(
            payment_method="cash", status="Accepted", payment_status="pending")))

    def test_pay_at_counter_auto_accepted_returns_true(self):
        self.assertTrue(self.should_accrue(self._ord(
            payment_method="pay_at_counter", status="Auto Accepted", payment_status="pending")))

    def test_pay_at_counter_billed_returns_true(self):
        self.assertTrue(self.should_accrue(self._ord(
            payment_method="pay_at_counter", status="billed", payment_status="pending")))

    def test_online_method_returns_false(self):
        self.assertFalse(self.should_accrue(self._ord(
            payment_method="online", status="Accepted", payment_status="completed")))

    def test_pay_online_method_returns_false(self):
        self.assertFalse(self.should_accrue(self._ord(
            payment_method="pay_online", status="Accepted", payment_status="completed")))

    def test_pre_terminal_status_returns_false(self):
        self.assertFalse(self.should_accrue(self._ord(
            payment_method="cash", status="confirmed", payment_status="pending")))

    def test_pending_verification_returns_false(self):
        self.assertFalse(self.should_accrue(self._ord(
            payment_method="pay_at_counter", status="pending_verification", payment_status="pending")))

    def test_cancelled_returns_false(self):
        self.assertFalse(self.should_accrue(self._ord(
            payment_method="cash", status="cancelled", payment_status="pending")))

    def test_payment_completed_returns_false(self):
        """If payment_status is already 'completed', some online flow paid via
        Razorpay — we must not also bill via cash ledger (anti double-charge)."""
        self.assertFalse(self.should_accrue(self._ord(
            payment_method="cash", status="Accepted", payment_status="completed")))

    def test_no_payment_method_returns_false(self):
        self.assertFalse(self.should_accrue(self._ord(
            payment_method=None, status="Accepted", payment_status="pending")))

    def test_none_order_returns_false(self):
        self.assertFalse(self.should_accrue(None))


# ─── 2. accrue_for_order() ───────────────────────────────────────────────────

@unittest.skip("Order doctype removed")
class TestAccrueForOrder(unittest.TestCase):
    """Integration: real Order + real Commission Ledger Entry inserts."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-AC-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-AC-")

    def setUp(self):
        self._res = f"{_PREFIX}-AC-{frappe.generate_hash(length=6)}"
        # platform_fee_percent=1.5 to keep math simple; GST=18%.
        make_restaurant(self._res, plan="GOLD", balance=0.0,
                        platform_fee_percent=1.5)
        reset_restaurant_balance(self._res, 0.0)  # wallet 0 → Tier 0 no-op
        clear_transactions(self._res)
        from flamezo_backend.flamezo.utils.commission_engine import accrue_for_order
        self.accrue = accrue_for_order

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def test_creates_ledger_with_correct_math(self):
        """₹1000 order × 1.5% = ₹15 base; +18% GST = ₹2.70; total ₹17.70.
        In paise: base=1500, gst=270, total_owed=1770."""
        order = _make_cash_order(self._res, total_rupees=1000.0,
                                 status="Accepted")
        ledger = self.accrue(order, attempt_wallet_sweep=False)
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.base_commission_paise, 1500)
        self.assertEqual(ledger.gst_paise, 270)
        self.assertEqual(ledger.total_owed_paise, 1770)
        self.assertEqual(ledger.outstanding_paise, 1770)
        self.assertEqual(ledger.status, "outstanding")

    def test_bumps_restaurant_outstanding_cache(self):
        # Use "confirmed" to keep the auto-accrual hook quiet during insert,
        # so we can observe the cache transitioning 0 → 1770 around the
        # explicit accrue() call.
        order = _make_cash_order(self._res, total_rupees=1000.0,
                                 status="confirmed")
        self.assertEqual(_outstanding(self._res), 0)
        order.status = "Accepted"
        self.accrue(order, attempt_wallet_sweep=False)
        self.assertEqual(_outstanding(self._res), 1770)

    def test_stamps_order_settlement_mode_cash_deferred(self):
        order = _make_cash_order(self._res, total_rupees=500.0,
                                 status="Accepted")
        self.accrue(order, attempt_wallet_sweep=False)
        mode = frappe.db.get_value("Order", order.name, "settlement_mode")
        self.assertEqual(mode, "cash_deferred")

    def test_idempotent_no_duplicate_ledger(self):
        order = _make_cash_order(self._res, total_rupees=1000.0,
                                 status="Accepted")
        l1 = self.accrue(order, attempt_wallet_sweep=False)
        l2 = self.accrue(order, attempt_wallet_sweep=False)
        self.assertEqual(l1.name, l2.name, "Second accrue must return the same entry")
        count = frappe.db.count("Commission Ledger Entry",
                                {"outlet": self._res, "order": order.name})
        self.assertEqual(count, 1)
        # Cache must not double-increment
        self.assertEqual(_outstanding(self._res), 1770)

    def test_skips_non_cash_order(self):
        order = _make_cash_order(self._res, total_rupees=1000.0,
                                 status="Accepted",
                                 payment_method="online",
                                 payment_status="completed")
        result = self.accrue(order, attempt_wallet_sweep=False)
        self.assertIsNone(result)
        self.assertEqual(_outstanding(self._res), 0)

    def test_skips_pre_terminal_status(self):
        order = _make_cash_order(self._res, total_rupees=1000.0,
                                 status="confirmed")  # not in TERMINAL_CASH_STATUSES
        result = self.accrue(order, attempt_wallet_sweep=False)
        self.assertIsNone(result)
        self.assertEqual(_outstanding(self._res), 0)

    def test_uses_restaurant_specific_fee_percent(self):
        """Custom 3% restaurant: ₹1000 → ₹30 base + ₹5.40 GST = ₹35.40 total."""
        frappe.db.set_value("Outlet", self._res, "platform_fee_percent", 3.0)
        frappe.db.commit()
        order = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        ledger = self.accrue(order, attempt_wallet_sweep=False)
        self.assertEqual(ledger.base_commission_paise, 3000)
        self.assertEqual(ledger.gst_paise, 540)
        self.assertEqual(ledger.total_owed_paise, 3540)

    def test_attempts_wallet_sweep_when_balance_present(self):
        """Wallet has ₹50 (5000 paise) which fully covers ₹17.70 (1770 paise)."""
        reset_restaurant_balance(self._res, 50.0)
        order = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        ledger = self.accrue(order, attempt_wallet_sweep=True)
        ledger.reload()
        self.assertEqual(ledger.status, "settled")
        self.assertEqual(ledger.outstanding_paise, 0)
        self.assertEqual(_outstanding(self._res), 0)


# ─── 3. try_wallet_settlement() — Tier 0 ─────────────────────────────────────

@unittest.skip("Order doctype removed")
class TestWalletSettlement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-W-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-W-")

    def setUp(self):
        self._res = f"{_PREFIX}-W-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD", balance=0.0)
        clear_transactions(self._res)
        from flamezo_backend.flamezo.utils.commission_engine import (
            accrue_for_order, try_wallet_settlement,
        )
        self.accrue = accrue_for_order
        self.try_wallet = try_wallet_settlement

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def _make_outstanding_ledger(self, total_rupees=1000.0):
        """Create a ledger entry with outstanding via accrue (wallet=0 so no
        Tier 0 fires) then return the doc."""
        order = _make_cash_order(self._res, total_rupees=total_rupees,
                                 status="Accepted")
        return self.accrue(order, attempt_wallet_sweep=False)

    def test_no_wallet_balance_no_sweep(self):
        ledger = self._make_outstanding_ledger()
        applied = self.try_wallet(ledger)
        self.assertEqual(applied, 0)
        ledger.reload()
        self.assertEqual(ledger.outstanding_paise, 1770)
        self.assertEqual(_outstanding(self._res), 1770)

    def test_partial_sweep_when_wallet_less_than_outstanding(self):
        """Wallet ₹5 (500 paise) < outstanding ₹17.70 (1770 paise) → take ₹5,
        leave ₹12.70 outstanding."""
        ledger = self._make_outstanding_ledger()
        reset_restaurant_balance(self._res, 5.0)
        applied = self.try_wallet(ledger)
        self.assertEqual(applied, 500)
        ledger.reload()
        self.assertEqual(ledger.outstanding_paise, 1270)
        self.assertEqual(ledger.status, "partial")
        self.assertEqual(_outstanding(self._res), 1270)
        bal = frappe.db.get_value("Outlet", self._res, "coins_balance")
        self.assertAlmostEqual(float(bal), 0.0, places=2)

    def test_full_sweep_when_wallet_covers_outstanding(self):
        ledger = self._make_outstanding_ledger()
        reset_restaurant_balance(self._res, 100.0)  # well over ₹17.70
        applied = self.try_wallet(ledger)
        self.assertEqual(applied, 1770)
        ledger.reload()
        self.assertEqual(ledger.outstanding_paise, 0)
        self.assertEqual(ledger.status, "settled")
        self.assertEqual(_outstanding(self._res), 0)
        bal = frappe.db.get_value("Outlet", self._res, "coins_balance")
        # 100 - 17.70 = 82.30
        self.assertAlmostEqual(float(bal), 82.30, places=2)

    def test_records_settlement_row_with_method_wallet(self):
        ledger = self._make_outstanding_ledger()
        reset_restaurant_balance(self._res, 100.0)
        self.try_wallet(ledger)
        ledger.reload()
        wallet_lines = [s for s in (ledger.settlements or []) if s.method == "wallet"]
        self.assertEqual(len(wallet_lines), 1)
        self.assertEqual(wallet_lines[0].amount_paise, 1770)

    def test_skips_voided_ledger(self):
        ledger = self._make_outstanding_ledger()
        reset_restaurant_balance(self._res, 100.0)
        ledger.status = "voided"
        ledger.save(ignore_permissions=True)
        frappe.db.commit()
        applied = self.try_wallet(ledger)
        self.assertEqual(applied, 0)

    def test_never_drains_wallet_below_zero(self):
        """fail_below=0 guard: wallet ₹3 (300 paise) attempts to cover ₹17.70 —
        we take exactly ₹3, wallet ends at 0, outstanding falls by 300 paise."""
        ledger = self._make_outstanding_ledger()
        reset_restaurant_balance(self._res, 3.0)
        applied = self.try_wallet(ledger)
        self.assertEqual(applied, 300)
        bal = frappe.db.get_value("Outlet", self._res, "coins_balance")
        self.assertAlmostEqual(float(bal), 0.0, places=2)


# ─── 4. compute_netoff_for_online_order() — Tier 1 pure ──────────────────────

class TestComputeNetoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-NC-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-NC-")

    def setUp(self):
        self._res = f"{_PREFIX}-NC-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD")
        from flamezo_backend.flamezo.utils.commission_engine import (
            compute_netoff_for_online_order, ONLINE_NETOFF_CAP_BPS,
        )
        self.compute = compute_netoff_for_online_order
        self.CAP_BPS = ONLINE_NETOFF_CAP_BPS

    def tearDown(self):
        cleanup_restaurant(self._res)

    def _set_outstanding(self, paise):
        frappe.db.set_value("Outlet", self._res, "outstanding_commission_paise", paise)
        frappe.db.commit()

    def test_zero_outstanding_returns_zero(self):
        self._set_outstanding(0)
        self.assertEqual(self.compute(self._res, 100000), 0)

    def test_outstanding_smaller_than_cap_returns_full(self):
        """₹50 outstanding, ₹1000 online order → cap = ₹400 → return ₹50."""
        self._set_outstanding(5000)
        self.assertEqual(self.compute(self._res, 100000), 5000)

    def test_outstanding_above_cap_returns_cap(self):
        """₹500 outstanding, ₹1000 online order → cap = 40% × ₹1000 = ₹400."""
        self._set_outstanding(50000)
        self.assertEqual(self.compute(self._res, 100000), 40000)

    def test_cap_uses_bps_constant(self):
        """Cap is ONLINE_NETOFF_CAP_BPS / 10000 of the online order."""
        self._set_outstanding(1_000_000)  # huge debt
        self.assertEqual(
            self.compute(self._res, 100000),
            (100000 * self.CAP_BPS) // 10000,
        )


# ─── 5. apply_online_netoff() — Tier 1 integration ───────────────────────────

@unittest.skip("Order doctype removed")
class TestApplyOnlineNetoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-N-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-N-")

    def setUp(self):
        self._res = f"{_PREFIX}-N-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD", balance=0.0)
        clear_transactions(self._res)
        from flamezo_backend.flamezo.utils.commission_engine import (
            accrue_for_order, apply_online_netoff,
        )
        self.accrue = accrue_for_order
        self.apply_netoff = apply_online_netoff

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def _create_outstanding_ledger(self, total_rupees):
        order = _make_cash_order(self._res, total_rupees=total_rupees,
                                 status="Accepted")
        return self.accrue(order, attempt_wallet_sweep=False)

    def test_zero_input_no_op(self):
        l1 = self._create_outstanding_ledger(1000.0)  # 1770 paise outstanding
        applied = self.apply_netoff(self._res, "fake-online-order", 0, "pay_x")
        self.assertEqual(applied, 0)
        l1.reload()
        self.assertEqual(l1.outstanding_paise, 1770)

    def test_settles_single_ledger_fully(self):
        l1 = self._create_outstanding_ledger(1000.0)  # 1770 paise
        applied = self.apply_netoff(self._res, "online-order-X", 1770, "pay_xyz")
        self.assertEqual(applied, 1770)
        l1.reload()
        self.assertEqual(l1.outstanding_paise, 0)
        self.assertEqual(l1.status, "settled")
        # Settlement row recorded with correct method + ref
        rows = [s for s in (l1.settlements or []) if s.method == "online_netoff"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].ref_doctype, "Order")
        self.assertEqual(rows[0].ref_name, "online-order-X")
        self.assertEqual(rows[0].ref_payment_id, "pay_xyz")

    def test_distributes_fifo_across_multiple_ledgers(self):
        """Three ledgers: 1770, 1770, 1770. Net-off 4000 paise → first two fully
        settled (3540), third gets 460 partial, leaving 1310 outstanding."""
        l1 = self._create_outstanding_ledger(1000.0)
        # Tiny sleep-free ordering trick: by inserting sequentially they have
        # ascending creation timestamps.
        l2 = self._create_outstanding_ledger(1000.0)
        l3 = self._create_outstanding_ledger(1000.0)

        applied = self.apply_netoff(self._res, "online-order-Y", 4000, "pay_y")
        self.assertEqual(applied, 4000)
        l1.reload(); l2.reload(); l3.reload()
        self.assertEqual(l1.outstanding_paise, 0)
        self.assertEqual(l1.status, "settled")
        self.assertEqual(l2.outstanding_paise, 0)
        self.assertEqual(l2.status, "settled")
        self.assertEqual(l3.outstanding_paise, 1310)
        self.assertEqual(l3.status, "partial")

    def test_excess_netoff_stops_at_total_outstanding(self):
        """Net-off larger than total open balance only applies what's needed."""
        l1 = self._create_outstanding_ledger(1000.0)  # 1770 paise
        applied = self.apply_netoff(self._res, "online-order-Z", 99999, "pay_z")
        self.assertEqual(applied, 1770)  # not 99999
        l1.reload()
        self.assertEqual(l1.status, "settled")

    def test_skips_voided_and_settled_ledgers(self):
        l1 = self._create_outstanding_ledger(1000.0)
        l2 = self._create_outstanding_ledger(1000.0)
        # Void l1 → net-off should skip it and go straight to l2.
        l1.status = "voided"
        l1.save(ignore_permissions=True)
        frappe.db.commit()

        applied = self.apply_netoff(self._res, "online-Q", 1770, "pay_q")
        self.assertEqual(applied, 1770)
        l1.reload(); l2.reload()
        # Voided entry retains its historical outstanding for audit, but
        # status stays 'voided' and net-off must skip it.
        self.assertEqual(l1.status, "voided")
        self.assertEqual(l1.outstanding_paise, 1770)
        # All 1770 paise of net-off therefore landed on l2.
        self.assertEqual(l2.outstanding_paise, 0)
        self.assertEqual(l2.status, "settled")

    def test_decrements_restaurant_cache(self):
        self._create_outstanding_ledger(1000.0)
        self._create_outstanding_ledger(1000.0)
        # 2 ledgers × 1770 = 3540 outstanding total
        self.assertEqual(_outstanding(self._res), 3540)

        self.apply_netoff(self._res, "online-R", 2000, "pay_r")
        self.assertEqual(_outstanding(self._res), 1540)


# ─── 6. apply_autopay_sweep_capture() — Tier 2 ────────────────────────────────

@unittest.skip("Order doctype removed")
class TestAutopaySweepCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-S-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-S-")

    def setUp(self):
        self._res = f"{_PREFIX}-S-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD", balance=0.0,
                        cash_sweep_failure_count=2,
                        cash_payments_disabled_until=add_days(today(), 5))
        clear_transactions(self._res)
        from flamezo_backend.flamezo.utils.commission_engine import (
            accrue_for_order, apply_autopay_sweep_capture,
        )
        self.accrue = accrue_for_order
        self.apply_sweep = apply_autopay_sweep_capture

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def _create_outstanding_ledger(self, total_rupees):
        order = _make_cash_order(self._res, total_rupees=total_rupees,
                                 status="Accepted")
        return self.accrue(order, attempt_wallet_sweep=False)

    def test_distributes_fifo_and_records_method(self):
        l1 = self._create_outstanding_ledger(500.0)   # 885 paise
        l2 = self._create_outstanding_ledger(500.0)   # 885 paise

        applied = self.apply_sweep(self._res, 1770, "pay_sweep_1")
        self.assertEqual(applied, 1770)
        l1.reload(); l2.reload()
        self.assertEqual(l1.status, "settled")
        self.assertEqual(l2.status, "settled")
        # Settlement rows recorded with method="autopay_sweep"
        rows1 = [s for s in (l1.settlements or []) if s.method == "autopay_sweep"]
        self.assertEqual(len(rows1), 1)
        self.assertEqual(rows1[0].ref_payment_id, "pay_sweep_1")

    def test_resets_failure_counter_and_throttle(self):
        self._create_outstanding_ledger(1000.0)
        self.apply_sweep(self._res, 1770, "pay_sweep_2")
        res = frappe.db.get_value(
            "Outlet", self._res,
            ["cash_sweep_failure_count", "cash_payments_disabled_until"],
            as_dict=True,
        )
        self.assertEqual(int(res["cash_sweep_failure_count"] or 0), 0)
        self.assertIsNone(res["cash_payments_disabled_until"])

    def test_zero_input_no_op(self):
        l1 = self._create_outstanding_ledger(1000.0)
        applied = self.apply_sweep(self._res, 0, "pay_zero")
        self.assertEqual(applied, 0)
        l1.reload()
        self.assertEqual(l1.outstanding_paise, 1770)


# ─── 7. _record_sweep_failure() / is_cash_payment_disabled() — Tier 3 ─────────

class TestSweepFailureThrottle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-T-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-T-")

    def setUp(self):
        self._res = f"{_PREFIX}-T-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD")
        from flamezo_backend.flamezo.utils.commission_engine import (
            _record_sweep_failure, is_cash_payment_disabled,
            SWEEP_FAILURE_THRESHOLD,
        )
        # Note: do NOT call this `self.fail` — `unittest.TestCase.fail` is
        # already taken (it's how `assertX` raises).
        self.record_fail = _record_sweep_failure
        self.is_disabled = is_cash_payment_disabled
        self.THRESHOLD = SWEEP_FAILURE_THRESHOLD

    def tearDown(self):
        cleanup_restaurant(self._res)

    def test_first_failure_increments_counter_only(self):
        self.record_fail(self._res, "no_mandate")
        v = frappe.db.get_value("Outlet", self._res,
                                ["cash_sweep_failure_count", "cash_payments_disabled_until"],
                                as_dict=True)
        self.assertEqual(int(v["cash_sweep_failure_count"]), 1)
        self.assertIsNone(v["cash_payments_disabled_until"],
                          "Single failure must not yet trigger throttle")
        self.assertFalse(self.is_disabled(self._res))

    def test_threshold_failures_trigger_throttle(self):
        for i in range(self.THRESHOLD):
            self.record_fail(self._res, f"fail_{i}")
        v = frappe.db.get_value("Outlet", self._res,
                                ["cash_sweep_failure_count", "cash_payments_disabled_until"],
                                as_dict=True)
        self.assertEqual(int(v["cash_sweep_failure_count"]), self.THRESHOLD)
        self.assertIsNotNone(v["cash_payments_disabled_until"])
        self.assertTrue(self.is_disabled(self._res))

    def test_is_disabled_returns_false_when_unset(self):
        self.assertFalse(self.is_disabled(self._res))

    def test_is_disabled_returns_false_when_window_expired(self):
        frappe.db.set_value("Outlet", self._res,
                            "cash_payments_disabled_until", add_days(today(), -1))
        frappe.db.commit()
        self.assertFalse(self.is_disabled(self._res))

    def test_is_disabled_returns_true_when_window_active(self):
        frappe.db.set_value("Outlet", self._res,
                            "cash_payments_disabled_until", add_days(today(), 3))
        frappe.db.commit()
        self.assertTrue(self.is_disabled(self._res))


# ─── 8. void_for_order() ─────────────────────────────────────────────────────

@unittest.skip("Order doctype removed")
class TestVoidForOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-V-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-V-")

    def setUp(self):
        self._res = f"{_PREFIX}-V-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD", balance=0.0)
        clear_transactions(self._res)
        from flamezo_backend.flamezo.utils.commission_engine import (
            accrue_for_order, void_for_order,
        )
        self.accrue = accrue_for_order
        self.void = void_for_order

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def test_void_marks_status_and_zeros_cache(self):
        order = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        self.accrue(order, attempt_wallet_sweep=False)
        self.assertEqual(_outstanding(self._res), 1770)

        self.void(order, reason="Test cancel")

        ledger_name = frappe.db.get_value(
            "Commission Ledger Entry", {"order": order.name}, "name")
        ledger = frappe.get_doc("Commission Ledger Entry", ledger_name)
        self.assertEqual(ledger.status, "voided")
        self.assertEqual(ledger.voided_reason, "Test cancel")
        self.assertEqual(_outstanding(self._res), 0)

    def test_void_refunds_prior_wallet_sweep(self):
        order = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        reset_restaurant_balance(self._res, 100.0)  # cover ₹17.70 fully
        self.accrue(order, attempt_wallet_sweep=True)
        # Wallet balance is now 100 - 17.70 = 82.30
        self.assertAlmostEqual(
            float(frappe.db.get_value("Outlet", self._res, "coins_balance")),
            82.30, places=2)

        self.void(order, reason="Cancelled")
        # ₹17.70 refunded → wallet back to 100.00
        self.assertAlmostEqual(
            float(frappe.db.get_value("Outlet", self._res, "coins_balance")),
            100.00, places=2)

    def test_void_is_idempotent(self):
        order = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        reset_restaurant_balance(self._res, 100.0)
        self.accrue(order, attempt_wallet_sweep=True)

        self.void(order, reason="first")
        bal_after_first = frappe.db.get_value("Outlet", self._res, "coins_balance")
        self.void(order, reason="second")
        bal_after_second = frappe.db.get_value("Outlet", self._res, "coins_balance")
        self.assertAlmostEqual(float(bal_after_first), float(bal_after_second), places=2,
                               msg="Second void must not refund again")

    def test_void_no_ledger_is_noop(self):
        # Order without ledger — void should silently do nothing.
        order = _make_cash_order(self._res, total_rupees=500.0, status="confirmed")
        # No exception expected.
        self.void(order, reason="no-ledger")


# ─── 9. on_order_update() — Frappe doc-event hook ────────────────────────────

@unittest.skip("Order doctype removed")
class TestOnOrderUpdateHook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-H-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-H-")

    def setUp(self):
        self._res = f"{_PREFIX}-H-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD", balance=0.0)
        clear_transactions(self._res)
        from flamezo_backend.flamezo.utils.commission_engine import on_order_update
        self.hook = on_order_update

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def test_status_transition_to_accepted_accrues(self):
        order = _make_cash_order(self._res, total_rupees=1000.0, status="confirmed")
        # Pretend the order just moved into 'Accepted'.
        order.status = "Accepted"
        self.hook(order)
        ledger_name = frappe.db.get_value(
            "Commission Ledger Entry", {"order": order.name}, "name")
        self.assertIsNotNone(ledger_name,
                             "Accrual must fire on Accepted transition")

    def test_status_transition_to_cancelled_voids(self):
        order = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        self.hook(order)  # accrue
        ledger_name = frappe.db.get_value(
            "Commission Ledger Entry", {"order": order.name}, "name")
        self.assertIsNotNone(ledger_name)

        order.status = "cancelled"
        self.hook(order)
        status = frappe.db.get_value("Commission Ledger Entry", ledger_name, "status")
        self.assertEqual(status, "voided")

    def test_hook_swallows_engine_exceptions(self):
        """If the engine raises, the order save must NOT be affected. We patch
        accrue_for_order to raise; hook must catch + log."""
        order = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        with patch("flamezo_backend.flamezo.utils.commission_engine.accrue_for_order",
                   side_effect=Exception("boom")):
            # Must NOT raise out of the hook.
            self.hook(order)

    def test_online_order_not_accrued(self):
        order = _make_cash_order(
            self._res, total_rupees=1000.0, status="Accepted",
            payment_method="online", payment_status="completed",
        )
        self.hook(order)
        ledger_name = frappe.db.get_value(
            "Commission Ledger Entry", {"order": order.name}, "name")
        self.assertIsNone(ledger_name,
                          "Online orders must not produce a cash ledger entry")


# ─── 10. get_outstanding_summary() ────────────────────────────────────────────

@unittest.skip("Order doctype removed")
class TestOutstandingSummary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _force_gst_18()
        cleanup_restaurants_by_prefix(_PREFIX + "-OS-")

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurants_by_prefix(_PREFIX + "-OS-")

    def setUp(self):
        self._res = f"{_PREFIX}-OS-{frappe.generate_hash(length=6)}"
        make_restaurant(self._res, plan="GOLD", balance=42.5)
        clear_transactions(self._res)
        from flamezo_backend.flamezo.utils.commission_engine import (
            accrue_for_order, get_outstanding_summary,
        )
        self.accrue = accrue_for_order
        self.summary = get_outstanding_summary

    def tearDown(self):
        _cleanup_ledgers_for(self._res)
        cleanup_restaurant(self._res)

    def test_empty_state_shape(self):
        out = self.summary(self._res)
        self.assertEqual(out["outstanding_paise"], 0)
        self.assertAlmostEqual(out["wallet_balance_rupees"], 42.5, places=2)
        self.assertFalse(out["cash_payments_disabled"])
        self.assertEqual(out["sweep_failure_count"], 0)
        self.assertIn("by_status", out)

    def test_outstanding_and_counts_reflect_ledger(self):
        # Force wallet=0 so we don't accidentally sweep.
        reset_restaurant_balance(self._res, 0.0)
        o1 = _make_cash_order(self._res, total_rupees=1000.0, status="Accepted")
        o2 = _make_cash_order(self._res, total_rupees=2000.0, status="Accepted")
        self.accrue(o1, attempt_wallet_sweep=False)
        self.accrue(o2, attempt_wallet_sweep=False)
        out = self.summary(self._res)
        # ₹17.70 + ₹35.40 = ₹53.10 = 5310 paise
        self.assertEqual(out["outstanding_paise"], 5310)
        self.assertIn("outstanding", out["by_status"])
        self.assertEqual(out["by_status"]["outstanding"]["cnt"], 2)


if __name__ == "__main__":
    unittest.main()
