"""
Creator Weekly Performance Score & Payout Engine — v2 (hardened).

Implements product-docs/creator-weekly-score-algorithm.md plus the v2
hardening pass: self-engagement exclusion, engager trust-weighting,
engagement-concentration + velocity anomaly detection, rolling-average
smoothing, cohort percentile adjustment, merchant-rating-weighted collab
scoring, revenue-correlation bonus, and a review queue for anything
flagged instead of blind auto-pay. See creator-weekly-score-algorithm.md
Section 10 ("Hardening — v2") for the plain-English version of all of
this; this docstring covers structure, that doc covers reasoning.

Split into two layers on purpose:

  1. PURE CALCULATION CORE (top of file, no Frappe/DB import) — every
     coefficient lives in `ScoreConfig`, every formula is a small testable
     function, and `compute_weekly_score()` takes plain data in and returns
     a plain result out. Safe to call with synthetic/sample data, safe to
     unit test without a site, safe to retune by editing `ScoreConfig`
     without touching formula logic.

  2. FRAPPE INTEGRATION LAYER (bottom of file) — pulls real weekly signals
     out of the DB for a real creator and drives the actual payout. This is
     the only part of the file that talks to `frappe.db`.

Two doctypes this depends on do NOT exist yet and are explicitly stubbed
rather than faked against something real that doesn't fit:
  - `Creator Collab Invite` (see creator-program-fundamentals-v1-locked.md
    Section 9) — merchant collab tracking isn't built, so
    `_gather_collab_signals()` returns zeros until it is.
  - A cross-merchant-spendable creator reward ledger — the existing wallet
    infra (`utils/loyalty.py`, `api/ugc.py`'s `UGC Voucher`) is restaurant-
    locked, which doesn't match "redeemable at any Flamezo merchant" from
    the program spec. `credit_creator_reward()` is written against a new
    `Creator Reward Ledger` doctype (JSON alongside this file) instead of
    silently bolting onto a system built for a different purpose.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import frappe
from frappe.utils import cint, flt, getdate, now_datetime, today


# ═══════════════════════════════════════════════════════════════════════
# 1. CONFIG — every tunable constant, centralized. Retuning after real
#    data comes in means editing these values, never the formulas below.
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ScoreConfig:
	# App Score per-unit weights — algorithm doc Section 2
	weight_like: float = 0.5
	weight_comment: float = 2.0
	weight_view: float = 0.05
	weight_new_follower: float = 4.0
	weight_collab_completed: float = 40.0   # multiplies collab QUALITY points (rating-weighted), not a raw count
	weight_revenue_bonus: float = 1.0        # revenue_bonus_points already in final units, pass-through weight
	revenue_bonus_per_incremental_booking: float = 20.0  # score points per extra booking correlated with a collab

	# IG Score weights — Section 3. Reach is LOG-scaled (weight_reach_log
	# multiplies log10(reach + 1), not raw reach) — a linear reach term
	# was tested against realistic numbers and found to swamp engagement
	# rate at scale. Log-scaling caps how much raw scale alone can
	# contribute, so engagement rate — the harder signal to fake — stays
	# dominant regardless of audience size.
	weight_reach_log: float = 15.0
	weight_engagement_rate: float = 8.0  # per percentage point (0-100 scale)

	# Blend schedule — Section 4
	blend_ig_weight_max: float = 0.60      # at 0 city Club members
	blend_ig_weight_min: float = 0.30      # floor, reached at/above the reference size
	blend_reference_city_members: int = 10_000

	# Payout conversion — Section 1, 8
	rupees_per_point: float = 5.0
	payout_floor: float = 150.0
	payout_cap: float = 2000.0

	# Eligibility gate — Section 1
	min_qualifying_posts: int = 2

	# ── v2 hardening ──────────────────────────────────────────────────

	# Engager trust weighting — new/unverified accounts count for less,
	# closes the "make 3 alt accounts, mass-like your own post" hole that
	# raw counting doesn't catch on its own.
	trust_weight_new_account: float = 0.2
	trust_age_full_days: int = 30

	# Engagement concentration — flag if a small handful of accounts drive
	# most of a week's activity (cheap proxy for coordinated/pod engagement,
	# same "network clustering" signal real fraud-detection systems use).
	concentration_flag_ratio: float = 0.5
	concentration_min_engagers: int = 5   # skip below this — avoids false positives on small early creators
	concentration_top_n: int = 3

	# Velocity anomaly — flag if this week's raw engagement spikes far past
	# the creator's own trailing average. Industry practice for engagement-
	# rate anomalies runs ±50% off a benchmark; week-over-week spikes from
	# coordinated pods run much higher (3-10x), so the multiplier here is
	# deliberately looser than a rate-benchmark check would use.
	anomaly_spike_multiplier: float = 3.0
	anomaly_min_trailing_weeks: int = 2

	# Rolling-average smoothing — dampens single-week spikes (the easiest
	# thing to game: borrow engagement for one big payout, disappear).
	rolling_window_weeks: int = 3
	rolling_current_week_weight: float = 0.7

	# Cohort percentile adjustment — SMALL, bounded, never a replacement of
	# the absolute score. Percentile-only pay creates a "race to the
	# bottom" (a known algorithmic-wage failure mode) where everyone works
	# harder for a fixed pool; this only nudges pay toward/away from a
	# creator's relative standing.
	percentile_adjustment_max: float = 0.10
	percentile_min_cohort_size: int = 5

	# Review queue — anomaly-flagged weeks always route to review; unusually
	# large payouts do too, even without an anomaly flag, as a second net.
	review_payout_threshold: float = 1500.0


DEFAULT_CONFIG = ScoreConfig()


# ═══════════════════════════════════════════════════════════════════════
# 2. INPUT TYPES — one week of signals for one creator. Frozen + validated
#    at construction so a bad value fails loudly at the boundary, not deep
#    inside a formula.
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AppWeekSignals:
	"""This creator's in-app activity for one week — 100% Flamezo-native,
	can't be inflated with bought Instagram followers.

	`likes`/`comments` are TRUST-WEIGHTED sums (see `compute_trust_weight`),
	not raw counts — a like from a day-old account contributes less than
	one from an established account. `raw_engagement_total` carries the
	unweighted sum separately, used only for anomaly detection, never for
	scoring itself.
	"""
	qualifying_posts: int
	likes: float = 0.0
	comments: float = 0.0
	views: int = 0
	new_followers: int = 0
	collabs_completed: float = 0.0    # quality-weighted (sum of rating/5 per completed collab), not a raw count
	revenue_bonus_points: float = 0.0  # pre-computed incremental-booking bonus, see compute_revenue_bonus
	raw_engagement_total: float = 0.0  # unweighted likes+comments — anomaly detection input only
	engager_concentration: float = 0.0  # 0.0-1.0, top-N-engager share of this week's raw engagement
	total_engagers: int = 0

	def __post_init__(self):
		for field_name in (
			"qualifying_posts", "likes", "comments", "views", "new_followers",
			"collabs_completed", "revenue_bonus_points", "raw_engagement_total",
			"total_engagers",
		):
			value = getattr(self, field_name)
			if value < 0:
				raise ValueError(f"AppWeekSignals.{field_name} cannot be negative, got {value}")
		if not (0.0 <= self.engager_concentration <= 1.0):
			raise ValueError(
				f"AppWeekSignals.engager_concentration must be within 0-1, got {self.engager_concentration}"
			)


@dataclass(frozen=True)
class InstagramWeekSignals:
	"""This creator's Instagram performance for one week, if any qualifying
	tagged post/story existed. `None` fields mean 'no IG data this week'
	(not connected, or no matching post found) — deliberately distinct from
	0, which would wrongly imply a real post that reached nobody."""
	reach: Optional[int] = None
	engagement_rate_pct: Optional[float] = None

	def __post_init__(self):
		if self.reach is not None and self.reach < 0:
			raise ValueError(f"InstagramWeekSignals.reach cannot be negative, got {self.reach}")
		if self.engagement_rate_pct is not None and not (0 <= self.engagement_rate_pct <= 100):
			raise ValueError(
				f"InstagramWeekSignals.engagement_rate_pct must be within 0-100, "
				f"got {self.engagement_rate_pct}"
			)

	@property
	def has_data(self) -> bool:
		return self.reach is not None and self.engagement_rate_pct is not None

	@classmethod
	def empty(cls) -> "InstagramWeekSignals":
		"""Explicit constructor for 'no IG data this week' — reads better
		at call sites than `InstagramWeekSignals()`."""
		return cls(reach=None, engagement_rate_pct=None)


@dataclass(frozen=True)
class WeeklyScoreResult:
	"""Everything about how one creator's payout for one week was derived —
	this IS the transparency receipt from algorithm doc Section 7, not a
	separate re-derivation of it."""
	qualified: bool
	app_score: float
	ig_score: float
	ig_weight: float
	app_weight: float
	blended_score: float          # before smoothing
	smoothed_score: float         # after rolling-average blend — what payout is actually based on
	percentile: Optional[float]   # this week's cohort standing, 0-100, None if cohort too small
	raw_payout: float             # before floor/cap clamp
	payout: float                 # what actually gets credited (0 if withheld for review)
	floored: bool
	capped: bool
	anomaly_flagged: bool
	anomaly_reason: Optional[str]
	review_required: bool         # anomaly OR payout above review threshold — withholds auto-credit

	def to_receipt_dict(self) -> dict:
		"""Structured breakdown matching the app-facing weekly receipt —
		the shape the notification/profile layer renders to the creator."""
		return {
			"qualified": self.qualified,
			"app_score": round(self.app_score, 1),
			"ig_score": round(self.ig_score, 1),
			"ig_weight_pct": round(self.ig_weight * 100, 1),
			"app_weight_pct": round(self.app_weight * 100, 1),
			"final_score": round(self.blended_score, 1),
			"smoothed_score": round(self.smoothed_score, 1),
			"percentile": round(self.percentile, 1) if self.percentile is not None else None,
			"raw_payout_inr": round(self.raw_payout, 2),
			"payout_inr": round(self.payout, 2),
			"floored": self.floored,
			"capped": self.capped,
			"anomaly_flagged": self.anomaly_flagged,
			"anomaly_reason": self.anomaly_reason,
			"review_status": "pending_review" if self.review_required else "auto_paid",
		}


# ═══════════════════════════════════════════════════════════════════════
# 3. PURE FORMULAS — each one directly traceable to a section of the
#    algorithm doc. No Frappe import above this line; safe to unit test
#    or feed sample data through in a plain Python REPL.
# ═══════════════════════════════════════════════════════════════════════

def compute_app_score(signals: AppWeekSignals, config: ScoreConfig = DEFAULT_CONFIG) -> float:
	"""App_Score — algorithm doc Section 2. Collabs are weighted ~80x a
	single like on purpose: driving a real merchant visit is the literal
	business outcome the program exists for. `collabs_completed` is
	quality-weighted (Tier 3) — a rushed low-effort collab and a great one
	no longer score identically. `revenue_bonus_points` (Tier 3) adds
	whatever downstream booking correlation was measured, on top."""
	return (
		signals.likes * config.weight_like
		+ signals.comments * config.weight_comment
		+ signals.views * config.weight_view
		+ signals.new_followers * config.weight_new_follower
		+ signals.collabs_completed * config.weight_collab_completed
		+ signals.revenue_bonus_points * config.weight_revenue_bonus
	)


def compute_ig_score(signals: InstagramWeekSignals, config: ScoreConfig = DEFAULT_CONFIG) -> float:
	"""IG_Score — Section 3. Returns 0.0 when there's no IG data this week
	(absent, not penalized beyond scoring lower). Reach enters log-scaled
	specifically so engagement rate — the harder signal to fake with bought
	followers — stays dominant no matter how large raw reach gets."""
	if not signals.has_data:
		return 0.0
	return (
		math.log10(signals.reach + 1) * config.weight_reach_log
		+ signals.engagement_rate_pct * config.weight_engagement_rate
	)


def compute_blend_weights(
	city_club_members: int, config: ScoreConfig = DEFAULT_CONFIG
) -> tuple[float, float]:
	"""Returns (ig_weight, app_weight) — Section 4's shifting blend. Linear
	ramp from `blend_ig_weight_max` at 0 members down to
	`blend_ig_weight_min` at/above `blend_reference_city_members`."""
	if city_club_members < 0:
		raise ValueError(f"city_club_members cannot be negative, got {city_club_members}")
	progress = min(1.0, city_club_members / config.blend_reference_city_members)
	ig_weight = config.blend_ig_weight_max - progress * (
		config.blend_ig_weight_max - config.blend_ig_weight_min
	)
	return ig_weight, 1.0 - ig_weight


def compute_trust_weight(account_age_days: Optional[int], config: ScoreConfig = DEFAULT_CONFIG) -> float:
	"""Trust weight (`trust_weight_new_account`..1.0) for one engager,
	based on account age — the in-app equivalent of Instagram's
	engagement-rate-over-reach fix. `None`/non-positive age (unknown or
	unregistered account) gets the most conservative weight."""
	if account_age_days is None or account_age_days <= 0:
		return config.trust_weight_new_account
	if account_age_days >= config.trust_age_full_days:
		return 1.0
	progress = account_age_days / config.trust_age_full_days
	return config.trust_weight_new_account + progress * (1.0 - config.trust_weight_new_account)


def compute_engager_concentration(engagement_by_phone: dict, config: ScoreConfig = DEFAULT_CONFIG) -> float:
	"""Share of this week's total (raw) engagement contributed by the top
	N engagers (0.0-1.0) — a cheap proxy for coordinated/pod engagement.
	0.0 for no engagement at all."""
	if not engagement_by_phone:
		return 0.0
	total = sum(engagement_by_phone.values())
	if total <= 0:
		return 0.0
	top_values = sorted(engagement_by_phone.values(), reverse=True)[: config.concentration_top_n]
	return sum(top_values) / total


def detect_anomaly(
	signals: AppWeekSignals,
	trailing_raw_engagement: list[float],
	config: ScoreConfig = DEFAULT_CONFIG,
) -> tuple[bool, Optional[str]]:
	"""Returns (flagged, reason) — velocity spike vs. own trailing history,
	and engager concentration, checked independently; either alone is
	enough to flag. Reason is always an explicit string, never a bare
	boolean — explainability is required for anything that withholds a
	payout (see the review queue below)."""
	reasons = []

	if len(trailing_raw_engagement) >= config.anomaly_min_trailing_weeks:
		trailing_avg = sum(trailing_raw_engagement) / len(trailing_raw_engagement)
		if trailing_avg > 0 and signals.raw_engagement_total > trailing_avg * config.anomaly_spike_multiplier:
			reasons.append(
				f"engagement {signals.raw_engagement_total:.0f} is "
				f"{signals.raw_engagement_total / trailing_avg:.1f}x the trailing "
				f"{len(trailing_raw_engagement)}-week average ({trailing_avg:.0f})"
			)

	if (
		signals.total_engagers >= config.concentration_min_engagers
		and signals.engager_concentration > config.concentration_flag_ratio
	):
		reasons.append(
			f"top {config.concentration_top_n} engagers account for "
			f"{signals.engager_concentration * 100:.0f}% of this week's activity "
			f"(threshold {config.concentration_flag_ratio * 100:.0f}%)"
		)

	if reasons:
		return True, "; ".join(reasons)
	return False, None


def smooth_score(
	current_score: float, trailing_scores: list[float], config: ScoreConfig = DEFAULT_CONFIG
) -> float:
	"""Blends the current week's blended score with a trailing rolling
	average. Dampens single-week spikes without punishing genuine sustained
	growth. Falls back to the current score unchanged when there's no
	history yet — a creator's first qualifying week isn't smoothed against
	nothing."""
	if not trailing_scores:
		return current_score
	trailing_avg = sum(trailing_scores) / len(trailing_scores)
	return (
		config.rolling_current_week_weight * current_score
		+ (1 - config.rolling_current_week_weight) * trailing_avg
	)


def compute_percentile(score: float, cohort_scores: list[float]) -> Optional[float]:
	"""Empirical percentile rank of `score` within `cohort_scores` (this
	week's other qualifying creators), 0-100. `None` if the cohort is
	empty. Simple empirical-CDF percentile — the standard low-complexity
	approach, no need for fancier interpolation at this scale."""
	if not cohort_scores:
		return None
	at_or_below = sum(1 for s in cohort_scores if s <= score)
	return 100.0 * at_or_below / len(cohort_scores)


def apply_percentile_adjustment(
	base_payout: float, percentile: Optional[float], config: ScoreConfig = DEFAULT_CONFIG
) -> float:
	"""Bounded ± adjustment based on cohort standing. Deliberately SMALL
	and bounded (`percentile_adjustment_max`), never a replacement of the
	absolute score — percentile-only pay creates a "race to the bottom"
	(a known algorithmic-wage failure mode: everyone works harder for a
	fixed pool). This only nudges pay toward/away from relative standing,
	it never redefines what "good" means from absolute zero."""
	if percentile is None:
		return base_payout
	adjustment_fraction = (percentile - 50) / 50 * config.percentile_adjustment_max
	return base_payout * (1 + adjustment_fraction)


def compute_revenue_bonus(
	bookings_before: int, bookings_after: int, config: ScoreConfig = DEFAULT_CONFIG
) -> float:
	"""Score-point bonus for incremental bookings correlated with a
	collab — bookings at the outlet in the window after vs. before. Never
	negative (a quiet week after a collab isn't punished, just not
	bonused) — this is a bonus signal, not a penalty mechanism."""
	incremental = max(0, bookings_after - bookings_before)
	return incremental * config.revenue_bonus_per_incremental_booking


def compute_weekly_score(
	app_signals: AppWeekSignals,
	ig_signals: InstagramWeekSignals,
	city_club_members: int,
	*,
	trailing_scores: list[float] = (),
	trailing_raw_engagement: list[float] = (),
	cohort_scores: list[float] = (),
	config: ScoreConfig = DEFAULT_CONFIG,
) -> WeeklyScoreResult:
	"""
	The full v2 algorithm in one call. Pure function — no Frappe/DB
	dependency. This is the entry point to call with synthetic sample data
	for testing, and the same entry point the real weekly job calls with
	DB-sourced data below.

	`trailing_scores` / `trailing_raw_engagement`: this creator's own
	history (last `rolling_window_weeks`), for smoothing + anomaly
	detection. `cohort_scores`: all OTHER qualifying creators' blended
	scores the same week, for percentile.
	"""
	qualified = app_signals.qualifying_posts >= config.min_qualifying_posts

	if not qualified:
		# No posts, no pay, no penalty beyond the missed payout. Score is
		# never computed for a non-qualifying week, not computed-then-
		# zeroed — `qualified=False` and a real 0 score stay distinct.
		return WeeklyScoreResult(
			qualified=False, app_score=0.0, ig_score=0.0, ig_weight=0.0, app_weight=0.0,
			blended_score=0.0, smoothed_score=0.0, percentile=None,
			raw_payout=0.0, payout=0.0, floored=False, capped=False,
			anomaly_flagged=False, anomaly_reason=None, review_required=False,
		)

	app_score = compute_app_score(app_signals, config)
	ig_score = compute_ig_score(ig_signals, config)
	ig_weight, app_weight = compute_blend_weights(city_club_members, config)
	blended_score = ig_weight * ig_score + app_weight * app_score

	smoothed = smooth_score(blended_score, list(trailing_scores), config)

	cohort = list(cohort_scores)
	percentile = (
		compute_percentile(smoothed, cohort) if len(cohort) >= config.percentile_min_cohort_size else None
	)

	anomaly_flagged, anomaly_reason = detect_anomaly(app_signals, list(trailing_raw_engagement), config)

	base_payout = smoothed * config.rupees_per_point
	raw_payout = apply_percentile_adjustment(base_payout, percentile, config)
	payout = max(config.payout_floor, min(config.payout_cap, raw_payout))

	review_required = anomaly_flagged or payout >= config.review_payout_threshold

	return WeeklyScoreResult(
		qualified=True, app_score=app_score, ig_score=ig_score,
		ig_weight=ig_weight, app_weight=app_weight,
		blended_score=blended_score, smoothed_score=smoothed, percentile=percentile,
		raw_payout=raw_payout, payout=payout,
		floored=raw_payout < config.payout_floor, capped=raw_payout > config.payout_cap,
		anomaly_flagged=anomaly_flagged, anomaly_reason=anomaly_reason,
		review_required=review_required,
	)


# ═══════════════════════════════════════════════════════════════════════
# 4. FRAPPE INTEGRATION LAYER — real DB queries + the actual weekly job.
#    Everything below this line touches frappe.db; everything above it
#    doesn't.
# ═══════════════════════════════════════════════════════════════════════

def _week_bounds(reference_date=None):
	"""Monday-Sunday bounds for the week containing `reference_date`
	(defaults to today, evaluated at CALL time via frappe.utils.today() —
	not import time, so this stays correct in a long-running worker)."""
	ref = getdate(reference_date or today())
	start = ref - timedelta(days=ref.weekday())
	end = start + timedelta(days=6)
	return start, end


def _qualifying_post_ids(club: str, week_start, week_end) -> list[str]:
	rows = frappe.db.sql(
		"""SELECT name FROM `tabCreator Club Post`
		   WHERE club=%s AND DATE(creation) BETWEEN %s AND %s""",
		(club, week_start, week_end),
		as_dict=True,
	)
	return [r.name for r in rows]


def _account_age_days(phone: str, as_of_date) -> Optional[int]:
	"""Days since this phone's Customer record was created — the v1 trust
	signal (Section 9 of the algorithm doc flags extending this to also
	check for a completed transaction once it's decided which booking
	doctypes should count; account age alone is what's implemented now,
	not silently assumed to be more than it is)."""
	from flamezo_backend.flamezo.utils.customer_helpers import (
		_find_customer_by_normalized_phone,
		normalize_phone,
	)

	customer_name = _find_customer_by_normalized_phone(normalize_phone(phone))
	if not customer_name:
		return None
	created = frappe.db.get_value("Customer", customer_name, "creation")
	if not created:
		return None
	return (getdate(as_of_date) - getdate(created)).days


def _trust_weighted_engagement(
	doctype: str, post_ids: list[str], post_owner_phone: str, as_of_date, config: ScoreConfig = DEFAULT_CONFIG
) -> tuple[float, dict]:
	"""Returns (trust_weighted_sum, raw_count_by_phone) for likes/comments
	on `post_ids`, EXCLUDING the post owner's own phone (self-engagement
	exclusion — closes the alt-account gaming hole) and weighting every
	remaining engager by account age (`compute_trust_weight`)."""
	if not post_ids:
		return 0.0, {}
	placeholders = ", ".join(["%s"] * len(post_ids))
	rows = frappe.db.sql(
		f"SELECT customer_phone FROM `tab{doctype}` WHERE post IN ({placeholders})",
		post_ids,
		as_dict=True,
	)

	from flamezo_backend.flamezo.utils.customer_helpers import normalize_phone

	owner_normalized = normalize_phone(post_owner_phone) if post_owner_phone else None
	raw_by_phone: dict = {}
	weighted_sum = 0.0
	for row in rows:
		phone = normalize_phone(row.customer_phone) if row.customer_phone else None
		if not phone or phone == owner_normalized:
			continue  # self-engagement — excluded entirely, not just down-weighted
		raw_by_phone[phone] = raw_by_phone.get(phone, 0) + 1
		age = _account_age_days(phone, as_of_date)
		weighted_sum += compute_trust_weight(age, config)

	return weighted_sum, raw_by_phone


def _sum_views_for_posts(post_ids: list[str]) -> int:
	"""Views are Redis-buffered (utils/redis_counters.py, scope
	`club_post_views`), not a direct DB column — read through the same
	module every other view-count consumer uses."""
	if not post_ids:
		return 0
	from flamezo_backend.flamezo.utils import redis_counters as rc

	counts = rc.get_counts("club_post_views", post_ids)
	return sum(counts.values())


_REVENUE_CORRELATION_WINDOW_DAYS = 7  # bookings this many days before/after a collab, per compute_revenue_bonus


def _outlet_bookings_before(outlet: str, center_date, days: int) -> int:
	"""Completed/paid Orders at `outlet` in the `days` days strictly
	BEFORE `center_date` — one half of the signal `compute_revenue_bonus`
	correlates. Counts `payment_status='completed'` only — a cancelled/
	failed order isn't real incremental business."""
	start = center_date - timedelta(days=days)
	return frappe.db.count("Order", {
		"restaurant": outlet,
		"creation": ["between", [start, center_date]],
		"payment_status": "completed",
	})


def _outlet_bookings_after(outlet: str, center_date, days: int) -> int:
	"""Same as `_outlet_bookings_before`, but the `days` days AFTER
	`center_date`."""
	end = center_date + timedelta(days=days)
	return frappe.db.count("Order", {
		"restaurant": outlet,
		"creation": ["between", [center_date, end]],
		"payment_status": "completed",
	})


def _gather_collab_signals(creator_name: str, week_start, week_end, config: ScoreConfig = DEFAULT_CONFIG):
	"""Sums quality-weighted points and revenue bonus across every collab
	this creator completed this week — `Creator Collab Invite` /
	`creator_collabs.py` now exist (creator-program-fundamentals-v1-
	locked.md Section 8), so this is real, not a stub.

	quality_points = sum(rating/5) per completed collab this week — an
	  unrated collab (merchant never rated it) counts as a neutral 1.0,
	  same as a 5-star rating would with rating=5 (5/5=1.0) — deliberately
	  not zero, since "completed" already means the deliverable happened;
	  a rating just refines it up or down from there.
	revenue_bonus = sum of compute_revenue_bonus() per collab, correlating
	  paid Orders at that outlet in the 7 days before vs. after.
	"""
	if not frappe.db.table_exists("Creator Collab Invite"):
		return 0.0, 0.0

	collabs = frappe.db.sql(
		"""SELECT name, outlet, merchant_rating, completed_at
		   FROM `tabCreator Collab Invite`
		   WHERE creator=%s AND status='completed'
		     AND completed_at BETWEEN %s AND %s""",
		(creator_name, week_start, week_end),
		as_dict=True,
	)
	if not collabs:
		return 0.0, 0.0

	quality_points = 0.0
	revenue_bonus = 0.0
	for c in collabs:
		rating = c.merchant_rating if c.merchant_rating else 5  # unrated = neutral, see docstring
		quality_points += min(5, max(1, rating)) / 5.0

		collab_date = getdate(c.completed_at)
		before = _outlet_bookings_before(c.outlet, collab_date, _REVENUE_CORRELATION_WINDOW_DAYS)
		after = _outlet_bookings_after(c.outlet, collab_date, _REVENUE_CORRELATION_WINDOW_DAYS)
		bonus = compute_revenue_bonus(before, after, config)
		revenue_bonus += bonus
		frappe.db.set_value("Creator Collab Invite", c.name, "revenue_bonus_points", bonus)

	return quality_points, revenue_bonus


def gather_app_signals(creator_name: str, week_start, week_end, config: ScoreConfig = DEFAULT_CONFIG) -> AppWeekSignals:
	"""Pulls one creator's real in-app activity for one week, with
	self-engagement excluded, trust-weighting applied, and concentration
	computed for anomaly detection."""
	club_row = frappe.db.get_value(
		"Creator Club", {"creator": creator_name}, ["name"], as_dict=True
	)
	if not club_row:
		return AppWeekSignals(qualifying_posts=0)
	club = club_row.name

	owner_phone = frappe.db.get_value("Flamezo Creator", creator_name, "customer_phone")

	post_ids = _qualifying_post_ids(club, week_start, week_end)
	if not post_ids:
		return AppWeekSignals(qualifying_posts=0)

	weighted_likes, likes_by_phone = _trust_weighted_engagement(
		"Creator Club Post Like", post_ids, owner_phone, week_end, config
	)
	weighted_comments, comments_by_phone = _trust_weighted_engagement(
		"Creator Club Post Comment", post_ids, owner_phone, week_end, config
	)

	combined_by_phone: dict = {}
	for phone, n in likes_by_phone.items():
		combined_by_phone[phone] = combined_by_phone.get(phone, 0) + n
	for phone, n in comments_by_phone.items():
		combined_by_phone[phone] = combined_by_phone.get(phone, 0) + n

	raw_total = sum(combined_by_phone.values())
	concentration = compute_engager_concentration(combined_by_phone, config)

	new_followers = frappe.db.count("Creator Club Member", {
		"club": club,
		"creation": ["between", [week_start, week_end]],
	})

	quality_points, revenue_bonus = _gather_collab_signals(creator_name, week_start, week_end, config)

	return AppWeekSignals(
		qualifying_posts=len(post_ids),
		likes=weighted_likes,
		comments=weighted_comments,
		views=_sum_views_for_posts(post_ids),
		new_followers=cint(new_followers),
		collabs_completed=quality_points,
		revenue_bonus_points=revenue_bonus,
		raw_engagement_total=raw_total,
		engager_concentration=concentration,
		total_engagers=len(combined_by_phone),
	)


def gather_ig_signals(creator_name: str, week_start, week_end) -> InstagramWeekSignals:
	"""STUB — reads from wherever the collab story-match / insights-poll
	pipeline (creator-program-fundamentals-v1-locked.md Section 7) stores
	its results, once that pipeline exists. Returns 'no data' rather than
	fabricating numbers — a missing IG term correctly contributes 0 to the
	blend, it doesn't need a fake fallback to behave sanely."""
	return InstagramWeekSignals.empty()


def city_club_member_count(city: str) -> int:
	"""Total active Club membership across a city — the blend's maturity
	proxy (algorithm doc Section 4)."""
	if not city:
		return 0
	result = frappe.db.sql(
		"""SELECT COUNT(DISTINCT ccm.customer_phone)
		   FROM `tabCreator Club Member` ccm
		   JOIN `tabCreator Club` cc ON cc.name = ccm.club
		   JOIN `tabFlamezo Creator` fc ON fc.name = cc.creator
		   WHERE fc.city = %s AND cc.is_active = 1""",
		city,
	)
	return cint(result[0][0]) if result else 0


def _trailing_history(creator_name: str, week_start, config: ScoreConfig = DEFAULT_CONFIG) -> tuple[list[float], list[float]]:
	"""Returns (trailing_smoothed_scores, trailing_raw_engagement) for the
	`rolling_window_weeks` weeks immediately before `week_start`, from
	already-persisted `Creator Weekly Score` rows. Empty lists for a
	creator's first weeks — smoothing/anomaly detection both handle that
	correctly (no history = no adjustment)."""
	rows = frappe.db.sql(
		"""SELECT smoothed_score, final_score FROM `tabCreator Weekly Score`
		   WHERE creator=%s AND week_start < %s AND qualified=1
		   ORDER BY week_start DESC LIMIT %s""",
		(creator_name, week_start, config.rolling_window_weeks),
		as_dict=True,
	)
	scores = [flt(r.smoothed_score or r.final_score) for r in rows]
	# Raw engagement history isn't separately persisted (only the derived
	# score is) — reconstructing it exactly would need a second stored
	# column; approximating with the same trailing scores is a reasonable
	# v1 proxy since both move together, and is flagged here rather than
	# silently presented as more precise than it is.
	return scores, scores


def credit_creator_reward(creator_name: str, amount: float, week_start, week_end):
	"""Credits a `Creator Reward Ledger` entry — see this module's
	docstring for why this is a new ledger rather than reusing the
	restaurant-locked UGC Voucher / loyalty-coin systems. Idempotent per
	(creator, week_start)."""
	existing = frappe.db.exists("Creator Reward Ledger", {
		"creator": creator_name,
		"week_start": week_start,
	})
	if existing:
		return existing

	entry = frappe.get_doc({
		"doctype": "Creator Reward Ledger",
		"creator": creator_name,
		"week_start": week_start,
		"week_end": week_end,
		"amount": flt(amount),
		"reason": f"Creator weekly reward — {week_start} to {week_end}",
	})
	entry.insert(ignore_permissions=True)
	frappe.db.commit()
	return entry.name


def approve_flagged_week(weekly_score_name: str, reviewed_by: str):
	"""Manual approval path for a `pending_review` week — the ONLY place a
	human touches this pipeline, and only for the minority of weeks that
	tripped an anomaly flag or crossed the large-payout threshold. Credits
	the reward on approval; does nothing (leaves rejected) otherwise."""
	doc = frappe.get_doc("Creator Weekly Score", weekly_score_name)
	if doc.review_status != "pending_review":
		frappe.throw(f"Week {weekly_score_name} is not pending review (status={doc.review_status})")

	doc.review_status = "approved"
	doc.reviewed_by = reviewed_by
	doc.reviewed_at = now_datetime()
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	if doc.payout_inr and flt(doc.payout_inr) > 0:
		credit_creator_reward(doc.creator, flt(doc.payout_inr), doc.week_start, doc.week_end)


def reject_flagged_week(weekly_score_name: str, reviewed_by: str):
	"""Rejects a `pending_review` week — no credit issued, ever, for this
	week. Reason for rejection is whatever's already in `anomaly_reason`;
	no separate free-text needed since it's the same explanation that
	triggered the flag."""
	doc = frappe.get_doc("Creator Weekly Score", weekly_score_name)
	if doc.review_status != "pending_review":
		frappe.throw(f"Week {weekly_score_name} is not pending review (status={doc.review_status})")

	doc.review_status = "rejected"
	doc.reviewed_by = reviewed_by
	doc.reviewed_at = now_datetime()
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def run_weekly_payout(week_start=None, week_end=None, config: ScoreConfig = DEFAULT_CONFIG):
	"""
	Scheduled job entry point — register weekly in hooks.py's
	scheduler_events, same cron group as redis_counters.flush_all etc.

	Two passes, so percentile can compare every creator against the same
	week's full cohort without a second DB gather:
	  Pass A — gather real signals + compute the pre-percentile blended
	           score for every approved creator.
	  Pass B — using the full cohort from Pass A, compute the final score
	           (smoothing, percentile, anomaly, payout) per creator and
	           persist + credit (or route to review).
	"""
	start, end = (getdate(week_start), getdate(week_end)) if week_start else _week_bounds()
	creators = frappe.db.get_all(
		"Flamezo Creator",
		filters={"status": "approved"},
		fields=["name", "city"],
	)

	# Pass A
	prepared = []
	cohort_blended_scores = []
	for creator in creators:
		app_signals = gather_app_signals(creator.name, start, end, config)
		ig_signals = gather_ig_signals(creator.name, start, end)
		members = city_club_member_count(creator.city)

		if app_signals.qualifying_posts < config.min_qualifying_posts:
			prepared.append((creator.name, app_signals, ig_signals, members, None))
			continue

		app_score = compute_app_score(app_signals, config)
		ig_score = compute_ig_score(ig_signals, config)
		ig_weight, app_weight = compute_blend_weights(members, config)
		blended = ig_weight * ig_score + app_weight * app_score
		cohort_blended_scores.append(blended)
		prepared.append((creator.name, app_signals, ig_signals, members, blended))

	# Pass B
	results = []
	for creator_name, app_signals, ig_signals, members, own_blended in prepared:
		trailing_scores, trailing_engagement = _trailing_history(creator_name, start, config)
		# Cohort excludes the creator's own score for a meaningful comparison.
		cohort = [s for s in cohort_blended_scores if own_blended is None or s != own_blended] \
			if own_blended is not None else cohort_blended_scores

		result = compute_weekly_score(
			app_signals, ig_signals, members,
			trailing_scores=trailing_scores,
			trailing_raw_engagement=trailing_engagement,
			cohort_scores=cohort,
			config=config,
		)
		results.append((creator_name, result))

		_persist_weekly_receipt(creator_name, start, end, result)

		if result.qualified and result.payout > 0 and not result.review_required:
			credit_creator_reward(creator_name, result.payout, start, end)

	qualified_count = sum(1 for _, r in results if r.qualified)
	flagged_count = sum(1 for _, r in results if r.review_required)
	frappe.logger().info(
		f"[creator_score_engine] weekly payout run {start}..{end}: "
		f"{len(results)} creators processed, {qualified_count} qualified, "
		f"{flagged_count} routed to review"
	)
	return results


def _persist_weekly_receipt(creator_name: str, week_start, week_end, result: WeeklyScoreResult):
	"""Stores the receipt for the in-app transparency view (algorithm doc
	Section 7) — this is what a creator's weekly breakdown screen reads
	from, what trailing-history lookups read from, and what any future
	`ScoreConfig` retuning gets validated against."""
	if frappe.db.exists("Creator Weekly Score", {"creator": creator_name, "week_start": week_start}):
		return  # idempotent — same guard as credit_creator_reward

	frappe.get_doc({
		"doctype": "Creator Weekly Score",
		"creator": creator_name,
		"week_start": week_start,
		"week_end": week_end,
		**result.to_receipt_dict(),
	}).insert(ignore_permissions=True)
	frappe.db.commit()
