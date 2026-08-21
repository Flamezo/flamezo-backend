"""
Creator Collab Invites — merchant-initiated collabs
(creator-program-fundamentals-v1-locked.md Section 8).

Note on caps: the original product doc split invite limits by merchant
plan (Silver 2/month, Gold 10/month). That distinction no longer exists —
`patches/migrate_silver_to_gold_2026.py` consolidated every restaurant
onto a single GOLD plan as part of the broader business-model pivot. This
module uses one flat monthly cap for every merchant instead of resurrecting
a two-tier system the rest of the app no longer has.

Three independent limits, all enforced automatically, no manual review:
  - Per merchant: `MONTHLY_INVITE_CAP` invites sent per calendar month
  - Per creator-merchant pair: `COOLDOWN_DAYS` after any COMPLETED collab
    before the same merchant can invite the same creator again
  - Per creator: `WEEKLY_ACCEPT_CAP` accepted invites per week — the
    (WEEKLY_ACCEPT_CAP + 1)th+ acceptance in a week auto-waitlists instead
    of confirming immediately
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_first_day, get_last_day, getdate, now_datetime

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone

MONTHLY_INVITE_CAP = 5   # flat cap for every merchant — see module docstring
COOLDOWN_DAYS = 30        # per creator-merchant pair, after a completed collab
WEEKLY_ACCEPT_CAP = 3     # per creator, across all merchants


def _require_outlet_access(outlet_id):
	"""Merchant-side auth — same `validate_restaurant_for_api` helper every
	other merchant-portal endpoint in the app uses (commission.py, boost.py,
	etc.). Resolves the outlet AND verifies `frappe.session.user` actually
	manages it; raises PermissionError otherwise. Returns the resolved
	restaurant name."""
	return validate_restaurant_for_api(outlet_id, frappe.session.user)


def _require_creator_phone(invite, phone):
	"""Creator-side auth for accept/decline — verifies a real verified
	session for `phone`, AND that `phone` is actually this invite's own
	creator (normalized both sides — Flamezo Creator.customer_phone can
	carry a +91 prefix while session phones never do, same gotcha fixed
	in clubs.py's is_admin check)."""
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)
	creator_phone = frappe.db.get_value("Flamezo Creator", invite.creator, "customer_phone")
	if normalize_phone(phone) != normalize_phone(creator_phone or ""):
		frappe.throw(_("This invite isn't yours to respond to."), frappe.PermissionError)


# ── merchant discovery ──────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def discover_creators(category=None, city=None, min_followers=None, page=1, limit=20):
	"""Merchant-facing browse — filters by category/city/follower count.
	`available_this_week` tells the merchant whether this creator has
	room left in their weekly accept cap before they invite, rather than
	finding out after the fact."""
	page = max(1, cint(page))
	limit = min(cint(limit), 50)
	offset = (page - 1) * limit

	conditions = ["fc.status='approved'"]
	params = []
	if category:
		conditions.append("cc.category=%s")
		params.append(category)
	if city:
		conditions.append("fc.city=%s")
		params.append(city)
	if min_followers:
		conditions.append("fc.meta_followers>=%s")
		params.append(cint(min_followers))

	where = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT fc.name AS creator_id, fc.display_name, fc.meta_followers, fc.city,
		       cc.name AS club_id, cc.club_name, cc.category, cc.niche, cc.followers_count
		FROM `tabFlamezo Creator` fc
		JOIN `tabCreator Club` cc ON cc.creator = fc.name
		WHERE {where} AND cc.is_active=1
		ORDER BY fc.meta_followers DESC
		LIMIT %s OFFSET %s
		""",
		params + [limit + 1, offset],
		as_dict=True,
	)
	has_more = len(rows) > limit
	creators = rows[:limit]
	for c in creators:
		c["available_this_week"] = _accepted_this_week_count(c["creator_id"]) < WEEKLY_ACCEPT_CAP

	return {"success": True, "data": {"creators": creators, "page": page, "has_more": has_more}}


@frappe.whitelist(allow_guest=True)
def get_my_collab_invites(phone, status=None):
	"""Creator-facing — their own invites (any status, or filtered), most
	recent first. This is what a "Collab Invites" screen in the app reads
	from; without it a creator has no way to even see an invite exists to
	accept/decline."""
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
		return {"success": True, "data": {"invites": []}}

	filters = {"creator": creator_name}
	if status:
		filters["status"] = status

	rows = frappe.db.sql(
		"""
		SELECT ci.name, ci.outlet, ci.status, ci.offer_details, ci.deliverable,
		       ci.proposed_date, ci.completed_at, ci.merchant_rating, ci.creation,
		       r.restaurant_name AS outlet_name
		FROM `tabCreator Collab Invite` ci
		LEFT JOIN `tabOutlet` r ON r.name = ci.outlet
		WHERE ci.creator=%(creator)s {status_clause}
		ORDER BY ci.creation DESC
		""".format(status_clause="AND ci.status=%(status)s" if status else ""),
		{"creator": creator_name, "status": status},
		as_dict=True,
	)
	return {"success": True, "data": {"invites": rows}}


# ── send / accept / decline / complete ──────────────────────────────────

@frappe.whitelist()
def send_collab_invite(outlet_id, creator_id, offer_details, deliverable=None, proposed_date=None):
	"""Merchant sends an invite — auto-enforces the monthly cap and the
	per-pair cooldown, no human approval needed for a legitimate send.
	`outlet_id` must belong to the calling user (`validate_restaurant_for_api`
	throws PermissionError otherwise) — closes a real gap where anyone
	could previously send invites on any merchant's behalf."""
	outlet_id = _require_outlet_access(outlet_id)
	if not frappe.db.exists("Flamezo Creator", creator_id):
		frappe.throw(_("Creator not found"), frappe.DoesNotExistError)

	sent_this_month = _invites_sent_this_month(outlet_id)
	if sent_this_month >= MONTHLY_INVITE_CAP:
		frappe.throw(
			_(f"Monthly invite limit reached ({MONTHLY_INVITE_CAP}/month). Try again next month."),
			frappe.ValidationError,
		)

	cooldown_remaining = _cooldown_remaining_days(outlet_id, creator_id)
	if cooldown_remaining > 0:
		frappe.throw(
			_(f"This creator completed a collab with you recently — {cooldown_remaining} day(s) left before you can invite them again."),
			frappe.ValidationError,
		)

	invite = frappe.get_doc({
		"doctype": "Creator Collab Invite",
		"outlet": outlet_id,
		"creator": creator_id,
		"offer_details": offer_details,
		"deliverable": deliverable,
		"proposed_date": proposed_date,
		"status": "pending",
	})
	invite.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"invite_id": invite.name}}


@frappe.whitelist(allow_guest=True)
def respond_to_invite(invite_id, accept, phone):
	"""Creator accepts or declines. Accepting past the weekly cap
	auto-waitlists instead of confirming — protects creators from being
	overwhelmed without them having to manage their own capacity.
	`phone` must be a verified session belonging to THIS invite's own
	creator — closes a real gap where anyone could previously accept/
	decline any creator's invites."""
	invite = frappe.get_doc("Creator Collab Invite", invite_id)
	_require_creator_phone(invite, phone)
	if invite.status != "pending":
		frappe.throw(_(f"This invite is already {invite.status}."), frappe.ValidationError)

	accept = cint(accept)
	if not accept:
		invite.status = "declined"
		invite.save(ignore_permissions=True)
		frappe.db.commit()
		return {"success": True, "data": {"status": "declined"}}

	accepted_this_week = _accepted_this_week_count(invite.creator)
	invite.status = "accepted" if accepted_this_week < WEEKLY_ACCEPT_CAP else "waitlisted"
	invite.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"status": invite.status}}


@frappe.whitelist()
def complete_collab(invite_id, merchant_rating=None):
	"""Marks a collab completed — this is what
	`creator_score_engine._gather_collab_signals` reads to compute the
	rating-weighted quality points for that creator's weekly score
	(creator-weekly-score-algorithm.md Section 10, Tier 3). Only the
	invite's own outlet owner can complete/rate it — closes a real gap
	where anyone could previously mark any invite completed with any
	rating."""
	invite = frappe.get_doc("Creator Collab Invite", invite_id)
	_require_outlet_access(invite.outlet)
	if invite.status not in ("accepted", "waitlisted"):
		frappe.throw(_(f"Cannot complete an invite with status '{invite.status}'."), frappe.ValidationError)

	invite.status = "completed"
	invite.completed_at = now_datetime()
	if merchant_rating is not None:
		rating = cint(merchant_rating)
		if not (1 <= rating <= 5):
			frappe.throw(_("merchant_rating must be between 1 and 5"), frappe.ValidationError)
		invite.merchant_rating = rating
	invite.save(ignore_permissions=True)
	frappe.db.commit()
	return {"success": True, "data": {"status": "completed"}}


# ── internal helpers (also used by creator_score_engine.py) ─────────────

def _invites_sent_this_month(outlet_id) -> int:
	today = getdate()
	start = get_first_day(today)
	end = get_last_day(today)
	return frappe.db.count("Creator Collab Invite", {
		"outlet": outlet_id,
		"creation": ["between", [start, end]],
	})


def _cooldown_remaining_days(outlet_id, creator_id) -> int:
	last_completed = frappe.db.get_value(
		"Creator Collab Invite",
		{"outlet": outlet_id, "creator": creator_id, "status": "completed"},
		"completed_at",
		order_by="completed_at desc",
	)
	if not last_completed:
		return 0
	days_since = (now_datetime() - frappe.utils.get_datetime(last_completed)).days
	return max(0, COOLDOWN_DAYS - days_since)


def _accepted_this_week_count(creator_id) -> int:
	today = getdate()
	week_start = today - timedelta(days=today.weekday())
	week_end = week_start + timedelta(days=6)
	return frappe.db.count("Creator Collab Invite", {
		"creator": creator_id,
		"status": ["in", ["accepted", "completed"]],
		"creation": ["between", [week_start, week_end]],
	})
