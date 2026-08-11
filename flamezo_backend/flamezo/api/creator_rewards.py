"""
HTTP-facing endpoints for the creator weekly-score engine
(utils/creator_score_engine.py) and reward redemption
(utils/creator_reward_redemption.py) — both had real, tested logic with
no app-callable API layer until now.
"""

import frappe
from frappe import _

from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session, normalize_phone
from flamezo_backend.flamezo.utils.creator_reward_redemption import (
	get_available_balance,
	redeem_creator_reward,
)


def _require_own_creator(phone: str) -> str:
	"""Verifies a real verified session AND resolves it to that phone's
	own Flamezo Creator record — every endpoint here acts on "my own"
	rewards/scores only, never another creator's by ID. Falls back to a
	normalized comparison (Flamezo Creator.customer_phone can carry a +91
	prefix while session phones never do — same gotcha fixed in clubs.py's
	is_admin check) only when the exact match misses; the creator table is
	small enough that a full scan there is fine."""
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
def get_my_weekly_scores(phone, limit=12):
	"""This creator's own weekly transparency receipts (algorithm doc
	Section 7), most recent first — what the "how was my payout
	calculated" screen in the app would read from."""
	creator_name = _require_own_creator(phone)
	limit = min(int(limit), 52)
	rows = frappe.db.get_all(
		"Creator Weekly Score",
		filters={"creator": creator_name},
		fields=[
			"name", "week_start", "week_end", "qualified", "app_score", "ig_score",
			"ig_weight_pct", "app_weight_pct", "final_score", "smoothed_score", "percentile",
			"payout_inr", "floored", "capped", "review_status", "anomaly_reason",
		],
		order_by="week_start desc",
		limit_page_length=limit,
	)
	return {"success": True, "data": {"weeks": rows}}


@frappe.whitelist(allow_guest=True)
def get_my_wallet_balance(phone):
	"""This creator's current spendable FlameZO Cash — earned (Creator
	Reward Ledger) minus already-redeemed (Creator Reward Redemption)."""
	creator_name = _require_own_creator(phone)
	return {"success": True, "data": {"balance": get_available_balance(creator_name)}}


@frappe.whitelist(allow_guest=True)
def redeem_my_reward(phone, outlet_id, amount):
	"""Spend FlameZO Cash at `outlet_id` — the 14-day-per-outlet,
	content-gated flow (creator-program-fundamentals-v1-locked.md Section
	5). Re-validates everything server-side inside
	`redeem_creator_reward`; this wrapper's only job is resolving `phone`
	to a real, own creator first."""
	creator_name = _require_own_creator(phone)
	result = redeem_creator_reward(creator_name, outlet_id, float(amount))
	return {"success": result["success"], "data": result}


# ── admin — reviewing anomaly-flagged / large-payout weeks ──────────────

def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Not permitted."), frappe.PermissionError)


@frappe.whitelist()
def get_pending_review_weeks(limit=50):
	"""Admin queue — weeks withheld from auto-pay pending a human look
	(algorithm doc Section 10, Tier 4). Not exposed to creators."""
	_require_system_manager()
	limit = min(int(limit), 200)
	rows = frappe.db.get_all(
		"Creator Weekly Score",
		filters={"review_status": "pending_review"},
		fields=["name", "creator", "week_start", "week_end", "payout_inr", "anomaly_flagged", "anomaly_reason"],
		order_by="week_start desc",
		limit_page_length=limit,
	)
	return {"success": True, "data": {"weeks": rows}}


@frappe.whitelist()
def approve_review(weekly_score_name):
	_require_system_manager()
	from flamezo_backend.flamezo.utils.creator_score_engine import approve_flagged_week

	approve_flagged_week(weekly_score_name, frappe.session.user)
	return {"success": True, "data": {"status": "approved"}}


@frappe.whitelist()
def reject_review(weekly_score_name):
	_require_system_manager()
	from flamezo_backend.flamezo.utils.creator_score_engine import reject_flagged_week

	reject_flagged_week(weekly_score_name, frappe.session.user)
	return {"success": True, "data": {"status": "rejected"}}
