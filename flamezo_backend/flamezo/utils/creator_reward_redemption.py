"""
Creator Reward Redemption — 14-day per-outlet cooldown, content-gated.

The problem this solves: FlameZO Cash earned via the weekly score engine
(utils/creator_score_engine.py) is spendable at ANY Flamezo merchant, by
design (creator-program-fundamentals-v1-locked.md Section 4). Nothing
stops a creator from always redeeming it at the one outlet nearest them —
which is fine for the creator individually, but works against two of the
program's actual goals: a Club's content feed staying varied (Section 10
of crowd-and-clubs.md — "a curated lifestyle feed", not one venue on
repeat), and organic creator exposure spreading across merchants instead
of concentrating on whichever is most convenient.

The fix isn't "you can't pay here" alone — that just relocates the
inconvenience without producing anything of value. Redemption at an
outlet requires a FRESH `Creator Club Post` tagging that outlet (posted
within `PROOF_WINDOW_DAYS`) — redemption IS the content-generation
mechanism, not a bare spending restriction. A 14-day cooldown then applies
per (creator, outlet) pair: same outlet again only after 14 days, same
logic shape as the merchant-collab-invite cooldown in the fundamentals
doc, but governing a different flow (self-initiated spend, not a
merchant-sent invite — see that doc's Section 7 for the distinction).

Split the same way as the score engine:
  1. PURE CORE — no frappe import, testable with plain data.
  2. FRAPPE INTEGRATION — real balance/history queries + the actual
     redemption mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import frappe
from frappe.utils import flt, get_datetime, now_datetime


COOLDOWN_DAYS = 14
PROOF_WINDOW_DAYS = 7  # a Club post tagging the outlet must be this recent to count as proof


# ═══════════════════════════════════════════════════════════════════════
# 1. PURE CORE
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RedemptionCheck:
	"""Result of checking whether a redemption is allowed — always carries
	an explicit reason when denied, same explainability principle as the
	score engine's anomaly detection. Nobody should ever see "redemption
	failed" with no further explanation."""
	allowed: bool
	reason: Optional[str]


def check_redemption(
	available_balance: float,
	amount: float,
	last_redemption_at_outlet: Optional[object],
	has_qualifying_proof_post: bool,
	now=None,
	cooldown_days: int = COOLDOWN_DAYS,
) -> RedemptionCheck:
	"""Pure decision function — every real-world check reduced to plain
	inputs so it's testable without a DB. `last_redemption_at_outlet`:
	datetime of this creator's most recent redemption at THIS outlet, or
	None if they never have. `now`: injected for deterministic testing;
	real callers pass the actual current time.
	"""
	if amount <= 0:
		return RedemptionCheck(False, "Redemption amount must be positive.")

	if amount > available_balance:
		return RedemptionCheck(
			False, f"Insufficient balance: have ₹{available_balance:.2f}, requested ₹{amount:.2f}."
		)

	if not has_qualifying_proof_post:
		return RedemptionCheck(
			False,
			f"No Club post tagging this outlet in the last {PROOF_WINDOW_DAYS} days — "
			"post about this visit before redeeming here.",
		)

	if last_redemption_at_outlet is not None:
		now = now or _now()
		days_since = (now - last_redemption_at_outlet).days
		if days_since < cooldown_days:
			return RedemptionCheck(
				False,
				f"Redeemed at this outlet {days_since} day(s) ago — wait "
				f"{cooldown_days - days_since} more day(s), or redeem somewhere new.",
			)

	return RedemptionCheck(True, None)


def _now():
	"""Isolated so tests can monkeypatch this one function instead of
	fighting frappe.utils.now_datetime() directly. Matches the same
	naive-local-time convention `redeemed_at` is stored with, so a diff
	against a DB-read datetime stays consistent."""
	return now_datetime()


# ═══════════════════════════════════════════════════════════════════════
# 2. FRAPPE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════

def get_available_balance(creator_name: str) -> float:
	"""Total earned (Creator Reward Ledger) minus total redeemed (Creator
	Reward Redemption) — the creator's real spendable FlameZO Cash."""
	earned = frappe.db.sql(
		"SELECT COALESCE(SUM(amount), 0) FROM `tabCreator Reward Ledger` WHERE creator=%s",
		creator_name,
	)[0][0]
	redeemed = frappe.db.sql(
		"SELECT COALESCE(SUM(amount), 0) FROM `tabCreator Reward Redemption` WHERE creator=%s",
		creator_name,
	)[0][0]
	return flt(earned) - flt(redeemed)


def _last_redemption_at_outlet(creator_name: str, outlet: str):
	row = frappe.db.get_value(
		"Creator Reward Redemption",
		{"creator": creator_name, "outlet": outlet},
		"redeemed_at",
		order_by="redeemed_at desc",
	)
	return get_datetime(row) if row else None


def _qualifying_proof_post(creator_name: str, outlet: str, as_of=None) -> Optional[str]:
	"""Most recent Club post by this creator tagging `outlet`, posted
	within `PROOF_WINDOW_DAYS` of `as_of` (defaults to now). Returns the
	post name to store as redemption proof, or None if nothing qualifies."""
	as_of = as_of or now_datetime()
	window_start = as_of - timedelta(days=PROOF_WINDOW_DAYS)
	post = frappe.db.get_value(
		"Creator Club Post",
		{
			"creator": creator_name,
			"outlet": outlet,
			"creation": ["between", [window_start, as_of]],
		},
		"name",
		order_by="creation desc",
	)
	return post


def redeem_creator_reward(creator_name: str, outlet: str, amount: float) -> dict:
	"""
	The actual redemption mutation. Re-validates everything server-side
	(never trust a client-computed "allowed" flag) using the same
	`check_redemption` pure function the tests exercise directly, then
	writes the `Creator Reward Redemption` row that both deducts the
	balance (via `get_available_balance`'s subtraction) and starts this
	outlet's 14-day cooldown clock.

	Returns {"success": bool, "reason": str|None, "redemption": str|None}
	— never throws for an ordinary denial (insufficient balance, cooldown,
	no proof post), only for a totally malformed call (bad creator/outlet).
	"""
	if not frappe.db.exists("Flamezo Creator", creator_name):
		frappe.throw(f"Unknown creator: {creator_name}")
	if not frappe.db.exists("Outlet", outlet):
		frappe.throw(f"Unknown outlet: {outlet}")

	balance = get_available_balance(creator_name)
	last_redemption = _last_redemption_at_outlet(creator_name, outlet)
	proof_post = _qualifying_proof_post(creator_name, outlet)

	check = check_redemption(
		available_balance=balance,
		amount=amount,
		last_redemption_at_outlet=last_redemption,
		has_qualifying_proof_post=proof_post is not None,
	)

	if not check.allowed:
		return {"success": False, "reason": check.reason, "redemption": None}

	entry = frappe.get_doc({
		"doctype": "Creator Reward Redemption",
		"creator": creator_name,
		"outlet": outlet,
		"amount": flt(amount),
		"redeemed_at": now_datetime(),
		"proof_post": proof_post,
	})
	entry.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "reason": None, "redemption": entry.name}
