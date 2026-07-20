"""
Public Commission API
=====================

Merchant dashboard + ops endpoints for the cash commission engine. Pure
thin wrappers over `utils.commission_engine` and `utils.razorpay_route` —
no business logic lives here.
"""

import frappe
from frappe import _

from flamezo_backend.flamezo.utils import commission_engine
from flamezo_backend.flamezo.utils import razorpay_route as route_adapter
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api


@frappe.whitelist()
def get_commission_status(restaurant_id):
    """Compact dashboard view of where the restaurant stands on cash
    commission: outstanding, wallet balance, throttle state, count by
    ledger status."""
    name = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    return {"success": True, "data": commission_engine.get_outstanding_summary(name)}


@frappe.whitelist()
def list_ledger_entries(restaurant_id, status=None, limit=50, offset=0):
    """Paginated Commission Ledger history. `status` may be
    'outstanding' / 'partial' / 'settled' / 'voided' or omitted for all."""
    name = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    filters = {"restaurant": name}
    if status:
        filters["status"] = status

    entries = frappe.db.get_list(
        "Commission Ledger Entry",
        filters=filters,
        fields=[
            "name", "order", "status", "accrued_at", "settled_at",
            "order_total_paise", "base_commission_paise", "gst_paise",
            "total_owed_paise", "settled_paise", "outstanding_paise",
            "accrual_source",
        ],
        order_by="creation desc",
        limit_page_length=int(limit),
        limit_start=int(offset),
    )
    return {"success": True, "data": entries}


@frappe.whitelist()
def get_ledger_entry(restaurant_id, ledger_name):
    """Full Commission Ledger Entry incl. settlement child rows. Used by
    drill-down view in the merchant dashboard."""
    name = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    if frappe.db.get_value("Commission Ledger Entry", ledger_name, "restaurant") != name:
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("Commission Ledger Entry", ledger_name)
    return {
        "success": True,
        "data": {
            "name": doc.name,
            "order": doc.order,
            "status": doc.status,
            "accrued_at": doc.accrued_at,
            "settled_at": doc.settled_at,
            "voided_reason": doc.voided_reason,
            "amounts": {
                "order_total_paise": doc.order_total_paise,
                "platform_fee_percent": doc.platform_fee_percent,
                "base_commission_paise": doc.base_commission_paise,
                "gst_percent": doc.gst_percent,
                "gst_paise": doc.gst_paise,
                "total_owed_paise": doc.total_owed_paise,
                "settled_paise": doc.settled_paise,
                "outstanding_paise": doc.outstanding_paise,
            },
            "settlements": [
                {
                    "method": s.method,
                    "amount_paise": s.amount_paise,
                    "ref_doctype": s.ref_doctype,
                    "ref_name": s.ref_name,
                    "ref_payment_id": s.ref_payment_id,
                    "settled_at": s.settled_at,
                    "note": s.note,
                }
                for s in (doc.settlements or [])
            ],
            "notes": doc.notes,
        },
    }


@frappe.whitelist()
def submit_route_kyc(restaurant_id, legal_name=None, business_type=None,
                     pan_number=None, bank_account_number=None, bank_ifsc=None,
                     bank_holder_name=None):
    """Collect Route KYC fields from the merchant dashboard onboarding form
    and trigger Linked Account creation. Idempotent — re-submitting only
    overwrites the fields the merchant explicitly passes.

    On success the Restaurant moves into `route_mode = flamezo_hold` with
    `razorpay_kyc_status = under_review`. KYC outcome arrives via webhook
    (`account.activated` flips it to `direct_split` automatically).
    """
    name = validate_restaurant_for_api(restaurant_id, frappe.session.user)

    update = {}
    if legal_name is not None:
        update["legal_name"] = legal_name
    if business_type is not None:
        update["business_type"] = business_type
    if pan_number is not None:
        update["pan_number"] = (pan_number or "").strip().upper()
    if bank_account_number is not None:
        update["bank_account_number"] = bank_account_number
    if bank_ifsc is not None:
        update["bank_ifsc"] = (bank_ifsc or "").strip().upper()
    if bank_holder_name is not None:
        update["bank_holder_name"] = bank_holder_name

    if update:
        frappe.db.set_value("Restaurant", name, update)
        frappe.db.commit()

    return route_adapter.ensure_linked_account(name)


@frappe.whitelist()
def sync_route_kyc_status(restaurant_id):
    """Manual sync triggered by the Sync button on the merchant's Route/payout page.

    Handles all three states in one shot:
      1. No account_id (orphan) — query Razorpay by reference_id, save the ID,
         then fall through to KYC sync.
      2. Account exists, status still pending — pull live status from Razorpay.
      3. Account exists, status already final — return current state, no API call.
    """
    import requests as _requests
    from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config

    name = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    res = frappe.get_doc("Restaurant", name)
    current = (res.get("razorpay_kyc_status") or "").lower()

    # ── Pass 1: orphan reconnect (no account_id saved) ────────────────────────
    if not res.get("razorpay_account_id"):
        cfg = get_razorpay_config()
        auth = (cfg.get("key_id"), cfg.get("key_secret"))
        try:
            resp = _requests.get(
                "https://api.razorpay.com/v2/accounts",
                auth=auth,
                params={"count": 1, "reference_id": name},
                timeout=15,
            )
            items = resp.json().get("items") or []
            if items:
                account_id = items[0].get("id")
                if account_id:
                    frappe.db.set_value("Restaurant", name, "razorpay_account_id", account_id)
                    frappe.db.commit()
                    res.reload()
            else:
                return {"success": True, "kyc_status": "not_started", "synced": False,
                        "message": "No Razorpay account found for this restaurant."}
        except Exception as e:
            frappe.log_error(f"sync_route_kyc_status orphan lookup failed for {name}: {e}",
                             "razorpay_route.sync_button")
            return {"success": False, "error": str(e)}

    # ── Pass 2: KYC status sync ───────────────────────────────────────────────
    current = (res.get("razorpay_kyc_status") or "").lower()
    if current in ("activated", "rejected", "suspended"):
        return {"success": True, "kyc_status": current, "synced": False,
                "message": "Status is already final — nothing to sync."}

    result = route_adapter.reconcile_kyc_status(res)
    return {
        "success": result.get("success", False),
        "kyc_status": result.get("kyc_status") or current,
        "synced": bool(result.get("changed")),
    }


def reconcile_all_pending_kyc():
    """Scheduled (daily): two-pass self-healing for Route linked accounts.

    Pass 1 — KYC status sync: for every restaurant that has a linked account
    ID but is still pending, pull the live status from Razorpay and update the
    DB. Catches missed `account.*` webhooks so merchants don't stay stuck in
    flamezo_hold after Razorpay approves them.

    Pass 2 — Orphan reconnect: for every restaurant with NO linked account ID,
    ask Razorpay whether an account already exists for that reference_id (our
    restaurant doc name). If yes, save the ID and sync the KYC status. Catches
    the rare case where account creation succeeded on Razorpay but our DB write
    failed before storing the ID.
    """
    import requests as _requests
    from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config

    # ── Pass 1: KYC status sync ───────────────────────────────────────────────
    pending = frappe.get_all(
        "Restaurant",
        filters={
            "razorpay_account_id": ["is", "set"],
            "razorpay_kyc_status": ["in", ["under_review", "needs_clarification", ""]],
        },
        pluck="name",
    )
    for rname in pending:
        try:
            route_adapter.reconcile_kyc_status(rname)
        except Exception as e:
            frappe.log_error(f"reconcile_all_pending_kyc {rname}: {e}", "razorpay_route.reconcile_all")

    # ── Pass 2: Orphan reconnect ──────────────────────────────────────────────
    orphans = frappe.get_all(
        "Restaurant",
        filters={"razorpay_account_id": ["in", ["", None]]},
        fields=["name"],
        pluck="name",
    )
    if not orphans:
        return

    cfg = get_razorpay_config()
    auth = (cfg.get("key_id"), cfg.get("key_secret"))

    for rname in orphans:
        try:
            # Razorpay uses our doc name as the reference_id when we call
            # ensure_linked_account — search by it to find any orphaned account.
            resp = _requests.get(
                "https://api.razorpay.com/v2/accounts",
                auth=auth,
                params={"count": 1, "reference_id": rname},
                timeout=15,
            )
            items = resp.json().get("items") or []
            if not items:
                continue

            account_id = items[0].get("id")
            live_status = (items[0].get("status") or "").lower()
            if not account_id:
                continue

            # Link the account and sync status in one shot.
            frappe.db.set_value("Restaurant", rname, "razorpay_account_id", account_id)
            frappe.db.commit()
            route_adapter.reconcile_kyc_status(rname)
            frappe.log_error(
                f"Orphan reconnected: {rname} → {account_id} (status={live_status})",
                "razorpay_route.orphan_reconnect",
            )
        except Exception as e:
            frappe.log_error(f"Orphan reconnect failed for {rname}: {e}", "razorpay_route.orphan_reconnect")


@frappe.whitelist()
def trigger_manual_sweep(restaurant_id):
    """Admin / merchant tool: force a Tier 2 autopay sweep right now
    instead of waiting for the weekly cadence. Useful when a merchant just
    set up their mandate after a big cash day.

    Per-restaurant rate-limited to one call per minute via Frappe's
    `frappe.cache` to prevent accidental double-charges from impatient
    clicks."""
    name = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    cache_key = f"cash_sweep_manual:{name}"
    if frappe.cache().get_value(cache_key):
        return {"success": False, "error": "rate_limited", "retry_after_sec": 60}
    frappe.cache().set_value(cache_key, "1", expires_in_sec=60)
    return commission_engine.sweep_via_autopay(name)


@frappe.whitelist()
def admin_void_ledger(restaurant_id, ledger_name, reason):
    """Admin override: void a Commission Ledger Entry (e.g. dispute, bad
    accrual). Requires System Manager. Refunds any wallet sweeps already
    applied to the entry."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    name = validate_restaurant_for_api(restaurant_id, frappe.session.user)
    if frappe.db.get_value("Commission Ledger Entry", ledger_name, "restaurant") != name:
        frappe.throw(_("Ledger entry does not belong to this restaurant"))

    order = frappe.db.get_value("Commission Ledger Entry", ledger_name, "order")
    commission_engine.void_for_order(order, reason=reason or "Admin override")
    return {"success": True, "voided": ledger_name}
