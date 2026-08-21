"""
Flamezo Commission Engine
=========================

Single source of truth for collecting the Success Share Flamezo owes itself
on every restaurant order (default 3% for new restaurants, 1.5% for
restaurants grandfathered before May 2026). Two flows coexist:

  ONLINE   — customer pays via Razorpay → Route split deducts commission at
             source (97% / 98.5% to restaurant linked account, 3% / 1.5%
             to Flamezo — depending on the restaurant's configured rate).
             Handled inline in `payments.create_payment_order` via the
             `razorpay_route` adapter; no Commission Ledger Entry needed.

  CASH     — customer pays cash at counter → Flamezo never touches the money.
             A Commission Ledger Entry is created representing the liability
             and a settlement waterfall recovers the amount without ever
             charging the restaurant upfront:

                Tier 0  wallet           — deduct from coins_balance if any
                Tier 1  online_netoff    — auto-attach to the next online order
                                           Razorpay transfer so Flamezo keeps
                                           the commission portion + cash debt
                Tier 2  autopay_sweep    — weekly mandate charge for any
                                           leftover balance
                Tier 3  throttle         — auto-disable cash payment method
                                           after N consecutive sweep failures

The engine is intentionally agnostic of *how* online payments are routed. If
the restaurant later switches to per-restaurant Razorpay keys or a different
PSP entirely, the waterfall keeps working — only the Tier 1 hook point in the
online payment path needs to know about Route specifics.

Every public function in this module is idempotent and safe to call from
webhooks, scheduler tasks, or admin tools.
"""

from __future__ import annotations

import math
from typing import Optional

import frappe
from frappe.utils import now_datetime, getdate

# ── Public constants ────────────────────────────────────────────────────────

# Order statuses that mean "cash has been (or will imminently be) collected".
# We accrue commission on first transition into any of these — and void on
# transitions to `cancelled`.
TERMINAL_CASH_STATUSES = {
    "Accepted",
    "Auto Accepted",
    "preparing",
    "ready",
    "In Billing",
    "delivered",
    "billed",
}

CASH_PAYMENT_METHODS = {"cash", "pay_at_counter"}

# How much of a single online order we are willing to consume for Tier 1
# net-off. Capped so a restaurant doesn't get its entire online payout eaten
# by one big cash debt — they still need cash flow to operate.
ONLINE_NETOFF_CAP_BPS = 4000  # 40.00% of the order, in basis points

# Tier 3 throttle: after this many failed weekly autopay sweeps, the
# restaurant's `cash_payments_disabled_until` is set to force online-only mode
# so Tier 1 can drain the outstanding balance.
SWEEP_FAILURE_THRESHOLD = 3

# Min outstanding to bother sweeping via autopay (avoid ₹1 sweeps).
MIN_AUTOPAY_SWEEP_PAISE = 5000  # ₹50

# Wallet-debit transaction type used for Tier 0 sweeps. Matches the existing
# Coin Transaction `transaction_type` enum so we don't fragment ledger views.
WALLET_TXN_TYPE = "Commission Deduction"


# ── Internal helpers ────────────────────────────────────────────────────────

def _get_commission_percent(restaurant) -> float:
    """Resolve the platform fee percent for a restaurant, falling back to the
    global GOLD default. Kept as a single helper so all accrual + split math
    agrees on the same number."""
    rate = frappe.db.get_value("Outlet", restaurant, "platform_fee_percent")
    if rate is None:
        rate = frappe.db.get_single_value("Flamezo Settings", "gold_commission_percent") or 3.0
    return float(rate)


def _get_gst_percent() -> float:
    settings = frappe.get_single("Flamezo Settings")
    if not bool(settings.charge_gst):
        return 0.0
    return float(settings.gst_percent or 18.0)


def _compute_commission_paise(order_total_paise: int, fee_percent: float, gst_percent: float):
    """Compute (base_commission_paise, gst_paise, total_owed_paise) using
    floor() so we never round *up* against the restaurant. Pure function."""
    base = int(math.floor(order_total_paise * (fee_percent / 100.0)))
    gst = int(math.floor(base * (gst_percent / 100.0)))
    return base, gst, base + gst


def _bump_restaurant_outstanding(restaurant: str, delta_paise: int):
    """Increment / decrement Restaurant.outstanding_commission_paise atomically
    via SQL. The field is the fast denormalised cache that the engine reads
    to decide whether to sweep; Commission Ledger Entry rows remain the
    authoritative source of truth."""
    if delta_paise == 0:
        return
    frappe.db.sql(
        """
        UPDATE `tabOutlet`
        SET outstanding_commission_paise = GREATEST(
            0,
            COALESCE(outstanding_commission_paise, 0) + %s
        )
        WHERE name = %s
        """,
        (int(delta_paise), restaurant),
    )


def _record_settlement(ledger_entry_name: str, method: str, amount_paise: int,
                       ref_doctype: str = "", ref_name: str = "",
                       ref_payment_id: str = "", note: str = "") -> "frappe.Document":
    """Append a settlement line to a Commission Ledger Entry, update its
    rollup totals + status, and decrement the Restaurant cache. Returns the
    refreshed ledger doc. Idempotency is the caller's responsibility — the
    engine guarantees it for each method (see settle_via_*)."""
    ledger = frappe.get_doc("Commission Ledger Entry", ledger_entry_name)
    if ledger.status == "voided":
        return ledger
    ledger.append("settlements", {
        "method": method,
        "amount_paise": int(amount_paise),
        "ref_doctype": ref_doctype,
        "ref_name": ref_name,
        "ref_payment_id": ref_payment_id,
        "settled_at": now_datetime(),
        "note": note,
    })
    ledger.save(ignore_permissions=True)
    _bump_restaurant_outstanding(ledger.outlet, -int(amount_paise))
    return ledger


# ── Accrual ─────────────────────────────────────────────────────────────────

def should_accrue_for_order(order_doc) -> bool:
    """Predicate: is this order eligible to produce a Commission Ledger Entry?

    Used by hooks.py on Order.on_update — kept as a pure function so it's easy
    to test and reuse from admin tools (e.g. backfill scripts).
    """
    if not order_doc:
        return False
    if (order_doc.get("payment_method") or "").lower() not in CASH_PAYMENT_METHODS:
        return False
    if order_doc.get("status") not in TERMINAL_CASH_STATUSES:
        return False
    # Online orders that happen to have payment_method=cash by accident are
    # ignored — if payment_status is already 'completed' something has paid
    # via Razorpay and we mustn't double-charge.
    if (order_doc.get("payment_status") or "").lower() == "completed":
        return False
    return True


def accrue_for_order(order, attempt_wallet_sweep: bool = True) -> Optional["frappe.Document"]:
    """Create (or fetch existing) Commission Ledger Entry for a cash order and
    immediately try Tier 0 (wallet) settlement. Idempotent — safe to call
    repeatedly from Order on_update hooks.

    Returns the Commission Ledger Entry doc, or None if not applicable.
    """
    order_doc = order if hasattr(order, "name") else frappe.get_doc("Order", order)

    if not should_accrue_for_order(order_doc):
        return None

    # Idempotency: one ledger per order. `order` field is unique on the doctype.
    existing_name = frappe.db.get_value("Commission Ledger Entry", {"order": order_doc.name}, "name")
    if existing_name:
        ledger = frappe.get_doc("Commission Ledger Entry", existing_name)
        # If a previous accrual was voided (e.g. order was cancelled then
        # un-cancelled), don't auto-resurrect. Manual admin action required.
        if ledger.status != "voided" and attempt_wallet_sweep and ledger.outstanding_paise > 0:
            try_wallet_settlement(ledger)
        return ledger

    fee_percent = _get_commission_percent(order_doc.outlet)
    gst_percent = _get_gst_percent()
    total_paise = int(round(float(order_doc.total or 0) * 100))
    base, gst, total_owed = _compute_commission_paise(total_paise, fee_percent, gst_percent)

    ledger = frappe.get_doc({
        "doctype": "Commission Ledger Entry",
        "outlet": order_doc.outlet,
        "order": order_doc.name,
        "accrual_source": "pay_at_counter" if order_doc.get("payment_method") == "pay_at_counter" else "cash_order",
        "status": "outstanding",
        "order_total_paise": total_paise,
        "platform_fee_percent": fee_percent,
        "base_commission_paise": base,
        "gst_percent": gst_percent,
        "gst_paise": gst,
        "total_owed_paise": total_owed,
        "settled_paise": 0,
        "outstanding_paise": total_owed,
        "notes": f"Accrued on cash order {order_doc.name} (₹{total_paise/100:.2f} GMV).",
    })
    ledger.insert(ignore_permissions=True)
    _bump_restaurant_outstanding(order_doc.outlet, total_owed)

    # Mark the order so dashboards/reports can show "commission tracked"
    try:
        frappe.db.set_value("Order", order_doc.name, {
            "settlement_mode": "cash_deferred",
            "platform_fee_amount": base,
        }, update_modified=False)
    except Exception:
        # Order may not have these fields yet during the migration window —
        # the patch installs them. Don't block accrual on it.
        pass

    frappe.db.commit()

    if attempt_wallet_sweep:
        try_wallet_settlement(ledger)

    return ledger


def on_order_update(order_doc, method=None):  # noqa: ARG001 — `method` is part of the Frappe hook signature
    """Frappe `on_update` hook for Order. Handles two transitions:

      • Cash order moves to a terminal cash status → accrue.
      • Order moves to `cancelled` → void any prior accrual + refund wallet.

    Wrapped in a broad except so a commission-engine bug never blocks an
    order save (the engine sits in the merchant's critical path)."""
    try:
        status = (order_doc.get("status") or "").lower()
        if status == "cancelled":
            void_for_order(order_doc.name, reason="Order cancelled")
            return

        if should_accrue_for_order(order_doc):
            accrue_for_order(order_doc)
    except Exception as e:
        frappe.log_error(
            f"commission_engine.on_order_update failed for {getattr(order_doc, 'name', '?')}: {e}",
            "commission_engine.hook"
        )


def void_for_order(order, reason: str = "Order cancelled"):
    """Void the ledger entry for an order (called from cancellation hook).
    Reverses any wallet deductions already made for this order so the
    restaurant gets their coins back. Idempotent."""
    order_name = order if isinstance(order, str) else order.name
    ledger_name = frappe.db.get_value("Commission Ledger Entry", {"order": order_name}, "name")
    if not ledger_name:
        return
    ledger = frappe.get_doc("Commission Ledger Entry", ledger_name)
    if ledger.status == "voided":
        return

    # Refund any wallet sweeps tied to this ledger
    from flamezo_backend.flamezo.api.coin_billing import refund_coins
    for s in (ledger.settlements or []):
        if s.method == "wallet" and int(s.amount_paise or 0) > 0:
            try:
                refund_coins(
                    restaurant=ledger.outlet,
                    amount=int(s.amount_paise) / 100.0,
                    description=f"Refund: cash commission voided for order {order_name} ({reason})",
                    ref_doctype="Commission Ledger Entry",
                    ref_name=ledger.name,
                )
            except Exception as e:
                frappe.log_error(
                    f"Failed to refund wallet sweep for voided ledger {ledger.name}: {e}",
                    "commission_engine.void"
                )

    # Wipe out remaining outstanding from the Restaurant cache
    _bump_restaurant_outstanding(ledger.outlet, -int(ledger.outstanding_paise or 0))

    ledger.status = "voided"
    ledger.voided_reason = reason
    ledger.save(ignore_permissions=True)
    frappe.db.commit()


# ── Tier 0 — Wallet sweep ───────────────────────────────────────────────────

def try_wallet_settlement(ledger) -> int:
    """Tier 0: drain as much of `ledger.outstanding_paise` as the restaurant's
    wallet allows. Returns paise actually deducted.

    Uses the existing coin_billing module so wallet accounting (balance,
    transaction log, auto-recharge hooks) all stay consistent. We deliberately
    pass `fail_below=0` here — for commission collection we will *never* let
    the wallet go negative; the next tier picks up the slack."""
    if not ledger or ledger.status == "voided":
        return 0
    outstanding = int(ledger.outstanding_paise or 0)
    if outstanding <= 0:
        return 0

    # Read wallet balance in paise
    balance_rupees = frappe.db.get_value("Outlet", ledger.outlet, "coins_balance") or 0
    balance_paise = int(round(float(balance_rupees) * 100))
    if balance_paise <= 0:
        return 0

    take_paise = min(outstanding, balance_paise)
    take_rupees = take_paise / 100.0

    from flamezo_backend.flamezo.api.coin_billing import record_transaction
    try:
        record_transaction(
            restaurant=ledger.outlet,
            txn_type=WALLET_TXN_TYPE,
            amount=take_rupees,
            description=(
                f"Cash commission settled from wallet for ledger {ledger.name} "
                f"(₹{take_rupees:.2f} of ₹{outstanding/100:.2f} outstanding)"
            ),
            ref_doctype="Commission Ledger Entry",
            ref_name=ledger.name,
            fail_below=0,  # Never go negative for commission collection
        )
    except Exception as e:
        # Wallet too low or some race — Tier 1 will handle it.
        frappe.log_error(
            f"Wallet sweep skipped for ledger {ledger.name}: {e}",
            "commission_engine.tier0"
        )
        return 0

    _record_settlement(
        ledger.name,
        method="wallet",
        amount_paise=take_paise,
        ref_doctype="Outlet",
        ref_name=ledger.outlet,
        note=f"Wallet balance was ₹{balance_rupees:.2f}",
    )
    return take_paise


# ── Tier 1 — Online net-off ─────────────────────────────────────────────────

def compute_netoff_for_online_order(restaurant: str, online_order_total_paise: int) -> int:
    """How much outstanding cash commission should be folded into the platform
    fee portion of the next online order's Razorpay split? Pure decision
    function — does not mutate state.

    Caps at `ONLINE_NETOFF_CAP_BPS` of the online order so the restaurant
    isn't left with zero settlement on a big online ticket.
    """
    outstanding = int(frappe.db.get_value("Outlet", restaurant, "outstanding_commission_paise") or 0)
    if outstanding <= 0:
        return 0
    cap = int(math.floor(online_order_total_paise * ONLINE_NETOFF_CAP_BPS / 10000))
    return min(outstanding, cap)


def apply_online_netoff(restaurant: str, online_order_name: str,
                        netoff_amount_paise: int, razorpay_payment_id: str = "") -> int:
    """Tier 1: when an online order is *captured* (Razorpay confirms payment),
    distribute the platform's extra-take across the restaurant's oldest
    outstanding Commission Ledger Entries, FIFO.

    `netoff_amount_paise` should be what was actually held back from the
    restaurant's transfer in the Route split (i.e. the value that
    `payments.create_payment_order` injected into the platform-fee portion
    on top of the base Success Share %).

    Returns the total paise actually applied across ledgers (may be < input
    if outstanding shrank between order creation and capture).
    """
    remaining = int(netoff_amount_paise)
    if remaining <= 0:
        return 0

    open_ledgers = frappe.get_all(
        "Commission Ledger Entry",
        filters={
            "outlet": restaurant,
            "status": ["in", ["outstanding", "partial"]],
        },
        fields=["name", "outstanding_paise"],
        order_by="creation asc",
        limit_page_length=200,
    )

    applied_total = 0
    for row in open_ledgers:
        if remaining <= 0:
            break
        slice_paise = min(int(row.outstanding_paise or 0), remaining)
        if slice_paise <= 0:
            continue
        _record_settlement(
            row.name,
            method="online_netoff",
            amount_paise=slice_paise,
            ref_doctype="Order",
            ref_name=online_order_name,
            ref_payment_id=razorpay_payment_id,
            note=f"Recovered via online order {online_order_name}",
        )
        remaining -= slice_paise
        applied_total += slice_paise

    return applied_total


# ── Tier 2 — Autopay sweep ──────────────────────────────────────────────────

def sweep_via_autopay(restaurant: str) -> dict:
    """Tier 2: charge the full outstanding cash commission via the restaurant's
    Razorpay autopay mandate. Returns a result dict for the caller to log /
    report. Does not raise — failures are recorded on the restaurant's
    `cash_sweep_failure_count`.

    This reuses the same RBI-compliant pre-debit order + recurring payment
    pattern that `payments.charge_monthly_bill` already uses; the worker
    learns about success via the standard payment.captured webhook (which
    sees `notes.type == "cash_sweep"` and re-enters this engine to settle).
    """
    outstanding = int(frappe.db.get_value("Outlet", restaurant, "outstanding_commission_paise") or 0)
    if outstanding < MIN_AUTOPAY_SWEEP_PAISE:
        return {"success": True, "skipped": "below_min", "outstanding": outstanding}

    res = frappe.get_doc("Outlet", restaurant)
    if res.mandate_status != "active" or not res.razorpay_token_id or not res.razorpay_customer_id:
        _record_sweep_failure(restaurant, "no_active_mandate")
        return {"success": False, "error": "no_active_mandate"}

    # Build the charge
    from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client
    import time

    client = get_razorpay_client()
    payment_after_ts = int(time.time()) + (36 * 3600) + (5 * 60)  # RBI 36h pre-debit

    try:
        rzp_order = client.order.create({
            "amount": outstanding,
            "currency": "INR",
            "payment_capture": True,
            "receipt": f"cashsweep_{restaurant[:20]}_{int(time.time())}",
            "notification": {
                "token_id": res.razorpay_token_id,
                "payment_after": payment_after_ts,
            },
            "notes": {
                "restaurant": restaurant,
                "type": "cash_sweep",
                "outstanding_paise": outstanding,
            },
        })
        order_id = rzp_order.get("id")

        contact = res.get("owner_phone") or "9999999999"
        email = res.get("owner_email") or f"billing@{restaurant.replace(' ', '').lower()}.com"

        payment = client.payment.createRecurring({
            "email": email,
            "contact": contact,
            "amount": outstanding,
            "currency": "INR",
            "order_id": order_id,
            "customer_id": res.razorpay_customer_id,
            "token": res.razorpay_token_id,
            "recurring": True,
            "description": f"Flamezo cash commission sweep — ₹{outstanding/100:.2f}",
            "notes": {
                "restaurant": restaurant,
                "type": "cash_sweep",
                "outstanding_paise": outstanding,
            },
        })
        return {
            "success": True,
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment.get("id") if isinstance(payment, dict) else None,
            "amount_paise": outstanding,
        }
    except Exception as e:
        _record_sweep_failure(restaurant, str(e))
        return {"success": False, "error": str(e)}


def apply_autopay_sweep_capture(restaurant: str, amount_paise: int, razorpay_payment_id: str) -> int:
    """Called from the payment.captured webhook when `notes.type == 'cash_sweep'`.
    Distributes the captured amount across open ledger entries FIFO, exactly
    like Tier 1, but with method=`autopay_sweep` for audit clarity."""
    remaining = int(amount_paise)
    if remaining <= 0:
        return 0

    open_ledgers = frappe.get_all(
        "Commission Ledger Entry",
        filters={"outlet": restaurant, "status": ["in", ["outstanding", "partial"]]},
        fields=["name", "outstanding_paise"],
        order_by="creation asc",
        limit_page_length=500,
    )

    applied = 0
    for row in open_ledgers:
        if remaining <= 0:
            break
        slice_paise = min(int(row.outstanding_paise or 0), remaining)
        if slice_paise <= 0:
            continue
        _record_settlement(
            row.name,
            method="autopay_sweep",
            amount_paise=slice_paise,
            ref_doctype="Razorpay Payment",
            ref_name=razorpay_payment_id,
            ref_payment_id=razorpay_payment_id,
            note="Weekly autopay sweep",
        )
        remaining -= slice_paise
        applied += slice_paise

    # Successful sweep clears the failure counter / throttle
    frappe.db.set_value("Outlet", restaurant, {
        "cash_sweep_failure_count": 0,
        "cash_payments_disabled_until": None,
    })
    frappe.db.commit()
    return applied


# ── Tier 3 — Throttle ───────────────────────────────────────────────────────

def _record_sweep_failure(restaurant: str, reason: str):
    """Increment the failure counter on the Restaurant; activate Tier 3
    throttle if we hit the threshold."""
    count = (frappe.db.get_value("Outlet", restaurant, "cash_sweep_failure_count") or 0) + 1
    payload = {"cash_sweep_failure_count": count, "last_cash_sweep_error": reason[:140]}
    if count >= SWEEP_FAILURE_THRESHOLD:
        # Disable cash for 7 days, forcing online-only mode so Tier 1 drains
        # the outstanding balance.
        from frappe.utils import add_days
        payload["cash_payments_disabled_until"] = add_days(getdate(), 7)
    frappe.db.set_value("Outlet", restaurant, payload)
    frappe.db.commit()


def is_cash_payment_disabled(restaurant: str) -> bool:
    """Hook for the customer-facing payment-method picker: when True, the
    UI should hide the 'pay at counter' option until the restaurant catches
    up via online net-off."""
    until = frappe.db.get_value("Outlet", restaurant, "cash_payments_disabled_until")
    if not until:
        return False
    until_date = getdate(until)
    today = getdate()
    if not until_date or not today:
        return False
    return until_date >= today


# ── Read-only views (used by dashboards + the public commission API) ────────

def get_outstanding_summary(restaurant: str) -> dict:
    """Compact summary of a restaurant's commission state — for the merchant
    dashboard widget. Built off the Restaurant cache + a single aggregate
    query for richness."""
    res = frappe.db.get_value("Outlet",
        restaurant,
        ["outstanding_commission_paise", "cash_sweep_failure_count",
         "cash_payments_disabled_until", "coins_balance"],
        as_dict=True,
    ) or {}

    by_status = frappe.db.sql(
        """
        SELECT status, COUNT(*) AS cnt, COALESCE(SUM(total_owed_paise), 0) AS owed,
               COALESCE(SUM(settled_paise), 0) AS settled,
               COALESCE(SUM(outstanding_paise), 0) AS outstanding
        FROM `tabCommission Ledger Entry`
        WHERE outlet = %s
        GROUP BY status
        """,
        (restaurant,),
        as_dict=True,
    )
    counts = {row["status"]: row for row in by_status}

    return {
        "outstanding_paise": int(res.get("outstanding_commission_paise") or 0),
        "wallet_balance_rupees": float(res.get("coins_balance") or 0),
        "cash_payments_disabled": is_cash_payment_disabled(restaurant),
        "cash_payments_disabled_until": res.get("cash_payments_disabled_until"),
        "sweep_failure_count": int(res.get("cash_sweep_failure_count") or 0),
        "by_status": counts,
    }

