import hashlib
import json
import logging
import math
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

import frappe
from .base import get_openai_client, handle_ai_error

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Generate menu item recommendations with embedding cache and co-order signals."""

    def __init__(self, embedding_model: str = "text-embedding-3-small"):
        self.client = get_openai_client()
        self.embedding_model = embedding_model

    def generate_recommendations(
        self,
        dishes: List[Dict[str, Any]],
        categories: Optional[List[Dict[str, Any]]] = None,
        min_recommendations: int = 9,
        co_order_matrix: Optional[Dict[Tuple[str, str], float]] = None,
        restaurant: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Generate deterministic recommendations for each dish.
        Uses embedding cache (incremental re-runs), co-order matrix, and time signals.
        """
        if not dishes:
            return [], []

        dish_embeddings = self._build_embeddings(dishes, restaurant=restaurant)
        dish_map = {dish.get("id"): dish for dish in dishes if dish.get("id")}
        categories_by_id = {c.get("id"): c for c in categories or [] if c.get("id")}
        co_matrix = co_order_matrix or {}

        results = []
        insufficient: List[str] = []

        for dish in dishes:
            dish_id = dish.get("id")
            if not dish_id:
                continue

            candidates = []
            for other_id, other_dish in dish_map.items():
                if other_id == dish_id:
                    continue
                sim = self._cosine(
                    dish_embeddings.get(dish_id, []),
                    dish_embeddings.get(other_id, []),
                )
                # Look up co-order frequency (pair is stored lexically sorted)
                pair = (min(dish_id, other_id), max(dish_id, other_id))
                co_freq = co_matrix.get(pair, 0.0)
                score = self._score_pair(dish, other_dish, sim, co_order_freq=co_freq)
                candidates.append((score, other_dish, sim, co_freq))

            # Sort deterministically
            candidates.sort(key=lambda item: (-item[0], item[1].get("id", "")))

            top_candidates = self._select_diverse_candidates(
                base_dish=dish,
                candidates=candidates,
                min_recommendations=min_recommendations,
                base_embedding=dish_embeddings.get(dish_id, []),
                embeddings=dish_embeddings,
            )

            if len(top_candidates) < min_recommendations:
                insufficient.append(dish_id)

            recs = []
            for score, cand, sim, co_freq in top_candidates[:min_recommendations]:
                recs.append({
                    "id": cand.get("id"),
                    "name": cand.get("name"),
                    "category": cand.get("category"),
                    "mainCategory": cand.get("mainCategory"),
                    "isVegetarian": cand.get("isVegetarian", False),
                    "price": cand.get("price"),
                    "reason": self._build_reason(dish, cand, categories_by_id, sim, co_freq),
                    "score": round(score, 4),
                    "co_order_freq": round(co_freq, 4),
                })

            results.append({
                "id": dish_id,
                "name": dish.get("name"),
                "category": dish.get("category"),
                "mainCategory": dish.get("mainCategory"),
                "isVegetarian": dish.get("isVegetarian", False),
                "recommendations": recs,
            })

        return results, insufficient

    def _build_embeddings(
        self,
        dishes: List[Dict[str, Any]],
        restaurant: Optional[str] = None,
    ) -> Dict[str, List[float]]:
        """
        Create embeddings for each dish, using cache for unchanged dishes.
        Only calls OpenAI API for dishes whose text has changed since last run.
        Cache key: md5 of _dish_to_text() output.
        """
        inputs_to_embed = []
        ids_to_embed = []
        cached_embeddings: Dict[str, List[float]] = {}

        # Load existing cache for this restaurant
        cache_by_product_id: Dict[str, Any] = {}
        if restaurant:
            try:
                cache_rows = frappe.get_all(
                    "Menu Product Embedding Cache",
                    fields=["product_id", "text_hash", "embedding_vector", "name"],
                    filters={"restaurant": restaurant},
                )
                for row in cache_rows:
                    cache_by_product_id[row.product_id] = row
            except Exception as e:
                logger.warning(f"Could not load embedding cache: {e}")

        for dish in dishes:
            dish_id = dish.get("id")
            if not dish_id:
                continue

            text = self._dish_to_text(dish)
            text_hash = hashlib.md5(text.encode()).hexdigest()

            cached = cache_by_product_id.get(dish_id)
            if cached and cached.text_hash == text_hash and cached.embedding_vector:
                # Cache hit — reuse stored vector
                try:
                    vec = cached.embedding_vector
                    if isinstance(vec, str):
                        vec = json.loads(vec)
                    if isinstance(vec, list) and vec:
                        cached_embeddings[dish_id] = vec
                        continue
                except Exception:
                    pass

            # Cache miss — needs fresh embedding
            ids_to_embed.append(dish_id)
            inputs_to_embed.append(text)

        # Batch embed all cache-miss dishes
        fresh_embeddings: Dict[str, List[float]] = {}
        if inputs_to_embed:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=inputs_to_embed,
            )
            for dish_id, emb in zip(ids_to_embed, response.data):
                fresh_embeddings[dish_id] = emb.embedding

            # Persist fresh embeddings to cache
            if restaurant:
                self._upsert_embedding_cache(
                    restaurant, dishes, fresh_embeddings, cache_by_product_id
                )

        return {**cached_embeddings, **fresh_embeddings}

    def _upsert_embedding_cache(
        self,
        restaurant: str,
        dishes: List[Dict[str, Any]],
        fresh_embeddings: Dict[str, List[float]],
        existing_cache: Dict[str, Any],
    ):
        """Upsert embedding cache rows for freshly embedded dishes."""
        dish_map = {d.get("id"): d for d in dishes if d.get("id")}
        try:
            for dish_id, vector in fresh_embeddings.items():
                dish = dish_map.get(dish_id)
                if not dish:
                    continue
                text = self._dish_to_text(dish)
                text_hash = hashlib.md5(text.encode()).hexdigest()

                # Find the Menu Product doc name
                product_doc_name = frappe.db.get_value(
                    "Menu Product",
                    {"product_id": dish_id, "restaurant": restaurant},
                    "name",
                )
                if not product_doc_name:
                    continue

                existing = existing_cache.get(dish_id)
                if existing:
                    # Update existing cache row
                    frappe.db.set_value(
                        "Menu Product Embedding Cache",
                        existing.name,
                        {
                            "text_hash": text_hash,
                            "embedding_vector": json.dumps(vector),
                            "embedding_model": self.embedding_model,
                        },
                        update_modified=False,
                    )
                else:
                    # Insert new cache row
                    frappe.get_doc({
                        "doctype": "Menu Product Embedding Cache",
                        "restaurant": restaurant,
                        "product": product_doc_name,
                        "product_id": dish_id,
                        "text_hash": text_hash,
                        "embedding_model": self.embedding_model,
                        "embedding_vector": json.dumps(vector),
                    }).insert(ignore_permissions=True)
        except Exception as e:
            logger.warning(f"Failed to upsert embedding cache: {e}")

    def _dish_to_text(self, dish: Dict[str, Any]) -> str:
        """Compact text representation for embedding. Changing this busts all caches."""
        name = dish.get("name", "")
        category = dish.get("category", "")
        main_category = dish.get("mainCategory", "")
        description = dish.get("description") or ""
        veg = "vegetarian" if dish.get("isVegetarian") else "non-vegetarian"
        price = dish.get("price", "")
        return (
            f"Dish: {name}. Category: {category}. Main category: {main_category}. "
            f"Type: {veg}. Price: {price}. Description: {description}"
        )

    def _cosine(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _score_pair(
        self,
        base: Dict[str, Any],
        candidate: Dict[str, Any],
        similarity: float,
        co_order_freq: float = 0.0,
    ) -> float:
        """
        Hybrid scoring formula:
          0.45 × embedding_similarity  (semantic match)
          0.30 × co_order_frequency    (real purchase signal — what customers actually order together)
          0.10 × price_similarity
          + category/main/beverage/dessert/offer/popularity bonuses
          - dietary penalty
        """
        base_category = (base.get("category") or "").lower()
        cand_category = (candidate.get("category") or "").lower()
        base_main = (base.get("mainCategory") or "").lower()
        cand_main = (candidate.get("mainCategory") or "").lower()

        price_base = base.get("price") or 0
        price_cand = candidate.get("price") or 0
        price_gap = abs(price_base - price_cand)
        price_norm = 1 - min(price_gap / (max(price_base, price_cand, 1)), 1)

        dietary_penalty = -0.2 if base.get("isVegetarian") and not candidate.get("isVegetarian") else 0.0
        category_bonus = 0.15 if base_category != cand_category else 0.0
        main_bonus = 0.1 if base_main != cand_main else 0.0
        beverage_bonus = 0.1 if "beverage" in cand_main and base_main != cand_main else 0.0
        dessert_bonus = 0.08 if "dessert" in cand_main and base_main != cand_main else 0.0
        offer_bonus = 0.05 if candidate.get("originalPrice") and candidate.get("originalPrice") > candidate.get("price", 0) else 0.0

        pop_boost = 0.0
        if candidate.get("isSpecial"):
            pop_boost += 0.05
        if "special" in cand_category or "top" in cand_category:
            pop_boost += 0.03

        biz_bonus = (
            0.05 * min(1.0, candidate.get("priorityWeight") or 0) +
            0.03 * min(1.0, candidate.get("popularityScore") or 0)
        )

        return (
            0.45 * similarity
            + 0.30 * co_order_freq
            + 0.10 * price_norm
            + category_bonus + main_bonus
            + beverage_bonus + dessert_bonus
            + offer_bonus + pop_boost + biz_bonus
            + dietary_penalty
        )

    def _build_reason(
        self,
        base: Dict[str, Any],
        candidate: Dict[str, Any],
        categories_by_id: Dict[str, Dict[str, Any]],
        similarity: float,
        co_order_freq: float = 0.0,
    ) -> str:
        """
        Build a human-readable reason for the pairing.
        Priority:
        1. Co-order frequency (most credible — real customer behavior)
        2. Offer/savings
        3. Semantic/category rules
        """
        base_main = base.get("mainCategory") or ""
        cand_main = candidate.get("mainCategory") or ""
        base_cat = base.get("category") or ""
        cand_cat = candidate.get("category") or ""
        cat_label = cand_cat or categories_by_id.get(candidate.get("category") or "", {}).get("name", "")

        # 1. Co-order signal (translate normalized 0-1 freq back to percentage)
        if co_order_freq >= 0.5:
            pct = int(50 + co_order_freq * 50)  # maps 0.5→75, 1.0→100
            return f"{pct}% of customers order these together"
        elif co_order_freq >= 0.25:
            return "Frequently ordered together"

        # 2. Offer/savings
        original = candidate.get("originalPrice")
        price = candidate.get("price") or 0
        if original and original > price:
            savings = int(original - price)
            if savings > 0:
                return f"Save ₹{savings} when ordered together"

        # 3. Semantic/category rules
        parts = []
        if similarity >= 0.8:
            parts.append("Similar profile")
        elif similarity <= 0.4 and cand_main and base_main != cand_main:
            parts.append(f"Contrast with {cand_main}")
        if base_main != cand_main and cand_main:
            parts.append(f"Balances {base_main or 'dish'} with {cand_main}")
        elif base_cat and cand_cat and base_cat != cand_cat:
            parts.append(f"Adds variety from {cat_label or 'another category'}")

        return "; ".join(dict.fromkeys(parts)) if parts else "Pairs well with this dish"

    def _select_diverse_candidates(
        self,
        base_dish: Dict[str, Any],
        candidates: List[Tuple],
        min_recommendations: int,
        base_embedding: Optional[List[float]],
        embeddings: Dict[str, List[float]],
    ) -> List[Tuple]:
        """Diversity selection — prevents all recommendations from same category."""
        base_main = (base_dish.get("mainCategory") or "").lower()
        available_counts = defaultdict(int)
        for item in candidates:
            cand = item[1]
            main = (cand.get("mainCategory") or "").lower() or "default"
            available_counts[main] += 1

        total_available = sum(available_counts.values())
        if total_available == 0:
            return []

        sorted_mains = sorted(available_counts.items(), key=lambda x: x[1], reverse=True)
        slots = []
        remaining = min_recommendations
        for main, count in sorted_mains:
            if main == base_main:
                continue
            if remaining <= 0:
                break
            target = max(1, min(int((count / total_available) * min_recommendations * 1.2), count, remaining))
            if target > 0:
                slots.append((main, target))
                remaining -= target

        if remaining > 0 and base_main in available_counts:
            same_cat_target = min(int(min_recommendations * 0.3), available_counts[base_main], remaining)
            if same_cat_target > 0:
                slots.append((base_main, same_cat_target))

        caps = {}
        for main, count in available_counts.items():
            base_cap = int(min_recommendations * 0.3) if main == base_main else int(min_recommendations * 0.4)
            caps[main] = min(base_cap, count)
        caps["default"] = min(min_recommendations, total_available)

        counts = defaultdict(int)
        picked_ids = set()
        selected = []
        buckets = defaultdict(list)
        for item in candidates:
            cand = item[1]
            buckets[(cand.get("mainCategory") or "").lower() or "default"].append(item)

        for main, need in slots:
            if len(selected) >= min_recommendations:
                break
            taken = 0
            for item in buckets.get(main, []):
                cand = item[1]
                if cand["id"] in picked_ids:
                    continue
                if counts[main] >= caps.get(main, caps["default"]):
                    continue
                selected.append(item)
                picked_ids.add(cand["id"])
                counts[main] += 1
                taken += 1
                if len(selected) >= min_recommendations or taken >= need:
                    break

        # Backfill
        if len(selected) < min_recommendations:
            for item in candidates:
                if len(selected) >= min_recommendations:
                    break
                cand = item[1]
                if cand["id"] in picked_ids:
                    continue
                main = (cand.get("mainCategory") or "").lower() or "default"
                if counts[main] >= caps.get(main, caps["default"]):
                    continue
                selected.append(item)
                picked_ids.add(cand["id"])
                counts[main] += 1

        return selected[:min_recommendations]


@frappe.whitelist()
def get_recommendations(dishes, categories=None, min_recommendations=9, co_order_matrix=None, restaurant=None):
    """API endpoint for recommendation generation."""
    try:
        engine = RecommendationEngine()
        results, insufficient = engine.generate_recommendations(
            dishes,
            categories,
            min_recommendations,
            co_order_matrix=co_order_matrix,
            restaurant=restaurant,
        )
        return {
            "success": True,
            "data": {"recommendations": results},
            "insufficient": insufficient,
        }
    except Exception as e:
        return handle_ai_error(e)
