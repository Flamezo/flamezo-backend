"""
Live badge-tier computation — creator-marketplace-blueprint.html §07/§19.

Pulled forward from Phase 5 (which builds the stored `Creator Badge`
doctype + history + the weekly recompute job) because Phase 1's gig
eligibility filter (Collab Gig.min_badge_tier) needs a real answer to
"what tier is this creator right now" before Phase 5 exists. Computed
live from Collab Deal history rather than cached — correct, just not
yet the cheap/indexed lookup Phase 5's stored doctype will provide.

Known approximation, to revisit once later phases land:
  - "Elite Creator" needs 6+ CONSECUTIVE months at Top Rated per the
    locked criteria — that needs a stored earned_at history (Phase 5)
    to know when a creator first qualified. Approximated here as
    "currently meets Top Rated criteria AND their first released deal
    was 6+ months ago" — a reasonable proxy, not exact history.
  - "Zero disputes lost" can't be checked yet — Collab Dispute
    (Phase 4) doesn't exist. Treated as satisfied by default; this
    function must be updated once Phase 4 ships so a creator who's
    actually lost disputes stops qualifying.
"""

import frappe
from frappe.utils import flt, getdate, today

TIER_ORDER = ["new_creator", "verified_creator", "top_rated", "elite_creator"]


def get_creator_badge_tier(creator_name: str) -> str:
	deals = frappe.db.sql(
		"""
		SELECT status, deadline, delivered_at, creation
		FROM `tabCollab Deal`
		WHERE creator = %(creator)s AND status = 'released'
		""",
		{"creator": creator_name},
		as_dict=True,
	)
	released_count = len(deals)
	if released_count == 0:
		return "new_creator"

	anomaly_flagged = frappe.db.get_value(
		"Creator Weekly Score", {"creator": creator_name}, "anomaly_flagged", order_by="week_start desc"
	)
	has_unresolved_anomaly = bool(anomaly_flagged)

	first_deal_date = min(getdate(d.creation) for d in deals)
	days_since_first_deal = (getdate(today()) - first_deal_date).days

	on_time_count = sum(1 for d in deals if d.delivered_at and d.deadline and getdate(d.delivered_at) <= getdate(d.deadline))
	on_time_pct = (on_time_count / released_count) * 100 if released_count else 0

	avg_rating = flt(
		frappe.db.get_value(
			"Creator Collab Invite", {"creator": creator_name, "merchant_rating": [">", 0]}, "avg(merchant_rating)"
		)
	)

	is_top_rated = released_count >= 15 and avg_rating >= 4.5 and on_time_pct >= 90
	is_elite = is_top_rated and days_since_first_deal >= 180  # see module docstring's approximation note
	is_verified = released_count >= 3 and not has_unresolved_anomaly and days_since_first_deal < 90

	if is_elite:
		return "elite_creator"
	if is_top_rated:
		return "top_rated"
	if is_verified:
		return "verified_creator"
	return "new_creator"


def meets_minimum_tier(creator_name: str, min_tier: str) -> bool:
	if not min_tier:
		return True
	current = get_creator_badge_tier(creator_name)
	return TIER_ORDER.index(current) >= TIER_ORDER.index(min_tier)
