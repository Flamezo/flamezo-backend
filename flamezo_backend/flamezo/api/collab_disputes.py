"""
Collab Dispute lifecycle — creator-marketplace-blueprint.html §08. Phase 4
of the marketplace build.

Raise -> Evidence (24h) -> Review (48h, ops) -> Resolved -> optional single
Appeal -> Closed. Blocks escrow release/auto-release the moment it's raised
(collab_deals.py's `_has_dispute_doctype()` checks already do this — this
module is the missing half those checks were waiting on).

Money movement on resolution reuses the exact same primitives
collab_deals.py already established (Razorpay refund for the merchant's
share, the same explicit non-silent stub for the creator's share pending
the not-yet-built creator-KYC/linked-account flow) — never a second,
divergent way of moving the same money.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, now_datetime

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client

APPEAL_WINDOW_HOURS = 72  # from resolved_at — launch default, not derived from real data yet (matches this doc's other config values)
RESOLUTION_SLA_BREACH_LOG = "collab_disputes.resolution_sla_breached"


# ── identity helpers (mirror collab_deals.py's private helpers — this
#    module can't import those, they're underscore-private there, so the
#    small duplication here is deliberate rather than reaching into
#    another module's internals) ────────────────────────────────────────

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


def _load_deal(deal_id):
	if not frappe.db.exists("Collab Deal", deal_id):
		frappe.throw(_("Deal not found"), frappe.DoesNotExistError)
	return frappe.get_doc("Collab Deal", deal_id)


def _resolve_caller_role(deal, phone, outlet_id):
	"""Returns ('creator', creator_name) or ('merchant', outlet_id) — throws
	if the caller isn't a real party to this deal. Exactly one of
	phone/outlet_id is expected, matching every other dual-sided endpoint
	in this marketplace (see collab_deals.get_deal)."""
	if phone:
		creator_name = _require_own_creator(phone)
		if deal.creator != creator_name:
			frappe.throw(_("This deal isn't yours."), frappe.PermissionError)
		return "creator", creator_name
	if outlet_id:
		outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
		if deal.outlet != outlet:
			frappe.throw(_("This deal isn't yours."), frappe.PermissionError)
		return "merchant", outlet
	frappe.throw(_("phone or outlet_id is required."), frappe.ValidationError)


def _load_dispute(dispute_id):
	if not frappe.db.exists("Collab Dispute", dispute_id):
		frappe.throw(_("Dispute not found"), frappe.DoesNotExistError)
	return frappe.get_doc("Collab Dispute", dispute_id)


def _require_dispute_party(dispute, deal, phone, outlet_id):
	role, _identity = _resolve_caller_role(deal, phone, outlet_id)
	return role


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def _append_evidence_json(existing_json, text, attachment_url):
	items = json.loads(existing_json) if existing_json else []
	items.append({
		"text": text or "",
		"attachment_url": attachment_url or None,
		"submitted_at": now_datetime().isoformat(),
	})
	return json.dumps(items)


# ── raise ────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def raise_dispute(deal_id, reason, reason_detail=None, phone=None, outlet_id=None):
	deal = _load_deal(deal_id)
	role, _identity = _resolve_caller_role(deal, phone, outlet_id)

	if deal.status != "delivered":
		frappe.throw(
			_("A dispute can only be raised against a delivered deal awaiting release, not one that's '{0}'.").format(deal.status),
			frappe.ValidationError,
		)
	if frappe.db.exists("Collab Dispute", {"deal": deal.name, "status": ["not in", ["resolved", "closed"]]}):
		frappe.throw(_("This deal already has an open dispute."), frappe.ValidationError)

	dispute = frappe.get_doc({
		"doctype": "Collab Dispute",
		"deal": deal.name,
		"raised_by_role": role,
		"reason": reason,
		"reason_detail": reason_detail,
	})
	dispute.insert(ignore_permissions=True)

	# Deal moves to 'disputed' immediately — this is what blocks
	# approve_release/auto_release_escrow the moment a dispute exists
	# (collab_deals.py's ALLOWED_TRANSITIONS already permits delivered -> disputed).
	deal.status = "disputed"
	deal.save(ignore_permissions=True)

	# Escrow Transaction mirrors the same 'disputed' state, cash deals only.
	if deal.deal_type == "cash" and deal.escrow_required:
		frappe.db.set_value("Escrow Transaction", {"deal": deal.name}, "state", "disputed")

	# Move straight into the evidence window — 'raised' is the created
	# state, but there's nothing to wait on before evidence collection
	# opens.
	dispute.status = "evidence"
	dispute.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"dispute_id": dispute.name, "status": dispute.status, "evidence_due_at": dispute.evidence_due_at}}


# ── evidence ─────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def submit_evidence(dispute_id, text=None, attachment_url=None, phone=None, outlet_id=None):
	dispute = _load_dispute(dispute_id)
	deal = _load_deal(dispute.deal)
	role = _require_dispute_party(dispute, deal, phone, outlet_id)

	if dispute.status != "evidence":
		frappe.throw(_("This dispute isn't accepting evidence right now — it's '{0}'.").format(dispute.status), frappe.ValidationError)
	if not text and not attachment_url:
		frappe.throw(_("Provide text or an attachment."), frappe.ValidationError)

	field = "creator_evidence_json" if role == "creator" else "merchant_evidence_json"
	dispute.set(field, _append_evidence_json(dispute.get(field), text, attachment_url))

	# Both sides in → no reason to sit out the rest of the 24h window.
	if dispute.creator_evidence_json and dispute.merchant_evidence_json:
		dispute.status = "review"

	dispute.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"status": dispute.status}}


# ── ops resolution ──────────────────────────────────────────────────────

def _split_amounts(escrow, split_creator_pct):
	creator_amount = flt(escrow.amount_inr) * flt(split_creator_pct) / 100
	merchant_refund = flt(escrow.amount_inr) - creator_amount
	return round(creator_amount, 2), round(merchant_refund, 2)


def _refund_escrow_amount(escrow, amount_inr, reason):
	"""Real Razorpay refund for a specific amount — same primitive
	collab_deals._refund_overdue_escrow uses, generalised to a partial
	amount for the split_partial case."""
	if amount_inr <= 0:
		return
	client = get_razorpay_client()
	client.payment.refund(escrow.razorpay_payment_id, {
		"amount": int(round(amount_inr * 100)),
		"notes": {"type": "collab_deal_escrow_refund", "deal_id": escrow.deal, "reason": reason},
	})


def _payout_creator_share(deal, escrow, amount_inr):
	"""Real Route transfer via utils/creator_payout.execute_route_transfer —
	same primitive collab_deals._transfer_to_creator uses for a normal
	(non-disputed) release, so dispute resolution never has a second,
	divergent way of paying a creator. Falls back to the same loud,
	explicit log (never a silent no-op) for a creator who hasn't
	completed payout KYC yet."""
	if amount_inr <= 0:
		return
	from flamezo_backend.flamezo.utils.creator_payout import creator_payout_ready, execute_route_transfer

	if not creator_payout_ready(deal.creator):
		frappe.log_error(
			title="collab_disputes.transfer_pending_creator_kyc",
			message=(
				f"Deal {deal.name}: dispute resolution awarded the creator {deal.creator} "
				f"₹{amount_inr}, but they haven't completed Razorpay payout KYC yet — no "
				f"transfer was sent."
			),
		)
		return

	result = execute_route_transfer(
		deal.creator, escrow.razorpay_payment_id, amount_inr,
		notes={"type": "collab_dispute_payout", "deal_id": deal.name},
	)
	if result.get("success"):
		escrow.razorpay_transfer_id = result["transfer_id"]
	else:
		frappe.log_error(
			title="collab_disputes.transfer_failed",
			message=f"Deal {deal.name}: dispute-resolution Route transfer to creator {deal.creator} failed: {result.get('error')}",
		)


@frappe.whitelist()
def resolve_dispute(dispute_id, resolution_outcome, at_fault, resolution_notes=None, split_creator_pct=None):
	"""Ops-only. `resolution_outcome`: release_full / refund_full / split_partial / no_fault.
	`at_fault`: creator / merchant / none — drives the badge consequence
	(blueprint §08: a dispute lost by the creator counts against
	Top Rated/Elite eligibility; lost by the merchant never touches the
	creator's score — see utils/creator_badges.py)."""
	_require_system_manager()
	dispute = _load_dispute(dispute_id)
	if dispute.status not in ("evidence", "review"):
		frappe.throw(_("Only a dispute in evidence/review can be resolved — this one is '{0}'.").format(dispute.status), frappe.ValidationError)
	if resolution_outcome not in ("release_full", "refund_full", "split_partial", "no_fault"):
		frappe.throw(_("Invalid resolution_outcome."), frappe.ValidationError)
	if at_fault not in ("creator", "merchant", "none"):
		frappe.throw(_("Invalid at_fault."), frappe.ValidationError)
	if resolution_outcome == "split_partial" and not split_creator_pct:
		frappe.throw(_("split_creator_pct is required for split_partial."), frappe.ValidationError)

	if dispute.status == "evidence":
		# Ops can resolve before the 24h evidence window naturally closes
		# (an obvious case doesn't need to wait) — the state machine still
		# requires passing through 'review' first, so step through it
		# rather than skipping straight to 'resolved'.
		dispute.status = "review"
		dispute.save(ignore_permissions=True)

	deal = _load_deal(dispute.deal)

	creator_amount = merchant_refund = 0.0
	if deal.deal_type == "cash" and deal.escrow_required:
		escrow = frappe.get_doc("Escrow Transaction", {"deal": deal.name})
		if resolution_outcome in ("release_full", "no_fault"):
			creator_amount = flt(deal.price_inr) - flt(escrow.platform_fee_inr)
			_payout_creator_share(deal, escrow, creator_amount)
			escrow.state = "released"
			deal.status = "released"
		elif resolution_outcome == "refund_full":
			merchant_refund = flt(deal.price_inr)
			_refund_escrow_amount(escrow, merchant_refund, "dispute_resolved_refund_full")
			escrow.state = "refunded"
			deal.status = "refunded"
		else:  # split_partial
			creator_amount, merchant_refund = _split_amounts(escrow, split_creator_pct)
			_refund_escrow_amount(escrow, merchant_refund, "dispute_resolved_split")
			_payout_creator_share(deal, escrow, creator_amount)
			escrow.state = "released"  # some value did release to the creator — see collab_dispute.py's status-mapping note
			deal.status = "released"
		escrow.save(ignore_permissions=True)
	else:
		# Barter (or a cash deal that somehow never escrowed) — no money to
		# move, this is purely a reputation/status verdict.
		deal.status = "refunded" if resolution_outcome == "refund_full" else "released"

	deal.save(ignore_permissions=True)

	dispute.resolution_outcome = resolution_outcome
	dispute.at_fault = at_fault
	dispute.resolution_notes = resolution_notes
	dispute.resolved_by = frappe.session.user
	if resolution_outcome == "split_partial":
		dispute.split_creator_pct = split_creator_pct
	dispute.resolved_creator_amount_inr = creator_amount
	dispute.resolved_merchant_refund_inr = merchant_refund
	dispute.status = "resolved"
	dispute.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"status": dispute.status, "deal_status": deal.status}}


# ── appeal ───────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def request_appeal(dispute_id, appeal_reason, phone=None, outlet_id=None):
	dispute = _load_dispute(dispute_id)
	deal = _load_deal(dispute.deal)
	_require_dispute_party(dispute, deal, phone, outlet_id)

	if dispute.status != "resolved":
		frappe.throw(_("Only a resolved dispute can be appealed."), frappe.ValidationError)
	if dispute.appeal_requested:
		frappe.throw(_("An appeal has already been requested on this dispute — one appeal, final."), frappe.ValidationError)
	deadline = add_to_date(dispute.resolved_at, hours=APPEAL_WINDOW_HOURS)
	if now_datetime() > deadline:
		frappe.throw(_("The {0}-hour appeal window has closed.").format(APPEAL_WINDOW_HOURS), frappe.ValidationError)

	dispute.appeal_requested = 1
	dispute.appeal_reason = appeal_reason
	dispute.status = "appealed"
	dispute.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"status": dispute.status}}


@frappe.whitelist()
def resolve_appeal(dispute_id, appeal_outcome, appeal_resolution_notes=None):
	"""Ops-only, senior reviewer. `appeal_outcome`: upheld (original
	verdict stands) / overturned (money/at-fault DOES NOT auto-reverse
	here — an overturned appeal on a cash deal needing money moved back
	is rare enough and consequential enough that it goes through
	resolve_dispute again as a fresh manual action by a human who can see
	exactly what already moved, rather than this endpoint attempting to
	auto-reverse a Razorpay refund/stub payout it can't safely automate)."""
	_require_system_manager()
	dispute = _load_dispute(dispute_id)
	if dispute.status != "appealed":
		frappe.throw(_("Only an appealed dispute can be resolved here."), frappe.ValidationError)
	if appeal_outcome not in ("upheld", "overturned"):
		frappe.throw(_("Invalid appeal_outcome."), frappe.ValidationError)

	dispute.appeal_outcome = appeal_outcome
	dispute.appeal_resolution_notes = appeal_resolution_notes
	dispute.appeal_resolved_by = frappe.session.user
	dispute.status = "closed"
	dispute.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"status": dispute.status}}


# ── read ─────────────────────────────────────────────────────────────────

def _dispute_summary(d):
	return {
		"dispute_id": d.name, "deal_id": d.deal, "status": d.status,
		"raised_by_role": d.raised_by_role, "reason": d.reason, "reason_detail": d.reason_detail,
		"evidence_due_at": d.evidence_due_at, "resolution_due_at": d.resolution_due_at,
		"resolution_outcome": d.resolution_outcome, "at_fault": d.at_fault,
		"resolution_notes": d.resolution_notes, "split_creator_pct": d.split_creator_pct,
		"resolved_creator_amount_inr": d.resolved_creator_amount_inr,
		"resolved_merchant_refund_inr": d.resolved_merchant_refund_inr,
		"appeal_requested": d.appeal_requested, "appeal_outcome": d.appeal_outcome,
		"raised_at": d.raised_at, "resolved_at": d.resolved_at, "closed_at": d.closed_at,
	}


@frappe.whitelist(allow_guest=True)
def get_dispute(dispute_id=None, phone=None, outlet_id=None):
	if not dispute_id:
		return {"success": True, "data": None}
	dispute = _load_dispute(dispute_id)
	deal = _load_deal(dispute.deal)
	role = _require_dispute_party(dispute, deal, phone, outlet_id)
	data = _dispute_summary(dispute)
	# Each party only ever sees their own evidence submissions plus the
	# other side's — evidence is meant to be visible to both once
	# submitted (blueprint §08's "both sides submit evidence"), never
	# secret from either party to a dispute they're both in.
	data["creator_evidence"] = json.loads(dispute.creator_evidence_json) if dispute.creator_evidence_json else []
	data["merchant_evidence"] = json.loads(dispute.merchant_evidence_json) if dispute.merchant_evidence_json else []
	data["your_role"] = role
	return {"success": True, "data": data}


@frappe.whitelist(allow_guest=True)
def list_my_disputes(phone, status=None):
	creator_name = _require_own_creator(phone)
	deal_names = frappe.db.get_all("Collab Deal", filters={"creator": creator_name}, pluck="name")
	if not deal_names:
		return {"success": True, "data": {"disputes": []}}
	filters = {"deal": ["in", deal_names]}
	if status:
		filters["status"] = status
	rows = frappe.db.get_all(
		"Collab Dispute", filters=filters,
		fields=["name", "deal", "status", "reason", "raised_by_role", "raised_at", "resolved_at"],
		order_by="creation desc",
	)
	return {"success": True, "data": {"disputes": rows}}


@frappe.whitelist()
def list_outlet_disputes(outlet_id=None, status=None):
	if not outlet_id:
		return {"success": True, "data": {"disputes": []}}
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	deal_names = frappe.db.get_all("Collab Deal", filters={"outlet": outlet}, pluck="name")
	if not deal_names:
		return {"success": True, "data": {"disputes": []}}
	filters = {"deal": ["in", deal_names]}
	if status:
		filters["status"] = status
	rows = frappe.db.get_all(
		"Collab Dispute", filters=filters,
		fields=["name", "deal", "status", "reason", "raised_by_role", "raised_at", "resolved_at"],
		order_by="creation desc",
	)
	return {"success": True, "data": {"disputes": rows}}


@frappe.whitelist()
def list_pending_review(limit=50):
	"""Ops queue — every dispute waiting on a human resolution decision."""
	_require_system_manager()
	rows = frappe.db.get_all(
		"Collab Dispute", filters={"status": ["in", ["evidence", "review"]]},
		fields=["name", "deal", "status", "reason", "raised_by_role", "raised_at", "evidence_due_at", "resolution_due_at"],
		order_by="raised_at asc", limit_page_length=min(int(limit), 200),
	)
	return {"success": True, "data": {"disputes": rows}}


# ── background job ───────────────────────────────────────────────────────

def sweep_dispute_slas():
	"""Scheduled job (every 15 min, see hooks.py):
	  - evidence window expired, still in 'evidence' -> move to 'review'
	    regardless of whether both sides submitted (a party who never
	    responds doesn't get to stall the deal forever)
	  - resolution SLA breached, still in 'review' -> log a loud error so
	    ops actually sees it (never auto-resolves money without a human)
	  - resolved past the appeal window with no appeal requested ->
	    auto-close (money already moved at resolution; closing just
	    finalises the record)
	"""
	now = now_datetime()

	expired_evidence = frappe.db.get_all(
		"Collab Dispute", filters={"status": "evidence", "evidence_due_at": ["<=", now]}, pluck="name",
	)
	for name in expired_evidence:
		try:
			d = frappe.get_doc("Collab Dispute", name)
			d.status = "review"
			d.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error(title="collab_disputes.sweep_evidence_expiry", message=frappe.get_traceback())

	breached = frappe.db.get_all(
		"Collab Dispute", filters={"status": "review", "resolution_due_at": ["<=", now]}, pluck="name",
	)
	for name in breached:
		frappe.log_error(
			title=RESOLUTION_SLA_BREACH_LOG,
			message=f"Dispute {name} has been in 'review' past its 48h resolution SLA — needs ops attention now.",
		)

	appeal_cutoff = add_to_date(now, hours=-APPEAL_WINDOW_HOURS)
	stale_resolved = frappe.db.get_all(
		"Collab Dispute",
		filters={"status": "resolved", "appeal_requested": 0, "resolved_at": ["<=", appeal_cutoff]},
		pluck="name",
	)
	for name in stale_resolved:
		try:
			d = frappe.get_doc("Collab Dispute", name)
			d.status = "closed"
			d.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error(title="collab_disputes.sweep_auto_close", message=frappe.get_traceback())
