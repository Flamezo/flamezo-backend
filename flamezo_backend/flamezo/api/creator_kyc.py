"""
Creator payout KYC endpoints — the app-facing surface for
utils/creator_payout.py. Barter-only creators never need to call any of
this; it's only required before a creator's first CASH deal can
actually pay out (blueprint §05).
"""

import frappe
from frappe import _

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils.creator_payout import ensure_creator_linked_account, reconcile_creator_kyc_status

KYC_FIELDS = [
	"legal_name", "pan_number", "owner_email", "address", "kyc_city", "state", "zip_code",
	"bank_account_number", "bank_ifsc", "bank_holder_name",
]


def _require_own_creator(phone: str) -> str:
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
	creator_name = frappe.db.get_value("Flamezo Creator", {"customer_phone": phone}, "name")
	if not creator_name:
		normalized = normalize_phone(phone)
		for row in frappe.db.get_all("Flamezo Creator", fields=["name", "customer_phone"]):
			if normalize_phone(row.customer_phone or "") == normalized:
				creator_name = row.name
				break
	if not creator_name:
		frappe.throw(_("No creator profile found for this phone."), frappe.DoesNotExistError)
	return creator_name


@frappe.whitelist(allow_guest=True)
def submit_creator_kyc(phone, **fields):
	"""Save whichever KYC fields are provided, then attempt to create/attach
	the Razorpay Linked Account. Safe to call repeatedly (e.g. the creator
	fixes one missing field and resubmits) — ensure_creator_linked_account
	is fully idempotent."""
	creator_name = _require_own_creator(phone)
	creator = frappe.get_doc("Flamezo Creator", creator_name)
	for f in KYC_FIELDS:
		if f in fields and fields[f] is not None:
			creator.set(f, fields[f])
	creator.save(ignore_permissions=True)
	frappe.db.commit()

	result = ensure_creator_linked_account(creator)
	return {"success": result.get("success", False), "data": result}


@frappe.whitelist(allow_guest=True)
def get_creator_kyc_status(phone):
	creator_name = _require_own_creator(phone)
	row = frappe.db.get_value(
		"Flamezo Creator", creator_name,
		["razorpay_linked_account_id", "razorpay_kyc_status"] + KYC_FIELDS,
		as_dict=True,
	)
	missing = [f for f in KYC_FIELDS if not (row.get(f) or "").strip()]
	return {
		"success": True,
		"data": {
			"has_linked_account": bool(row.razorpay_linked_account_id),
			"kyc_status": row.razorpay_kyc_status,
			"missing_fields": missing,
		},
	}


@frappe.whitelist(allow_guest=True)
def sync_creator_kyc_status(phone):
	"""Manual 'Sync Status' — same fallback purpose as the outlet
	Route-KYC dashboard's own Sync Status button."""
	creator_name = _require_own_creator(phone)
	result = reconcile_creator_kyc_status(creator_name)
	return {"success": result.get("success", False), "data": result}
