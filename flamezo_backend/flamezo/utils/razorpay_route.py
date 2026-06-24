"""
Razorpay Route Adapter
======================

Thin, replaceable wrapper around Razorpay's Route APIs (Linked Accounts +
split-payment transfers). Designed so the rest of the codebase only depends
on this module's interface — when we eventually switch to per-restaurant
Razorpay keys, alternate PSPs, or off-platform settlements, only this file
changes.

Three responsibilities:

  1. **Linked Account onboarding** — `ensure_linked_account(restaurant)`:
     idempotent create-or-fetch of the restaurant's Razorpay merchant
     account under Flamezo's parent. Pushes KYC fields from the Restaurant
     doc. Updates `razorpay_kyc_status` from webhook events (see
     `update_kyc_status`).

  2. **Order split spec** — `build_transfer_payload(restaurant, total_paise,
     platform_keep_paise)`: returns the `transfers=[{...}]` array to pass to
     `client.order.create()` so Razorpay automatically splits the captured
     payment between Flamezo and the restaurant.

  3. **Refund reversal** — `reverse_transfer(order)`: when refunding a Route
     order, also reverse the merchant portion so Flamezo doesn't eat the
     loss.

  Plus a small `RouteDecision` helper that the payments API uses to choose
  between `direct_split` (Route-enabled), `flamezo_hold` (pre-KYC), and
  `disabled` (compliance pause). Decoupling the *policy* from the call sites
  keeps the rest of the code clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import frappe

from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client


# ── Policy: pick the settlement mode for an online order ────────────────────

@dataclass
class RouteDecision:
    mode: str  # 'direct_split' | 'flamezo_hold' | 'disabled'
    linked_account_id: Optional[str]
    reason: str


def decide_route_mode(restaurant) -> RouteDecision:
    """Decide how to handle the next online order for this restaurant.

    Rules (deliberately conservative — failing closed to `flamezo_hold` keeps
    money flowing even when Route is misconfigured):

      • restaurant.route_mode == 'disabled' → disabled  (compliance suspension)
      • KYC activated + linked account on file → direct_split
      • anything else → flamezo_hold  (Flamezo collects, settles to restaurant
                                       offline / weekly NEFT)
    """
    res = restaurant if hasattr(restaurant, "name") else frappe.get_doc("Restaurant", restaurant)
    explicit = (res.get("route_mode") or "").strip()

    if explicit == "disabled":
        return RouteDecision("disabled", None, "explicit_disabled")
    if explicit == "flamezo_hold":
        return RouteDecision("flamezo_hold", None, "explicit_hold")

    linked_id = res.get("razorpay_account_id")
    kyc_status = (res.get("razorpay_kyc_status") or "").lower()
    if linked_id and kyc_status == "activated":
        return RouteDecision("direct_split", linked_id, "kyc_activated")

    return RouteDecision("flamezo_hold", None, f"kyc_{kyc_status or 'missing'}")


# ── Linked account lifecycle ────────────────────────────────────────────────

def ensure_linked_account(restaurant) -> dict:
    """Create the Razorpay Linked Account for a restaurant if it doesn't have
    one yet, or return the existing record. Idempotent.

    The caller is responsible for collecting KYC fields onto the Restaurant
    doc beforehand:
      • legal_name, business_type, pan_number
      • bank_account_number, bank_ifsc, bank_holder_name
      • owner_email, owner_phone, address, city, state, zip_code, gst_number

    On success, writes `razorpay_account_id` and `razorpay_kyc_status =
    under_review` back to the Restaurant. KYC outcome arrives later via the
    `account.*` webhook events (see `webhooks.handle_account_status`).
    """
    res = restaurant if hasattr(restaurant, "name") else frappe.get_doc("Restaurant", restaurant)

    if res.get("razorpay_account_id"):
        return {
            "success": True,
            "linked_account_id": res.razorpay_account_id,
            "kyc_status": res.razorpay_kyc_status,
            "created": False,
        }

    missing = _missing_kyc_fields(res)
    if missing:
        return {
            "success": False,
            "error": "incomplete_kyc",
            "missing_fields": missing,
        }

    client = get_razorpay_client()

    # Build payload per Razorpay Route 'Accounts' API. The exact attribute
    # names mirror the Razorpay v2 schema — kept here as a single source of
    # truth so changes track upstream API revisions in one place.
    _state = _normalize_state(res.get("state") or "")
    payload = {
        "email": res.owner_email,
        "phone": _normalize_phone(res.owner_phone),
        "type": "route",
        "reference_id": res.name,
        "legal_business_name": res.get("legal_name") or res.restaurant_name,
        "business_type": res.get("business_type") or "proprietorship",
        "contact_name": res.get("owner_name") or res.restaurant_name,
        "profile": {
            "category": "food",
            "subcategory": "restaurant",
            "addresses": {
                "registered": {
                    "street1": (res.get("address") or "").strip()[:100],
                    "street2": (res.get("city") or res.get("address") or "").strip()[:100],
                    "city": (res.get("city") or "").strip(),
                    "state": _state,
                    "postal_code": (res.get("zip_code") or "").strip(),
                    "country": "IN",
                }
            },
        },
        # For proprietorship the owner's PAN goes in the stakeholder KYC only.
        # Sending it in legal_info.pan causes Razorpay to reject it as a
        # "company PAN" mismatch. Only non-proprietorship types use this field.
        "legal_info": {
            **({"pan": res.get("pan_number", "").strip()} if (res.get("business_type") or "proprietorship") != "proprietorship" and res.get("pan_number") else {}),
            **({"gst": res.get("gst_number", "").strip()} if res.get("gst_number") else {}),
        },
    }

    try:
        # Razorpay's Python SDK exposes the v2 endpoint as `client.account`.
        # We use `request` for portability across SDK versions where the
        # helper isn't present.
        if hasattr(client, "account") and hasattr(client.account, "create"):
            account = client.account.create(payload)
        else:
            account = client.request("POST", "/v2/accounts", params=payload)

        account_id = account.get("id")
        if not account_id:
            raise Exception(f"Razorpay returned no account id: {account!r}")

        # Now create the Stakeholder + Bank Account product config so the
        # account can actually receive payouts.
        _attach_bank_and_stakeholder(client, account_id, res)

        frappe.db.set_value("Restaurant", res.name, {
            "razorpay_account_id": account_id,
            "razorpay_kyc_status": "under_review",
            "route_mode": "flamezo_hold",  # stays in hold until KYC clears
        })
        frappe.db.commit()

        return {
            "success": True,
            "linked_account_id": account_id,
            "kyc_status": "under_review",
            "created": True,
        }
    except Exception as e:
        frappe.log_error(
            f"Linked account creation failed for {res.name}: {e}",
            "razorpay_route.ensure_linked_account",
        )
        return {"success": False, "error": str(e)}


def _attach_bank_and_stakeholder(client, account_id: str, res):
    """Push stakeholder + bank account into a freshly-created Linked Account.
    Uses direct requests calls — Razorpay SDK's client.request() is unreliable
    for v2 sub-resource endpoints. Two-step: create product first, then PATCH
    settlements (Razorpay rejects settlements in the initial POST body)."""
    import requests as _requests
    from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config
    cfg = get_razorpay_config()
    auth = (cfg["key_id"], cfg["key_secret"])
    BASE = "https://api.razorpay.com"

    try:
        _requests.post(
            f"{BASE}/v2/accounts/{account_id}/stakeholders",
            auth=auth,
            json={
                "name": res.get("owner_name") or res.restaurant_name,
                "email": res.owner_email,
                "phone": {"primary": _normalize_phone(res.owner_phone)},
                "kyc": {"pan": (res.get("pan_number") or "").strip()},
                "addresses": {
                    "residential": {
                        "street": (res.get("address") or "").strip()[:100],
                        "city": (res.get("city") or "").strip(),
                        "state": _normalize_state(res.get("state") or ""),
                        "postal_code": (res.get("zip_code") or "").strip(),
                        "country": "IN",
                    }
                },
            },
        ).raise_for_status()
    except Exception as e:
        frappe.log_error(f"Stakeholder attach failed for {account_id}: {e}", "razorpay_route.stakeholder")

    try:
        # Step 1: create Route product (no settlements in body — Razorpay rejects it)
        r = _requests.post(
            f"{BASE}/v2/accounts/{account_id}/products",
            auth=auth,
            json={"product_name": "route", "tnc_accepted": True},
        )
        product_id = r.json().get("id")
        if not product_id:
            raise Exception(f"No product id returned: {r.text}")

        # Step 2: PATCH settlements onto the product
        _requests.patch(
            f"{BASE}/v2/accounts/{account_id}/products/{product_id}",
            auth=auth,
            json={
                "settlements": {
                    "account_number": res.get("bank_account_number") or "",
                    "ifsc_code": res.get("bank_ifsc") or "",
                    "beneficiary_name": res.get("bank_holder_name") or res.restaurant_name,
                },
                "tnc_accepted": True,
            },
        ).raise_for_status()
    except Exception as e:
        frappe.log_error(f"Product/bank config failed for {account_id}: {e}", "razorpay_route.product")


def update_kyc_status(linked_account_id: str, new_status: str, raw_event: Optional[dict] = None):
    """Called from the `account.*` webhook handler. Maps Razorpay's status
    strings to our internal enum and writes back to the Restaurant doc.

    Razorpay statuses encountered: `created`, `activated`, `under_review`,
    `needs_clarification`, `rejected`, `suspended`.
    """
    res_name = frappe.db.get_value("Restaurant", {"razorpay_account_id": linked_account_id})
    if not res_name:
        return

    mapping = {
        "activated": "activated",
        # Razorpay's instant-activation fast path for clean proprietorships /
        # auto-approved KYC. Treat exactly like a manual `activated`.
        "instantly_activated": "activated",
        # KYC paperwork accepted but full activation still pending Razorpay
        # ops review — account cannot yet receive transfers, so we keep
        # `route_mode = flamezo_hold` (handled below).
        "activated_kyc_pending": "under_review",
        "under_review": "under_review",
        "needs_clarification": "needs_clarification",
        "rejected": "rejected",
        "suspended": "suspended",
    }
    internal = mapping.get((new_status or "").lower(), "under_review")

    update = {"razorpay_kyc_status": internal}
    # Flip route_mode automatically — admins can override any time.
    if internal == "activated":
        update["route_mode"] = "direct_split"
    elif internal in ("rejected", "suspended"):
        update["route_mode"] = "flamezo_hold"

    frappe.db.set_value("Restaurant", res_name, update)
    frappe.db.commit()


# ── Order split spec ────────────────────────────────────────────────────────

def build_transfer_payload(linked_account_id: str, total_paise: int,
                           platform_keep_paise: int, order_name: str = "") -> list:
    """Build the `transfers` array for `client.order.create()`. Razorpay's
    semantics: any amount listed under `transfers` is routed to the linked
    account; the *remainder* of the captured payment stays in the parent
    (Flamezo) account.

    We compute the merchant slice as `total - platform_keep` so the caller
    only needs to think about what Flamezo wants to keep (Success Share +
    any cash net-off).
    """
    merchant_slice = max(0, total_paise - max(0, int(platform_keep_paise)))
    return [{
        "account": linked_account_id,
        "amount": merchant_slice,
        "currency": "INR",
        "on_hold": 0,
        "notes": {"order": order_name} if order_name else {},
    }]


def suspend_linked_account(restaurant) -> dict:
    """Suspend a restaurant's Razorpay linked account so no further transfers
    can be routed to it. Sets route_mode to flamezo_hold on the restaurant doc."""
    import requests as _requests
    from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config
    res = restaurant if hasattr(restaurant, "name") else frappe.get_doc("Restaurant", restaurant)
    account_id = res.get("razorpay_account_id")
    if not account_id:
        return {"success": False, "error": "no_linked_account"}
    cfg = get_razorpay_config()
    auth = (cfg["key_id"], cfg["key_secret"])
    try:
        r = _requests.delete(
            f"https://api.razorpay.com/v2/accounts/{account_id}",
            auth=auth,
        )
        r.raise_for_status()
        frappe.db.set_value("Restaurant", res.name, {
            "route_mode": "flamezo_hold",
            "razorpay_kyc_status": "suspended",
        })
        frappe.db.commit()
        return {"success": True, "account_id": account_id, "status": "suspended"}
    except Exception as e:
        frappe.log_error(f"Suspend linked account failed for {account_id}: {e}", "razorpay_route.suspend")
        return {"success": False, "error": str(e)}


def reactivate_linked_account(restaurant) -> dict:
    """Re-enable a suspended Razorpay linked account. Sets route_mode back to
    flamezo_hold (KYC must be re-verified before direct_split is re-enabled)."""
    import requests as _requests
    from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config
    res = restaurant if hasattr(restaurant, "name") else frappe.get_doc("Restaurant", restaurant)
    account_id = res.get("razorpay_account_id")
    if not account_id:
        return {"success": False, "error": "no_linked_account"}
    cfg = get_razorpay_config()
    auth = (cfg["key_id"], cfg["key_secret"])
    try:
        r = _requests.patch(
            f"https://api.razorpay.com/v2/accounts/{account_id}",
            auth=auth,
            json={"profile": {}},
        )
        r.raise_for_status()
        resp = r.json()
        new_status = resp.get("status", "")
        frappe.db.set_value("Restaurant", res.name, {
            "route_mode": "flamezo_hold",
            "razorpay_kyc_status": new_status or "under_review",
        })
        frappe.db.commit()
        return {"success": True, "account_id": account_id, "status": new_status}
    except Exception as e:
        frappe.log_error(f"Reactivate linked account failed for {account_id}: {e}", "razorpay_route.reactivate")
        return {"success": False, "error": str(e)}


def reverse_transfer(order, refund_amount_paise: int) -> dict:
    """Reverse the merchant portion of a Route transfer when an order is
    refunded. Razorpay's `reverse_transfer` API handles the prorated math
    when we pass `reverse_all=1` and an amount.

    `order` may be a Frappe doc or an Order name.
    """
    order_doc = order if hasattr(order, "name") else frappe.get_doc("Order", order)
    transfer_id = order_doc.get("razorpay_transfer_id")
    if not transfer_id:
        return {"success": False, "error": "no_transfer_id"}

    client = get_razorpay_client()
    try:
        # SDK exposes this as transfer.reverse but versions differ — use
        # raw request for safety.
        result = client.request(
            "POST",
            f"/v1/transfers/{transfer_id}/reversals",
            params={"amount": int(refund_amount_paise), "currency": "INR"},
        )
        return {"success": True, "reversal": result}
    except Exception as e:
        frappe.log_error(f"Reverse transfer failed for {transfer_id}: {e}", "razorpay_route.reverse")
        return {"success": False, "error": str(e)}


# ── Internal helpers ────────────────────────────────────────────────────────

def _missing_kyc_fields(res) -> list:
    required = [
        ("restaurant_name", "Restaurant Name"),
        ("owner_email", "Owner Email"),
        ("owner_phone", "Owner Phone"),
        ("pan_number", "PAN Number"),
        ("bank_account_number", "Bank Account Number"),
        ("bank_ifsc", "Bank IFSC"),
        ("bank_holder_name", "Bank Holder Name"),
        ("business_type", "Business Type"),
        ("address", "Address"),
        ("city", "City"),
        ("state", "State"),
        ("zip_code", "Zip Code"),
    ]
    return [label for field, label in required if not res.get(field)]


def _normalize_phone(phone: Optional[str]) -> str:
    """Razorpay wants 10-digit Indian numbers, no +91 prefix."""
    if not phone:
        return ""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits[-10:]


# Razorpay requires exact Title Case state names (e.g. "Gujarat", not "gujarat " or "GUJARAT").
# This map also handles common abbreviations restaurants might type.
_STATE_ALIASES = {
    "andhra pradesh": "Andhra Pradesh", "ap": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chhattisgarh": "Chhattisgarh",
    "goa": "Goa",
    "gujarat": "Gujarat", "gj": "Gujarat",
    "haryana": "Haryana", "hr": "Haryana",
    "himachal pradesh": "Himachal Pradesh", "hp": "Himachal Pradesh",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka", "ka": "Karnataka",
    "kerala": "Kerala", "kl": "Kerala",
    "madhya pradesh": "Madhya Pradesh", "mp": "Madhya Pradesh",
    "maharashtra": "Maharashtra", "mh": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha", "orissa": "Odisha",
    "punjab": "Punjab", "pb": "Punjab",
    "rajasthan": "Rajasthan", "rj": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu", "tn": "Tamil Nadu", "tamilnadu": "Tamil Nadu",
    "telangana": "Telangana", "ts": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh", "up": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand", "uk": "Uttarakhand",
    "west bengal": "West Bengal", "wb": "West Bengal",
    "delhi": "Delhi", "new delhi": "Delhi",
    "jammu and kashmir": "Jammu And Kashmir", "j&k": "Jammu And Kashmir",
    "ladakh": "Ladakh",
    "chandigarh": "Chandigarh",
    "puducherry": "Puducherry", "pondicherry": "Puducherry",
    "andaman and nicobar islands": "Andaman And Nicobar Islands",
    "dadra and nagar haveli": "Dadra And Nagar Haveli And Daman And Diu",
    "daman and diu": "Dadra And Nagar Haveli And Daman And Diu",
    "lakshadweep": "Lakshadweep",
}


def _normalize_state(state: str) -> str:
    """Trim whitespace and map to Razorpay-accepted Title Case state name."""
    cleaned = state.strip()
    mapped = _STATE_ALIASES.get(cleaned.lower())
    if mapped:
        return mapped
    # Fall back to Title Case of whatever was provided (handles correct-but-wrong-case input)
    return cleaned.title() if cleaned else ""
