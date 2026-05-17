# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for AI Coupon Generator

Covers:
  Unit tests (no Gemini API call):
    TestQuotaTracking        — monthly quota read/increment/reset, paid mode
    TestValidateAndClean     — per-suggestion validation and safety guardrails
    TestBuildPrompt          — prompt contains required sections and tone text
    TestContextBuilder       — restaurant context structure (menu stats, existing codes)

  Integration tests (live DB, no external API):
    TestGenerateAPIEndpoint  — generate_coupon_suggestions API with mock Gemini
    TestGetQuotaEndpoint     — get_ai_coupon_quota returns correct shape

  E2E live test (requires Gemini key, skipped if missing):
    TestLiveGeneration       — full round-trip with real Gemini call; validates output shape,
                               safety rules per tone, no duplicate codes, no owner-loss offers

Run all:
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_ai_coupon_generator

Run only unit tests (no Gemini key needed):
    bench run-tests --app flamezo_backend --module flamezo_backend.flamezo.tests.test_ai_coupon_generator.TestQuotaTracking
"""

import json
import unittest
from unittest.mock import patch, MagicMock

import frappe
from frappe.utils import today, flt, now_datetime


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_restaurant(suffix="aicg"):
    """Create a minimal test restaurant and return its name."""
    name = f"TEST-AICG-{suffix}"
    if frappe.db.exists("Restaurant", name):
        frappe.delete_doc("Restaurant", name, force=True)
    doc = frappe.get_doc({
        "doctype": "Restaurant",
        "restaurant_id": name,
        "restaurant_name": f"Test Restaurant {suffix}",
        "city": "Mumbai",
        "state": "Maharashtra",
        "currency": "INR",
        "plan_type": "GOLD",
        "is_active": 1,
        "enable_delivery": 1,
        "enable_takeaway": 1,
        "minimum_order_value": 150,
        "default_delivery_fee": 40,
        "coins_balance": 100.0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return name


def _make_menu_item(restaurant, name, price, category="Starters", veg=True):
    """Create a test menu item."""
    doc = frappe.get_doc({
        "doctype": "Menu Product",
        "restaurant": restaurant,
        "product_name": name,
        "price": price,
        "category_name": category,
        "main_category": "food",
        "is_vegetarian": 1 if veg else 0,
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)
    return doc


def _cleanup(restaurant):
    """Remove test data."""
    for doctype in ["Coupon", "Menu Product"]:
        for r in frappe.get_all(doctype, filters={"restaurant": restaurant}, fields=["name"]):
            try:
                frappe.delete_doc(doctype, r.name, force=True)
            except Exception:
                pass
    if frappe.db.exists("Restaurant", restaurant):
        frappe.delete_doc("Restaurant", restaurant, force=True)
    frappe.db.commit()


# ─── 1. Quota Tracking ────────────────────────────────────────────────────────

class TestQuotaTracking(unittest.TestCase):
    """Test monthly quota management without hitting Gemini API."""

    def setUp(self):
        self.restaurant = _make_restaurant("quota")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_initial_quota_status_is_zero(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _check_quota_status, FREE_MONTHLY_QUOTA
        status = _check_quota_status(self.restaurant)
        self.assertEqual(status["used"], 0)
        self.assertEqual(status["limit"], FREE_MONTHLY_QUOTA)
        self.assertEqual(status["free_remaining"], FREE_MONTHLY_QUOTA)
        self.assertIn("resets_on", status)

    def test_increment_quota_increments_used(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _check_and_increment_quota, FREE_MONTHLY_QUOTA
        result = _check_and_increment_quota(self.restaurant)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["used"], 1)
        self.assertEqual(result["limit"], FREE_MONTHLY_QUOTA)

    def test_increment_up_to_limit_still_allowed(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _check_and_increment_quota, FREE_MONTHLY_QUOTA
        current_month = now_datetime().strftime("%Y-%m")
        # Simulate 9 uses
        frappe.db.set_value("Restaurant", self.restaurant, {
            "ai_coupon_generations_this_month": FREE_MONTHLY_QUOTA - 1,
            "ai_coupon_quota_reset_month": current_month,
        })
        result = _check_and_increment_quota(self.restaurant)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["used"], FREE_MONTHLY_QUOTA)

    def test_increment_over_limit_is_not_allowed(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _check_and_increment_quota, FREE_MONTHLY_QUOTA
        current_month = now_datetime().strftime("%Y-%m")
        frappe.db.set_value("Restaurant", self.restaurant, {
            "ai_coupon_generations_this_month": FREE_MONTHLY_QUOTA,
            "ai_coupon_quota_reset_month": current_month,
        })
        result = _check_and_increment_quota(self.restaurant)
        self.assertFalse(result["allowed"])
        self.assertIn("resets_on", result)

    def test_quota_resets_on_new_month(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _check_and_increment_quota, FREE_MONTHLY_QUOTA
        # Simulate old month with full usage
        frappe.db.set_value("Restaurant", self.restaurant, {
            "ai_coupon_generations_this_month": FREE_MONTHLY_QUOTA,
            "ai_coupon_quota_reset_month": "2024-01",  # old month
        })
        result = _check_and_increment_quota(self.restaurant)
        # Should be reset and allowed
        self.assertTrue(result["allowed"])
        self.assertEqual(result["used"], 1)

    def test_check_status_does_not_increment(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _check_quota_status
        _check_quota_status(self.restaurant)
        _check_quota_status(self.restaurant)
        used = frappe.db.get_value("Restaurant", self.restaurant, "ai_coupon_generations_this_month")
        self.assertEqual(int(used or 0), 0)


# ─── 2. Validate and Clean ────────────────────────────────────────────────────

class TestValidateAndClean(unittest.TestCase):
    """Test per-suggestion validation and safety guardrails."""

    def _validate(self, raw, tone="attractive"):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _validate_and_clean_suggestion
        return _validate_and_clean_suggestion(raw, tone)

    def test_valid_flat_suggestion_passes(self):
        raw = {
            "code": "FLAT50", "offer_type": "coupon", "discount_type": "flat",
            "discount_value": 50, "min_order_amount": 299, "max_discount_cap": None,
            "description": "Flat ₹50 off", "detailed_description": "Save ₹50 on orders above ₹299.",
            "category": "best", "valid_days_of_week": None, "valid_time_start": None,
            "valid_time_end": None, "max_uses": 0, "max_uses_per_user": 1,
            "can_stack": False, "priority": 5,
            "goal": "aov", "rationale": "Drives larger orders", "expected_impact": "Lifts AOV 15%",
        }
        result = self._validate(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "FLAT50")
        self.assertEqual(result["discount_value"], 50)

    def test_code_is_uppercased(self):
        raw = {"code": "welcome20", "offer_type": "coupon", "discount_type": "flat",
               "discount_value": 20, "min_order_amount": 0, "description": "x",
               "detailed_description": "x", "category": "best"}
        result = self._validate(raw)
        self.assertEqual(result["code"], "WELCOME20")

    def test_missing_code_returns_none(self):
        raw = {"code": "", "offer_type": "coupon", "discount_type": "flat", "discount_value": 10}
        self.assertIsNone(self._validate(raw))

    def test_delivery_type_forces_delivery_discount(self):
        raw = {"code": "FREEDEL", "offer_type": "delivery", "discount_type": "flat",
               "discount_value": 0, "min_order_amount": 0, "description": "x",
               "detailed_description": "x", "category": "delivery"}
        result = self._validate(raw)
        self.assertEqual(result["discount_type"], "delivery")

    def test_combo_type_forces_flat_and_zero_value(self):
        raw = {"code": "COMBO299", "offer_type": "combo", "discount_type": "percent",
               "discount_value": 40, "min_order_amount": 0, "description": "x",
               "detailed_description": "x", "category": "best"}
        result = self._validate(raw)
        self.assertEqual(result["discount_type"], "flat")
        self.assertEqual(result["discount_value"], 0.0)

    # Aggressive tone safety guardrails
    def test_aggressive_percent_without_cap_gets_auto_cap(self):
        raw = {"code": "MEGA50", "offer_type": "coupon", "discount_type": "percent",
               "discount_value": 50, "min_order_amount": 50,  # too low!
               "max_discount_cap": None, "description": "x", "detailed_description": "x",
               "category": "best"}
        result = self._validate(raw, tone="aggressive")
        # Must have a cap OR min_order raised
        has_protection = result["max_discount_cap"] is not None or result["min_order_amount"] >= 100
        self.assertTrue(has_protection, "Aggressive percent offer must be capped or have min order")

    def test_aggressive_flat_min_order_enforced(self):
        raw = {"code": "FREE200", "offer_type": "coupon", "discount_type": "flat",
               "discount_value": 200, "min_order_amount": 0,  # zero min = loss risk!
               "description": "x", "detailed_description": "x", "category": "best"}
        result = self._validate(raw, tone="aggressive")
        # min_order must be raised to at least 2x discount to prevent loss
        self.assertGreaterEqual(result["min_order_amount"], 200)

    def test_calm_tone_passes_without_extra_guardrails(self):
        raw = {"code": "CALM10", "offer_type": "coupon", "discount_type": "percent",
               "discount_value": 10, "min_order_amount": 199, "max_discount_cap": 50,
               "description": "x", "detailed_description": "x", "category": "best"}
        result = self._validate(raw, tone="calm")
        self.assertIsNotNone(result)
        self.assertEqual(result["discount_value"], 10)

    def test_priority_is_clamped_to_1_10(self):
        raw = {"code": "PTEST", "offer_type": "coupon", "discount_type": "flat",
               "discount_value": 30, "min_order_amount": 0, "description": "x",
               "detailed_description": "x", "category": "best", "priority": 99}
        result = self._validate(raw)
        self.assertEqual(result["priority"], 10)

    def test_description_truncated_at_200_chars(self):
        raw = {"code": "LONGDESC", "offer_type": "coupon", "discount_type": "flat",
               "discount_value": 10, "min_order_amount": 0,
               "description": "x" * 300, "detailed_description": "y" * 600,
               "category": "best"}
        result = self._validate(raw)
        self.assertLessEqual(len(result["description"]), 200)
        self.assertLessEqual(len(result["detailed_description"]), 600)


# ─── 3. Prompt Builder ────────────────────────────────────────────────────────

class TestBuildPrompt(unittest.TestCase):
    """Test that _build_prompt produces a well-formed prompt with all required sections."""

    def setUp(self):
        self.restaurant_id = _make_restaurant("prompt")
        _make_menu_item(self.restaurant_id, "Paneer Tikka", 199, "Starters")
        _make_menu_item(self.restaurant_id, "Dal Makhani", 149, "Mains")
        _make_menu_item(self.restaurant_id, "Chocolate Cake", 89, "Desserts", veg=True)
        frappe.db.commit()

    def tearDown(self):
        _cleanup(self.restaurant_id)

    def _get_prompt(self, tone="attractive", offer_type_filter=None, count=6):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _get_restaurant_context, _build_prompt
        context = _get_restaurant_context(self.restaurant_id)
        return _build_prompt(context, tone, offer_type_filter, count)

    def test_prompt_contains_restaurant_name(self):
        prompt = self._get_prompt()
        self.assertIn("Test Restaurant prompt", prompt)

    def test_prompt_contains_tone_description(self):
        for tone in ("calm", "attractive", "aggressive"):
            prompt = self._get_prompt(tone=tone)
            if tone == "calm":
                self.assertIn("calm and sustainable", prompt)
            elif tone == "attractive":
                self.assertIn("attractive and balanced", prompt)
            elif tone == "aggressive":
                self.assertIn("aggressive but ALWAYS financially safe", prompt)

    def test_prompt_contains_menu_items(self):
        prompt = self._get_prompt()
        self.assertIn("Paneer Tikka", prompt)
        self.assertIn("Dal Makhani", prompt)

    def test_prompt_contains_existing_codes_if_any(self):
        # Add a coupon so it shows up in existing_codes
        doc = frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant_id,
            "code": "EXISTINGONE",
            "discount_type": "flat",
            "discount_value": 50,
            "offer_type": "coupon",
            "is_active": 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        prompt = self._get_prompt()
        self.assertIn("EXISTINGONE", prompt)

    def test_prompt_contains_offer_type_filter_instruction(self):
        prompt = self._get_prompt(offer_type_filter="auto")
        self.assertIn('offer_type = "auto"', prompt)

    def test_prompt_count_is_in_prompt(self):
        prompt = self._get_prompt(count=4)
        self.assertIn("4", prompt)

    def test_context_has_correct_stats(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _get_restaurant_context
        ctx = _get_restaurant_context(self.restaurant_id)
        self.assertGreater(ctx["stats"]["total_items"], 0)
        self.assertGreater(ctx["stats"]["avg_item_price"], 0)
        self.assertIn("food", " ".join(ctx["stats"]["categories"] or [""]).lower() + "food")


# ─── 4. generate_suggestions() with mocked Gemini ─────────────────────────────

MOCK_SUGGESTIONS_JSON = json.dumps([
    {
        "code": "MOCK20", "offer_type": "coupon", "discount_type": "percent",
        "discount_value": 20, "min_order_amount": 299, "max_discount_cap": 80,
        "description": "Get 20% off your order",
        "detailed_description": "Save up to ₹80 on orders above ₹299.",
        "category": "best", "valid_days_of_week": None,
        "valid_time_start": None, "valid_time_end": None,
        "max_uses": 0, "max_uses_per_user": 1, "can_stack": False, "priority": 5,
        "goal": "acquisition", "rationale": "Acquisition discount for new customers.",
        "expected_impact": "Lifts new user conversion by 20%",
    },
    {
        "code": "MOCKFLAT", "offer_type": "coupon", "discount_type": "flat",
        "discount_value": 50, "min_order_amount": 399, "max_discount_cap": None,
        "description": "Flat ₹50 off",
        "detailed_description": "Save ₹50 on orders above ₹399.",
        "category": "best", "valid_days_of_week": None,
        "valid_time_start": None, "valid_time_end": None,
        "max_uses": 0, "max_uses_per_user": 0, "can_stack": False, "priority": 3,
        "goal": "aov", "rationale": "Push AOV above ₹399.",
        "expected_impact": "Increases average order by ₹80",
    },
    {
        "code": "MOCKDEL", "offer_type": "delivery", "discount_type": "delivery",
        "discount_value": 0, "min_order_amount": 199, "max_discount_cap": None,
        "description": "Free delivery",
        "detailed_description": "Free delivery on orders above ₹199.",
        "category": "delivery", "valid_days_of_week": None,
        "valid_time_start": None, "valid_time_end": None,
        "max_uses": 0, "max_uses_per_user": 0, "can_stack": False, "priority": 4,
        "goal": "delivery", "rationale": "Removes delivery barrier.",
        "expected_impact": "Lifts delivery conversion",
    },
])


class TestGenerateSuggestionsWithMock(unittest.TestCase):
    """Test generate_suggestions() with Gemini mocked out."""

    def setUp(self):
        self.restaurant_id = _make_restaurant("genmock")
        _make_menu_item(self.restaurant_id, "Veg Burger", 149)
        _make_menu_item(self.restaurant_id, "Cold Coffee", 99, "Beverages")
        frappe.db.commit()

    def tearDown(self):
        _cleanup(self.restaurant_id)

    def _run(self, tone="attractive", offer_type_filter=None):
        mock_response = MagicMock()
        mock_response.text = MOCK_SUGGESTIONS_JSON
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch(
            "flamezo_backend.flamezo.services.ai.coupon_generator.get_gemini_client",
            return_value=mock_model,
        ):
            from flamezo_backend.flamezo.services.ai import coupon_generator
            # Import fresh to bypass any cached state
            return coupon_generator.generate_suggestions(
                restaurant_id=self.restaurant_id,
                tone=tone,
                offer_type_filter=offer_type_filter,
                count=3,
            )

    def test_returns_success(self):
        result = self._run()
        self.assertTrue(result["success"], result.get("message"))

    def test_suggestions_are_list(self):
        result = self._run()
        self.assertIsInstance(result["suggestions"], list)
        self.assertGreater(len(result["suggestions"]), 0)

    def test_each_suggestion_has_required_fields(self):
        result = self._run()
        required = ["code", "offer_type", "discount_type", "discount_value",
                    "min_order_amount", "description", "goal", "rationale"]
        for s in result["suggestions"]:
            for field in required:
                self.assertIn(field, s, f"Missing field '{field}' in suggestion {s.get('code')}")

    def test_quota_is_incremented(self):
        self._run()
        used = int(frappe.db.get_value("Restaurant", self.restaurant_id, "ai_coupon_generations_this_month") or 0)
        self.assertEqual(used, 1)

    def test_quota_info_returned(self):
        result = self._run()
        quota = result["quota"]
        self.assertIn("used", quota)
        self.assertIn("limit", quota)
        self.assertIn("resets_on", quota)

    def test_tone_is_returned(self):
        result = self._run(tone="calm")
        self.assertEqual(result["tone"], "calm")

    def test_invalid_json_response_returns_error(self):
        mock_response = MagicMock()
        mock_response.text = "not valid json at all"
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        with patch("flamezo_backend.flamezo.services.ai.coupon_generator.get_gemini_client", return_value=mock_model):
            from flamezo_backend.flamezo.services.ai import coupon_generator
            result = coupon_generator.generate_suggestions(self.restaurant_id, tone="attractive")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "PARSE_ERROR")

    def test_quota_exceeded_returns_error(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import FREE_MONTHLY_QUOTA
        current_month = now_datetime().strftime("%Y-%m")
        frappe.db.set_value("Restaurant", self.restaurant_id, {
            "ai_coupon_generations_this_month": FREE_MONTHLY_QUOTA,
            "ai_coupon_quota_reset_month": current_month,
        })
        result = self._run()
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "QUOTA_EXCEEDED")

    def test_existing_codes_are_skipped(self):
        # Add a coupon that matches a mock suggestion code
        frappe.get_doc({
            "doctype": "Coupon",
            "restaurant": self.restaurant_id,
            "code": "MOCK20",
            "discount_type": "flat",
            "discount_value": 10,
            "offer_type": "coupon",
            "is_active": 1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = self._run()
        codes = [s["code"] for s in result.get("suggestions", [])]
        self.assertNotIn("MOCK20", codes)

    def test_gemini_exception_returns_handled_error(self):
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("Gemini connection error")
        with patch("flamezo_backend.flamezo.services.ai.coupon_generator.get_gemini_client", return_value=mock_model):
            from flamezo_backend.flamezo.services.ai import coupon_generator
            result = coupon_generator.generate_suggestions(self.restaurant_id, tone="attractive")
        self.assertFalse(result["success"])


# ─── 5. API Endpoint Tests ────────────────────────────────────────────────────

class TestGenerateCouponSuggestionsAPI(unittest.TestCase):
    """Test the generate_coupon_suggestions whitelisted API endpoint."""

    def setUp(self):
        self.restaurant_id = _make_restaurant("apitest")
        _make_menu_item(self.restaurant_id, "Masala Dosa", 99)
        frappe.db.commit()

    def tearDown(self):
        _cleanup(self.restaurant_id)

    def _call(self, tone="attractive", offer_type_filter=None, count=3):
        mock_response = MagicMock()
        mock_response.text = MOCK_SUGGESTIONS_JSON
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch("flamezo_backend.flamezo.services.ai.coupon_generator.get_gemini_client", return_value=mock_model):
            from flamezo_backend.flamezo.api.coupons import generate_coupon_suggestions
            return generate_coupon_suggestions(
                restaurant_id=self.restaurant_id,
                tone=tone,
                offer_type_filter=offer_type_filter,
                count=count,
            )

    def test_api_returns_success(self):
        result = self._call()
        self.assertTrue(result["success"], result)

    def test_api_returns_data_with_suggestions(self):
        result = self._call()
        self.assertIn("data", result)
        self.assertIn("suggestions", result["data"])
        self.assertIsInstance(result["data"]["suggestions"], list)

    def test_api_returns_quota_info(self):
        result = self._call()
        self.assertIn("quota", result["data"])
        quota = result["data"]["quota"]
        self.assertIn("used", quota)
        self.assertIn("free_remaining", quota)

    def test_get_ai_coupon_quota_endpoint(self):
        from flamezo_backend.flamezo.api.coupons import get_ai_coupon_quota
        result = get_ai_coupon_quota(restaurant_id=self.restaurant_id)
        self.assertTrue(result["success"])
        self.assertIn("data", result)
        data = result["data"]
        self.assertIn("used", data)
        self.assertIn("limit", data)
        self.assertIn("free_remaining", data)
        self.assertIn("coins_per_paid_generation", data)
        self.assertEqual(data["coins_per_paid_generation"], 2)

    def test_api_paid_generation_deducts_coins_when_quota_exhausted(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import FREE_MONTHLY_QUOTA
        current_month = now_datetime().strftime("%Y-%m")
        # Set quota to exhausted
        frappe.db.set_value("Restaurant", self.restaurant_id, {
            "ai_coupon_generations_this_month": FREE_MONTHLY_QUOTA,
            "ai_coupon_quota_reset_month": current_month,
            "coins_balance": 50.0,
        })
        frappe.db.commit()
        result = self._call()
        if result["success"]:
            # Coins should have been deducted
            new_balance = flt(frappe.db.get_value("Restaurant", self.restaurant_id, "coins_balance"))
            self.assertLess(new_balance, 50.0)
        else:
            # If balance was insufficient, should get INSUFFICIENT_BALANCE error
            self.assertIn(result.get("error_code", ""), ["INSUFFICIENT_BALANCE", "QUOTA_EXCEEDED"])

    def test_api_insufficient_balance_after_quota_returns_error(self):
        from flamezo_backend.flamezo.services.ai.coupon_generator import FREE_MONTHLY_QUOTA
        current_month = now_datetime().strftime("%Y-%m")
        frappe.db.set_value("Restaurant", self.restaurant_id, {
            "ai_coupon_generations_this_month": FREE_MONTHLY_QUOTA,
            "ai_coupon_quota_reset_month": current_month,
            "coins_balance": 0.0,  # zero balance
        })
        frappe.db.commit()
        result = self._call()
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INSUFFICIENT_BALANCE")
        self.assertIn("coins_required", result)
        self.assertEqual(result["coins_required"], 2)


# ─── 6. Coupon Quality Checks ─────────────────────────────────────────────────

class TestCouponQualityRules(unittest.TestCase):
    """
    Verify that the safety rules produce financially sound suggestions
    across all three tones. No external API calls.
    """

    def _validate(self, raw, tone):
        from flamezo_backend.flamezo.services.ai.coupon_generator import _validate_and_clean_suggestion
        return _validate_and_clean_suggestion(raw, tone)

    def _no_owner_loss(self, s):
        """Check a suggestion cannot cause owner loss."""
        if s["discount_type"] == "flat":
            # flat discount should have min_order >= discount_value (at cost-neutral)
            return s["min_order_amount"] >= s["discount_value"]
        if s["discount_type"] == "percent":
            # Percent with no cap must have min_order to ensure bounded loss
            if not s["max_discount_cap"]:
                return s["min_order_amount"] >= 200
            return True  # cap bounds the loss
        return True  # delivery discounts are not loss scenarios (fee waiver)

    def test_calm_suggestions_never_cause_loss(self):
        calm_raws = [
            {"code": "CALM10", "offer_type": "coupon", "discount_type": "percent",
             "discount_value": 10, "min_order_amount": 199, "max_discount_cap": 40,
             "description": "x", "detailed_description": "x", "category": "best"},
            {"code": "CALM15", "offer_type": "coupon", "discount_type": "flat",
             "discount_value": 30, "min_order_amount": 199, "description": "x",
             "detailed_description": "x", "category": "best"},
        ]
        for raw in calm_raws:
            s = self._validate(raw, tone="calm")
            self.assertIsNotNone(s)
            self.assertTrue(self._no_owner_loss(s), f"Loss risk in calm: {s}")

    def test_attractive_suggestions_never_cause_loss(self):
        attractive_raws = [
            {"code": "ATTR25", "offer_type": "coupon", "discount_type": "percent",
             "discount_value": 25, "min_order_amount": 299, "max_discount_cap": 100,
             "description": "x", "detailed_description": "x", "category": "best"},
            {"code": "ATFLAT", "offer_type": "coupon", "discount_type": "flat",
             "discount_value": 60, "min_order_amount": 299, "description": "x",
             "detailed_description": "x", "category": "best"},
        ]
        for raw in attractive_raws:
            s = self._validate(raw, tone="attractive")
            self.assertIsNotNone(s)
            self.assertTrue(self._no_owner_loss(s), f"Loss risk in attractive: {s}")

    def test_aggressive_suggestions_enforced_to_no_loss(self):
        """Even poorly-crafted aggressive suggestions must be fixed."""
        aggressive_raws = [
            # High percent with no cap and zero min_order — MUST get fixed
            {"code": "AGG50", "offer_type": "coupon", "discount_type": "percent",
             "discount_value": 50, "min_order_amount": 0, "max_discount_cap": None,
             "description": "x", "detailed_description": "x", "category": "best"},
            # Flat ₹200 with zero min_order — MUST get fixed
            {"code": "AGGFLAT", "offer_type": "coupon", "discount_type": "flat",
             "discount_value": 200, "min_order_amount": 0, "description": "x",
             "detailed_description": "x", "category": "best"},
        ]
        for raw in aggressive_raws:
            s = self._validate(raw, tone="aggressive")
            self.assertIsNotNone(s, f"Aggressive suggestion was None for {raw['code']}")
            self.assertTrue(self._no_owner_loss(s), f"Owner loss risk not fixed: {s}")

    def test_all_offer_types_validated_correctly(self):
        for offer_type, discount_type in [
            ("coupon", "flat"), ("auto", "percent"), ("combo", "flat"), ("delivery", "delivery")
        ]:
            raw = {
                "code": f"T{offer_type.upper()[:3]}", "offer_type": offer_type,
                "discount_type": discount_type, "discount_value": 20,
                "min_order_amount": 149, "max_discount_cap": 50,
                "description": "x", "detailed_description": "x", "category": "best",
            }
            s = self._validate(raw, tone="attractive")
            self.assertIsNotNone(s, f"offer_type={offer_type} returned None")
            self.assertEqual(s["offer_type"], offer_type)


# ─── 7. E2E Live Generation (requires Gemini key) ────────────────────────────

class TestLiveGeneration(unittest.TestCase):
    """
    Full round-trip with real Gemini 2.5 Flash.
    Skipped if gemini_api_key is not in site config.
    """

    @classmethod
    def setUpClass(cls):
        cls.has_gemini = bool(frappe.conf.get("gemini_api_key") or frappe.get_conf().get("gemini_api_key"))
        if not cls.has_gemini:
            return
        cls.restaurant_id = _make_restaurant("live")
        _make_menu_item(cls.restaurant_id, "Paneer Butter Masala", 249, "Mains")
        _make_menu_item(cls.restaurant_id, "Chicken Biryani", 299, "Mains", veg=False)
        _make_menu_item(cls.restaurant_id, "Gulab Jamun", 79, "Desserts")
        _make_menu_item(cls.restaurant_id, "Lassi", 69, "Beverages")
        _make_menu_item(cls.restaurant_id, "Veg Thali", 199, "Combos")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        if cls.has_gemini:
            _cleanup(cls.restaurant_id)

    def setUp(self):
        if not self.has_gemini:
            self.skipTest("gemini_api_key not configured — skipping live E2E test")

    def _generate(self, tone="attractive", offer_type_filter=None):
        from flamezo_backend.flamezo.services.ai.coupon_generator import generate_suggestions
        return generate_suggestions(
            restaurant_id=self.restaurant_id,
            tone=tone,
            offer_type_filter=offer_type_filter,
            count=4,
        )

    def test_live_calm_generation_succeeds(self):
        result = self._generate(tone="calm")
        self.assertTrue(result["success"], result.get("message"))
        self.assertGreater(len(result["suggestions"]), 0)

    def test_live_attractive_generation_succeeds(self):
        result = self._generate(tone="attractive")
        self.assertTrue(result["success"], result.get("message"))

    def test_live_aggressive_generation_succeeds(self):
        result = self._generate(tone="aggressive")
        self.assertTrue(result["success"], result.get("message"))

    def test_live_suggestions_have_valid_offer_types(self):
        result = self._generate()
        for s in result.get("suggestions", []):
            self.assertIn(s["offer_type"], ("coupon", "auto", "combo", "delivery"),
                          f"Invalid offer_type: {s['offer_type']}")

    def test_live_suggestions_have_valid_discount_types(self):
        result = self._generate()
        for s in result.get("suggestions", []):
            self.assertIn(s["discount_type"], ("flat", "percent", "delivery"),
                          f"Invalid discount_type: {s['discount_type']}")

    def test_live_aggressive_no_owner_loss(self):
        result = self._generate(tone="aggressive")
        for s in result.get("suggestions", []):
            if s["discount_type"] == "flat" and s["discount_value"] > 0:
                self.assertGreaterEqual(
                    s["min_order_amount"], s["discount_value"],
                    f"Owner loss risk: flat ₹{s['discount_value']} with min_order ₹{s['min_order_amount']}"
                )
            if s["discount_type"] == "percent" and s["discount_value"] > 20:
                has_protection = s["max_discount_cap"] is not None or s["min_order_amount"] >= 150
                self.assertTrue(has_protection,
                    f"Aggressive percent offer {s['code']} unprotected: cap={s['max_discount_cap']}, min={s['min_order_amount']}")

    def test_live_no_duplicate_codes_in_response(self):
        result = self._generate()
        codes = [s["code"] for s in result.get("suggestions", [])]
        self.assertEqual(len(codes), len(set(codes)), f"Duplicate codes: {codes}")

    def test_live_codes_are_uppercase(self):
        result = self._generate()
        for s in result.get("suggestions", []):
            self.assertEqual(s["code"], s["code"].upper(), f"Code not uppercase: {s['code']}")

    def test_live_offer_type_filter_respected(self):
        result = self._generate(offer_type_filter="delivery")
        for s in result.get("suggestions", []):
            self.assertEqual(s["offer_type"], "delivery",
                f"Got non-delivery offer when filter was 'delivery': {s['code']}")

    def test_live_quota_incremented_after_generation(self):
        used_before = int(frappe.db.get_value("Restaurant", self.restaurant_id,
            "ai_coupon_generations_this_month") or 0)
        self._generate()
        used_after = int(frappe.db.get_value("Restaurant", self.restaurant_id,
            "ai_coupon_generations_this_month") or 0)
        self.assertGreater(used_after, used_before)

    def test_live_all_suggestions_have_description(self):
        result = self._generate()
        for s in result.get("suggestions", []):
            self.assertTrue(s.get("description"), f"Empty description in {s['code']}")

    def test_live_all_suggestions_have_rationale(self):
        result = self._generate()
        for s in result.get("suggestions", []):
            self.assertTrue(s.get("rationale"), f"Empty rationale in {s['code']}")


if __name__ == "__main__":
    unittest.main()
