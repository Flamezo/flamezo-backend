"""
Tests for the 20/10 Recommendation Engine.

Tests cover:
1. RecommendationEngine scoring logic (unit)
2. Co-order matrix computation (unit)
3. Embedding cache logic (unit, mocked OpenAI)
4. Reason generation (unit)
5. API endpoint behavior (integration-style, using frappe test infrastructure)
6. Co-order event logging (unit, mocked frappe)
7. Diversity selection (unit)
8. Dietary penalty logic
"""

import hashlib
import json
import math
import sys
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_dish(
    id="d1",
    name="Butter Chicken",
    category="Curries",
    main_category="food",
    price=250,
    is_vegetarian=False,
    description="Rich creamy tomato curry",
    original_price=None,
):
    d = {
        "id": id,
        "name": name,
        "category": category,
        "mainCategory": main_category,
        "price": price,
        "isVegetarian": is_vegetarian,
        "description": description,
    }
    if original_price is not None:
        d["originalPrice"] = original_price
    return d


SAMPLE_DISHES = [
    make_dish("d1", "Butter Chicken", "Curries", "food", 250, False),
    make_dish("d2", "Dal Makhani", "Dal", "food", 180, True),
    make_dish("d3", "Garlic Naan", "Breads", "food", 60, True),
    make_dish("d4", "Mango Lassi", "Drinks", "beverage", 80, True),
    make_dish("d5", "Gulab Jamun", "Desserts", "dessert", 90, True),
    make_dish("d6", "Paneer Tikka", "Starters", "food", 200, True),
    make_dish("d7", "Chicken Biryani", "Rice", "food", 280, False),
    make_dish("d8", "Jeera Rice", "Rice", "food", 120, True),
    make_dish("d9", "Coke", "Drinks", "beverage", 40, True),
    make_dish("d10", "Raita", "Accompaniments", "food", 60, True),
]


def _make_mock_frappe():
    mock_frappe = MagicMock()
    mock_frappe.db = MagicMock()
    mock_frappe.get_all = MagicMock(return_value=[])
    mock_frappe.get_doc = MagicMock()
    return mock_frappe


def _get_engine(mock_frappe=None):
    """Return a RecommendationEngine with mocked dependencies."""
    if mock_frappe is None:
        mock_frappe = _make_mock_frappe()
    # Purge any cached module so we start clean
    for key in list(sys.modules.keys()):
        if "dinematters" in key and "recommendations" in key:
            del sys.modules[key]

    with patch.dict("sys.modules", {"frappe": mock_frappe}):
        with patch("dinematters.dinematters.services.ai.base.get_openai_client"):
            from dinematters.dinematters.services.ai.recommendations import RecommendationEngine
            engine = RecommendationEngine.__new__(RecommendationEngine)
            engine.embedding_model = "text-embedding-3-small"
            engine.client = MagicMock()
            return engine, mock_frappe


# ---------------------------------------------------------------------------
# Unit tests for cosine similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity(unittest.TestCase):

    def setUp(self):
        self.engine, _ = _get_engine()

    def test_identical_vectors_is_one(self):
        v = [0.1, 0.2, 0.3, 0.4]
        self.assertAlmostEqual(self.engine._cosine(v, v), 1.0, places=5)

    def test_orthogonal_vectors_is_zero(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(self.engine._cosine(a, b), 0.0, places=5)

    def test_empty_vector_returns_zero(self):
        self.assertEqual(self.engine._cosine([], [1.0]), 0.0)
        self.assertEqual(self.engine._cosine([1.0], []), 0.0)
        self.assertEqual(self.engine._cosine([], []), 0.0)

    def test_opposite_vectors_is_negative_one(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        self.assertAlmostEqual(self.engine._cosine(a, b), -1.0, places=5)

    def test_result_between_negative_one_and_one(self):
        import random
        rng = random.Random(42)
        for _ in range(10):
            a = [rng.gauss(0, 1) for _ in range(8)]
            b = [rng.gauss(0, 1) for _ in range(8)]
            result = self.engine._cosine(a, b)
            self.assertGreaterEqual(result, -1.0001)
            self.assertLessEqual(result, 1.0001)


# ---------------------------------------------------------------------------
# Unit tests for _score_pair
# ---------------------------------------------------------------------------

class TestScorePair(unittest.TestCase):

    def setUp(self):
        self.engine, _ = _get_engine()

    def test_dietary_penalty_veg_recommending_nonveg(self):
        """Veg base dish recommending non-veg should get -0.2 penalty."""
        veg_dish = make_dish("v1", is_vegetarian=True, price=100)
        non_veg_dish = make_dish("n1", is_vegetarian=False, price=100)
        # Pure sim component: 0.45 * 0.9 = 0.405, penalty = -0.2
        score = self.engine._score_pair(veg_dish, non_veg_dish, similarity=0.9, co_order_freq=0.0)
        self.assertLess(score, 0.405)

    def test_no_penalty_nonveg_to_veg(self):
        """Non-veg base recommending veg should NOT get dietary penalty."""
        non_veg_base = make_dish("n1", is_vegetarian=False, price=100)
        veg_cand = make_dish("v1", is_vegetarian=True, price=100)
        score = self.engine._score_pair(non_veg_base, veg_cand, similarity=0.5, co_order_freq=0.0)
        # No penalty, pure sim floor is 0.45*0.5 = 0.225
        self.assertGreater(score, 0.22)

    def test_co_order_boost_increases_score(self):
        """Higher co_order_freq should increase score linearly."""
        base = make_dish("d1", price=100)
        cand = make_dish("d2", price=100)
        score_no_co = self.engine._score_pair(base, cand, similarity=0.5, co_order_freq=0.0)
        score_with_co = self.engine._score_pair(base, cand, similarity=0.5, co_order_freq=0.8)
        self.assertGreater(score_with_co, score_no_co)
        # co_order contribution: 0.30 * 0.8 = 0.24
        self.assertAlmostEqual(score_with_co - score_no_co, 0.30 * 0.8, places=3)

    def test_beverage_cross_category_bonus(self):
        """Beverage recommended to food dish should score higher than food-to-food."""
        food_dish = make_dish("f1", main_category="food", category="Curries")
        bev_dish = make_dish("b1", main_category="beverage", category="Drinks")
        other_food = make_dish("f2", main_category="food", category="Rice")
        score_bev = self.engine._score_pair(food_dish, bev_dish, similarity=0.5, co_order_freq=0.0)
        score_food = self.engine._score_pair(food_dish, other_food, similarity=0.5, co_order_freq=0.0)
        self.assertGreater(score_bev, score_food)

    def test_offer_bonus(self):
        """Dish on offer (originalPrice > price) should score higher by exactly 0.05."""
        base = make_dish("d1", price=200)
        offer_dish = make_dish("d2", original_price=300, price=200)
        no_offer_dish = make_dish("d3", price=200)  # same price, no offer
        score_offer = self.engine._score_pair(base, offer_dish, similarity=0.5, co_order_freq=0.0)
        score_no_offer = self.engine._score_pair(base, no_offer_dish, similarity=0.5, co_order_freq=0.0)
        self.assertGreater(score_offer, score_no_offer)
        self.assertAlmostEqual(score_offer - score_no_offer, 0.05, places=3)

    def test_score_is_float(self):
        base = make_dish("d1")
        cand = make_dish("d2")
        score = self.engine._score_pair(base, cand, similarity=0.7, co_order_freq=0.3)
        self.assertIsInstance(score, float)

    def test_zero_similarity_zero_coorder_low_score(self):
        """With no semantic or co-order signal, score should be very low."""
        base = make_dish("d1", price=100)
        cand = make_dish("d2", price=100)
        score = self.engine._score_pair(base, cand, similarity=0.0, co_order_freq=0.0)
        # Only price_norm (≈1.0 × 0.10) + category_bonus (0.15) at most
        self.assertLess(score, 0.4)

    def test_dessert_bonus(self):
        """Dessert recommended from food base should get dessert bonus."""
        food = make_dish("f1", main_category="food", category="Curries")
        dessert = make_dish("ds1", main_category="dessert", category="Desserts")
        score_dessert = self.engine._score_pair(food, dessert, similarity=0.5, co_order_freq=0.0)
        # dessert_bonus=0.08 on top of plain food→food
        food2 = make_dish("f2", main_category="food", category="Rice")
        score_food = self.engine._score_pair(food, food2, similarity=0.5, co_order_freq=0.0)
        self.assertGreater(score_dessert, score_food)


# ---------------------------------------------------------------------------
# Unit tests for _build_reason
# ---------------------------------------------------------------------------

class TestBuildReason(unittest.TestCase):

    def setUp(self):
        self.engine, _ = _get_engine()

    def test_high_co_order_returns_percentage_reason(self):
        """co_order_freq >= 0.5 should return percentage-based reason."""
        base = make_dish("d1")
        cand = make_dish("d2")
        reason = self.engine._build_reason(base, cand, {}, similarity=0.5, co_order_freq=0.8)
        self.assertIn("customers order these together", reason)
        self.assertIn("%", reason)

    def test_percentage_calculation_at_0_5_freq(self):
        """At freq=0.5 the percentage should be 75%."""
        base = make_dish("d1")
        cand = make_dish("d2")
        reason = self.engine._build_reason(base, cand, {}, similarity=0.5, co_order_freq=0.5)
        self.assertIn("75%", reason)

    def test_percentage_calculation_at_1_0_freq(self):
        """At freq=1.0 the percentage should be 100%."""
        base = make_dish("d1")
        cand = make_dish("d2")
        reason = self.engine._build_reason(base, cand, {}, similarity=0.5, co_order_freq=1.0)
        self.assertIn("100%", reason)

    def test_medium_co_order_returns_frequently_ordered(self):
        """0.25 <= co_order_freq < 0.5 should return 'Frequently ordered together'."""
        base = make_dish("d1")
        cand = make_dish("d2")
        reason = self.engine._build_reason(base, cand, {}, similarity=0.5, co_order_freq=0.3)
        self.assertEqual(reason, "Frequently ordered together")

    def test_offer_savings_reason(self):
        """Offer savings should be surfaced when co-order freq is low."""
        base = make_dish("d1")
        cand = make_dish("d2", original_price=300, price=200)
        reason = self.engine._build_reason(base, cand, {}, similarity=0.3, co_order_freq=0.0)
        self.assertIn("Save ₹100", reason)

    def test_fallback_reason_is_nonempty_string(self):
        """Zero co-order + no offer should still return a non-empty string."""
        base = make_dish("d1")
        cand = make_dish("d2")
        reason = self.engine._build_reason(base, cand, {}, similarity=0.5, co_order_freq=0.0)
        self.assertIsInstance(reason, str)
        self.assertGreater(len(reason), 0)

    def test_high_similarity_reason_contains_similar_profile(self):
        """similarity >= 0.8 should surface 'Similar profile'."""
        base = make_dish("d1", main_category="food")
        cand = make_dish("d2", main_category="food")
        reason = self.engine._build_reason(base, cand, {}, similarity=0.85, co_order_freq=0.0)
        self.assertIn("Similar profile", reason)

    def test_offer_co_order_takes_priority_over_savings(self):
        """High co-order should override offer savings in reason."""
        base = make_dish("d1")
        cand = make_dish("d2", original_price=500, price=100)
        reason = self.engine._build_reason(base, cand, {}, similarity=0.5, co_order_freq=0.9)
        self.assertIn("customers order these together", reason)
        self.assertNotIn("Save", reason)


# ---------------------------------------------------------------------------
# Unit tests for _dish_to_text
# ---------------------------------------------------------------------------

class TestDishToText(unittest.TestCase):

    def setUp(self):
        self.engine, _ = _get_engine()

    def test_contains_name(self):
        dish = make_dish("d1", name="Paneer Butter Masala")
        self.assertIn("Paneer Butter Masala", self.engine._dish_to_text(dish))

    def test_contains_category(self):
        dish = make_dish("d1", category="Curries")
        self.assertIn("Curries", self.engine._dish_to_text(dish))

    def test_contains_veg_status(self):
        veg = make_dish("d1", is_vegetarian=True)
        non_veg = make_dish("d2", is_vegetarian=False)
        self.assertIn("vegetarian", self.engine._dish_to_text(veg))
        self.assertIn("non-vegetarian", self.engine._dish_to_text(non_veg))

    def test_contains_price(self):
        dish = make_dish("d1", price=220)
        self.assertIn("220", self.engine._dish_to_text(dish))

    def test_hash_changes_with_description(self):
        dish1 = make_dish("d1", description="Original description")
        dish2 = make_dish("d1", description="Updated description")
        h1 = hashlib.md5(self.engine._dish_to_text(dish1).encode()).hexdigest()
        h2 = hashlib.md5(self.engine._dish_to_text(dish2).encode()).hexdigest()
        self.assertNotEqual(h1, h2)

    def test_hash_stable_for_same_content(self):
        dish = make_dish("d1")
        h1 = hashlib.md5(self.engine._dish_to_text(dish).encode()).hexdigest()
        h2 = hashlib.md5(self.engine._dish_to_text(dish).encode()).hexdigest()
        self.assertEqual(h1, h2)

    def test_hash_changes_with_name(self):
        dish1 = make_dish("d1", name="Dish A")
        dish2 = make_dish("d1", name="Dish B")
        h1 = hashlib.md5(self.engine._dish_to_text(dish1).encode()).hexdigest()
        h2 = hashlib.md5(self.engine._dish_to_text(dish2).encode()).hexdigest()
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# Unit tests for diversity selection
# ---------------------------------------------------------------------------

class TestDiversitySelection(unittest.TestCase):

    def setUp(self):
        self.engine, _ = _get_engine()

    def _make_candidates(self, dishes):
        """Create fake candidates list: (score, dish, sim, co_freq)."""
        return [(0.8 - i * 0.01, d, 0.8 - i * 0.01, 0.0) for i, d in enumerate(dishes)]

    def test_no_duplicates_in_selection(self):
        """Selected items must have unique IDs."""
        base = make_dish("base")
        dishes = [make_dish(f"d{i}", main_category=f"cat{i % 3}") for i in range(20)]
        candidates = self._make_candidates(dishes)
        selected = self.engine._select_diverse_candidates(base, candidates, 8, [], {})
        ids = [d.get("id") for _, d, _, _ in selected]
        self.assertEqual(len(ids), len(set(ids)))

    def test_returns_correct_count_when_enough_dishes(self):
        """Should return min_recommendations items when enough diverse dishes exist."""
        base = make_dish("base", main_category="food")
        diverse = [
            make_dish(f"d{i}", main_category=["food", "beverage", "dessert", "snack"][i % 4])
            for i in range(24)
        ]
        candidates = self._make_candidates(diverse)
        selected = self.engine._select_diverse_candidates(base, candidates, 8, [], {})
        self.assertEqual(len(selected), 8)

    def test_same_category_capped(self):
        """Same-category dishes should be capped at ~30% of recommendations."""
        base = make_dish("base", main_category="food")
        same_cat = [make_dish(f"s{i}", main_category="food") for i in range(20)]
        candidates = self._make_candidates(same_cat)
        selected = self.engine._select_diverse_candidates(base, candidates, 9, [], {})
        food_count = sum(1 for _, d, _, _ in selected if d.get("mainCategory") == "food")
        # 30% of 9 = 2.7, so max 3
        self.assertLessEqual(food_count, 3)

    def test_empty_candidates_returns_empty(self):
        base = make_dish("base")
        selected = self.engine._select_diverse_candidates(base, [], 5, [], {})
        self.assertEqual(selected, [])

    def test_fewer_dishes_than_requested(self):
        """Should return what's available without error."""
        base = make_dish("base", main_category="food")
        dishes = [make_dish("d1", main_category="beverage"), make_dish("d2", main_category="dessert")]
        candidates = self._make_candidates(dishes)
        selected = self.engine._select_diverse_candidates(base, candidates, 9, [], {})
        self.assertLessEqual(len(selected), 9)


# ---------------------------------------------------------------------------
# Unit tests for co-order matrix computation
# ---------------------------------------------------------------------------

class TestCoOrderMatrix(unittest.TestCase):

    def setUp(self):
        self.mock_frappe = _make_mock_frappe()
        mock_frappe_utils = MagicMock()
        mock_frappe_utils.now.return_value = "2026-01-01 00:00:00"
        self.patcher = patch.dict("sys.modules", {
            "frappe": self.mock_frappe,
            "frappe.utils": mock_frappe_utils,
        })
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        for key in list(sys.modules.keys()):
            if "recommendation_tasks" in key:
                del sys.modules[key]

    def _import(self):
        from dinematters.dinematters.tasks.recommendation_tasks import _compute_co_order_matrix
        return _compute_co_order_matrix

    def test_empty_rows_returns_empty_dict(self):
        self.mock_frappe.db.sql.return_value = []
        fn = self._import()
        self.assertEqual(fn("REST-001"), {})

    def test_values_in_zero_to_one_range(self):
        rows = [
            MagicMock(product_a_id="d1", product_b_id="d2", cnt=100),
            MagicMock(product_a_id="d1", product_b_id="d3", cnt=10),
            MagicMock(product_a_id="d2", product_b_id="d3", cnt=50),
        ]
        self.mock_frappe.db.sql.return_value = rows
        fn = self._import()
        result = fn("REST-001")
        for v in result.values():
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_keys_are_tuples(self):
        rows = [MagicMock(product_a_id="d1", product_b_id="d2", cnt=5)]
        self.mock_frappe.db.sql.return_value = rows
        fn = self._import()
        result = fn("REST-001")
        self.assertIn(("d1", "d2"), result)

    def test_higher_count_yields_higher_score(self):
        # Use many rows so p95 is set by the high-count outlier rather than the minimum.
        # With 20 rows, p95_idx = max(0, int(20*0.95)-1) = 18, p95 = sorted[18].
        # Make most rows have cnt=50 so p95=50; pair (a,b) has cnt=50 (score=1.0)
        # and pair (c,d) has cnt=1 (score = log(2)/log(51) < 1.0).
        rows = [MagicMock(product_a_id=f"x{i}", product_b_id=f"y{i}", cnt=50) for i in range(19)]
        rows.append(MagicMock(product_a_id="c", product_b_id="d", cnt=1))
        # Rename one to (a,b) for clarity
        rows[0].product_a_id = "a"
        rows[0].product_b_id = "b"
        rows[0].cnt = 50
        self.mock_frappe.db.sql.return_value = rows
        fn = self._import()
        result = fn("REST-001")
        self.assertGreater(result[("a", "b")], result[("c", "d")])

    def test_single_pair_normalizes_to_one(self):
        rows = [MagicMock(product_a_id="x", product_b_id="y", cnt=42)]
        self.mock_frappe.db.sql.return_value = rows
        fn = self._import()
        result = fn("REST-001")
        self.assertAlmostEqual(result[("x", "y")], 1.0, places=3)

    def test_restaurant_param_passed_to_sql(self):
        self.mock_frappe.db.sql.return_value = []
        fn = self._import()
        fn("MY-RESTAURANT")
        call_args = self.mock_frappe.db.sql.call_args
        self.assertIn("MY-RESTAURANT", call_args[0])

    def test_many_pairs_p95_normalization(self):
        """p95 normalization: max value should be at most 1.0."""
        rows = [MagicMock(product_a_id=f"a{i}", product_b_id=f"b{i}", cnt=i + 1) for i in range(100)]
        self.mock_frappe.db.sql.return_value = rows
        fn = self._import()
        result = fn("REST-001")
        for v in result.values():
            self.assertLessEqual(v, 1.0)


# ---------------------------------------------------------------------------
# Unit tests for log_co_order_events
# ---------------------------------------------------------------------------

class TestLogCoOrderEvents(unittest.TestCase):

    def _make_order(self, status="confirmed", n_items=2):
        order = MagicMock()
        order.restaurant = "REST-001"
        order.name = "ORD-001"
        order.status = status
        items = []
        for i in range(n_items):
            item = MagicMock()
            item.product = f"PROD-{i:03d}"
            items.append(item)
        order.order_items = items
        return order

    def _run(self, order, mock_frappe=None):
        if mock_frappe is None:
            mock_frappe = _make_mock_frappe()
            mock_frappe.db.get_value.side_effect = lambda dt, name, field: f"pid_{name}"
        inserted = []
        mock_frappe.get_doc.side_effect = lambda d: MagicMock(
            insert=lambda **kw: inserted.append(dict(d))
        )
        mock_frappe_utils = MagicMock()
        mock_frappe_utils.now.return_value = "2026-01-01 00:00:00"
        for key in list(sys.modules.keys()):
            if "recommendation_tasks" in key:
                del sys.modules[key]
        with patch.dict("sys.modules", {"frappe": mock_frappe, "frappe.utils": mock_frappe_utils}):
            from dinematters.dinematters.tasks.recommendation_tasks import log_co_order_events
            log_co_order_events(order)
        co_events = [d for d in inserted if d.get("doctype") == "Co Order Event"]
        return co_events, mock_frappe

    def test_two_items_logs_one_pair(self):
        order = self._make_order(n_items=2)
        events, _ = self._run(order)
        self.assertEqual(len(events), 1)

    def test_three_items_logs_three_pairs(self):
        """C(3,2) = 3 pairs."""
        order = self._make_order(n_items=3)
        events, _ = self._run(order)
        self.assertEqual(len(events), 3)

    def test_four_items_logs_six_pairs(self):
        """C(4,2) = 6 pairs."""
        order = self._make_order(n_items=4)
        events, _ = self._run(order)
        self.assertEqual(len(events), 6)

    def test_single_item_logs_nothing(self):
        order = self._make_order(n_items=1)
        events, _ = self._run(order)
        self.assertEqual(len(events), 0)

    def test_cancelled_order_not_logged(self):
        order = self._make_order(status="cancelled", n_items=3)
        events, _ = self._run(order)
        self.assertEqual(len(events), 0)

    def test_events_have_required_fields(self):
        order = self._make_order(n_items=2)
        events, _ = self._run(order)
        for ev in events:
            self.assertEqual(ev["doctype"], "Co Order Event")
            self.assertEqual(ev["restaurant"], "REST-001")
            self.assertIn("product_a_id", ev)
            self.assertIn("product_b_id", ev)

    def test_hook_never_raises_on_db_error(self):
        """DB errors must be swallowed — hook must not block order placement."""
        mock_frappe = _make_mock_frappe()
        mock_frappe.db.get_value.side_effect = Exception("DB connection failed")
        order = self._make_order(n_items=2)
        try:
            self._run(order, mock_frappe=mock_frappe)
        except Exception as e:
            self.fail(f"log_co_order_events raised: {e}")

    def test_hook_never_raises_on_insert_error(self):
        """Insert errors per pair must also be silently swallowed."""
        mock_frappe = _make_mock_frappe()
        mock_frappe.db.get_value.side_effect = lambda dt, name, field: f"pid_{name}"
        mock_frappe.get_doc.side_effect = Exception("Insert failed")
        order = self._make_order(n_items=3)
        try:
            self._run(order, mock_frappe=mock_frappe)
        except Exception as e:
            self.fail(f"log_co_order_events raised: {e}")

    def test_pairs_are_lexically_ordered(self):
        """product_a_id should always be <= product_b_id in each logged pair."""
        order = self._make_order(n_items=3)
        events, _ = self._run(order)
        for ev in events:
            self.assertLessEqual(ev["product_a_id"], ev["product_b_id"])


# ---------------------------------------------------------------------------
# Unit tests for embedding cache
# ---------------------------------------------------------------------------

class TestEmbeddingCache(unittest.TestCase):

    def setUp(self):
        self.mock_frappe = _make_mock_frappe()
        self.patcher = patch.dict("sys.modules", {"frappe": self.mock_frappe})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        for key in list(sys.modules.keys()):
            if "recommendations" in key and "dinematters" in key:
                del sys.modules[key]

    def _get_engine(self):
        with patch("dinematters.dinematters.services.ai.base.get_openai_client"):
            from dinematters.dinematters.services.ai.recommendations import RecommendationEngine
            engine = RecommendationEngine.__new__(RecommendationEngine)
            engine.embedding_model = "text-embedding-3-small"
            engine.client = MagicMock()
            return engine

    def _make_api_response(self, vectors):
        response = MagicMock()
        response.data = [MagicMock(embedding=v) for v in vectors]
        return response

    def test_cache_hit_skips_api_call(self):
        """If text_hash matches, OpenAI must NOT be called."""
        engine = self._get_engine()
        dish = make_dish("d1")
        text = engine._dish_to_text(dish)
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cached_vec = [0.1, 0.2, 0.3]

        cache_row = MagicMock()
        cache_row.product_id = "d1"
        cache_row.text_hash = text_hash
        cache_row.embedding_vector = json.dumps(cached_vec)
        cache_row.name = "CACHE-001"

        self.mock_frappe.get_all.return_value = [cache_row]

        result = engine._build_embeddings([dish], restaurant="REST-001")
        engine.client.embeddings.create.assert_not_called()
        self.assertEqual(result["d1"], cached_vec)

    def test_cache_miss_calls_api(self):
        """No cache row → OpenAI API must be called."""
        engine = self._get_engine()
        dish = make_dish("d1")
        self.mock_frappe.get_all.return_value = []
        self.mock_frappe.db.get_value.return_value = "MenuProduct-001"
        engine.client.embeddings.create.return_value = self._make_api_response([[0.5, 0.6, 0.7]])

        result = engine._build_embeddings([dish], restaurant="REST-001")
        engine.client.embeddings.create.assert_called_once()
        self.assertEqual(result["d1"], [0.5, 0.6, 0.7])

    def test_stale_hash_calls_api(self):
        """If text_hash doesn't match (dish changed), API must be called."""
        engine = self._get_engine()
        dish = make_dish("d1", description="New description")

        cache_row = MagicMock()
        cache_row.product_id = "d1"
        cache_row.text_hash = "old_stale_hash"
        cache_row.embedding_vector = json.dumps([0.1, 0.2])
        cache_row.name = "CACHE-001"

        self.mock_frappe.get_all.return_value = [cache_row]
        self.mock_frappe.db.get_value.return_value = "MenuProduct-001"
        engine.client.embeddings.create.return_value = self._make_api_response([[0.9, 0.8, 0.7]])

        result = engine._build_embeddings([dish], restaurant="REST-001")
        engine.client.embeddings.create.assert_called_once()
        self.assertEqual(result["d1"], [0.9, 0.8, 0.7])

    def test_multiple_dishes_partial_cache_hit(self):
        """Only uncached dishes should trigger API calls."""
        engine = self._get_engine()
        dishes = [make_dish("d1"), make_dish("d2")]
        d1_text = engine._dish_to_text(dishes[0])
        d1_hash = hashlib.md5(d1_text.encode()).hexdigest()

        cache_row = MagicMock()
        cache_row.product_id = "d1"
        cache_row.text_hash = d1_hash
        cache_row.embedding_vector = json.dumps([0.1, 0.2])
        cache_row.name = "CACHE-001"

        self.mock_frappe.get_all.return_value = [cache_row]
        self.mock_frappe.db.get_value.return_value = "MenuProduct-002"
        engine.client.embeddings.create.return_value = self._make_api_response([[0.7, 0.8]])

        result = engine._build_embeddings(dishes, restaurant="REST-001")
        # API called exactly once (for d2 only)
        engine.client.embeddings.create.assert_called_once()
        self.assertEqual(result["d1"], [0.1, 0.2])
        self.assertEqual(result["d2"], [0.7, 0.8])


# ---------------------------------------------------------------------------
# Integration-style tests for generate_recommendations
# ---------------------------------------------------------------------------

class TestGenerateRecommendations(unittest.TestCase):

    def setUp(self):
        self.mock_frappe = _make_mock_frappe()
        self.patcher = patch.dict("sys.modules", {"frappe": self.mock_frappe})
        self.patcher.start()
        self.mock_frappe.get_all.return_value = []
        self.mock_frappe.db.get_value.return_value = "MockProduct"

    def tearDown(self):
        self.patcher.stop()
        for key in list(sys.modules.keys()):
            if "recommendations" in key and "dinematters" in key:
                del sys.modules[key]

    def _get_engine_with_mock_embeddings(self, dim=8):
        with patch("dinematters.dinematters.services.ai.base.get_openai_client"):
            from dinematters.dinematters.services.ai.recommendations import RecommendationEngine
            engine = RecommendationEngine.__new__(RecommendationEngine)
            engine.embedding_model = "text-embedding-3-small"
            engine.client = MagicMock()

        def mock_create(model, input):
            response = MagicMock()
            embeddings = []
            for i, _ in enumerate(input):
                emb = MagicMock()
                emb.embedding = [(i * 0.1 + j * 0.01) for j in range(dim)]
                embeddings.append(emb)
            response.data = embeddings
            return response

        engine.client.embeddings.create.side_effect = mock_create
        return engine

    def test_returns_result_for_each_dish(self):
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations(SAMPLE_DISHES[:5], min_recommendations=3)
        self.assertEqual(len(results), 5)

    def test_each_result_has_recommendations_list(self):
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations(SAMPLE_DISHES[:5], min_recommendations=3)
        for result in results:
            self.assertIn("recommendations", result)
            self.assertIsInstance(result["recommendations"], list)

    def test_source_dish_not_in_own_recommendations(self):
        """A dish must never recommend itself."""
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations(SAMPLE_DISHES, min_recommendations=5)
        for result in results:
            rec_ids = [r["id"] for r in result["recommendations"]]
            self.assertNotIn(result["id"], rec_ids)

    def test_no_duplicate_recommendations_per_dish(self):
        """Each recommendation list must have unique IDs."""
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations(SAMPLE_DISHES, min_recommendations=5)
        for result in results:
            rec_ids = [r["id"] for r in result["recommendations"]]
            self.assertEqual(len(rec_ids), len(set(rec_ids)))

    def test_empty_input_returns_empty(self):
        engine = self._get_engine_with_mock_embeddings()
        results, insufficient = engine.generate_recommendations([])
        self.assertEqual(results, [])
        self.assertEqual(insufficient, [])

    def test_recommendations_have_reason(self):
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations(SAMPLE_DISHES[:5], min_recommendations=3)
        for result in results:
            for rec in result["recommendations"]:
                self.assertIn("reason", rec)
                self.assertIsInstance(rec["reason"], str)
                self.assertGreater(len(rec["reason"]), 0)

    def test_recommendations_have_score(self):
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations(SAMPLE_DISHES[:5], min_recommendations=3)
        for result in results:
            for rec in result["recommendations"]:
                self.assertIn("score", rec)
                self.assertGreaterEqual(rec["score"], 0)

    def test_recommendations_have_id_field(self):
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations(SAMPLE_DISHES[:5], min_recommendations=3)
        for result in results:
            for rec in result["recommendations"]:
                self.assertIn("id", rec)
                self.assertIsNotNone(rec["id"])

    def test_co_order_boosts_rank(self):
        """A high co-order pair should be scored higher than no-signal pair."""
        engine = self._get_engine_with_mock_embeddings()
        # Use all SAMPLE_DISHES so diversity selection has plenty of categories to fill
        # and d2 has a strong co-order signal with d1
        co_matrix = {("d1", "d2"): 0.9}
        results, _ = engine.generate_recommendations(
            SAMPLE_DISHES, min_recommendations=5, co_order_matrix=co_matrix
        )
        d1_result = next((r for r in results if r["id"] == "d1"), None)
        self.assertIsNotNone(d1_result)
        rec_ids = [r["id"] for r in d1_result["recommendations"]]
        # With a 0.9 co-order boost (0.30 * 0.9 = 0.27 added to d2's score),
        # d2 must appear in d1's recommendations
        self.assertIn("d2", rec_ids)

    def test_insufficient_list_populated_for_small_menu(self):
        """With only 2 dishes and min_recommendations=5, should flag insufficient."""
        engine = self._get_engine_with_mock_embeddings()
        tiny = SAMPLE_DISHES[:2]
        _, insufficient = engine.generate_recommendations(tiny, min_recommendations=5)
        self.assertGreater(len(insufficient), 0)

    def test_single_dish_returns_empty_recommendations(self):
        """Single dish has no candidates to recommend."""
        engine = self._get_engine_with_mock_embeddings()
        results, _ = engine.generate_recommendations([SAMPLE_DISHES[0]], min_recommendations=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
