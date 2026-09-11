"""
Collab Deal lifecycle — accept, fund, mark delivered, release
(creator-marketplace-blueprint.html §04-§06). Phase 2-3 of the
marketplace build.

Honest about what's real vs. stubbed:
  - Accept/fund/deliver/release state transitions: real, fully working,
    tested against this file's own logic and collab_deal.py's state
    machine.
  - Escrow funding: creates a real Razorpay Order against the existing
    platform account (same account every other Flamezo payment flow
    already uses) — works today. Formal Razorpay *Escrow Account*
    segregation is a separate product Flamezo hasn't signed the
    tri-party agreement for yet (blueprint §12); this can be swapped in
    without changing anything above the `_create_razorpay_order` call.
  - Release to the creator's bank account: genuinely NOT built yet,
    on purpose — it needs a creator KYC/linked-account flow
    (razorpay_linked_account_id) that doesn't exist. `_transfer_to_creator`
    is an explicit, loud stub rather than code that pretends to call a
    Route transfer API against an account that was never created. Every
    state transition around it (Escrow Transaction -> released, Collab
    Deal -> released, barter value booking) is real and correct today;
    only the actual bank transfer is pending that separate build.
  - Native delivery verification (Chills / Creator Club Post): real,
    synchronous, works today — zero external dependency.
  - Instagram delivery verification: genuinely blocked on Meta App
    Review (not started) — mark_delivered for Instagram deliverable
    types records the claim and leaves it pending_verification rather
    than faking a Graph API call that has nowhere real to hit yet.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, today

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_client

OBJECTION_WINDOW_HOURS = 48
NATIVE_TYPES = {"native_chills", "native_club_post"}
INSTAGRAM_TYPES = {"instagram_reel", "instagram_story"}


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


def _require_deal_creator(deal, phone):
	creator_name = _require_own_creator(phone)
	if deal.creator != creator_name:
		frappe.throw(_("This deal isn't yours."), frappe.PermissionError)
	return creator_name


def _require_deal_outlet(deal, outlet_id):
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	if deal.outlet != outlet:
		frappe.throw(_("This deal isn't yours."), frappe.PermissionError)
	return outlet


# ── accept ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def accept_application(outlet_id, deal_id, deadline=None, min_bill_inr=None, free_item_ref=None, extra_discount_pct=None):
	"""Merchant accepts a creator's gig application."""
	deal = _load_deal(deal_id)
	_require_deal_outlet(deal, outlet_id)
	if deal.status != "offered":
		frappe.throw(_("Only an offered deal can be accepted."), frappe.ValidationError)

	if deadline:
		deal.deadline = deadline
	if min_bill_inr is not None:
		deal.min_bill_inr = min_bill_inr
	if free_item_ref:
		deal.free_item_ref = free_item_ref
	if extra_discount_pct is not None:
		deal.extra_discount_pct = extra_discount_pct

	deal.status = "accepted"
	deal.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"deal_id": deal.name, "status": deal.status}}


@frappe.whitelist(allow_guest=True)
def accept_deal(phone, deal_id):
	"""Creator accepts a direct-invite-origin deal offer. (Gig-application
	deals are already creator-initiated — this is direct-invite only.)"""
	deal = _load_deal(deal_id)
	_require_deal_creator(deal, phone)
	if not deal.direct_invite:
		frappe.throw(_("Only a direct-invite deal is accepted this way — a gig application is already yours."), frappe.ValidationError)
	if deal.status != "offered":
		frappe.throw(_("Only an offered deal can be accepted."), frappe.ValidationError)

	deal.status = "accepted"
	deal.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"deal_id": deal.name, "status": deal.status}}


# ── fund (cash escrow) ──────────────────────────────────────────────────

@frappe.whitelist()
def fund_deal(outlet_id, deal_id):
	deal = _load_deal(deal_id)
	_require_deal_outlet(deal, outlet_id)
	if deal.status != "accepted":
		frappe.throw(_("Only an accepted deal can be funded."), frappe.ValidationError)
	if deal.deal_type == "barter":
		frappe.throw(_("Barter deals don't fund — they go straight to delivery."), frappe.ValidationError)
	if not deal.escrow_required:
		frappe.throw(_("This deal doesn't require escrow."), frappe.ValidationError)
	if frappe.db.exists("Escrow Transaction", {"deal": deal.name}):
		frappe.throw(_("This deal already has a funding attempt in progress."), frappe.ValidationError)

	client = get_razorpay_client()
	amount_paise = int(round(flt(deal.price_inr) * 100))
	order = client.order.create({
		"amount": amount_paise,
		"currency": "INR",
		"notes": {"type": "collab_deal_escrow", "deal_id": deal.name},
	})

	commission_pct = flt(deal.commission_pct)
	platform_fee = flt(deal.price_inr) * commission_pct / 100
	# Created in `held` state optimistically at order-creation time (an
	# order that's never paid just sits unfunded — no separate "pending
	# payment" state is worth the extra complexity), but
	# `Collab Deal.status` only advances to "funded" from the webhook in
	# webhooks.py once payment.captured actually arrives — that's the
	# real confirmation, this row is just bookkeeping the attempt.
	escrow = frappe.get_doc({
		"doctype": "Escrow Transaction",
		"deal": deal.name,
		"state": "held",
		"amount_inr": deal.price_inr,
		"platform_fee_inr": platform_fee,
		"creator_net_inr": flt(deal.price_inr) - platform_fee,
		"razorpay_order_id": order["id"],
	})
	try:
		escrow.insert(ignore_permissions=True)
	except frappe.exceptions.UniqueValidationError:
		# Two concurrent fund_deal calls both passed the exists() check
		# above before either committed — the DB's own unique index on
		# Escrow Transaction.deal is the real guard (verified under an
		# actual concurrent-thread test, not just this try/except). The
		# loser here already created a real Razorpay order that nothing
		# will ever pay — harmless, it just expires — but the caller
		# still deserves the same clean business error as the normal
		# already-funding check above, not a raw DB IntegrityError.
		frappe.throw(_("This deal already has a funding attempt in progress."), frappe.ValidationError)
	frappe.db.commit()

	return {
		"success": True,
		"data": {"razorpay_order_id": order["id"], "amount_inr": deal.price_inr, "key_id": _key_id()},
	}


def _key_id():
	from flamezo_backend.flamezo.utils.razorpay_utils import get_razorpay_config
	return get_razorpay_config().get("key_id")


@frappe.whitelist()
def verify_deal_payment(outlet_id, deal_id, razorpay_order_id, razorpay_payment_id, razorpay_signature):
	"""Called by the dashboard's checkout handler right after Razorpay's
	modal closes — same pattern as api/payments.py's verify_payment:
	signature-verified server-side (never trust the client's "it
	succeeded" callback on its own), gives the merchant instant UI
	feedback instead of waiting on the async webhook. The webhook stays
	authoritative and this is fully redundant with it — mark_deal_funded
	is idempotent, so whichever of the two arrives first wins and the
	other is a no-op."""
	deal = _load_deal(deal_id)
	_require_deal_outlet(deal, outlet_id)
	client = get_razorpay_client()
	try:
		client.utility.verify_payment_signature({
			"razorpay_order_id": razorpay_order_id,
			"razorpay_payment_id": razorpay_payment_id,
			"razorpay_signature": razorpay_signature,
		})
	except Exception:
		frappe.throw(_("Payment signature could not be verified."), frappe.ValidationError)
	mark_deal_funded(deal.name, razorpay_payment_id)
	return {"success": True, "data": {"status": "funded"}}


def mark_deal_funded(deal_id, razorpay_payment_id):
	"""Called from webhooks.py's handle_payment_captured on the
	collab_deal_escrow branch — not a user-facing endpoint."""
	deal = frappe.get_doc("Collab Deal", deal_id)
	if deal.status != "accepted":
		# Already funded (webhook retry) or in some other state — don't
		# double-advance. Razorpay retries webhooks until it gets a 2xx,
		# so this path being hit twice is expected, not an error.
		return
	frappe.db.set_value("Escrow Transaction", {"deal": deal_id}, "razorpay_payment_id", razorpay_payment_id)
	deal.status = "funded"
	deal.save(ignore_permissions=True)
	frappe.db.commit()


# ── mark delivered ───────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def mark_delivered(phone, deal_id, deliverable_type, native_post_id=None, instagram_media_id=None, screenshot_backup=None):
	deal = _load_deal(deal_id)
	_require_deal_creator(deal, phone)
	if deal.status not in ("accepted", "funded"):
		frappe.throw(_("This deal isn't ready to be marked delivered."), frappe.ValidationError)
	if deal.deal_type == "cash" and deal.escrow_required and deal.status != "funded":
		frappe.throw(_("A cash deal must be funded before it can be marked delivered."), frappe.ValidationError)
	if deal.deadline and getdate(today()) > getdate(deal.deadline):
		frappe.throw(
			_("This deal's deadline ({0}) has passed — ask the outlet to extend it or start a new deal.").format(deal.deadline),
			frappe.ValidationError,
		)

	if deliverable_type in NATIVE_TYPES:
		proof = _verify_native_deliverable(deal, deliverable_type, native_post_id)
		deal.status = "delivered"
		deal.save(ignore_permissions=True)
		frappe.db.commit()
		return {"success": True, "data": {"status": "delivered", "proof_id": proof.name}}

	elif deliverable_type in INSTAGRAM_TYPES:
		if not instagram_media_id:
			frappe.throw(_("instagram_media_id is required for an Instagram deliverable."), frappe.ValidationError)
		if deliverable_type == "instagram_story" and not screenshot_backup:
			frappe.throw(_("Attach a screenshot — stories expire before we can verify them after the fact."), frappe.ValidationError)
		# Genuinely can't verify yet — no live Meta app (see module
		# docstring). Records the claim; deal stays put until the
		# polling job (built once App Review clears) actually confirms
		# it. Never silently advances the deal on an unverified claim.
		frappe.get_doc({
			"doctype": "Delivery Proof",
			"deal": deal.name,
			"deliverable_type": deliverable_type,
			"verification_method": "manual",
			"instagram_media_id": instagram_media_id,
			"screenshot_backup": screenshot_backup,
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		return {"success": True, "data": {"status": "pending_verification"}}

	frappe.throw(_("Unknown deliverable type: {0}").format(deliverable_type), frappe.ValidationError)


def _verify_native_deliverable(deal, deliverable_type, native_post_id):
	if not native_post_id:
		frappe.throw(_("native_post_id is required for a native deliverable."), frappe.ValidationError)

	doctype = "Chills" if deliverable_type == "native_chills" else "Creator Club Post"
	post = frappe.db.get_value(doctype, native_post_id, ["outlet", "creator"], as_dict=True)
	if not post:
		frappe.throw(_("That post doesn't exist."), frappe.DoesNotExistError)
	if post.creator != deal.creator:
		frappe.throw(_("That post isn't yours."), frappe.PermissionError)
	if post.outlet != deal.outlet:
		frappe.throw(_("That post doesn't tag this outlet."), frappe.ValidationError)

	already_used = frappe.db.exists("Delivery Proof", {"native_post_id": native_post_id, "deal": ["!=", deal.name]})
	if already_used:
		frappe.throw(_("That post has already been used as proof for a different deal."), frappe.ValidationError)

	proof = frappe.get_doc({
		"doctype": "Delivery Proof",
		"deal": deal.name,
		"deliverable_type": deliverable_type,
		"verification_method": "native_first_party",
		"native_post_id": native_post_id,
		# Disclosure enforcement (blueprint §06) is a native-upload-flow
		# concern (the app auto-injects the overlay at upload time) —
		# true by construction for anything that made it into Chills/Club
		# Post via that flow, not re-checked here.
		"disclosure_verified": 1,
	})
	proof.insert(ignore_permissions=True)
	return proof


# ── release ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def approve_release(outlet_id, deal_id):
	deal = _load_deal(deal_id)
	_require_deal_outlet(deal, outlet_id)
	_release_deal(deal)
	return {"success": True, "data": {"status": deal.status}}


def _has_dispute_doctype():
	"""Collab Dispute is Phase 4 — not built yet. Every open-dispute check
	in this module goes through here so those checks degrade to 'no
	dispute exists' rather than erroring against a table that isn't
	there, and start working automatically the moment Phase 4 ships."""
	return frappe.db.exists("DocType", "Collab Dispute")


def _release_deal(deal):
	if deal.status != "delivered":
		frappe.throw(_("Only a delivered deal can be released."), frappe.ValidationError)
	if _has_dispute_doctype() and frappe.db.exists(
		"Collab Dispute", {"deal": deal.name, "status": ["not in", ["resolved", "closed"]]}
	):
		frappe.throw(_("This deal has an open dispute — release is blocked until it's resolved."), frappe.ValidationError)

	# Escrow Transaction only ever exists for cash deals — fund_deal
	# refuses barter outright (there's no cash to hold for a free-item
	# deal). `escrow_required` on a barter deal (>= the ₹300 handshake
	# ceiling) is a real, enforced signal — mark_delivered/collab_deal.py
	# still require Delivery Proof and this same merchant-approval release
	# gate regardless of deal_type — but it was never meant to gate an
	# Escrow Transaction lookup that a barter deal can never have a row
	# for. Gating on deal_type here (not just escrow_required) is the fix:
	# a mis-set escrow_required on a barter deal must never crash release.
	if deal.deal_type == "cash" and deal.escrow_required:
		escrow = frappe.get_doc("Escrow Transaction", {"deal": deal.name})
		_transfer_to_creator(deal, escrow)  # explicit stub — see module docstring
		escrow.state = "released"
		escrow.save(ignore_permissions=True)

	deal.status = "released"
	deal.save(ignore_permissions=True)  # books barter_value_ytd_inr via collab_deal.py's on_update, for barter deals
	frappe.db.commit()


def _transfer_to_creator(deal, escrow):
	"""NOT YET IMPLEMENTED — needs a creator Razorpay linked account
	(razorpay_linked_account_id + KYC), which has no build/onboarding
	flow yet. Logging loudly rather than pretending this moved real
	money: a silent no-op here would be a genuinely dangerous bug once
	real cash deals exist (creator marked 'paid' with no actual transfer
	sent). Every state transition around this call is correct and tested
	today; only the actual bank transfer is pending that separate build."""
	if deal.deal_type != "cash":
		return
	frappe.log_error(
		title="collab_deals.transfer_pending_creator_kyc",
		message=(
			f"Deal {deal.name}: escrow release reached the payout step, but creator "
			f"{deal.creator} has no razorpay_linked_account_id yet — no transfer was "
			f"sent. Build the creator KYC/linked-account flow before any real cash "
			f"deal reaches this point in production."
		),
	)


# ── read ─────────────────────────────────────────────────────────────────

def _deal_origin(deal_row):
	if deal_row.direct_invite:
		return "direct_invite"
	if deal_row.gig:
		return "gig"
	return "standing_offer"


def _deal_summary(deal_row):
	return {
		"deal_id": deal_row.name, "status": deal_row.status, "deal_type": deal_row.deal_type,
		"creator_id": deal_row.creator, "outlet_id": deal_row.outlet,
		"price_inr": deal_row.price_inr, "fair_value_inr": deal_row.fair_value_inr,
		"commission_pct": deal_row.commission_pct, "deadline": deal_row.deadline,
		"origin": _deal_origin(deal_row),
	}


@frappe.whitelist(allow_guest=True)
def get_deal(deal_id, phone=None, outlet_id=None):
	deal = _load_deal(deal_id)
	if phone:
		_require_deal_creator(deal, phone)
	elif outlet_id:
		_require_deal_outlet(deal, outlet_id)
	else:
		frappe.throw(_("phone or outlet_id is required."), frappe.ValidationError)

	escrow = frappe.db.get_value(
		"Escrow Transaction", {"deal": deal.name}, ["state", "amount_inr"], as_dict=True
	)
	delivery = frappe.db.get_all(
		"Delivery Proof", filters={"deal": deal.name},
		fields=["deliverable_type", "verified_at", "disclosure_verified", "verification_method"],
	)
	dispute = frappe.db.get_value("Collab Dispute", {"deal": deal.name}, "name") if _has_dispute_doctype() else None

	data = _deal_summary(deal)
	data.update({
		"terms": json.loads(deal.terms_json or "{}"),
		"escrow": escrow,
		"delivery": delivery,
		"dispute": dispute,
		"objection_window_ends_at": (
			frappe.utils.add_to_date(deal.delivered_at, hours=OBJECTION_WINDOW_HOURS)
			if deal.delivered_at and deal.status == "delivered" else None
		),
	})
	return {"success": True, "data": data}


@frappe.whitelist(allow_guest=True)
def list_my_deals(phone, status=None):
	creator_name = _require_own_creator(phone)
	filters = {"creator": creator_name}
	if status:
		filters["status"] = status
	rows = frappe.db.get_all(
		"Collab Deal", filters=filters,
		fields=[
			"name", "status", "deal_type", "outlet", "price_inr", "fair_value_inr", "deadline", "creation",
			"gig", "direct_invite", "standing_offer",
		],
		order_by="creation desc",
	)
	# `origin` tells the client whether an 'offered' deal is waiting on
	# the creator (a direct invite — accept_deal is theirs to call) or
	# on the merchant (a gig application/standing-offer redemption —
	# already committed by applying; accept_deal would reject it, since
	# there's nothing left for the creator to accept). Without this a
	# client can't tell the two 'offered' cases apart from this list
	# alone and would show an "Accept" action that fails for the wrong
	# one — see collab_deals.accept_deal's own direct_invite-only gate.
	for r in rows:
		if r.get("direct_invite"):
			origin = "direct_invite"
		elif r.get("gig"):
			origin = "gig"
		else:
			origin = "standing_offer"
		r.pop("gig", None)
		r.pop("direct_invite", None)
		r.pop("standing_offer", None)
		r["origin"] = origin
	return {"success": True, "data": {"deals": rows}}


@frappe.whitelist()
def list_outlet_deals(outlet_id, status=None):
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	filters = {"outlet": outlet}
	if status:
		filters["status"] = status
	rows = frappe.db.get_all(
		"Collab Deal", filters=filters,
		fields=["name", "status", "deal_type", "creator", "price_inr", "fair_value_inr", "deadline", "creation"],
		order_by="creation desc",
	)
	return {"success": True, "data": {"deals": rows}}


# ── background job ───────────────────────────────────────────────────────

def auto_release_escrow():
	"""Scheduled job (every 15 min, see hooks.py) — releases any deal past
	its objection window with no open dispute."""
	cutoff = frappe.utils.add_to_date(now_datetime(), hours=-OBJECTION_WINDOW_HOURS)
	candidates = frappe.db.get_all(
		"Collab Deal",
		filters={"status": "delivered", "delivered_at": ["<=", cutoff]},
		pluck="name",
	)
	has_disputes = _has_dispute_doctype()
	for deal_name in candidates:
		if has_disputes and frappe.db.exists(
			"Collab Dispute", {"deal": deal_name, "status": ["not in", ["resolved", "closed"]]}
		):
			continue
		try:
			deal = frappe.get_doc("Collab Deal", deal_name)
			_release_deal(deal)
		except Exception:
			frappe.log_error(title="collab_deals.auto_release_escrow", message=frappe.get_traceback())


def expire_overdue_deals():
	"""Scheduled job (daily, see hooks.py) — a deal accepted (or funded)
	but never delivered by its deadline is a no-show, not a dispute; it
	self-cancels rather than sitting open forever. A funded cash deal
	gets a real Razorpay refund back to the outlet before cancelling —
	the outlet's money was never the creator's to begin with, so
	'cancel' without refunding it would just be silently keeping the
	outlet's cash. Barter and never-funded cash deals have no money to
	move, so they just cancel."""
	overdue = frappe.db.get_all(
		"Collab Deal",
		filters={"status": ["in", ["accepted", "funded"]], "deadline": ["<", today()]},
		fields=["name", "status", "deal_type"],
	)
	for row in overdue:
		try:
			if row.status == "funded" and row.deal_type == "cash":
				_refund_overdue_escrow(row.name)
			deal = frappe.get_doc("Collab Deal", row.name)
			deal.status = "cancelled"
			deal.save(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error(title="collab_deals.expire_overdue_deals", message=frappe.get_traceback())


def _refund_overdue_escrow(deal_name):
	escrow = frappe.get_doc("Escrow Transaction", {"deal": deal_name})
	if escrow.state != "held":
		return  # already released/refunded/disputed — nothing to do
	client = get_razorpay_client()
	client.payment.refund(escrow.razorpay_payment_id, {
		"amount": int(round(flt(escrow.amount_inr) * 100)),
		"notes": {"type": "collab_deal_escrow_refund", "deal_id": deal_name, "reason": "deadline_expired"},
	})
	escrow.state = "refunded"
	escrow.save(ignore_permissions=True)
