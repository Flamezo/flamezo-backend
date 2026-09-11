"""
Collab Gig board — merchants post open gigs, creators browse and apply
(creator-marketplace-blueprint.html §02, §16). Phase 1 of the
marketplace build.

Every application is a real Collab Deal in status="offered" — not a
separate "application" record — so the deal lifecycle (accept, fund,
deliver, release, dispute) is identical regardless of whether it started
as a gig application or a direct invite. See collab_deal.py's state
machine.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, now_datetime

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils.creator_badges import get_creator_badge_tier, meets_minimum_tier, TIER_ORDER

MAX_OPEN_GIGS_PER_OUTLET = 10  # defensive cap — keeps the board from being cluttered by one merchant
MAX_LIST_LIMIT = 50

# "Pitch Slots" — how many gigs a creator can have simultaneously pending
# (Collab Deal.status == "offered") at once, tiered by badge. Not a
# purchased/earned currency like Upwork Connects — deliberately simpler:
# a slot frees the moment a merchant accepts/declines or a gig closes, no
# balance to track, no economy to maintain. Caps blanket-applying while
# giving proven creators more room, reusing the badge system rather than
# inventing a parallel reputation mechanic.
PITCH_SLOT_LIMITS = {
	"new_creator": 3,
	"verified_creator": 3,
	"top_rated": 6,
	"elite_creator": 10,
}


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


# ── merchant: post & manage gigs ────────────────────────────────────────

@frappe.whitelist()
def create_gig(outlet_id, title, deliverables, budget_inr=0, barter_allowed=0, barter_details=None,
	category=None, expires_at=None, merchant_covers_tds=0, min_followers=0, min_badge_tier=None):
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)

	open_count = frappe.db.count("Collab Gig", {"outlet": outlet, "status": "open"})
	if open_count >= MAX_OPEN_GIGS_PER_OUTLET:
		frappe.throw(
			_("You already have {0} open gigs — close one before posting another.").format(open_count),
			frappe.ValidationError,
		)

	if isinstance(deliverables, str):
		deliverables_json = deliverables  # already JSON-encoded by the caller
	else:
		deliverables_json = json.dumps(deliverables)

	gig = frappe.get_doc({
		"doctype": "Collab Gig",
		"outlet": outlet,
		"title": title,
		"deliverables_json": deliverables_json,
		"budget_inr": budget_inr,
		"barter_allowed": _bool(barter_allowed),
		"barter_details": barter_details,
		"category": category,
		"expires_at": expires_at,
		"merchant_covers_tds": _bool(merchant_covers_tds),
		"min_followers": min_followers,
		"min_badge_tier": min_badge_tier,
	})
	gig.insert(ignore_permissions=True)  # doctype-level validate() does the real checks
	frappe.db.commit()

	return {"success": True, "data": {"gig_id": gig.name, "status": gig.status}}


@frappe.whitelist()
def list_my_gigs(outlet_id, status=None):
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	filters = {"outlet": outlet}
	if status:
		filters["status"] = status

	rows = frappe.db.get_all(
		"Collab Gig",
		filters=filters,
		fields=["name", "title", "status", "budget_inr", "barter_allowed", "category", "expires_at", "creation"],
		order_by="creation desc",
	)
	gig_names = [r.name for r in rows]
	app_counts = {}
	if gig_names:
		count_rows = frappe.db.sql(
			"""SELECT gig, COUNT(*) AS cnt FROM `tabCollab Deal`
			   WHERE gig IN %(gigs)s GROUP BY gig""",
			{"gigs": gig_names},
			as_dict=True,
		)
		app_counts = {r.gig: r.cnt for r in count_rows}
	for r in rows:
		r["applications_count"] = app_counts.get(r.name, 0)

	return {"success": True, "data": {"gigs": rows}}


@frappe.whitelist()
def list_applications(outlet_id, gig_id):
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	gig_outlet = frappe.db.get_value("Collab Gig", gig_id, "outlet")
	if gig_outlet != outlet:
		frappe.throw(_("This gig isn't yours."), frappe.PermissionError)

	rows = frappe.db.sql(
		"""
		SELECT d.name AS deal_id, d.creator AS creator_id, d.deal_type,
		       d.price_inr AS proposed_price_inr, d.fair_value_inr AS proposed_fair_value_inr,
		       d.status, d.creation,
		       c.display_name AS creator_name, c.meta_followers AS follower_count
		FROM `tabCollab Deal` d
		LEFT JOIN `tabFlamezo Creator` c ON c.name = d.creator
		WHERE d.gig = %(gig_id)s
		ORDER BY d.creation DESC
		""",
		{"gig_id": gig_id},
		as_dict=True,
	)
	return {"success": True, "data": {"applications": rows}}


@frappe.whitelist()
def close_gig(outlet_id, gig_id):
	outlet = validate_restaurant_for_api(outlet_id, frappe.session.user)
	gig = frappe.get_doc("Collab Gig", gig_id)
	if gig.outlet != outlet:
		frappe.throw(_("This gig isn't yours."), frappe.PermissionError)
	if gig.status != "open":
		frappe.throw(_("Only an open gig can be closed."), frappe.ValidationError)

	gig.status = "filled"
	gig.save(ignore_permissions=True)

	# Any still-pending applications auto-decline — nothing should be left
	# dangling in "offered" against a gig that's no longer accepting them.
	pending = frappe.db.get_all("Collab Deal", {"gig": gig_id, "status": "offered"}, pluck="name")
	for deal_name in pending:
		deal = frappe.get_doc("Collab Deal", deal_name)
		deal.status = "cancelled"
		deal.save(ignore_permissions=True)

	frappe.db.commit()
	return {"success": True, "data": {"status": "filled", "declined_count": len(pending)}}


# ── creator: browse & apply ──────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def list_gigs(category=None, city=None, min_budget=None, barter_only=None, phone=None, page=1, limit=20):
	"""`phone` is optional — anonymous/guest browsing sees every open gig
	unfiltered. When a real creator session is passed, gigs they don't
	meet the eligibility bar for are filtered out client-side of the SQL
	(one badge-tier computation for the browsing creator, not one per
	gig — the eligibility check itself is a cheap in-memory comparison
	against each row already fetched)."""
	page = max(cint(page), 1)
	limit = min(max(cint(limit), 1), MAX_LIST_LIMIT)
	offset = (page - 1) * limit

	conditions = ["g.status = 'open'", "g.expires_at > %(now)s"]
	params = {"now": now_datetime()}

	if category:
		conditions.append("g.category = %(category)s")
		params["category"] = category
	if city:
		conditions.append("g.city = %(city)s")
		params["city"] = city
	if min_budget:
		conditions.append("g.budget_inr >= %(min_budget)s")
		params["min_budget"] = min_budget
	if _bool(barter_only):
		conditions.append("g.barter_allowed = 1")

	where_clause = " AND ".join(conditions)

	# Over-fetch when filtering by eligibility client-side, since some
	# rows in this page may get dropped below and we still want to fill
	# `limit` where possible without a second round trip.
	fetch_limit = (limit * 3 if phone else limit) + 1

	rows = frappe.db.sql(
		f"""
		SELECT g.name AS gig_id, g.outlet AS outlet_id, g.title, g.deliverables_json,
		       g.budget_inr, g.barter_allowed, g.barter_details, g.category, g.city, g.expires_at,
		       g.min_followers, g.min_badge_tier, r.outlet_name
		FROM `tabCollab Gig` g
		LEFT JOIN `tabOutlet` r ON r.name = g.outlet
		WHERE {where_clause}
		ORDER BY g.creation DESC
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		{**params, "limit": fetch_limit, "offset": offset},
		as_dict=True,
	)

	if phone:
		creator_name = _require_own_creator(phone)
		follower_count = cint(frappe.db.get_value("Flamezo Creator", creator_name, "meta_followers"))
		tier_rank = TIER_ORDER.index(get_creator_badge_tier(creator_name))
		rows = [
			r for r in rows
			if follower_count >= cint(r.min_followers)
			and (not r.min_badge_tier or TIER_ORDER.index(r.min_badge_tier) <= tier_rank)
		]

	has_more = len(rows) > limit
	gigs = rows[:limit]
	for g in gigs:
		g["deliverables"] = json.loads(g.pop("deliverables_json") or "[]")

	return {"success": True, "data": {"gigs": gigs, "page": page, "has_more": has_more}}


@frappe.whitelist(allow_guest=True)
def apply_to_gig(phone, gig_id, deal_type=None, proposed_price_inr=None, message=None):
	"""A gig offering both cash and barter lets the creator choose which
	they're applying for — defaults to whichever the gig actually offers
	when only one is available, rather than guessing."""
	creator_name = _require_own_creator(phone)

	gig = frappe.get_doc("Collab Gig", gig_id)
	if gig.status != "open":
		frappe.throw(_("This gig is no longer open."), frappe.ValidationError)
	if gig.expires_at and gig.expires_at <= now_datetime():
		frappe.throw(_("This gig has expired."), frappe.ValidationError)

	already_applied = frappe.db.exists(
		"Collab Deal", {"gig": gig_id, "creator": creator_name, "status": ["!=", "cancelled"]}
	)
	if already_applied:
		frappe.throw(_("You've already applied to this gig."), frappe.ValidationError)

	follower_count = cint(frappe.db.get_value("Flamezo Creator", creator_name, "meta_followers"))
	if follower_count < cint(gig.min_followers):
		frappe.throw(_("This gig needs at least {0} followers.").format(gig.min_followers), frappe.ValidationError)
	if not meets_minimum_tier(creator_name, gig.min_badge_tier):
		frappe.throw(_("This gig needs at least the '{0}' badge.").format(gig.min_badge_tier), frappe.ValidationError)

	pitch_slot_tier = get_creator_badge_tier(creator_name)
	pitch_slot_limit = PITCH_SLOT_LIMITS.get(pitch_slot_tier, PITCH_SLOT_LIMITS["new_creator"])
	open_applications = frappe.db.count("Collab Deal", {"creator": creator_name, "status": "offered"})
	if open_applications >= pitch_slot_limit:
		frappe.throw(
			_("You've used all {0} of your pitch slots — wait for a merchant to respond, or one will free up when a gig closes.").format(pitch_slot_limit),
			frappe.ValidationError,
		)

	gig_offers_cash = bool(cint(gig.budget_inr))
	gig_offers_barter = bool(gig.barter_allowed)
	if not deal_type:
		if gig_offers_cash and not gig_offers_barter:
			deal_type = "cash"
		elif gig_offers_barter and not gig_offers_cash:
			deal_type = "barter"
		else:
			frappe.throw(_("This gig offers both cash and barter — specify deal_type."), frappe.ValidationError)

	if deal_type == "cash" and not gig_offers_cash:
		frappe.throw(_("This gig doesn't offer a cash budget."), frappe.ValidationError)
	if deal_type == "barter" and not gig_offers_barter:
		frappe.throw(_("This gig doesn't accept barter."), frappe.ValidationError)

	price = proposed_price_inr if proposed_price_inr is not None else gig.budget_inr

	deal = frappe.get_doc({
		"doctype": "Collab Deal",
		"gig": gig.name,
		"creator": creator_name,
		"outlet": gig.outlet,
		"deal_type": deal_type,
		"terms_json": json.dumps({
			"deliverables": json.loads(gig.deliverables_json or "[]"),
			"message": message,
		}),
		"price_inr": price if deal_type == "cash" else 0,
		"fair_value_inr": price if deal_type == "barter" else 0,
		# 14-day default deadline from application — real deadline is set
		# properly by the merchant on accept_application (Phase 3).
		"deadline": add_days(now_datetime(), 14).date(),
	})
	deal.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"deal_id": deal.name, "status": deal.status}}


@frappe.whitelist(allow_guest=True)
def get_my_pitch_slots(phone):
	creator_name = _require_own_creator(phone)
	tier = get_creator_badge_tier(creator_name)
	limit = PITCH_SLOT_LIMITS.get(tier, PITCH_SLOT_LIMITS["new_creator"])
	used = frappe.db.count("Collab Deal", {"creator": creator_name, "status": "offered"})
	return {"success": True, "data": {"tier": tier, "used": used, "limit": limit, "available": max(limit - used, 0)}}


def _bool(value) -> int:
	if isinstance(value, str):
		return 1 if value.strip().lower() in ("1", "true", "yes") else 0
	return 1 if value else 0
