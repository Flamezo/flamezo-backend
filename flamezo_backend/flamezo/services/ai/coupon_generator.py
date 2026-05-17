"""
Flamezo AI Coupon Generator
Generates smart, context-aware coupon/offer suggestions using Gemini 2.5 Flash.

v2 improvements (10/10):
  - Richer prompt: cuisine inference, price tier, peak/off-peak hints
  - Existing coupon descriptions passed (not just codes) → avoids semantic duplicates
  - Combo items hint (item names → merchant can wire up IDs)
  - Time-window suggestions strongly encouraged for auto offers
  - Weekend/weekday urgency woven into aggressive tone
  - Better description quality: explicit 3-sentence requirement
  - Delivery threshold calibrated to actual delivery_fee
  - Robust JSON extraction (array search fallback)
  - Parse error logging with raw snippet for debugging

Tone modes:
  calm       — conservative (5–15%), loyalty-building, never risks margins
  attractive — balanced (15–30%), urgency-driven, competitive
  aggressive — high-impact (25–50%), ALWAYS with caps/min-order guardrails

Each call costs ~₹0.06 (6 paise). Quota: 10 generations/restaurant/month (free tier).
After quota: 2 wallet coins per generation.
"""

import json
import re
import logging
from typing import Any

import frappe
from frappe.utils import today, flt, now_datetime

from .base import get_gemini_client, handle_ai_error

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

FREE_MONTHLY_QUOTA = 10
OFFER_TYPES = ("coupon", "auto", "combo", "delivery")

TONE_DESCRIPTIONS = {
    "calm": (
        "calm and sustainable. Use small discounts (5–15%) that protect margins and build loyalty. "
        "Prefer flat discounts with safe min-order thresholds, or mild percentage discounts with caps. "
        "Include at least one time-window offer (e.g. lunchtime auto discount). "
        "Code names should feel warm and welcoming (LOYAL, WELCOME, THANKS, REGULAR, CARE)."
    ),
    "attractive": (
        "attractive and balanced. Use mid-range discounts (15–30%) with strong perceived value. "
        "Include urgency — at least one weekend-only or time-limited offer. "
        "At least one combo offer — vary the combo_type: use 'fixed_bundle' for a meal deal, 'bogo' for buy-2-get-1, or 'build_your_own' for a pick-your-combo. "
        "Code names should feel exciting (TREAT, FEAST, WEEKEND, SPECIAL, GRAB)."
    ),
    "aggressive": (
        "aggressive but ALWAYS financially safe. Use high-impact discounts (25–50%) that create buzz. "
        "MANDATORY safety rules — every offer must satisfy AT LEAST ONE: "
        "(a) min_order_amount >= discount_value * 2.5 for flat discounts, "
        "(b) max_discount_cap is set for percent discounts, "
        "(c) offer_type is 'combo' (combo_price handles margin). "
        "Include weekend-only offers, flash timing (e.g. 6–8 PM), and urgency language. "
        "Include at least one BOGO combo (combo_type='bogo') — it's the highest-impact combo for buzz. "
        "Code names should feel urgent (MEGA, BLAST, FLASH, DEAL, BIG, NOW, HOT)."
    ),
}

# Schema uses {{ }} to escape literal braces for .format(); only {count} and {existing_info} are interpolated
SUGGESTION_SCHEMA = """
Return a JSON array of exactly {count} coupon suggestion objects.
Each object MUST have ALL these fields:

{{
  "code": "UPPERCASE_CODE_4_TO_12_CHARS",
  "offer_type": "coupon|auto|combo|delivery",
  "discount_type": "flat|percent|delivery",
  "discount_value": <number>,
  "min_order_amount": <number — for combo this MUST be 0>,
  "max_discount_cap": <number or null>,
  "description": "<ONE clear line for the customer — what they get>",
  "detailed_description": "<EXACTLY 3 sentences: (1) the saving, (2) the condition/when valid, (3) the benefit to customer>",
  "category": "best|delivery|new|loyalty",
  "valid_days_of_week": <null or ["saturday","sunday"] etc>,
  "valid_time_start": <null or "HH:MM:SS">,
  "valid_time_end": <null or "HH:MM:SS">,
  "max_uses": <0 for unlimited or positive int>,
  "max_uses_per_user": <0 for unlimited, 1 for one-time>,
  "can_stack": false,
  "priority": <integer 1-10, higher = applied first>,
  "goal": "acquisition|aov|frequency|retention|delivery|upsell|offpeak",
  "rationale": "<2 sentences: why this specific offer will grow sales or AOV for THIS restaurant>",
  "expected_impact": "<1 sentence: specific measurable outcome e.g. 'Increases orders above ₹X by ~15%'>",
  "combo_items_hint": "<null or comma-separated names of 2-3 items to bundle, ONLY for combo type>",
  "combo_type": "<null for non-combo — for combo: 'fixed_bundle' | 'bogo' | 'build_your_own'>",
  "combo_name": "<null for non-combo — short display name shown on the menu card, e.g. 'Weekend Bundle', 'Buy 2 Get 1 Free', 'Build Your Meal'>",
  "combo_price": <null for non-combo and bogo — for fixed_bundle/build_your_own: the price the customer pays>,
  "items_to_select": <null for non-combo and fixed_bundle — for bogo/build_your_own: how many items to pick, integer>,
  "display_on_menu": <true for combo, false for all others — shows a card on the menu page>
}}

HARD RULES — violating any makes the output invalid:
1. combo offer_type: discount_type = "flat", discount_value = 0, min_order_amount = 0, combo_price = the bundle price
2. delivery offer_type: discount_type = "delivery"
3. aggressive tone flat discount: min_order_amount >= discount_value * 2.5
4. aggressive tone percent discount: max_discount_cap MUST be set (not null)
5. No duplicate codes within this response
6. Do NOT reuse or closely resemble these existing offers: {existing_info}
7. auto offer_type = no code needed, auto-applied; always use time or day restrictions
8. Use the restaurant's actual menu item names in descriptions and combo_items_hint

COMBO TYPE RULES:
- fixed_bundle: all items in combo_items_hint must be in cart. combo_price = bundle price. items_to_select = null.
- bogo: customer picks items_to_select items from pool (combo_items_hint), cheapest is FREE. combo_price = null. items_to_select = 2 (or as appropriate). Always generate with engaging combo_name.
- build_your_own: customer picks items_to_select items from pool (combo_items_hint), pays combo_price for all. items_to_select = 2 or 3.
- For all combos: display_on_menu = true, combo_name is REQUIRED (punchy, customer-facing label).
"""



def _get_city_culture_block(city: str, state: str, count: int) -> str:
    """
    Build the city-local-culture section for the prompt.
    Works for ALL Indian cities — relies entirely on Gemini's own knowledge.
    """
    if not city:
        return ""
    location = city.strip()
    if state:
        location += f", {state.strip()}"
    return f"""
## Hyper-Local Naming (CRITICAL)
This restaurant is in **{location}**.

You have deep knowledge of every Indian city — its local language, slang, demonym, food culture, and street vocabulary.
Use that knowledge now:
- What language do people speak in {city}? Use words from it in coupon codes.
- What are locals called? (e.g. Surtis, Mumbaikars, Chennaiites, Hyderabadis) — use the demonym.
- What local slang, cultural references, or food terms resonate with people from {city}?

RULE: At least {max(2, count - 2)} out of {count} coupon codes MUST use local language words, city name, or demonym.
The codes should make a local from {city} smile and feel "this was made for me."

Style examples from other cities (match this energy for {city}):
- Surat (Gujarati) → SURTNIMAJJA, KEMCHOUNVIND, JAMPAKDEAL
- Mumbai (Hindi/Marathi) → BINDAASKHAO, APNABOSS50, EKDUMSPECIAL
- Chennai (Tamil) → MACHANDEAL, VAANGOMACHAN, NALLATREAT
- Hyderabad (Telugu/Urdu) → NAWABIFEAST, DUMBOSS50, NIZAMIDEAL
- Punjab → TUSSIKHAAO, PAAJIKHAO, CHAKDE50
- Kolkata (Bengali) → DADATREAT, MOJADEAL, KOTKHAAO

Apply the same creativity and authenticity for **{city}**.
"""


def _infer_cuisine(restaurant_name: str, categories: list[str]) -> str:
    """Infer cuisine type from name and categories for richer prompt context."""
    text = (restaurant_name + " " + " ".join(categories)).lower()
    if any(k in text for k in ["pizza", "pasta", "italian", "spaghetti"]):
        return "Italian / Western"
    if any(k in text for k in ["sushi", "japanese", "ramen", "nigiri"]):
        return "Japanese / Asian Fusion"
    if any(k in text for k in ["biryani", "curry", "dal", "paneer", "mughlai"]):
        return "Indian"
    if any(k in text for k in ["burger", "sandwich", "wrap", "fries", "american"]):
        return "American / Café"
    if any(k in text for k in ["smoothie", "salad", "health", "bowl", "vegan", "protein"]):
        return "Health / Café"
    if any(k in text for k in ["cafe", "coffee", "frappe", "dessert", "cake", "chocolate"]):
        return "Café / Desserts"
    return "Multi-cuisine"


def _get_price_tier(avg_price: float) -> str:
    """Classify restaurant price tier for smarter threshold suggestions."""
    if avg_price <= 150:
        return "budget (avg ₹{:.0f}/item — suggest min orders ₹150–₹300)".format(avg_price)
    elif avg_price <= 350:
        return "mid-range (avg ₹{:.0f}/item — suggest min orders ₹300–₹600)".format(avg_price)
    elif avg_price <= 600:
        return "premium (avg ₹{:.0f}/item — suggest min orders ₹600–₹1200)".format(avg_price)
    else:
        return "luxury (avg ₹{:.0f}/item — suggest min orders ₹1000–₹2000)".format(avg_price)


def _get_restaurant_context(restaurant_id: str) -> dict[str, Any]:
    """Fetch all relevant restaurant data for the AI prompt."""
    restaurant = frappe.db.get_value(
        "Restaurant",
        restaurant_id,
        [
            "restaurant_name", "city", "state", "currency",
            "enable_delivery", "enable_takeaway", "enable_dine_in",
            "default_delivery_fee", "minimum_order_value",
            "tax_rate", "total_orders", "total_revenue",
            "ai_coupon_generations_this_month", "ai_coupon_quota_reset_month",
        ],
        as_dict=True,
    )
    if not restaurant:
        frappe.throw(f"Restaurant {restaurant_id} not found")

    # Menu items — sorted by price desc to surface premium items first
    menu_items = frappe.get_all(
        "Menu Product",
        filters={"restaurant": restaurant_id, "is_active": 1},
        fields=[
            "product_name", "price", "original_price",
            "category_name", "main_category", "is_vegetarian",
            "product_type", "description",
        ],
        order_by="price desc",
        limit=30,
    )

    # Existing active coupons — pass code + description so AI avoids semantic duplicates
    existing_coupons = frappe.get_all(
        "Coupon",
        filters={"restaurant": restaurant_id, "is_active": 1},
        fields=["code", "description", "discount_type", "discount_value"],
        limit=50,
    )

    # Menu stats
    prices = [flt(item.price) for item in menu_items if item.price]
    avg_price = sum(prices) / len(prices) if prices else 0
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    categories = list({
        item.category_name or item.main_category
        for item in menu_items
        if item.category_name or item.main_category
    })

    # Good combos: pair 2-3 mid-range items (not cheapest, not most expensive)
    mid_items = sorted(
        [i for i in menu_items if min_price < flt(i.price) < max_price],
        key=lambda x: flt(x.price)
    )
    combo_candidates = [i.product_name for i in mid_items[:6]]

    # Estimated AOV = 2 items at avg price
    estimated_aov = round(avg_price * 2.2, -1)

    # Free delivery threshold = 3-4x the delivery fee (makes financial sense)
    delivery_fee = flt(restaurant.default_delivery_fee or 0)
    free_delivery_threshold = max(round(delivery_fee * 3.5, -1), flt(restaurant.minimum_order_value or 0))

    return {
        "restaurant": restaurant,
        "menu_items": menu_items,
        "existing_coupons": existing_coupons,
        "stats": {
            "avg_item_price": round(avg_price, 2),
            "min_item_price": min_price,
            "max_item_price": max_price,
            "estimated_aov": max(estimated_aov, flt(restaurant.minimum_order_value or 0)),
            "total_items": len(menu_items),
            "categories": categories[:12],
            "cuisine": _infer_cuisine(restaurant.restaurant_name, categories),
            "price_tier": _get_price_tier(avg_price),
            "delivery_fee": delivery_fee,
            "free_delivery_threshold": free_delivery_threshold,
            "enable_delivery": bool(restaurant.enable_delivery),
            "enable_takeaway": bool(restaurant.enable_takeaway),
            "enable_dine_in": bool(restaurant.enable_dine_in),
            "combo_candidates": combo_candidates,
        },
    }


def _check_quota_status(restaurant_id: str) -> dict[str, Any]:
    """
    Read-only quota check — does NOT increment.
    Returns {"used": int, "limit": int, "free_remaining": int, "resets_on": str}
    """
    restaurant = frappe.db.get_value(
        "Restaurant", restaurant_id,
        ["ai_coupon_generations_this_month", "ai_coupon_quota_reset_month"],
        as_dict=True,
    )
    now = now_datetime()
    current_month = now.strftime("%Y-%m")
    reset_month = restaurant.get("ai_coupon_quota_reset_month") or ""
    used = int(restaurant.get("ai_coupon_generations_this_month") or 0)
    if reset_month != current_month:
        used = 0

    resets_on = f"{now.year + 1}-01-01" if now.month == 12 else f"{now.year}-{now.month + 1:02d}-01"
    return {
        "used": used,
        "limit": FREE_MONTHLY_QUOTA,
        "free_remaining": max(FREE_MONTHLY_QUOTA - used, 0),
        "resets_on": resets_on,
    }


def _check_and_increment_quota(restaurant_id: str) -> dict[str, Any]:
    """
    Check monthly quota and increment if within limit.
    Returns {"allowed": bool, "used": int, "limit": int, "free_remaining": int, "resets_on": str}
    """
    restaurant = frappe.db.get_value(
        "Restaurant", restaurant_id,
        ["ai_coupon_generations_this_month", "ai_coupon_quota_reset_month"],
        as_dict=True,
    )
    now = now_datetime()
    current_month = now.strftime("%Y-%m")
    if not restaurant:
        return {"allowed": False, "used": 0, "limit": FREE_MONTHLY_QUOTA,
                "free_remaining": 0, "resets_on": current_month}
    reset_month = restaurant.get("ai_coupon_quota_reset_month") or ""
    used = int(restaurant.get("ai_coupon_generations_this_month") or 0)

    if reset_month != current_month:
        used = 0
        frappe.db.set_value("Restaurant", restaurant_id, {
            "ai_coupon_generations_this_month": 0,
            "ai_coupon_quota_reset_month": current_month,
        }, update_modified=False)

    resets_on = f"{now.year + 1}-01-01" if now.month == 12 else f"{now.year}-{now.month + 1:02d}-01"

    if used >= FREE_MONTHLY_QUOTA:
        return {"allowed": False, "used": used, "limit": FREE_MONTHLY_QUOTA,
                "free_remaining": 0, "resets_on": resets_on}

    new_used = used + 1
    frappe.db.set_value("Restaurant", restaurant_id, {
        "ai_coupon_generations_this_month": new_used,
        "total_ai_generations": (frappe.db.get_value("Restaurant", restaurant_id, "total_ai_generations") or 0) + 1,
    }, update_modified=False)
    frappe.db.commit()

    return {"allowed": True, "used": new_used, "limit": FREE_MONTHLY_QUOTA,
            "free_remaining": max(FREE_MONTHLY_QUOTA - new_used, 0), "resets_on": resets_on}


def _build_prompt(context: dict, tone: str, offer_type_filter: str | None, count: int) -> str:
    """Construct the full context-rich prompt for Gemini."""
    restaurant = context["restaurant"]
    stats = context["stats"]
    menu_items = context["menu_items"]
    existing_coupons = context["existing_coupons"]

    # Menu listing — top 20 by price
    menu_lines = []
    for item in menu_items[:20]:
        veg = "VEG" if item.is_vegetarian else "NON-VEG"
        cat = item.category_name or item.main_category or "General"
        orig = f" (was ₹{item.original_price})" if item.original_price and flt(item.original_price) > flt(item.price) else ""
        menu_lines.append(f"  • {item.product_name} — ₹{item.price}{orig} | {cat} | {veg}")
    menu_text = "\n".join(menu_lines) if menu_lines else "  (No menu items found)"

    # Good combo candidates
    combo_text = ", ".join(stats["combo_candidates"]) if stats["combo_candidates"] else "top items"

    # Existing offers summary (avoid duplicates)
    if existing_coupons:
        existing_lines = [
            f"  • {c.code}: {c.description or ''} ({c.discount_type} {c.discount_value})"
            for c in existing_coupons
        ]
        existing_info = "\n" + "\n".join(existing_lines)
    else:
        existing_info = "none yet"

    # Service modes
    modes = []
    if stats["enable_delivery"]: modes.append("delivery")
    if stats["enable_takeaway"]: modes.append("takeaway")
    if stats["enable_dine_in"]:  modes.append("dine-in")
    modes_text = ", ".join(modes) if modes else "unknown"

    # Offer type constraint
    offer_type_instruction = ""
    if offer_type_filter and offer_type_filter in OFFER_TYPES:
        offer_type_instruction = (
            f"\nCRITICAL: ALL {count} suggestions MUST use offer_type = \"{offer_type_filter}\". No exceptions."
        )

    schema = SUGGESTION_SCHEMA.format(count=count, existing_info=existing_info)

    now = now_datetime()
    current_day = now.strftime("%A")
    current_time = now.strftime("%H:%M")
    is_weekend = current_day in ("Saturday", "Sunday")
    is_evening = 17 <= now.hour <= 21

    city_culture_block = _get_city_culture_block(restaurant.city, restaurant.state, count)

    prompt = f"""You are a world-class restaurant growth consultant and promotions strategist specializing in Indian restaurants.
Your job: generate {count} highly specific, immediately actionable coupon/offer suggestions for THIS restaurant.

## Restaurant Profile
- Name: {restaurant.restaurant_name}
- Location: {restaurant.city or "India"}{", " + restaurant.state if restaurant.state else ""}
- Cuisine: {stats["cuisine"]}
- Price Tier: {stats["price_tier"]}
- Service Modes: {modes_text}
- Delivery Fee: ₹{stats["delivery_fee"]}
- Recommended free-delivery threshold: ₹{stats["free_delivery_threshold"]} (3.5× delivery fee — economically sound)
- Estimated Average Order Value (AOV): ₹{stats["estimated_aov"]}
- Minimum order setting: ₹{restaurant.minimum_order_value or 0}
- Today: {current_day} {"(WEEKEND — great for urgency offers)" if is_weekend else "(weekday)"}
- Current time: {current_time} {"(EVENING PEAK — perfect for time-limited offers)" if is_evening else ""}
{city_culture_block}

## Menu ({stats["total_items"]} active items)
Price range: ₹{stats["min_item_price"]} – ₹{stats["max_item_price"]} | Avg: ₹{stats["avg_item_price"]}
Categories: {", ".join(stats["categories"])}

Top items (by price):
{menu_text}

Good combo pairings to consider: {combo_text}

## Already Active Coupons (DO NOT duplicate or closely resemble):
{existing_info}

## Generation Strategy
Tone: {TONE_DESCRIPTIONS[tone]}
{offer_type_instruction}

## Combo Type Guidance
When generating a combo offer, pick the most suitable combo_type:
- fixed_bundle: best for "Meal for 2", "Office Lunch Deal" — all dishes pre-selected, one price
- bogo: best for "Buy 2 Get 1 Free" — drives volume and social sharing, cheapest item free
- build_your_own: best for "Pick any 2 mains for ₹X" — high AOV, customer feels in control
Vary the type across suggestions. Always set combo_name (punchy, customer-facing). Always set display_on_menu=true.

## Diversity requirement
Among the {count} suggestions, include a MIX unless offer_type_filter is set:
- At least 1 auto offer (time or day restricted — no code needed)
- At least 1 combo offer (vary combo_type — use real item names from the menu above)
- At least 1 delivery offer (if delivery is enabled)
- Remaining: coupon codes (require customer to enter a code)

## Output Format
{schema}

CRITICAL OUTPUT INSTRUCTIONS:
- Return ONLY a raw JSON array.
- Do NOT wrap in markdown, code fences, or any explanation.
- Your response MUST start with [ and end with ].
- Use actual menu item names from the list above in descriptions and combo_items_hint.
- All monetary thresholds must make business sense for a {stats["price_tier"]} restaurant.
"""
    return prompt


def _validate_and_clean_suggestion(s: dict, tone: str) -> dict | None:
    """
    Validate a single suggestion dict. Auto-fix minor issues.
    Enforce safety guardrails. Return None if unfixable.
    """
    try:
        code = str(s.get("code") or "").strip().upper()
        # Strip non-alphanumeric except underscore/dash
        code = re.sub(r"[^A-Z0-9_-]", "", code)
        if not code or len(code) < 2 or len(code) > 20:
            return None

        offer_type = s.get("offer_type") or "coupon"
        if offer_type not in OFFER_TYPES:
            offer_type = "coupon"

        discount_type = s.get("discount_type") or "flat"
        if discount_type not in ("flat", "percent", "delivery"):
            discount_type = "flat"

        if offer_type == "delivery":
            discount_type = "delivery"

        if offer_type == "combo":
            discount_type = "flat"
            discount_value = 0.0
        else:
            discount_value = flt(s.get("discount_value") or 0)

        # Combo-specific fields
        raw_combo_type = s.get("combo_type") or None
        valid_combo_types = ("fixed_bundle", "bogo", "build_your_own")
        combo_type = raw_combo_type if raw_combo_type in valid_combo_types else "fixed_bundle"
        combo_name = str(s.get("combo_name") or "")[:100] or None
        raw_combo_price = s.get("combo_price")
        combo_price = flt(raw_combo_price) if raw_combo_price is not None else None
        raw_items_to_select = s.get("items_to_select")
        items_to_select = int(raw_items_to_select) if raw_items_to_select is not None else None
        display_on_menu = bool(s.get("display_on_menu")) if offer_type == "combo" else False

        # For non-combo types, clear all combo fields
        if offer_type != "combo":
            combo_type = None
            combo_name = None
            combo_price = None
            items_to_select = None
            display_on_menu = False
        else:
            # Enforce sensible defaults per combo_type
            if combo_type == "bogo":
                combo_price = None  # BOGO never has a combo_price
                if items_to_select is None:
                    items_to_select = 2
            elif combo_type == "build_your_own":
                if items_to_select is None:
                    items_to_select = 2
            elif combo_type == "fixed_bundle":
                items_to_select = None  # Not applicable for fixed bundles

        min_order = flt(s.get("min_order_amount") or 0)
        if offer_type == "combo":
            min_order = 0  # combo pricing is via combo_price, not min_order
        max_cap = flt(s.get("max_discount_cap") or 0) or None

        # ── Safety guardrails ────────────────────────────────────────────────
        if tone == "aggressive":
            if discount_type == "percent" and discount_value > 20:
                # Must have a cap
                if not max_cap:
                    max_cap = round(discount_value * 1.5)
                if min_order < 150:
                    min_order = max(150.0, discount_value * 2)
            if discount_type == "flat" and discount_value > 0:
                # min_order >= 2.5x discount to ensure net positive for owner
                if min_order < discount_value * 2.5:
                    min_order = round(discount_value * 2.5, -1)  # round to nearest 10

        # Mild guardrail for all tones: flat discount with zero min_order is risky
        if discount_type == "flat" and discount_value > 50 and min_order == 0:
            min_order = discount_value * 2

        # Validate valid_days_of_week
        valid_days = s.get("valid_days_of_week")
        if valid_days and isinstance(valid_days, list):
            valid_day_names = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
            valid_days = [d.lower() for d in valid_days if isinstance(d, str) and d.lower() in valid_day_names]
            valid_days = valid_days if valid_days else None
        else:
            valid_days = None

        # Validate time fields (HH:MM:SS format)
        def clean_time(t: Any) -> str | None:
            if not t:
                return None
            t = str(t).strip()
            if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", t):
                parts = t.split(":")
                return f"{int(parts[0]):02d}:{parts[1]}:{parts[2] if len(parts) > 2 else '00'}"
            return None

        valid_time_start = clean_time(s.get("valid_time_start"))
        valid_time_end = clean_time(s.get("valid_time_end"))

        # auto offers without time/day restrictions lose their purpose — add a sensible default
        if offer_type == "auto" and not valid_days and not valid_time_start:
            valid_time_start = "12:00:00"
            valid_time_end = "15:00:00"

        # combo_items_hint: strip to reasonable length, keep as string (not saved to DB)
        combo_items_hint = str(s.get("combo_items_hint") or "")[:200] or None
        if offer_type != "combo":
            combo_items_hint = None

        return {
            "code": code,
            "offer_type": offer_type,
            "discount_type": discount_type,
            "discount_value": discount_value,
            "min_order_amount": min_order,
            "max_discount_cap": max_cap,
            "description": str(s.get("description") or "")[:200],
            "detailed_description": str(s.get("detailed_description") or "")[:600],
            "category": str(s.get("category") or "best")[:50],
            "valid_days_of_week": valid_days,
            "valid_time_start": valid_time_start,
            "valid_time_end": valid_time_end,
            "max_uses": int(s.get("max_uses") or 0),
            "max_uses_per_user": int(s.get("max_uses_per_user") or 0),
            "can_stack": bool(s.get("can_stack") or False),
            "priority": min(max(int(s.get("priority") or 1), 1), 10),
            # Display-only extras
            "goal": str(s.get("goal") or "aov")[:50],
            "rationale": str(s.get("rationale") or "")[:400],
            "expected_impact": str(s.get("expected_impact") or "")[:200],
            "combo_items_hint": combo_items_hint,
            # New combo-type fields
            "combo_type": combo_type,
            "combo_name": combo_name,
            "combo_price": combo_price,
            "items_to_select": items_to_select,
            "display_on_menu": display_on_menu,
        }
    except Exception as e:
        logger.warning(f"[coupon_generator] Skipping invalid suggestion: {e} — raw: {s}")
        return None


def _extract_json_array(raw_text: str) -> list | None:
    """
    Robustly extract a JSON array from the model response.
    Handles: clean output, markdown fences, preamble text.
    """
    text = raw_text.strip()

    # 1. Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE).strip()

    # 2. Try direct parse if starts with [
    if text.startswith("["):
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass  # fall through to extraction

    # 3. Find the JSON array via bracket matching
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    end = -1
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return None
    try:
        result = json.loads(text[start:end])
        return result if isinstance(result, list) else None
    except json.JSONDecodeError:
        return None


def generate_suggestions(
    restaurant_id: str,
    tone: str = "attractive",
    offer_type_filter: str | None = None,
    count: int = 6,
) -> dict[str, Any]:
    """
    Main entry point. Generates coupon suggestions using Gemini 2.5 Flash.

    Args:
        restaurant_id: Frappe restaurant name/ID
        tone: "calm" | "attractive" | "aggressive"
        offer_type_filter: Optional — restrict to one offer_type
        count: Number of suggestions to generate (3–8)
    """
    tone = tone if tone in TONE_DESCRIPTIONS else "attractive"
    count = max(3, min(count, 8))
    if offer_type_filter and offer_type_filter not in OFFER_TYPES:
        offer_type_filter = None

    # Quota check + increment
    quota = _check_and_increment_quota(restaurant_id)
    if not quota["allowed"]:
        return {
            "success": False,
            "error_code": "QUOTA_EXCEEDED",
            "message": (
                f"You've used all {FREE_MONTHLY_QUOTA} free AI generations this month. "
                f"Quota resets on {quota['resets_on']}."
            ),
            "quota": quota,
        }

    context = _get_restaurant_context(restaurant_id)
    prompt = _build_prompt(context, tone, offer_type_filter, count)

    # Call Gemini
    try:
        model = get_gemini_client()
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.75,
                "top_p": 0.95,
                "max_output_tokens": 8192,
            },
        )
        raw_text = response.text.strip()
    except Exception as e:
        # Roll back quota increment since generation failed
        used = int(frappe.db.get_value("Restaurant", restaurant_id, "ai_coupon_generations_this_month") or 1)
        frappe.db.set_value("Restaurant", restaurant_id,
            {"ai_coupon_generations_this_month": max(used - 1, 0)}, update_modified=False)
        frappe.db.commit()
        return handle_ai_error(e)

    # Parse JSON
    suggestions_raw = _extract_json_array(raw_text)
    if suggestions_raw is None:
        logger.error(f"[coupon_generator] JSON parse failed for {restaurant_id}. Raw snippet: {raw_text[:300]}")
        return {
            "success": False,
            "error_code": "PARSE_ERROR",
            "message": "AI returned an unexpected format. Please try again.",
            "quota": {k: v for k, v in quota.items() if k != "allowed"},
        }

    # Validate and deduplicate
    existing_codes = {c.code for c in context["existing_coupons"]}
    suggestions = []
    seen_codes = set(existing_codes)

    for raw in suggestions_raw:
        if not isinstance(raw, dict):
            continue
        cleaned = _validate_and_clean_suggestion(raw, tone)
        if not cleaned:
            continue
        if cleaned["code"] in seen_codes:
            continue
        seen_codes.add(cleaned["code"])
        suggestions.append(cleaned)

    if not suggestions:
        logger.error(f"[coupon_generator] All suggestions invalid for {restaurant_id}. Raw: {raw_text[:300]}")
        return {
            "success": False,
            "error_code": "NO_VALID_SUGGESTIONS",
            "message": "AI generated suggestions that could not be validated. Please try again.",
            "quota": {k: v for k, v in quota.items() if k != "allowed"},
        }

    return {
        "success": True,
        "suggestions": suggestions,
        "quota": {k: v for k, v in quota.items() if k != "allowed"},
        "tone": tone,
        "offer_type_filter": offer_type_filter,
    }
