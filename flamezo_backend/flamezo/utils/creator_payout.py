"""
Creator payout KYC + Razorpay Route linked-account onboarding
(creator-marketplace-blueprint.html §05's "Creator payout accounts").

Deliberately a SEPARATE module from utils/razorpay_route.py rather than
generalising that file to cover both Outlets and Flamezo Creators —
razorpay_route.py is live, production, real-merchant-money code; adding
a second doctype's worth of branching to it is exactly the kind of
change that risks a subtle regression in code that already moves real
funds today. This module duplicates the same proven pattern (idempotent
create-or-fetch, stakeholder-then-product-then-settlements sequencing,
the same "created = account live, can receive transfers" status mapping
already corrected in razorpay_route.py's update_kyc_status) rather than
sharing code with it — a small amount of duplication is the safer trade
here than coupling two independently-evolving payout paths together.

Individual creators (not a registered business) is the default and only
supported business_type for now — PAN goes on stakeholder KYC exactly
like a merchant proprietorship does (razorpay_route.py's own comment:
"PAN in legal_info is only for incorporated entities... For
proprietorship it belongs in stakeholder KYC" — an individual creator is
even more clearly this case). No GST is collected or required.
"""

import requests

import frappe
from frappe import _

from frappe.utils import flt

from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client, get_razorpay_config

REQUIRED_KYC_FIELDS = [
	"pan_number", "owner_email", "customer_phone",
	"address", "kyc_city", "state", "zip_code",
	"bank_account_number", "bank_ifsc", "bank_holder_name",
]


def _missing_kyc_fields(creator) -> list:
	return [f for f in REQUIRED_KYC_FIELDS if not (creator.get(f) or "").strip()]


def _normalize_phone(phone: str) -> str:
	digits = "".join(c for c in (phone or "") if c.isdigit())
	return digits[-10:] if len(digits) >= 10 else digits


def _normalize_state(state: str) -> str:
	return (state or "").strip()


def ensure_creator_linked_account(creator) -> dict:
	"""Create the Razorpay Linked Account for a creator if they don't have
	one, or return the existing one. Idempotent — same re-submit/retry
	semantics as razorpay_route.ensure_linked_account (the bank-attach
	step is safe to re-run since it always PATCHes the latest details)."""
	res = creator if hasattr(creator, "name") else frappe.get_doc("Flamezo Creator", creator)

	if res.get("razorpay_linked_account_id"):
		result = {
			"success": True,
			"linked_account_id": res.razorpay_linked_account_id,
			"kyc_status": res.razorpay_kyc_status,
			"created": False,
		}
		if (res.get("razorpay_kyc_status") or "").lower() != "activated":
			attach = _attach_bank_and_stakeholder(get_razorpay_config(), res.razorpay_linked_account_id, res)
			result["bank_attached"] = attach.get("bank_ok", False)
			result["attach_errors"] = attach.get("errors", [])
		return result

	missing = _missing_kyc_fields(res)
	if missing:
		return {"success": False, "error": "incomplete_kyc", "missing_fields": missing}

	cfg = get_razorpay_config()
	auth = (cfg["key_id"], cfg["key_secret"])

	phone_str = _normalize_phone(res.customer_phone)
	phone_int = int(phone_str) if phone_str.isdigit() and len(phone_str) == 10 else None

	street1 = (res.get("address") or "").strip()[:100]
	street2 = (res.get("kyc_city") or "-").strip()[:100]
	state_upper = _normalize_state(res.get("state")).upper()

	payload = {
		"email": res.owner_email,
		"phone": phone_int or phone_str,
		"type": "route",
		"reference_id": res.name,
		"legal_business_name": (res.get("legal_name") or res.display_name or res.name).strip(),
		"business_type": "individual",
		"contact_name": (res.get("legal_name") or res.display_name or res.name).strip(),
		"profile": {
			"category": "others",
			"subcategory": "content_creator",
			"addresses": {
				"registered": {
					"street1": street1 or "-",
					"street2": street2,
					"city": (res.get("kyc_city") or "").strip(),
					"state": state_upper,
					"postal_code": (res.get("zip_code") or "").strip(),
					"country": "IN",
				}
			},
		},
		# No legal_info.pan here — individual PAN goes on the stakeholder,
		# not legal_info (that's for incorporated entities only). See
		# module docstring.
	}

	try:
		r = requests.post("https://api.razorpay.com/v2/accounts", auth=auth, json=payload, timeout=30)
		account = r.json()
		account_id = account.get("id")

		if not account_id and ("reference_id" in str(account) or "already in use" in str(account).lower()):
			payload_no_ref = {k: v for k, v in payload.items() if k != "reference_id"}
			r = requests.post("https://api.razorpay.com/v2/accounts", auth=auth, json=payload_no_ref, timeout=30)
			account = r.json()
			account_id = account.get("id")

		if not account_id:
			raise Exception(f"Account creation failed: {account!r}")

		frappe.db.set_value("Flamezo Creator", res.name, {
			"razorpay_linked_account_id": account_id,
			"razorpay_kyc_status": "under_review",
		})
		frappe.db.commit()

		attach = _attach_bank_and_stakeholder(cfg, account_id, res)

		return {
			"success": True, "linked_account_id": account_id, "kyc_status": "under_review", "created": True,
			"bank_attached": attach.get("bank_ok", False), "attach_errors": attach.get("errors", []),
		}
	except Exception as e:
		frappe.log_error(f"Linked account creation failed for {res.name}: {e}", "creator_payout.ensure_linked_account")
		return {"success": False, "error": str(e)}


def _attach_bank_and_stakeholder(cfg, account_id: str, res) -> dict:
	"""Push stakeholder (with the individual's own PAN) + bank settlements
	onto a Linked Account. Mirrors razorpay_route._attach_bank_and_stakeholder's
	exact sequencing (stakeholder, then product, then PATCH settlements) —
	see that file's own comment on why the product-listing GET can't be
	relied on (Razorpay 404s it) so this always attempts a create and
	tolerates an "already exists"-shaped failure rather than depending on
	a working list endpoint."""
	auth = (cfg["key_id"], cfg["key_secret"])
	BASE = "https://api.razorpay.com"
	TIMEOUT = 30
	result = {"stakeholder_ok": False, "bank_ok": False, "errors": []}

	phone_str = _normalize_phone(res.customer_phone)
	phone_int = int(phone_str) if phone_str.isdigit() and len(phone_str) == 10 else None

	try:
		r = requests.post(
			f"{BASE}/v2/accounts/{account_id}/stakeholders",
			auth=auth, timeout=TIMEOUT,
			json={
				"name": (res.get("legal_name") or res.display_name or res.name).strip(),
				"email": res.owner_email,
				**({"phone": {"primary": phone_int}} if phone_int else {}),
				**({"kyc": {"pan": res.pan_number.strip()}} if res.get("pan_number") else {}),
				"addresses": {
					"residential": {
						"street": (res.get("address") or "").strip()[:100],
						"city": (res.get("kyc_city") or "").strip(),
						"state": _normalize_state(res.get("state")),
						"postal_code": (res.get("zip_code") or "").strip(),
						"country": "IN",
					}
				},
			},
		)
		if r.ok or "already" in r.text.lower():
			result["stakeholder_ok"] = True
		else:
			result["errors"].append(f"stakeholder: HTTP {r.status_code} {r.text[:300]}")
			frappe.log_error(f"Stakeholder attach failed for {account_id}: HTTP {r.status_code} {r.text}", "creator_payout.stakeholder")
	except Exception as e:
		result["errors"].append(f"stakeholder: {e}")
		frappe.log_error(f"Stakeholder attach exception for {account_id}: {e}", "creator_payout.stakeholder")

	try:
		product_id = None
		r = requests.post(
			f"{BASE}/v2/accounts/{account_id}/products",
			auth=auth, timeout=TIMEOUT,
			json={"product_name": "route", "tnc_accepted": True},
		)
		if r.ok:
			product_id = r.json().get("id")
		elif "already" in r.text.lower():
			# Product already exists and the list endpoint 404s (same known
			# Razorpay quirk razorpay_route.py's own comment documents) —
			# nothing more we can do here without a working list call; the
			# settlements PATCH below will simply fail loudly if this
			# leaves product_id unset, which is surfaced via errors[].
			pass
		if not product_id:
			result["errors"].append(f"product: HTTP {r.status_code} {r.text[:300]}")
			frappe.log_error(f"Product create failed for {account_id}: HTTP {r.status_code} {r.text}", "creator_payout.product")
			return result

		pr = requests.patch(
			f"{BASE}/v2/accounts/{account_id}/products/{product_id}",
			auth=auth, timeout=TIMEOUT,
			json={
				"settlements": {
					"account_number": (res.get("bank_account_number") or "").strip(),
					"ifsc_code": (res.get("bank_ifsc") or "").strip().upper(),
					"beneficiary_name": (res.get("bank_holder_name") or res.display_name or res.name).strip(),
				},
				"tnc_accepted": True,
			},
		)
		if pr.ok:
			result["bank_ok"] = True
		else:
			result["errors"].append(f"settlements: HTTP {pr.status_code} {pr.text[:300]}")
			frappe.log_error(f"Bank/settlements attach failed for {account_id}: HTTP {pr.status_code} {pr.text}", "creator_payout.product")
	except Exception as e:
		result["errors"].append(f"product/bank: {e}")
		frappe.log_error(f"Product/bank config failed for {account_id}: {e}", "creator_payout.product")

	return result


def update_creator_kyc_status(linked_account_id: str, new_status: str):
	"""Same simple mapping razorpay_route.update_kyc_status now uses for
	Outlets ('created' = live/activated, 'suspended' = suspended — only
	two real values for a Route linked account per Razorpay's own docs).
	Kept as its own function (not shared) for the same reason
	ensure_creator_linked_account is its own function — see module
	docstring."""
	creator_name = frappe.db.get_value("Flamezo Creator", {"razorpay_linked_account_id": linked_account_id})
	if not creator_name:
		return

	mapping = {
		"created": "activated",
		"suspended": "suspended",
		"activated": "activated",
		"instantly_activated": "activated",
		"activated_kyc_pending": "under_review",
		"under_review": "under_review",
		"needs_clarification": "needs_clarification",
		"rejected": "rejected",
	}
	internal = mapping.get((new_status or "").lower(), "activated")

	current = (frappe.db.get_value("Flamezo Creator", creator_name, "razorpay_kyc_status") or "").lower()
	if current == "activated" and internal not in ("activated", "rejected", "suspended"):
		return  # same monotonic guard as the Outlet version — never let a stale pending status downgrade an activated account

	frappe.db.set_value("Flamezo Creator", creator_name, "razorpay_kyc_status", internal)
	frappe.db.commit()


def creator_payout_ready(creator_name: str) -> bool:
	"""True only if this creator has a linked account Razorpay considers
	live. The one real gate every cash-payout call site must check before
	attempting a transfer — never assume, always ask the DB."""
	account_id, status = frappe.db.get_value(
		"Flamezo Creator", creator_name, ["razorpay_linked_account_id", "razorpay_kyc_status"]
	) or (None, None)
	return bool(account_id) and (status or "").lower() == "activated"


def execute_route_transfer(creator_name: str, razorpay_payment_id: str, amount_inr, notes: dict = None) -> dict:
	"""The real Route payout leg — `POST /payments/{id}/transfers` against
	the ALREADY-CAPTURED payment that funded escrow, splitting the
	creator's share out of Flamezo's balance into their Linked Account.
	This is the one real-money-moving call every collab-deal payout call
	site (collab_deals.py, collab_disputes.py) must go through — no
	second, divergent implementation of the same transfer anywhere else.

	Callers MUST check creator_payout_ready() first; this function still
	guards defensively (never trusts a caller got that right) and returns
	a clean failure dict rather than letting an unconfigured account
	reach Razorpay's API as a confusing 400.
	"""
	if not creator_payout_ready(creator_name):
		return {"success": False, "error": "creator_not_payout_ready"}
	if flt(amount_inr) <= 0:
		return {"success": False, "error": "non_positive_amount"}

	account_id = frappe.db.get_value("Flamezo Creator", creator_name, "razorpay_linked_account_id")
	client = get_razorpay_client()
	try:
		resp = client.payment.transfer(razorpay_payment_id, {
			"transfers": [{
				"account": account_id,
				"amount": int(round(flt(amount_inr) * 100)),
				"currency": "INR",
				"notes": notes or {},
			}]
		})
		items = resp.get("items") or []
		if not items:
			raise Exception(f"transfer call returned no items: {resp!r}")
		transfer_id = items[0].get("id")
		if not transfer_id:
			raise Exception(f"transfer response missing id: {items[0]!r}")
		return {"success": True, "transfer_id": transfer_id}
	except Exception as e:
		frappe.log_error(
			f"Route transfer failed: creator={creator_name} payment={razorpay_payment_id} "
			f"amount={amount_inr} error={e}",
			"creator_payout.execute_route_transfer",
		)
		return {"success": False, "error": str(e)}


def reconcile_creator_kyc_status(creator) -> dict:
	"""Manual "Sync Status" fallback for a missed webhook — same purpose
	as razorpay_route.reconcile_kyc_status."""
	res = creator if hasattr(creator, "name") else frappe.get_doc("Flamezo Creator", creator)
	account_id = res.get("razorpay_linked_account_id")
	if not account_id:
		return {"success": False, "error": "no_linked_account"}

	cfg = get_razorpay_config()
	auth = (cfg["key_id"], cfg["key_secret"])
	try:
		r = requests.get(f"https://api.razorpay.com/v2/accounts/{account_id}", auth=auth, timeout=15)
		r.raise_for_status()
		live_status = (r.json().get("status") or "").lower()
		before = (res.get("razorpay_kyc_status") or "").lower()
		if live_status:
			update_creator_kyc_status(account_id, live_status)
		after = (frappe.db.get_value("Flamezo Creator", res.name, "razorpay_kyc_status") or "").lower()
		return {"success": True, "kyc_status": after, "changed": before != after}
	except Exception as e:
		frappe.log_error(f"reconcile_creator_kyc_status failed for {account_id}: {e}", "creator_payout.reconcile")
		return {"success": False, "error": str(e)}
