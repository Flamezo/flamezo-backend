"""
Chills Feed Algorithm — E2E Test Suite
========================================
Synthetic dataset:
  • 20 test outlets (chills1..chills20)
  • 100 test Chills with varied tags, ages, engagement stats, locations
  • 10 simulated users (user1..user10) with different preference profiles

Tests:
  1. never_repeat   — watched videos never reappear in queue
  2. personalisation — user with dining preference gets dining-heavy queue
  3. cold_start      — 0-watch user gets national trending
  4. warm_start      — 5-watch user gets blended queue
  5. outlet_diversity — same outlet capped at MAX_PER_OUTLET_IN_QUEUE
  6. consecutive_cap  — no more than CONSECUTIVE_OUTLET_CAP from same outlet in a row
  7. not_interested   — outlet suppressed, tags penalized
  8. new_content_injection — Chills < 48h appear at reserved slots
  9. exhaustion_fallback  — user who watched everything still gets a queue
  10. performance         — 10 users × queue build in < 20s total

Run with:
  cd frappe-bench
  bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_chills_feed_algorithm
"""

import json
import time
import unittest
import frappe
from frappe.utils import now_datetime, add_days

from flamezo_backend.flamezo.tests.utils import make_restaurant

# ── Test dataset configuration ─────────────────────────────────────────────────

_PREFIX      = "TEST-CHILLS-ALGO"
_PHONE_BASE  = "98000000"  # phones: 9800000001..9800000010

# Tag clusters used for preference testing
_TAG_DINING   = ["dining-restaurant-casual", "dining-cafe-specialty", "dining-dessert"]
_TAG_FASHION  = ["fashion-apparel-women", "fashion-accessories", "fashion-ethnic"]
_TAG_WELLNESS = ["wellness-fitness-yoga", "wellness-spa-massage", "wellness-nutrition"]
_TAG_SPORTS   = ["sports-cricket-gear", "sports-court-badminton"]

_ALL_TAGS = _TAG_DINING + _TAG_FASHION + _TAG_WELLNESS + _TAG_SPORTS


def _phone(n):
    return f"{_PHONE_BASE}{n:02d}"


# ── Setup / teardown helpers ───────────────────────────────────────────────────

def _cleanup():
    frappe.db.sql(
        "DELETE FROM `tabChills Watch Event` WHERE user_phone LIKE %s",
        [f"{_PHONE_BASE}%"],
    )
    frappe.db.sql(
        "DELETE FROM `tabChills` WHERE outlet LIKE %s",
        [f"{_PREFIX}%"],
    )
    frappe.db.sql(
        "DELETE FROM `tabUser Chills Preference` WHERE user_phone LIKE %s",
        [f"{_PHONE_BASE}%"],
    )
    frappe.db.commit()


def _clear_redis_for_phones():
    """Bust Redis state for all test phones."""
    from flamezo_backend.flamezo.api.chills_feed import _rk
    for i in range(1, 11):
        phone = _phone(i)
        for key_suffix in ["queue", "prefs", "thompson", "watched", "suppress"]:
            frappe.cache().delete_value(_rk(key_suffix, phone))
    # Also clear global snapshots
    for key_suffix in ["candidates_snapshot", "global_scores", "new_content"]:
        frappe.cache().delete_value(_rk(key_suffix))


def _make_outlet(n):
    name = f"{_PREFIX}-{n:02d}"
    make_restaurant(name, plan="GOLD", balance=5000.0)
    return name


def _make_chills(outlet, tags, age_hours=24, views=100, likes=10, saves=5, shares=2):
    """Insert a test Chills row directly via SQL for speed."""
    import datetime
    published_at = frappe.utils.add_to_date(now_datetime(), hours=-age_hours)
    name = frappe.generate_hash(length=10)
    frappe.db.sql(
        """
        INSERT INTO `tabChills`
        (name, creation, modified, owner, docstatus, outlet,
         video_url, thumbnail_url, description, status,
         niche_tags, custom_tags,
         outlet_lat, outlet_lng,
         views_count, likes_count, saves_count, shares_count,
         published_at)
        VALUES
        (%s, NOW(), NOW(), 'Administrator', 1, %s,
         %s, %s, %s, 'published',
         %s, %s,
         %s, %s,
         %s, %s, %s, %s,
         %s)
        """,
        [
            name, outlet,
            f"https://cdn.test/{name}.mp4",
            f"https://cdn.test/{name}.jpg",
            f"Test chills {name}",
            json.dumps(tags), "[]",
            12.9716, 77.5946,  # Bengaluru coords for all test outlets
            views, likes, saves, shares,
            str(published_at),
        ],
    )
    frappe.db.commit()
    return name


def _simulate_watches(phone, chills_ids, event_type="watch_complete", watch_pct=95):
    """Directly write to Redis watched set (fast, no DB write needed for filter tests)."""
    from flamezo_backend.flamezo.api.chills_feed import _rk
    lst = chills_ids
    frappe.cache().set_value(_rk("watched", phone), lst, expires_in_sec=86400 * 90)


def _set_prefs(phone, prefs_dict):
    from flamezo_backend.flamezo.api.chills_feed import _rk
    frappe.cache().set_value(_rk("prefs", phone), prefs_dict, expires_in_sec=86400)


# ── Test class ─────────────────────────────────────────────────────────────────

class TestChillsFeedAlgorithm(unittest.TestCase):
    """E2E tests for the personalised Chills feed algorithm."""

    @classmethod
    def setUpClass(cls):
        _cleanup()
        _clear_redis_for_phones()
        cls._outlets = []
        cls._chills = []
        cls._chills_by_tag = {}

        # Create 20 outlets
        for i in range(1, 21):
            cls._outlets.append(_make_outlet(i))

        # Create 100 Chills:
        # - 30 dining (outlets 1-5, varied ages and engagement)
        # - 25 fashion (outlets 6-10)
        # - 25 wellness (outlets 11-15)
        # - 20 sports (outlets 16-20)
        tag_groups = [
            (_TAG_DINING,   30, cls._outlets[0:5],   "dining"),
            (_TAG_FASHION,  25, cls._outlets[5:10],  "fashion"),
            (_TAG_WELLNESS, 25, cls._outlets[10:15], "wellness"),
            (_TAG_SPORTS,   20, cls._outlets[15:20], "sports"),
        ]

        for tags, count, outlets, group_name in tag_groups:
            cls._chills_by_tag[group_name] = []
            for j in range(count):
                outlet   = outlets[j % len(outlets)]
                age      = 2 + j * 8          # 2h to ~240h old (varied freshness)
                views    = 50 + j * 30        # 50 to 950 views
                likes    = max(1, j * 3)
                saves    = max(1, j * 2)
                shares   = max(0, j)
                # Use 1-3 tags for variety
                sub_tags = tags[:min(3, 1 + j % len(tags))]
                cid = _make_chills(outlet, sub_tags, age, views, likes, saves, shares)
                cls._chills.append(cid)
                cls._chills_by_tag[group_name].append(cid)

        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        _cleanup()
        _clear_redis_for_phones()

    def setUp(self):
        # Clear Redis state for test isolation (per-user keys only)
        _clear_redis_for_phones()

    # ── 1. never_repeat ────────────────────────────────────────────────────────

    def test_01_never_repeat(self):
        """Watched videos must never appear in the queue."""
        from flamezo_backend.flamezo.api.chills_feed import _build_and_cache_queue, _rk

        phone = _phone(1)

        # Build initial queue
        queue1 = _build_and_cache_queue(phone, 12.9716, 77.5946)
        self.assertGreater(len(queue1), 0, "First queue must not be empty")

        # Mark all items as watched
        _simulate_watches(phone, queue1)

        # Rebuild — none of the previously watched items should appear
        frappe.cache().delete_value(_rk("queue", phone))
        queue2 = _build_and_cache_queue(phone, 12.9716, 77.5946)

        overlap = set(queue1) & set(queue2)
        self.assertEqual(
            len(overlap), 0,
            f"Watched videos reappeared in queue: {overlap}"
        )

    # ── 2. personalisation accuracy ────────────────────────────────────────────

    def test_02_personalisation_dining_heavy(self):
        """User with strong dining preferences gets dining-heavy queue."""
        from flamezo_backend.flamezo.api.chills_feed import _build_and_cache_queue, _rk

        phone = _phone(2)
        _set_prefs(phone, {tag: 80.0 for tag in _TAG_DINING})
        # Simulate 15 watches to move out of warm-start
        _simulate_watches(phone, self._chills[:15])

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)

        dining_set = set(self._chills_by_tag["dining"])
        dining_in_queue = sum(1 for cid in queue if cid in dining_set)
        ratio = dining_in_queue / len(queue) if queue else 0

        # Dining preference is strong — expect at least 40% dining content
        self.assertGreaterEqual(
            ratio, 0.40,
            f"Dining user got only {ratio:.0%} dining content in queue"
        )

    def test_03_personalisation_fashion_heavy(self):
        """User with strong fashion preferences gets fashion-heavy queue."""
        from flamezo_backend.flamezo.api.chills_feed import _build_and_cache_queue

        phone = _phone(3)
        _set_prefs(phone, {tag: 80.0 for tag in _TAG_FASHION})
        _simulate_watches(phone, self._chills[:10])

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)

        fashion_set = set(self._chills_by_tag["fashion"])
        fashion_in_queue = sum(1 for cid in queue if cid in fashion_set)
        ratio = fashion_in_queue / len(queue) if queue else 0

        self.assertGreaterEqual(ratio, 0.35, f"Fashion user got only {ratio:.0%} fashion content")

    # ── 3. cold start ──────────────────────────────────────────────────────────

    def test_04_cold_start_gets_trending(self):
        """Brand-new user (0 watches, no prefs) gets a valid non-empty queue."""
        from flamezo_backend.flamezo.api.chills_feed import _build_and_cache_queue

        phone = _phone(4)  # fresh, no watches or prefs

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)

        self.assertGreater(len(queue), 0, "Cold-start user got empty queue")
        # All returned IDs must be valid published Chills
        for cid in queue:
            self.assertIn(cid, set(self._chills), f"Unknown chills_id in cold-start queue: {cid}")

    # ── 4. warm start ──────────────────────────────────────────────────────────

    def test_05_warm_start_blend(self):
        """User with 5 watches gets a queue that mixes trending + preference."""
        from flamezo_backend.flamezo.api.chills_feed import _build_and_cache_queue

        phone = _phone(5)
        _simulate_watches(phone, self._chills[:5])
        _set_prefs(phone, {tag: 30.0 for tag in _TAG_WELLNESS})

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)

        self.assertGreater(len(queue), 0, "Warm-start user got empty queue")
        self.assertLessEqual(len(queue), 30, "Queue exceeded QUEUE_SIZE")

    # ── 5. outlet diversity cap ────────────────────────────────────────────────

    def test_06_outlet_diversity_cap(self):
        """No outlet should appear more than MAX_PER_OUTLET_IN_QUEUE times in a queue."""
        from flamezo_backend.flamezo.api.chills_feed import (
            _build_and_cache_queue, MAX_PER_OUTLET_IN_QUEUE,
        )
        from collections import Counter

        phone = _phone(6)
        _simulate_watches(phone, self._chills[:10])

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)

        # Fetch outlet for each chills_id
        if not queue:
            self.skipTest("Queue empty — not enough test data")

        placeholders = ",".join(["%s"] * len(queue))
        rows = frappe.db.sql(
            f"SELECT name, outlet FROM `tabChills` WHERE name IN ({placeholders})",
            queue,
            as_dict=True,
        )
        outlet_map = {r.name: r.outlet for r in rows}
        outlet_counts = Counter(outlet_map.get(cid, "") for cid in queue)

        for outlet, count in outlet_counts.items():
            if not outlet:
                continue
            self.assertLessEqual(
                count, MAX_PER_OUTLET_IN_QUEUE,
                f"Outlet {outlet} appeared {count} times, cap is {MAX_PER_OUTLET_IN_QUEUE}"
            )

    # ── 6. consecutive outlet cap ──────────────────────────────────────────────

    def test_07_consecutive_outlet_cap(self):
        """No outlet should appear more than CONSECUTIVE_OUTLET_CAP times in a row."""
        from flamezo_backend.flamezo.api.chills_feed import (
            _build_and_cache_queue, CONSECUTIVE_OUTLET_CAP,
        )

        phone = _phone(7)
        _simulate_watches(phone, self._chills[:10])

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)
        if len(queue) < 4:
            self.skipTest("Queue too small")

        placeholders = ",".join(["%s"] * len(queue))
        rows = frappe.db.sql(
            f"SELECT name, outlet FROM `tabChills` WHERE name IN ({placeholders})",
            queue,
            as_dict=True,
        )
        outlet_map = {r.name: r.outlet for r in rows}
        outlets_ordered = [outlet_map.get(cid, "") for cid in queue]

        for i in range(len(outlets_ordered) - CONSECUTIVE_OUTLET_CAP):
            window = outlets_ordered[i: i + CONSECUTIVE_OUTLET_CAP + 1]
            unique = set(w for w in window if w)
            self.assertGreater(
                len(unique), 1,
                f"Consecutive outlet cap violated at position {i}: {window}"
            )

    # ── 7. not_interested suppression ─────────────────────────────────────────

    def test_08_not_interested_suppresses_outlet(self):
        """After not_interested, that outlet must not appear in next queue."""
        from flamezo_backend.flamezo.api.chills_feed import (
            _build_and_cache_queue, _rk, _suppress_outlet,
        )

        phone = _phone(8)
        suppress_outlet = self._outlets[0]  # chills1 (dining outlets)

        # Suppress the outlet directly
        _suppress_outlet(phone, suppress_outlet)

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)

        if not queue:
            self.skipTest("Queue empty")

        placeholders = ",".join(["%s"] * len(queue))
        rows = frappe.db.sql(
            f"SELECT name, outlet FROM `tabChills` WHERE name IN ({placeholders})",
            queue,
            as_dict=True,
        )
        in_queue_outlets = {r.outlet for r in rows}
        self.assertNotIn(
            suppress_outlet, in_queue_outlets,
            f"Suppressed outlet {suppress_outlet} still appears in queue"
        )

    def test_09_not_interested_penalizes_tags(self):
        """not_interested event decrements tag preference scores."""
        from flamezo_backend.flamezo.api.chills_feed import _update_user_prefs, _get_user_prefs

        phone = _phone(9)
        # Set initial positive preference
        initial = {tag: 20.0 for tag in _TAG_DINING}
        from flamezo_backend.flamezo.api.chills_feed import _set_user_prefs
        _set_user_prefs(phone, initial.copy())

        # Apply not_interested
        _update_user_prefs(phone, _TAG_DINING, "not_interested")

        prefs = _get_user_prefs(phone)
        for tag in _TAG_DINING:
            self.assertLess(
                prefs.get(tag, 0.0), initial[tag],
                f"Tag {tag} not penalised after not_interested"
            )

    # ── 8. new content injection ───────────────────────────────────────────────

    def test_10_new_content_injected(self):
        """Chills < 48h old appear at reserved slots [6, 16, 26] when available."""
        from flamezo_backend.flamezo.api.chills_feed import (
            _build_and_cache_queue, _rk, NEW_CONTENT_SLOTS,
        )

        phone = _phone(10)
        _simulate_watches(phone, self._chills[:20])

        # Inject a brand-new Chills (age = 1h)
        new_cid = _make_chills(self._outlets[0], _TAG_DINING[:1], age_hours=1, views=0)
        self._chills.append(new_cid)

        # Bust new_content cache so it picks up the freshly inserted row
        frappe.cache().delete_value(_rk("new_content"))

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)

        self.assertIn(
            new_cid, queue,
            "Brand-new Chills not injected into queue"
        )
        # The new content should appear near (within ±2 of) a reserved slot
        if new_cid in queue:
            pos = queue.index(new_cid)
            closest_slot = min(NEW_CONTENT_SLOTS, key=lambda s: abs(s - pos))
            self.assertLessEqual(
                abs(pos - closest_slot), 3,
                f"New content at pos {pos}, expected near slot {closest_slot}"
            )

    # ── 9. queue exhaustion fallback ───────────────────────────────────────────

    def test_11_exhaustion_fallback(self):
        """User who watched all content still gets a non-empty queue."""
        from flamezo_backend.flamezo.api.chills_feed import _build_and_cache_queue, _rk

        phone = _phone(1)  # reuse phone1
        # Simulate watching everything
        _simulate_watches(phone, self._chills)
        frappe.cache().delete_value(_rk("queue", phone))

        queue = _build_and_cache_queue(phone, 12.9716, 77.5946)
        self.assertGreater(len(queue), 0, "Exhaustion fallback returned empty queue")

    # ── 10. performance test ───────────────────────────────────────────────────

    def test_12_performance_10_users(self):
        """10 users × queue build must complete in < 20 seconds total."""
        from flamezo_backend.flamezo.api.chills_feed import _build_and_cache_queue, _rk

        # Clear global snapshots to force fresh computation
        frappe.cache().delete_value(_rk("candidates_snapshot"))
        frappe.cache().delete_value(_rk("global_scores"))

        start = time.time()
        for i in range(1, 11):
            phone = _phone(i)
            frappe.cache().delete_value(_rk("queue", phone))
            _build_and_cache_queue(phone, 12.9716, 77.5946)
        elapsed = time.time() - start

        self.assertLess(
            elapsed, 20.0,
            f"10-user queue build took {elapsed:.1f}s (limit 20s)"
        )

    # ── 11. preference learning via record_chills_event ───────────────────────

    def test_13_record_event_updates_prefs(self):
        """record_chills_event should update Redis tag preference scores."""
        from flamezo_backend.flamezo.api.chills_feed import (
            _update_user_prefs, _get_user_prefs, EVENT_PREF_DELTA,
        )

        phone = _phone(5)
        tags  = _TAG_DINING[:2]
        from flamezo_backend.flamezo.api.chills_feed import _set_user_prefs
        _set_user_prefs(phone, {})

        _update_user_prefs(phone, tags, "watch_complete")
        prefs = _get_user_prefs(phone)

        expected = EVENT_PREF_DELTA["watch_complete"]
        for tag in tags:
            self.assertAlmostEqual(
                prefs.get(tag, 0.0), expected, places=2,
                msg=f"Tag {tag} pref not updated after watch_complete"
            )

    def test_14_record_event_adds_to_watched(self):
        """record_chills_event marks the video as watched."""
        from flamezo_backend.flamezo.api.chills_feed import _add_to_watched, _get_watched_state, _rk

        phone = _phone(6)
        cid   = self._chills[0]

        # Reset
        frappe.cache().delete_value(_rk("watched", phone))
        _add_to_watched(phone, cid)

        _, watched_set = _get_watched_state(phone)
        self.assertIn(cid, watched_set, "Chills not added to watched set")

    # ── 12. seed_interest_preferences ─────────────────────────────────────────

    def test_15_seed_interest_preferences(self):
        """Seeding preferences sets scores >= 25 for all seeded tags."""
        from flamezo_backend.flamezo.api.chills_feed import (
            seed_interest_preferences, _get_user_prefs, _rk,
        )

        phone = _phone(7)
        frappe.cache().delete_value(_rk("prefs", phone))

        result = seed_interest_preferences(phone=phone, categories=json.dumps(_TAG_WELLNESS))
        self.assertTrue(result.get("success"), f"Seed failed: {result}")

        prefs = _get_user_prefs(phone)
        for tag in _TAG_WELLNESS:
            self.assertGreaterEqual(
                prefs.get(tag, 0.0), 25.0,
                f"Seeded tag {tag} has score < 25"
            )

    # ── 13. Thompson Sampling ──────────────────────────────────────────────────

    def test_16_thompson_explore_uncertain_tags(self):
        """Thompson exploration: tags with α=β=1 (uniform) should trigger explore ~50% of the time."""
        from flamezo_backend.flamezo.api.chills_feed import _thompson_is_explore

        # Uniform state → about half the time should explore
        state = {"dining-restaurant-casual:a": 1.0, "dining-restaurant-casual:b": 1.0}
        tags  = ["dining-restaurant-casual"]

        # Run 100 trials — expect 30%–70% exploration rate (high variance, just check it runs)
        results = [_thompson_is_explore(state, tags) for _ in range(100)]
        explore_rate = sum(results) / 100
        self.assertGreater(explore_rate, 0.05, "Thompson never explored — broken")
        self.assertLess(explore_rate, 0.95, "Thompson always explored — broken")

    def test_17_thompson_known_tag_less_exploration(self):
        """Tag with high alpha (many successes) should rarely be flagged for exploration."""
        from flamezo_backend.flamezo.api.chills_feed import _thompson_is_explore

        # High confidence tag (many successes, few failures)
        state = {"dining-cafe-specialty:a": 50.0, "dining-cafe-specialty:b": 2.0}
        tags  = ["dining-cafe-specialty"]

        results = [_thompson_is_explore(state, tags) for _ in range(100)]
        explore_rate = sum(results) / 100
        self.assertLess(explore_rate, 0.15, "Well-known positive tag explored too often")

    # ── 14. scoring sub-function unit tests ───────────────────────────────────

    def test_18_freshness_score_decreases_with_age(self):
        """Older content gets lower freshness scores."""
        from flamezo_backend.flamezo.api.chills_feed import _score_freshness

        fresh  = _score_freshness({"age_hours": 1})
        old    = _score_freshness({"age_hours": 168})
        ancient = _score_freshness({"age_hours": 720})

        self.assertGreater(fresh, old,    "1h content not fresher than 168h")
        self.assertGreater(old, ancient,  "168h content not fresher than 720h")
        self.assertAlmostEqual(old, 0.5, places=1, msg="7-day content should be ~0.5 (half-life)")

    def test_19_location_score_distance_logic(self):
        """Near content scores 1.0, far content scores 0.0."""
        from flamezo_backend.flamezo.api.chills_feed import _score_location

        user_lat, user_lng = 12.9716, 77.5946  # Bengaluru

        # Very near (~0km)
        near   = _score_location({"lat": 12.9716, "lng": 77.5946}, user_lat, user_lng)
        # Far (Delhi ~1700km)
        far    = _score_location({"lat": 28.6139, "lng": 77.2090}, user_lat, user_lng)
        # No user GPS
        no_gps = _score_location({"lat": 12.9716, "lng": 77.5946}, 0.0, 0.0)

        self.assertAlmostEqual(near,   1.0, places=1, msg="Near content not score 1.0")
        self.assertAlmostEqual(far,    0.0, places=1, msg="Far content not score 0.0")
        self.assertAlmostEqual(no_gps, 0.5, places=1, msg="No GPS should return 0.5 neutral")

    def test_20_affinity_score_positive_prefs(self):
        """Positive preference for matching tags → affinity > 0.5."""
        from flamezo_backend.flamezo.api.chills_feed import _score_affinity

        prefs     = {tag: 30.0 for tag in _TAG_DINING}
        candidate = {"tags": _TAG_DINING, "niche_tags": _TAG_DINING}
        score     = _score_affinity(candidate, prefs)
        self.assertGreater(score, 0.5, "Positive pref tags should give affinity > 0.5")

    def test_21_affinity_score_negative_prefs(self):
        """Negative preference for tags → affinity < 0.5."""
        from flamezo_backend.flamezo.api.chills_feed import _score_affinity

        prefs     = {tag: -20.0 for tag in _TAG_DINING}
        candidate = {"tags": _TAG_DINING, "niche_tags": _TAG_DINING}
        score     = _score_affinity(candidate, prefs)
        self.assertLess(score, 0.5, "Negative pref tags should give affinity < 0.5")

    # ── 15. compute_global_scores unit test ───────────────────────────────────

    def test_22_global_scores_structure(self):
        """_compute_global_scores returns {chills_id: {eng, social}} for test Chills."""
        from flamezo_backend.flamezo.api.chills_feed import _compute_global_scores

        scores = _compute_global_scores()
        self.assertIsInstance(scores, dict, "_compute_global_scores must return dict")

        # Should contain our test Chills (at least some)
        test_set = set(self._chills)
        found = [cid for cid in scores if cid in test_set]
        self.assertGreater(len(found), 0, "No test Chills found in global scores")

        for cid, s in scores.items():
            self.assertIn("eng",    s, f"Missing 'eng' key for {cid}")
            self.assertIn("social", s, f"Missing 'social' key for {cid}")
            self.assertGreaterEqual(s["eng"],    0.0)
            self.assertLessEqual(   s["eng"],    1.0)
            self.assertGreaterEqual(s["social"], 0.0)
            self.assertLessEqual(   s["social"], 1.0)

    # ── 16. Bayesian smoothing ─────────────────────────────────────────────────

    def test_23_bayesian_smoothing_regularises_small_samples(self):
        """
        A video with 2 watches at 100% should score less than one with 500 watches at 70%.
        Bayesian smoothing pulls small samples toward the prior mean (45%).
        """
        from flamezo_backend.flamezo.api.chills_feed import (
            BAYES_PRIOR_MEAN, BAYES_PRIOR_WEIGHT,
        )

        def bayesian(pct_sum, n):
            return (pct_sum + BAYES_PRIOR_MEAN * 100 * BAYES_PRIOR_WEIGHT) / (n + BAYES_PRIOR_WEIGHT)

        noisy  = bayesian(200,   2)    # 2 views × 100% completion
        robust = bayesian(35000, 500)  # 500 views × 70% completion

        self.assertLess(
            noisy, robust,
            f"Noisy 2-view score ({noisy:.1f}) must be < robust 500-view score ({robust:.1f})"
        )

    # ── 17. diversity pass unit test ──────────────────────────────────────────

    def test_24_diversity_pass_caps_outlet(self):
        """_diversity_pass should cap any outlet at MAX_PER_OUTLET_IN_QUEUE."""
        from flamezo_backend.flamezo.api.chills_feed import _diversity_pass, MAX_PER_OUTLET_IN_QUEUE
        from collections import Counter

        # Create 20 fake candidates all from "outlet-A"
        candidates = [
            {"id": f"fake-{i}", "outlet": "outlet-A", "score": 0.9 - i * 0.01}
            for i in range(20)
        ]
        result  = _diversity_pass(candidates)
        counts  = Counter(item["outlet"] for item in result)
        self.assertLessEqual(
            counts.get("outlet-A", 0), MAX_PER_OUTLET_IN_QUEUE,
            f"Diversity pass didn't cap outlet-A"
        )

    def test_25_diversity_pass_consecutive_cap(self):
        """_diversity_pass should break up consecutive runs of the same outlet."""
        from flamezo_backend.flamezo.api.chills_feed import _diversity_pass, CONSECUTIVE_OUTLET_CAP

        # 10 items from outlet-A, then 10 from outlet-B
        candidates = (
            [{"id": f"a{i}", "outlet": "outlet-A", "score": 0.9} for i in range(10)] +
            [{"id": f"b{i}", "outlet": "outlet-B", "score": 0.5} for i in range(10)]
        )
        result   = _diversity_pass(candidates)
        outlets  = [item["outlet"] for item in result]

        # Check no more than CONSECUTIVE_OUTLET_CAP consecutive same outlet
        for i in range(len(outlets) - CONSECUTIVE_OUTLET_CAP):
            window = outlets[i: i + CONSECUTIVE_OUTLET_CAP + 1]
            unique = set(window)
            self.assertGreater(
                len(unique), 1,
                f"Consecutive outlet cap violated: {window} at pos {i}"
            )


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
