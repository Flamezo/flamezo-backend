# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
The Collab Deal state machine — one flow whether a deal started as a gig
application, a direct invite, or a Standing Offer redemption (see
creator-marketplace-blueprint.html sections 04 and 17).

This controller enforces the state machine and money-field consistency
at the DB layer, on purpose — defense in depth below the API layer, so a
bad transition can't slip in through the desk UI, a data import, or an
API bug written later by someone who didn't re-read this file. It does
NOT talk to Razorpay or Instagram — that's the API/background-job
layer's job; a doctype controller doing network IO on save is a real
anti-pattern this codebase avoids elsewhere and shouldn't start here.

Barter fair-value handling exists specifically so barter never becomes
an invisible way to dodge 194R tracking — see the "Fixed — barter value
now tracked" callout in the blueprint's section 17. Every barter deal's
fair_value_inr is added to the creator's running annual total on
release (see on_update below); nothing about this doctype makes that
optional.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime, today

BARTER_HANDSHAKE_CEILING_INR = 300  # below this, no formal escrow — see blueprint §12

ALLOWED_TRANSITIONS = {
	"offered": {"accepted", "cancelled"},
	"accepted": {"funded", "delivered", "cancelled"},
	"funded": {"delivered", "cancelled"},
	"delivered": {"released", "disputed"},
	"disputed": {"released", "refunded"},
	"released": set(),
	"refunded": set(),
	"cancelled": set(),
}

TIMESTAMP_FIELD_BY_STATUS = {
	"accepted": "accepted_at",
	"funded": "funded_at",
	"delivered": "delivered_at",
	"released": "released_at",
}


class CollabDeal(Document):
	def validate(self):
		self._validate_origin()
		self._validate_deal_type_and_money()
		self._derive_escrow_required()
		self._validate_status_transition()
		self._stamp_transition_timestamp()

	def on_update(self):
		if self.has_value_changed("status") and self.status == "released":
			self._book_barter_value_if_needed()

	# ── origin ────────────────────────────────────────────────────────────

	def _validate_origin(self):
		origins = [bool(self.gig), bool(self.direct_invite), bool(self.standing_offer)]
		if sum(origins) != 1:
			frappe.throw(
				_("A deal must have exactly one origin: a gig, a direct invite, or a standing offer."),
				frappe.ValidationError,
			)

	# ── money ────────────────────────────────────────────────────────────

	def _validate_deal_type_and_money(self):
		if self.deal_type == "cash":
			if flt(self.price_inr) <= 0:
				frappe.throw(_("Cash deals need a positive price."), frappe.ValidationError)
			if flt(self.fair_value_inr):
				frappe.throw(_("fair_value_inr is barter-only — a cash deal shouldn't set it."), frappe.ValidationError)
			expected_commission = 5 if self.flamezo_mention_verified else 10
			if cint(self.commission_pct) != expected_commission:
				# Not a hard block on every write (ops may need to correct a
				# historical row), but the field is never allowed to insert
				# at anything other than the derived value.
				if self.is_new():
					self.commission_pct = expected_commission
		elif self.deal_type == "barter":
			if flt(self.fair_value_inr) <= 0:
				frappe.throw(_("Barter deals need a positive fair_value_inr — required for 194R tracking."), frappe.ValidationError)
			if flt(self.price_inr):
				frappe.throw(_("price_inr is cash-only — a barter deal shouldn't set it."), frappe.ValidationError)
			if flt(self.commission_pct):
				self.commission_pct = 0
		else:
			frappe.throw(_("deal_type must be 'cash' or 'barter'."), frappe.ValidationError)

	def _derive_escrow_required(self):
		"""Cash always escrows, regardless of size. Barter only escrows
		above the handshake ceiling — see blueprint §12's resolution of
		the minimum-deal-size question."""
		if self.deal_type == "cash":
			self.escrow_required = 1
		else:
			self.escrow_required = 1 if flt(self.fair_value_inr) >= BARTER_HANDSHAKE_CEILING_INR else 0

	# ── state machine ────────────────────────────────────────────────────

	def _validate_status_transition(self):
		if self.is_new():
			if self.status and self.status != "offered":
				frappe.throw(_("A new deal must start as 'offered'."), frappe.ValidationError)
			self.status = "offered"
			return

		previous_status = frappe.db.get_value("Collab Deal", self.name, "status")
		if previous_status == self.status:
			return  # not a transition, some other field changed

		allowed = ALLOWED_TRANSITIONS.get(previous_status, set())
		if self.status not in allowed:
			frappe.throw(
				_("Can't move a deal from '{0}' to '{1}'.").format(previous_status, self.status),
				frappe.ValidationError,
			)

		if self.status == "funded" and not self.escrow_required:
			frappe.throw(
				_("This deal doesn't require escrow — it should go straight from 'accepted' to 'delivered'."),
				frappe.ValidationError,
			)
		if self.status == "delivered" and self.deal_type == "cash" and self.escrow_required and not self.funded_at:
			frappe.throw(_("A cash deal must be funded before it can be marked delivered."), frappe.ValidationError)

	def _stamp_transition_timestamp(self):
		field = TIMESTAMP_FIELD_BY_STATUS.get(self.status)
		if field and not self.get(field):
			self.set(field, now_datetime())

	# ── tax tracking ─────────────────────────────────────────────────────

	def _book_barter_value_if_needed(self):
		"""Runs once, on release, only for barter — adds this deal's
		fair value to the creator's running annual total. Deliberately
		not skippable by any deal origin (gig, direct invite, or standing
		offer all pass through this same controller) — see the module
		docstring.

		Reset is lazy, not cron-driven: whichever barter deal is the
		first to release after the Indian financial year rolls over
		zeroes the counter before adding, rather than depending on a
		scheduled job firing at exactly midnight on April 1st. A missed
		cron here would silently under-report a creator's real exposure;
		a lazy check can't miss."""
		if self.deal_type != "barter":
			return
		current_fy = _current_financial_year()
		creator = frappe.db.get_value(
			"Flamezo Creator", self.creator, ["barter_value_ytd_inr", "barter_value_fy"], as_dict=True
		)
		base = flt(creator.barter_value_ytd_inr) if creator.barter_value_fy == current_fy else 0.0
		frappe.db.set_value(
			"Flamezo Creator",
			self.creator,
			{
				"barter_value_ytd_inr": base + flt(self.fair_value_inr),
				"barter_value_fy": current_fy,
			},
		)


def _current_financial_year():
	"""Indian FY: April 1 → March 31. e.g. any date in Sept 2026 or
	Feb 2027 both resolve to '2026-27'."""
	d = getdate(today())
	start_year = d.year if d.month >= 4 else d.year - 1
	return f"{start_year}-{str(start_year + 1)[-2:]}"
