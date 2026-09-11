"""
Creator Rate Cards — what a creator charges per deliverable type
(creator-marketplace-blueprint.html §02, §17). Phase 1 of the marketplace
build, zero external dependency.
"""

import json

import frappe
from frappe import _

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone

VALID_DELIVERABLE_TYPES = {
	"native_chills", "native_club_post", "instagram_reel", "instagram_story", "bundle",
}


def _require_own_creator(phone: str) -> str:
	"""Same pattern as creator_rewards.py::_require_own_creator — kept as
	its own copy rather than a cross-module import to avoid coupling two
	otherwise-independent API modules to each other's internals; the
	logic is small and stable enough that duplication here is cheaper
	than the coupling would be."""
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
def set_my_rate_card(phone, deliverable_type, price_inr=0, accepts_barter=0, barter_min_value_inr=0):
	"""Upsert — one rate card per (creator, deliverable_type). Real
	validation (uniqueness, "must offer something") lives on the doctype
	itself (defense in depth); this wrapper's job is auth + upsert
	routing."""
	creator_name = _require_own_creator(phone)

	if deliverable_type not in VALID_DELIVERABLE_TYPES:
		frappe.throw(_("Unknown deliverable type: {0}").format(deliverable_type), frappe.ValidationError)

	existing = frappe.db.get_value(
		"Creator Rate Card", {"creator": creator_name, "deliverable_type": deliverable_type}, "name"
	)
	if existing:
		card = frappe.get_doc("Creator Rate Card", existing)
	else:
		card = frappe.new_doc("Creator Rate Card")
		card.creator = creator_name
		card.deliverable_type = deliverable_type

	card.price_inr = price_inr
	card.accepts_barter = cint_bool(accepts_barter)
	card.barter_min_value_inr = barter_min_value_inr
	card.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"rate_card_id": card.name}}


@frappe.whitelist(allow_guest=True)
def get_my_rate_cards(phone):
	creator_name = _require_own_creator(phone)
	rows = frappe.db.get_all(
		"Creator Rate Card",
		filters={"creator": creator_name},
		fields=["name", "deliverable_type", "price_inr", "accepts_barter", "barter_min_value_inr", "is_active"],
		order_by="deliverable_type asc",
	)
	return {"success": True, "data": {"rate_cards": rows}}


@frappe.whitelist(allow_guest=True)
def get_creator_rate_cards(creator_id):
	"""Public/merchant-facing — a creator's active rate cards, shown on
	their portfolio (blueprint §15). No session required, this is public
	pricing info by design."""
	if not frappe.db.exists("Flamezo Creator", creator_id):
		frappe.throw(_("Creator not found"), frappe.DoesNotExistError)

	rows = frappe.db.get_all(
		"Creator Rate Card",
		filters={"creator": creator_id, "is_active": 1},
		fields=["deliverable_type", "price_inr", "accepts_barter", "barter_min_value_inr"],
		order_by="deliverable_type asc",
	)
	return {"success": True, "data": {"rate_cards": rows}}


def cint_bool(value) -> int:
	"""Frappe whitelisted methods receive query/form params as strings —
	'0'/'false'/'' must all resolve falsy, not just literal 0."""
	if isinstance(value, str):
		return 1 if value.strip().lower() in ("1", "true", "yes") else 0
	return 1 if value else 0
