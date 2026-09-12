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

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate, now_datetime

from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils.creator_badges import get_creator_badge_tier

MONTHLY_INVITE_CAP = 5   # flat cap for every merchant — see module docstring
COOLDOWN_DAYS = 30        # per creator-merchant pair, after a completed collab
WEEKLY_ACCEPT_CAP = 3     # per creator, across all merchants


def _require_outlet_access(outlet_id):
	"""Merchant-side auth — same `validate_restaurant_for_api` helper every
	other merchant-portal endpoint in the app uses (commission.py, etc.).
	Resolves the outlet AND verifies `frappe.session.user` actually
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
		SELECT fc.name AS creator_id, fc.display_name, fc.meta_followers, fc.city, fc.profile_image,
		       cc.name AS club_id, cc.club_name, cc.category, cc.niche, cc.followers_count, cc.description
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

	_attach_track_record(creators)

	return {"success": True, "data": {"creators": creators, "page": page, "has_more": has_more}}


def _attach_track_record(creators):
	"""Adds `collabs_done`, `avg_rating`, `rating_count` to each row — real
	history a merchant deciding who to invite actually wants to see, not
	just follower count. Two completion paths feed `collabs_done` since a
	creator's history spans both systems: legacy direct-invite collabs
	(Creator Collab Invite, status='completed') and marketplace deals
	(Collab Deal, status='released', any origin — gig/direct_invite/
	standing_offer). Ratings only exist on the invite side today (
	merchant_rating) — Collab Deal has no rating field yet (Phase 4/5).
	One bulk query per stat, keyed by creator_id, not one query per row —
	`creators` here is at most `limit` (<=50) rows from a single page."""
	if not creators:
		return
	creator_ids = [c["creator_id"] for c in creators]

	invite_counts = {
		r.creator: r.cnt for r in frappe.db.get_all(
			"Creator Collab Invite", filters={"creator": ["in", creator_ids], "status": "completed"},
			group_by="creator", fields=["creator", "count(*) as cnt"],
		)
	}
	deal_counts = {
		r.creator: r.cnt for r in frappe.db.get_all(
			"Collab Deal", filters={"creator": ["in", creator_ids], "status": "released"},
			group_by="creator", fields=["creator", "count(*) as cnt"],
		)
	}
	rating_rows = frappe.db.get_all(
		"Creator Collab Invite",
		filters={"creator": ["in", creator_ids], "merchant_rating": [">", 0]},
		group_by="creator",
		fields=["creator", "avg(merchant_rating) as avg_rating", "count(*) as rating_count"],
	)
	ratings = {r.creator: (flt(r.avg_rating), cint(r.rating_count)) for r in rating_rows}

	# Net earnings, not gross deal value — creator_net_inr is what actually
	# clears escrow after the platform fee, the same number a creator would
	# see on their own payout history. Barter deals have no Escrow
	# Transaction row at all (see collab_deals.py — barter never funds
	# through escrow), so this is cash-collab earnings only by construction,
	# not an oversight.
	earnings_rows = frappe.db.sql(
		"""
		SELECT d.creator AS creator, SUM(et.creator_net_inr) AS total
		FROM `tabEscrow Transaction` et
		JOIN `tabCollab Deal` d ON d.name = et.deal
		WHERE d.creator IN %(ids)s AND et.state = 'released'
		GROUP BY d.creator
		""",
		{"ids": creator_ids},
		as_dict=True,
	)
	earnings = {r.creator: flt(r.total) for r in earnings_rows}

	# Starting rate — the cheapest active cash rate card, same "Starting at"
	# framing merchants recognise from any freelance marketplace. A creator
	# with only barter-accepting cards (no cash price) has no cash floor to
	# show — `starting_rate_inr` stays None and the client falls back to an
	# "Open to barter" line instead of inventing a number.
	rate_rows = frappe.db.get_all(
		"Creator Rate Card",
		filters={"creator": ["in", creator_ids], "is_active": 1, "price_inr": [">", 0]},
		group_by="creator",
		fields=["creator", "min(price_inr) as min_price"],
	)
	starting_rates = {r.creator: flt(r.min_price) for r in rate_rows}
	barter_creators = {
		r.creator for r in frappe.db.get_all(
			"Creator Rate Card", filters={"creator": ["in", creator_ids], "is_active": 1, "accepts_barter": 1},
			fields=["creator"], distinct=True,
		)
	}

	for c in creators:
		cid = c["creator_id"]
		c["collabs_done"] = cint(invite_counts.get(cid, 0)) + cint(deal_counts.get(cid, 0))
		avg_rating, rating_count = ratings.get(cid, (0, 0))
		c["avg_rating"] = round(avg_rating, 1) if rating_count else None
		c["rating_count"] = rating_count
		c["total_earned_inr"] = earnings.get(cid, 0)
		# Badge tier is live-computed per creator (get_creator_badge_tier does
		# its own small set of queries) rather than a stored field — Phase 5
		# (creator_badges.py's own docstring) will replace this with a cached
		# value once the weekly recompute job exists. Fine for a <=50-row
		# page today; if Explore Creators ever needs to show hundreds of
		# creators at once, batch this the same way the stats above are
		# batched instead of one call per row.
		c["badge_tier"] = get_creator_badge_tier(cid)
		c["starting_rate_inr"] = starting_rates.get(cid)
		c["accepts_barter"] = cid in barter_creators


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
		       r.outlet_name AS outlet_name
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


@frappe.whitelist(allow_guest=True)
def get_creator_profile(creator_id=None):
	"""Full profile a merchant needs to actually decide whether to invite
	someone — every field discover_creators' row summary leaves out:
	full bio, Instagram handle, follower-count freshness, the complete
	rate card (not just the cheapest), and real collab history (not just
	a count). Pulls from every table that has creator-facing data —
	Flamezo Creator, Creator Club, Creator Rate Card, the same
	invite+deal union discover_creators uses for collabs_done/earnings,
	plus per-collab detail for the history list. No outlet_id required —
	this is public profile info by design, same as discover_creators and
	get_creator_rate_cards."""
	# useFrappeGetCall fires on component mount regardless of whether a
	# creator has actually been selected yet (see list_applications's
	# identical note — no real conditional-fetch support in this SDK) —
	# degrade to an empty profile instead of a raw TypeError. The
	# frontend already treats `data: null` as "nothing to show yet".
	if not creator_id:
		return {"success": True, "data": None}

	creator = frappe.db.get_value(
		"Flamezo Creator",
		creator_id,
		[
			"name", "display_name", "profile_image", "bio", "city", "status",
			"instagram_handle", "meta_followers", "meta_avg_views", "follower_count_last_synced",
			"approved_at",
		],
		as_dict=True,
	)
	if not creator or creator.status != "approved":
		frappe.throw(_("Creator not found"), frappe.DoesNotExistError)

	club = frappe.db.get_value(
		"Creator Club", {"creator": creator_id, "is_active": 1},
		["club_name", "category", "niche", "description", "cover_image", "followers_count"],
		as_dict=True,
	)

	rate_cards = frappe.db.get_all(
		"Creator Rate Card", filters={"creator": creator_id, "is_active": 1},
		fields=["deliverable_type", "price_inr", "accepts_barter", "barter_min_value_inr"],
		order_by="deliverable_type asc",
	)

	track_record = {"creator_id": creator_id}
	_attach_track_record([track_record])

	# Recent history — the same two completion paths collabs_done counts
	# (legacy Creator Collab Invite + marketplace Collab Deal), but here
	# as real rows a merchant can actually read, newest first, capped at
	# 10 so a long-established creator's profile doesn't turn into an
	# unbounded scroll.
	invite_history = frappe.db.sql(
		"""
		SELECT r.outlet_name, ci.offer_details AS detail, ci.merchant_rating AS rating,
		       ci.completed_at AS completed_at, 'invite' AS source, NULL AS value_inr, NULL AS deal_type
		FROM `tabCreator Collab Invite` ci
		LEFT JOIN `tabOutlet` r ON r.name = ci.outlet
		WHERE ci.creator = %(creator)s AND ci.status = 'completed'
		ORDER BY ci.completed_at DESC
		LIMIT 10
		""",
		{"creator": creator_id}, as_dict=True,
	)
	deal_history = frappe.db.sql(
		"""
		SELECT r.outlet_name, NULL AS detail, NULL AS rating,
		       d.released_at AS completed_at, 'deal' AS source,
		       CASE WHEN d.deal_type = 'cash' THEN d.price_inr ELSE d.fair_value_inr END AS value_inr,
		       d.deal_type AS deal_type
		FROM `tabCollab Deal` d
		LEFT JOIN `tabOutlet` r ON r.name = d.outlet
		WHERE d.creator = %(creator)s AND d.status = 'released'
		ORDER BY d.released_at DESC
		LIMIT 10
		""",
		{"creator": creator_id}, as_dict=True,
	)
	def _sort_key(row):
		# completed_at can be None (shouldn't happen given the WHERE
		# clauses above, but defend anyway) — datetime.min sorts a
		# missing date last, and comparing datetimes to datetimes (never
		# a bare "" string) is what actually broke this the first time.
		return row.completed_at or datetime.min

	recent_collabs = sorted(invite_history + deal_history, key=_sort_key, reverse=True)[:10]

	return {
		"success": True,
		"data": {
			**creator,
			"club": club,
			"rate_cards": rate_cards,
			"collabs_done": track_record["collabs_done"],
			"avg_rating": track_record["avg_rating"],
			"rating_count": track_record["rating_count"],
			"total_earned_inr": track_record["total_earned_inr"],
			"badge_tier": track_record["badge_tier"],
			"starting_rate_inr": track_record["starting_rate_inr"],
			"accepts_barter": track_record["accepts_barter"],
			"available_this_week": _accepted_this_week_count(creator_id) < WEEKLY_ACCEPT_CAP,
			"recent_collabs": recent_collabs,
		},
	}
