"""
Badge-tier computation and the earned-badge history it now feeds —
creator-marketplace-blueprint.html §07/§19, Phase 5.

`get_creator_badge_tier` stays the live, always-correct source of truth
(used for real-time enforcement — gig eligibility, paid-listing gates —
where a stale cached answer would be a real bug: a creator who just lost
Top Rated must stop qualifying immediately, not next Monday). The
`Creator Badge` doctype this module now also maintains is the *history*
layer on top of that: when a tier change happens, `sync_creator_badge`
records it with a timestamp and the exact numbers that justified it, so
the badge reads as earned and auditable (blueprint §07's explicit
design principle) instead of a number that silently changes with no
paper trail. Enforcement never reads the stored table — only display
(portfolio, badge history) does.

Known approximation, to revisit once more history exists:
  - "Elite Creator" needs 6+ CONSECUTIVE months at Top Rated per the
    locked criteria — that needs a stored earned_at history to know
    when a creator first qualified, which now exists via Creator Badge.
    Still approximated as "currently meets Top Rated criteria AND their
    first released deal was 6+ months ago" rather than walking the
    actual Creator Badge history for a genuine consecutive-months check
    (a creator who dropped out of Top Rated and re-qualified recently
    would be a false positive here) — a real refinement, not urgent
    enough to block Phase 5 shipping the history table itself.
"""

import json

import frappe
from frappe.utils import flt, getdate, now_datetime, today

TIER_ORDER = ["new_creator", "verified_creator", "top_rated", "elite_creator"]
EARNED_BADGE_TYPES = {"verified_creator", "top_rated", "elite_creator"}  # new_creator has no row — see doctype description


def _has_dispute_lost(creator_name: str) -> bool:
	"""True if this creator has any resolved dispute at_fault=creator that
	wasn't subsequently overturned on appeal (blueprint §08: "a dispute
	lost (creator's fault) should count against Top Rated/Elite
	eligibility"). Degrades to False if Collab Dispute doesn't exist yet
	(mirrors collab_deals._has_dispute_doctype's same pattern) so this
	function works unchanged both before and after Phase 4 ships."""
	if not frappe.db.exists("DocType", "Collab Dispute"):
		return False
	deal_names = frappe.db.get_all("Collab Deal", filters={"creator": creator_name}, pluck="name")
	if not deal_names:
		return False
	lost = frappe.db.sql(
		"""
		SELECT 1 FROM `tabCollab Dispute`
		WHERE deal IN %(deals)s
		  AND at_fault = 'creator'
		  AND status IN ('resolved', 'closed')
		  AND NOT (appeal_outcome = 'overturned')
		LIMIT 1
		""",
		{"deals": deal_names},
	)
	return bool(lost)


def _compute_badge_details(creator_name: str):
	"""Returns (tier, criteria_dict) — the criteria dict is exactly what
	gets stored as a Creator Badge's criteria_snapshot_json, so the live
	computation and the audit trail can never drift apart (one function,
	two consumers, not two implementations of the same rule)."""
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
	criteria = {"released_count": released_count}
	if released_count == 0:
		return "new_creator", criteria

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

	has_disputes_lost = _has_dispute_lost(creator_name)

	criteria.update({
		"avg_rating": avg_rating, "on_time_pct": round(on_time_pct, 1),
		"days_since_first_deal": days_since_first_deal,
		"has_unresolved_anomaly": has_unresolved_anomaly, "has_disputes_lost": has_disputes_lost,
	})

	is_top_rated = released_count >= 15 and avg_rating >= 4.5 and on_time_pct >= 90 and not has_disputes_lost
	is_elite = is_top_rated and days_since_first_deal >= 180  # see module docstring's approximation note
	is_verified = released_count >= 3 and not has_unresolved_anomaly and days_since_first_deal < 90

	if is_elite:
		return "elite_creator", criteria
	if is_top_rated:
		return "top_rated", criteria
	if is_verified:
		return "verified_creator", criteria
	return "new_creator", criteria


def get_creator_badge_tier(creator_name: str) -> str:
	tier, _criteria = _compute_badge_details(creator_name)
	return tier


def meets_minimum_tier(creator_name: str, min_tier: str) -> bool:
	if not min_tier:
		return True
	current = get_creator_badge_tier(creator_name)
	return TIER_ORDER.index(current) >= TIER_ORDER.index(min_tier)


# ── Phase 5 — stored earned-badge history ───────────────────────────────

def sync_creator_badge(creator_name: str) -> dict:
	"""Recomputes this creator's live tier and reconciles it against their
	current stored Creator Badge row, if any. A no-op when nothing
	changed (the common case on every weekly run) — only writes when the
	tier actually moved, so the history table only ever contains real
	transitions, never one row per week regardless of change."""
	tier, criteria = _compute_badge_details(creator_name)

	current_row = frappe.db.get_value(
		"Creator Badge", {"creator": creator_name, "is_current": 1}, ["name", "badge_type"], as_dict=True
	)
	current_tier = current_row.badge_type if current_row else "new_creator"

	if current_tier == tier:
		return {"changed": False, "tier": tier}

	now = now_datetime()
	if current_row:
		frappe.db.set_value("Creator Badge", current_row.name, {"is_current": 0, "lost_at": now})

	if tier in EARNED_BADGE_TYPES:
		frappe.get_doc({
			"doctype": "Creator Badge",
			"creator": creator_name,
			"badge_type": tier,
			"is_current": 1,
			"earned_at": now,
			"criteria_snapshot_json": json.dumps(criteria),
		}).insert(ignore_permissions=True)

	return {"changed": True, "tier": tier, "previous_tier": current_tier}


def sync_all_creator_badges() -> dict:
	"""Scheduled job (weekly, see hooks.py) — walks every creator who's
	ever had a released deal (no point checking one who's never earned
	anything) and reconciles their stored badge. Each creator wrapped
	individually so one bad row never blocks the rest, same discipline
	as every other sweep job in this module's siblings."""
	creator_names = frappe.db.sql(
		"SELECT DISTINCT creator FROM `tabCollab Deal` WHERE status = 'released'", as_list=True
	)
	changed = 0
	errors = 0
	for (creator_name,) in creator_names:
		try:
			result = sync_creator_badge(creator_name)
			if result["changed"]:
				changed += 1
			frappe.db.commit()
		except Exception:
			errors += 1
			frappe.db.rollback()
			frappe.log_error(title="creator_badges.sync_all_creator_badges", message=frappe.get_traceback())
	return {"scanned": len(creator_names), "changed": changed, "errors": errors}


def get_creator_badge_history(creator_name: str) -> list:
	"""Full earned/lost history, newest first — the audit trail the
	badge-criteria transparency principle (blueprint §07) promises."""
	rows = frappe.db.get_all(
		"Creator Badge", filters={"creator": creator_name},
		fields=["badge_type", "is_current", "earned_at", "lost_at", "criteria_snapshot_json"],
		order_by="earned_at desc",
	)
	for r in rows:
		r["criteria_snapshot"] = json.loads(r.pop("criteria_snapshot_json") or "{}")
	return rows
