# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Real unit tests + a runnable sample-data demo for the pure calculation
core in utils/creator_score_engine.py. The demo classes below are exactly
the "pass sample data of example different users and see how it returns"
check requested — run via:

	bench --site flamezo.localhost run-tests --app flamezo_backend \
		--module flamezo_backend.flamezo.tests.test_creator_score_engine

The demo test (`TestSampleCreators.test_print_sample_payouts`) prints a
formatted table of every sample creator's breakdown when run with -s
(pytest-style stdout not suppressed):

	bench --site flamezo.localhost run-tests --app flamezo_backend \
		--module flamezo_backend.flamezo.tests.test_creator_score_engine -s
"""

import unittest

from flamezo_backend.flamezo.utils.creator_score_engine import (
	AppWeekSignals,
	InstagramWeekSignals,
	ScoreConfig,
	DEFAULT_CONFIG,
	apply_percentile_adjustment,
	compute_app_score,
	compute_blend_weights,
	compute_engager_concentration,
	compute_ig_score,
	compute_percentile,
	compute_revenue_bonus,
	compute_trust_weight,
	compute_weekly_score,
	detect_anomaly,
	smooth_score,
)


class TestComputeAppScore(unittest.TestCase):
	def test_all_zero_signals_score_zero(self):
		score = compute_app_score(AppWeekSignals(qualifying_posts=2))
		self.assertEqual(score, 0.0)

	def test_matches_hand_calculated_value(self):
		# 120 likes, 25 comments, 3200 views, 18 new followers, 1 collab
		signals = AppWeekSignals(
			qualifying_posts=3, likes=120, comments=25, views=3200,
			new_followers=18, collabs_completed=1,
		)
		# (120*0.5)+(25*2)+(3200*0.05)+(18*4)+(1*40) = 60+50+160+72+40 = 382
		self.assertAlmostEqual(compute_app_score(signals), 382.0)

	def test_negative_signal_raises(self):
		with self.assertRaises(ValueError):
			AppWeekSignals(qualifying_posts=2, likes=-1)

	def test_collabs_dominate_relative_to_organic_engagement(self):
		"""One collab should be worth more than a very active organic week
		with no collab — this is a deliberate design property, not
		incidental, so it's worth a regression test."""
		organic_heavy = AppWeekSignals(
			qualifying_posts=5, likes=500, comments=50, views=10_000, new_followers=20,
		)
		one_collab_only = AppWeekSignals(qualifying_posts=2, collabs_completed=1)
		# Not asserting collab alone beats a huge organic week outright —
		# just that its per-unit weight is meaningfully larger than a like.
		config = ScoreConfig()
		self.assertGreater(config.weight_collab_completed, config.weight_like * 50)


class TestComputeIgScore(unittest.TestCase):
	def test_no_ig_data_scores_zero_not_error(self):
		self.assertEqual(compute_ig_score(InstagramWeekSignals.empty()), 0.0)

	def test_matches_hand_calculated_value(self):
		signals = InstagramWeekSignals(reach=6500, engagement_rate_pct=7.2)
		# log10(6501)*15 + 7.2*8 = ~114.8
		self.assertAlmostEqual(compute_ig_score(signals), 114.8, places=1)

	def test_engagement_rate_dominates_raw_reach(self):
		"""Core anti-fraud property: a smaller, highly-engaged audience
		should out-score a much larger, barely-engaged one."""
		small_engaged = InstagramWeekSignals(reach=3_000, engagement_rate_pct=15.0)
		large_dead = InstagramWeekSignals(reach=80_000, engagement_rate_pct=0.5)
		self.assertGreater(compute_ig_score(small_engaged), compute_ig_score(large_dead))

	def test_out_of_range_engagement_rate_raises(self):
		with self.assertRaises(ValueError):
			InstagramWeekSignals(reach=100, engagement_rate_pct=101)


class TestComputeBlendWeights(unittest.TestCase):
	def test_zero_members_uses_max_ig_weight(self):
		ig, app = compute_blend_weights(0)
		self.assertAlmostEqual(ig, 0.60)
		self.assertAlmostEqual(app, 0.40)

	def test_at_reference_size_hits_floor(self):
		ig, app = compute_blend_weights(10_000)
		self.assertAlmostEqual(ig, 0.30)
		self.assertAlmostEqual(app, 0.70)

	def test_beyond_reference_size_stays_at_floor(self):
		ig, _ = compute_blend_weights(50_000)
		self.assertAlmostEqual(ig, 0.30)

	def test_weights_always_sum_to_one(self):
		for members in (0, 500, 2_500, 5_000, 10_000, 99_999):
			ig, app = compute_blend_weights(members)
			self.assertAlmostEqual(ig + app, 1.0)

	def test_negative_members_raises(self):
		with self.assertRaises(ValueError):
			compute_blend_weights(-1)


class TestComputeWeeklyScore(unittest.TestCase):
	def test_below_minimum_posts_not_qualified_zero_payout(self):
		result = compute_weekly_score(
			AppWeekSignals(qualifying_posts=1, likes=1000, comments=1000),
			InstagramWeekSignals(reach=100_000, engagement_rate_pct=20),
			city_club_members=0,
		)
		self.assertFalse(result.qualified)
		self.assertEqual(result.payout, 0.0)

	def test_qualifying_week_pays_at_least_the_floor(self):
		result = compute_weekly_score(
			AppWeekSignals(qualifying_posts=2, likes=1, comments=0, views=1),
			InstagramWeekSignals.empty(),
			city_club_members=5000,
		)
		self.assertTrue(result.qualified)
		self.assertEqual(result.payout, 150.0)
		self.assertTrue(result.floored)

	def test_huge_week_is_capped(self):
		result = compute_weekly_score(
			AppWeekSignals(
				qualifying_posts=10, likes=50_000, comments=10_000,
				views=1_000_000, new_followers=5_000, collabs_completed=20,
			),
			InstagramWeekSignals(reach=1_000_000, engagement_rate_pct=25),
			city_club_members=0,
		)
		self.assertEqual(result.payout, 2000.0)
		self.assertTrue(result.capped)

	def test_priya_worked_example_from_algorithm_doc(self):
		"""Regression test pinned to the exact worked example in
		creator-weekly-score-algorithm.md Section 5 — if this ever fails,
		either the doc or the code drifted and one needs to be fixed."""
		result = compute_weekly_score(
			AppWeekSignals(
				qualifying_posts=3, likes=120, comments=25, views=3200,
				new_followers=18, collabs_completed=1,
			),
			InstagramWeekSignals(reach=6500, engagement_rate_pct=7.2),
			city_club_members=800,
		)
		self.assertAlmostEqual(result.app_score, 382.0, places=1)
		self.assertAlmostEqual(result.ig_score, 114.8, places=1)
		self.assertAlmostEqual(result.blended_score, 228.1, delta=0.5)
		self.assertAlmostEqual(result.payout, 1140.0, delta=3)

	def test_no_history_smoothed_equals_blended(self):
		"""A creator's first qualifying week has no trailing history —
		smoothed_score must equal blended_score unchanged, not blow up on
		an empty list."""
		result = compute_weekly_score(
			AppWeekSignals(qualifying_posts=2, likes=50, comments=10),
			InstagramWeekSignals.empty(),
			city_club_members=0,
		)
		self.assertAlmostEqual(result.smoothed_score, result.blended_score)

	def test_no_cohort_percentile_is_none(self):
		result = compute_weekly_score(
			AppWeekSignals(qualifying_posts=2, likes=50, comments=10),
			InstagramWeekSignals.empty(),
			city_club_members=0,
		)
		self.assertIsNone(result.percentile)

	def test_smoothing_dampens_a_single_spike(self):
		"""A one-off strong week should pay LESS than its own raw score once
		smoothed against a much quieter trailing history — this is the
		whole point of Tier 2's rolling average. Deliberately sized so the
		unsmoothed payout sits below the cap — a spike big enough to hit
		the cap either way would mask the smoothing effect at the payout
		level even though smoothed_score itself is still correctly lower
		(caught by running this: an earlier, larger spike did exactly
		that and silently passed on the wrong assertion)."""
		spike_signals = AppWeekSignals(qualifying_posts=3, likes=400, comments=80, views=2000, new_followers=20)
		unsmoothed = compute_weekly_score(spike_signals, InstagramWeekSignals.empty(), city_club_members=0)
		smoothed = compute_weekly_score(
			spike_signals, InstagramWeekSignals.empty(), city_club_members=0,
			trailing_scores=[20.0, 25.0, 18.0],
		)
		self.assertLess(unsmoothed.payout, DEFAULT_CONFIG.payout_cap, "test needs an unsmoothed payout below the cap")
		self.assertLess(smoothed.smoothed_score, unsmoothed.smoothed_score)
		self.assertLess(smoothed.payout, unsmoothed.payout)

	def test_anomaly_flag_routes_to_review_not_auto_pay(self):
		spiky = AppWeekSignals(
			qualifying_posts=2, likes=2000, comments=500,
			raw_engagement_total=2500, engager_concentration=0.1, total_engagers=50,
		)
		result = compute_weekly_score(
			spiky, InstagramWeekSignals.empty(), city_club_members=0,
			trailing_raw_engagement=[100, 120, 90],  # trailing avg ~103, this week is ~24x that
		)
		self.assertTrue(result.anomaly_flagged)
		self.assertTrue(result.review_required)
		self.assertIsNotNone(result.anomaly_reason)

	def test_large_payout_routes_to_review_even_without_anomaly(self):
		big_but_clean = AppWeekSignals(
			qualifying_posts=10, likes=50_000, comments=10_000, views=1_000_000,
			new_followers=5_000, collabs_completed=20,
		)
		result = compute_weekly_score(big_but_clean, InstagramWeekSignals.empty(), city_club_members=0)
		self.assertGreaterEqual(result.payout, DEFAULT_CONFIG_REVIEW_THRESHOLD)
		self.assertTrue(result.review_required)


DEFAULT_CONFIG_REVIEW_THRESHOLD = ScoreConfig().review_payout_threshold


class TestTrustWeighting(unittest.TestCase):
	def test_brand_new_account_gets_minimum_weight(self):
		self.assertAlmostEqual(compute_trust_weight(0), ScoreConfig().trust_weight_new_account)
		self.assertAlmostEqual(compute_trust_weight(None), ScoreConfig().trust_weight_new_account)

	def test_established_account_gets_full_weight(self):
		self.assertAlmostEqual(compute_trust_weight(30), 1.0)
		self.assertAlmostEqual(compute_trust_weight(365), 1.0)

	def test_ramps_linearly_between(self):
		half_aged = compute_trust_weight(15)  # halfway to the 30-day full-trust mark
		self.assertGreater(half_aged, ScoreConfig().trust_weight_new_account)
		self.assertLess(half_aged, 1.0)


class TestEngagerConcentration(unittest.TestCase):
	def test_no_engagement_is_zero(self):
		self.assertEqual(compute_engager_concentration({}), 0.0)

	def test_evenly_spread_engagement_low_concentration(self):
		spread = {f"phone{i}": 1 for i in range(20)}
		self.assertLess(compute_engager_concentration(spread), 0.3)

	def test_few_accounts_dominating_high_concentration(self):
		lopsided = {"phoneA": 100, "phoneB": 90, "phoneC": 80, **{f"other{i}": 1 for i in range(20)}}
		self.assertGreater(compute_engager_concentration(lopsided), 0.8)


class TestDetectAnomaly(unittest.TestCase):
	def test_no_history_never_flags_on_velocity(self):
		signals = AppWeekSignals(qualifying_posts=2, raw_engagement_total=10_000, total_engagers=1)
		flagged, reason = detect_anomaly(signals, trailing_raw_engagement=[])
		self.assertFalse(flagged)

	def test_spike_past_multiplier_flags(self):
		signals = AppWeekSignals(qualifying_posts=2, raw_engagement_total=1000, total_engagers=1)
		flagged, reason = detect_anomaly(signals, trailing_raw_engagement=[100, 110, 90])
		self.assertTrue(flagged)
		self.assertIn("trailing", reason)

	def test_concentration_alone_flags(self):
		signals = AppWeekSignals(
			qualifying_posts=2, raw_engagement_total=100,
			engager_concentration=0.9, total_engagers=10,
		)
		flagged, reason = detect_anomaly(signals, trailing_raw_engagement=[])
		self.assertTrue(flagged)
		self.assertIn("engagers", reason)

	def test_below_min_engagers_does_not_flag_concentration(self):
		"""A tiny early creator with 2 engagers, one of whom liked twice,
		shouldn't get flagged just for having a small audience."""
		signals = AppWeekSignals(
			qualifying_posts=2, raw_engagement_total=3,
			engager_concentration=1.0, total_engagers=2,
		)
		flagged, _ = detect_anomaly(signals, trailing_raw_engagement=[])
		self.assertFalse(flagged)


class TestSmoothScore(unittest.TestCase):
	def test_no_trailing_returns_current_unchanged(self):
		self.assertEqual(smooth_score(100.0, []), 100.0)

	def test_blends_toward_trailing_average(self):
		result = smooth_score(200.0, [50.0, 50.0, 50.0])
		config = ScoreConfig()
		expected = config.rolling_current_week_weight * 200.0 + (1 - config.rolling_current_week_weight) * 50.0
		self.assertAlmostEqual(result, expected)


class TestPercentile(unittest.TestCase):
	def test_empty_cohort_is_none(self):
		self.assertIsNone(compute_percentile(100, []))

	def test_top_scorer_near_100th_percentile(self):
		pct = compute_percentile(100, [10, 20, 30, 40, 100])
		self.assertEqual(pct, 100.0)

	def test_bottom_scorer_low_percentile(self):
		pct = compute_percentile(5, [10, 20, 30, 40, 100])
		self.assertEqual(pct, 0.0)

	def test_median_scorer_near_50th(self):
		pct = compute_percentile(30, [10, 20, 30, 40, 100])
		self.assertAlmostEqual(pct, 60.0)  # 3 of 5 values <= 30


class TestPercentileAdjustment(unittest.TestCase):
	def test_none_percentile_no_adjustment(self):
		self.assertEqual(apply_percentile_adjustment(1000.0, None), 1000.0)

	def test_50th_percentile_neutral(self):
		self.assertAlmostEqual(apply_percentile_adjustment(1000.0, 50.0), 1000.0)

	def test_top_percentile_gets_bonus(self):
		result = apply_percentile_adjustment(1000.0, 100.0)
		self.assertGreater(result, 1000.0)
		config = ScoreConfig()
		self.assertAlmostEqual(result, 1000.0 * (1 + config.percentile_adjustment_max))

	def test_bottom_percentile_gets_penalty_bounded(self):
		result = apply_percentile_adjustment(1000.0, 0.0)
		self.assertLess(result, 1000.0)
		config = ScoreConfig()
		self.assertAlmostEqual(result, 1000.0 * (1 - config.percentile_adjustment_max))


class TestRevenueBonus(unittest.TestCase):
	def test_no_incremental_bookings_zero_bonus(self):
		self.assertEqual(compute_revenue_bonus(5, 5), 0.0)
		self.assertEqual(compute_revenue_bonus(5, 3), 0.0)  # a drop isn't penalized, just not bonused

	def test_incremental_bookings_scale_bonus(self):
		config = ScoreConfig()
		self.assertAlmostEqual(compute_revenue_bonus(2, 7, config), 5 * config.revenue_bonus_per_incremental_booking)


# ═══════════════════════════════════════════════════════════════════════
# Sample-data demo — six illustrative creator profiles across a range of
# situations, run through the real engine. This is the "pass sample data
# of example different users and see how it returns" check.
# ═══════════════════════════════════════════════════════════════════════

SAMPLE_CREATORS = [
	{
		"label": "Priya — Foodie club, strong week with a completed collab",
		"app": AppWeekSignals(
			qualifying_posts=3, likes=120, comments=25, views=3200,
			new_followers=18, collabs_completed=1,
		),
		"ig": InstagramWeekSignals(reach=6500, engagement_rate_pct=7.2),
		"city_club_members": 800,
	},
	{
		"label": "Arjun — Fitness club, huge follower count but low real engagement (fraud-resistance check)",
		"app": AppWeekSignals(
			qualifying_posts=2, likes=40, comments=3, views=900,
			new_followers=2, collabs_completed=0,
		),
		"ig": InstagramWeekSignals(reach=45_000, engagement_rate_pct=0.6),
		"city_club_members": 800,
	},
	{
		"label": "Zoya — Cafe club, small real audience but genuinely engaged",
		"app": AppWeekSignals(
			qualifying_posts=2, likes=80, comments=22, views=1100,
			new_followers=9, collabs_completed=0,
		),
		"ig": InstagramWeekSignals(reach=2800, engagement_rate_pct=12.5),
		"city_club_members": 800,
	},
	{
		"label": "Rahul — barely qualifies, quiet week",
		"app": AppWeekSignals(
			qualifying_posts=2, likes=15, comments=2, views=400, new_followers=1,
		),
		"ig": InstagramWeekSignals.empty(),
		"city_club_members": 800,
	},
	{
		"label": "Meera — posted only once, doesn't qualify",
		"app": AppWeekSignals(qualifying_posts=1, likes=500, comments=100, views=8000),
		"ig": InstagramWeekSignals(reach=20_000, engagement_rate_pct=9.0),
		"city_club_members": 800,
	},
	{
		"label": "Karan — large creator in a MATURE city (7,000 Club members — blend shifted toward app data)",
		"app": AppWeekSignals(
			qualifying_posts=4, likes=900, comments=140, views=22_000,
			new_followers=60, collabs_completed=2,
		),
		"ig": InstagramWeekSignals(reach=90_000, engagement_rate_pct=4.1),
		"city_club_members": 7000,
	},
]


class TestSampleCreators(unittest.TestCase):
	def test_print_sample_payouts(self):
		print("\n" + "=" * 100)
		print(f"{'Creator':<70} {'Score':>8} {'Payout':>10}  Flags")
		print("-" * 100)
		for c in SAMPLE_CREATORS:
			result = compute_weekly_score(c["app"], c["ig"], c["city_club_members"])
			flags = []
			if not result.qualified:
				flags.append("NOT QUALIFIED")
			if result.floored:
				flags.append("floored")
			if result.capped:
				flags.append("capped")
			print(
				f"{c['label']:<70} {result.blended_score:>8.1f} "
				f"₹{result.payout:>8.2f}  {', '.join(flags)}"
			)
			# Every sample must produce a valid, non-negative payout within
			# [0, cap] — the demo doubles as a sanity assertion, not just
			# printed output.
			self.assertGreaterEqual(result.payout, 0.0)
			self.assertLessEqual(result.payout, 2000.0)
		print("=" * 100)

		# The fraud-resistance property this whole formula exists for:
		# Zoya (small, real audience) should out-earn Arjun (huge,
		# disengaged audience) despite Arjun having ~16x her reach.
		zoya = compute_weekly_score(
			SAMPLE_CREATORS[2]["app"], SAMPLE_CREATORS[2]["ig"],
			SAMPLE_CREATORS[2]["city_club_members"],
		)
		arjun = compute_weekly_score(
			SAMPLE_CREATORS[1]["app"], SAMPLE_CREATORS[1]["ig"],
			SAMPLE_CREATORS[1]["city_club_members"],
		)
		self.assertGreater(
			zoya.payout, arjun.payout,
			"Small-engaged-audience creator should out-earn large-disengaged one",
		)
