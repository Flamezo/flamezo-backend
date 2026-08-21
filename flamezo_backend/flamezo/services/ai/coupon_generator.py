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
  - Offer thresholds calibrated to restaurant AOV and price tier
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
OFFER_TYPES = ("coupon", "auto", "combo")

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
  "offer_type": "coupon|auto|combo",
  "discount_type": "flat|percent",
  "discount_value": <number>,
  "min_order_amount": <number — for combo this MUST be 0>,
  "max_discount_cap": <number or null>,
  "description": "<ONE clear line for the customer — what they get>",
  "detailed_description": "<EXACTLY 3 sentences: (1) the saving, (2) the condition/when valid, (3) the benefit to customer>",
  "category": "best|new|loyalty",
  "valid_days_of_week": <null or ["saturday","sunday"] etc>,
  "valid_time_start": <null or "HH:MM:SS">,
  "valid_time_end": <null or "HH:MM:SS">,
  "valid_from": <null, or "YYYY-MM-DD" ONLY if a start date is shown in the source poster/request>,
  "valid_until": <null, or "YYYY-MM-DD" ONLY if an end/expiry date is shown (e.g. "valid till Jul 31, 2026" → "2026-07-31")>,
  "max_uses": <0 for unlimited or positive int>,
  "max_uses_per_user": <0 for unlimited, 1 for one-time>,
  "can_stack": false,
  "priority": <integer 1-10, higher = applied first>,
  "goal": "acquisition|aov|frequency|retention|upsell|offpeak",
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
2. aggressive tone flat discount: min_order_amount >= discount_value * 2.5
3. aggressive tone percent discount: max_discount_cap MUST be set (not null)
4. No duplicate codes within this response
5. Do NOT reuse or closely resemble these existing offers: {existing_info}
6. auto offer_type = no code needed, auto-applied; always use time or day restrictions
7. Use the restaurant's actual menu item names in descriptions and combo_items_hint
8. Every coupon/auto offer MUST have discount_value > 0. discount_value = 0 is ONLY valid for combo. A "free item"/"complimentary gift" is NOT a zero-discount coupon — model it EITHER as a combo (combo_type = "bogo", the gift is the free item) OR as a flat coupon whose discount_value = the free item's menu price, with min_order_amount = the qualifying spend (e.g. "Spend ₹1000, get a free brownie worth ₹80" → flat, discount_value 80, min_order_amount 1000).

COMBO TYPE RULES:
- fixed_bundle: all items in combo_items_hint must be in cart. combo_price = bundle price. items_to_select = null.
- bogo: customer picks items_to_select items from pool (combo_items_hint), cheapest is FREE. combo_price = null. items_to_select = 2 (or as appropriate). Always generate with engaging combo_name.
- build_your_own: customer picks items_to_select items from pool (combo_items_hint), pays combo_price for all. items_to_select = 2 or 3.
- MUST FEEL LIKE A DEAL: for fixed_bundle and build_your_own, combo_price MUST be 15–30% BELOW the normal total of the cheapest items the customer could pick (so they perceive a real saving). A combo priced at or above the item sum is rejected — never do it.
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


def _infer_cuisine(outlet_name: str, categories: list[str]) -> str:
    """Infer cuisine type from name and categories for richer prompt context."""
    text = (outlet_name + " " + " ".join(categories)).lower()
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


def _get_outlet_context(outlet_id: str) -> dict[str, Any]:
    """Fetch all relevant restaurant data for the AI prompt."""
    restaurant = frappe.db.get_value(
        "Outlet",
        outlet_id,
        [
            "outlet_name", "city", "state", "currency",
            "enable_dine_in",
            "tax_rate", "total_orders", "total_revenue",
            "ai_coupon_generations_this_month", "ai_coupon_quota_reset_month",
        ],
        as_dict=True,
    )
    if not restaurant:
        frappe.throw(f"Outlet {outlet_id} not found")

    # Menu items — sorted by price desc to surface premium items first
    menu_items = frappe.get_all(
        "Menu Product",
        filters={"outlet": outlet_id, "is_active": 1},
        fields=[
            "product_name", "price", "original_price", "food_cost",
            "category_name", "main_category", "is_vegetarian",
            "product_type", "description",
        ],
        order_by="price desc",
        limit=30,
    )

    # Existing active coupons — pass code + description so AI avoids semantic duplicates
    existing_coupons = frappe.get_all(
        "Coupon",
        filters={"outlet": outlet_id, "is_active": 1},
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

    # ── Margin intelligence (food cost) — powers profit-safe offer generation ──
    costed = [i for i in menu_items if flt(i.get("food_cost")) > 0 and flt(i.get("price")) > 0]
    fc_pcts = [flt(i.food_cost) / flt(i.price) * 100 for i in costed]
    margin_pcts = [(flt(i.price) - flt(i.food_cost)) / flt(i.price) * 100 for i in costed]
    avg_food_cost_pct = round(sum(fc_pcts) / len(fc_pcts), 1) if fc_pcts else 0
    avg_margin_pct = round(sum(margin_pcts) / len(margin_pcts), 1) if margin_pcts else 0
    # Best "give it free" candidates = costed items with the LOWEST food-cost % (cheapest to gift)
    giveaway = sorted(costed, key=lambda x: flt(x.food_cost) / flt(x.price))[:6]
    giveaway_candidates = [
        f"{i.product_name} (₹{flt(i.price):.0f}, only {round(flt(i.food_cost) / flt(i.price) * 100)}% cost)"
        for i in giveaway
    ]
    # name → food_cost, for combo loss-protection at validation time
    cost_map = {
        (i.product_name or "").strip().lower(): flt(i.food_cost)
        for i in menu_items if flt(i.get("food_cost")) > 0
    }
    # name → {price, cost}, for per-offer economics (perceived discount vs real margin)
    econ_map = {
        (i.product_name or "").strip().lower(): {"price": flt(i.price), "cost": flt(i.food_cost)}
        for i in menu_items if flt(i.get("food_cost")) > 0 and flt(i.price) > 0
    }

    # Estimated AOV = 2 items at avg price
    estimated_aov = round(avg_price * 2.2, -1)

    return {
        "restaurant": restaurant,
        "menu_items": menu_items,
        "existing_coupons": existing_coupons,
        "cost_map": cost_map,
        "econ_map": econ_map,
        "stats": {
            "avg_item_price": round(avg_price, 2),
            "has_cost_data": len(costed) > 0,
            "costed_count": len(costed),
            "avg_food_cost_pct": avg_food_cost_pct,
            "avg_margin_pct": avg_margin_pct,
            "giveaway_candidates": giveaway_candidates,
            "min_item_price": min_price,
            "max_item_price": max_price,
            "estimated_aov": estimated_aov,
            "total_items": len(menu_items),
            "categories": categories[:12],
            "cuisine": _infer_cuisine(restaurant.outlet_name, categories),
            "price_tier": _get_price_tier(avg_price),
            "enable_dine_in": bool(restaurant.enable_dine_in),
            "combo_candidates": combo_candidates,
        },
    }


def _check_quota_status(outlet_id: str) -> dict[str, Any]:
    """
    Read-only quota check — does NOT increment.
    Returns {"used": int, "limit": int, "free_remaining": int, "resets_on": str}
    """
    restaurant = frappe.db.get_value(
        "Outlet", outlet_id,
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


def _check_and_increment_quota(outlet_id: str) -> dict[str, Any]:
    """
    Check monthly quota and increment if within limit.
    Returns {"allowed": bool, "used": int, "limit": int, "free_remaining": int, "resets_on": str}
    """
    restaurant = frappe.db.get_value(
        "Outlet", outlet_id,
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
        frappe.db.set_value("Outlet", outlet_id, {
            "ai_coupon_generations_this_month": 0,
            "ai_coupon_quota_reset_month": current_month,
        }, update_modified=False)

    resets_on = f"{now.year + 1}-01-01" if now.month == 12 else f"{now.year}-{now.month + 1:02d}-01"

    if used >= FREE_MONTHLY_QUOTA:
        return {"allowed": False, "used": used, "limit": FREE_MONTHLY_QUOTA,
                "free_remaining": 0, "resets_on": resets_on}

    new_used = used + 1
    frappe.db.set_value("Outlet", outlet_id, {
        "ai_coupon_generations_this_month": new_used,
        "total_ai_generations": (frappe.db.get_value("Outlet", outlet_id, "total_ai_generations") or 0) + 1,
    }, update_modified=False)
    frappe.db.commit()

    return {"allowed": True, "used": new_used, "limit": FREE_MONTHLY_QUOTA,
            "free_remaining": max(FREE_MONTHLY_QUOTA - new_used, 0), "resets_on": resets_on}


def _build_prompt(
    context: dict,
    tone: str,
    offer_type_filter: str | None,
    count: int,
    user_prompt: str | None = None,
    from_poster: bool = False,
) -> str:
    """Construct the full context-rich prompt for Gemini.

    user_prompt : merchant's free-text description ("NLP" offer creation) — the
                  generated offers must fulfil what the owner asked for.
    from_poster : True when an offer POSTER image is attached — read the offer(s)
                  off the poster and convert them into structured suggestions.
    """
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
        margin_note = ""
        if flt(item.get("food_cost")) > 0 and flt(item.price) > 0:
            fcp = round(flt(item.food_cost) / flt(item.price) * 100)
            margin_note = f" | makes for ₹{flt(item.food_cost):.0f} ({fcp}% cost, {100 - fcp}% margin)"
        menu_lines.append(f"  • {item.product_name} — ₹{item.price}{orig} | {cat} | {veg}{margin_note}")
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

    # ── Margin / profit guardrails (only when the owner has entered food costs) ──
    if stats.get("has_cost_data"):
        giveaway_text = "; ".join(stats["giveaway_candidates"]) if stats["giveaway_candidates"] else "the lowest-cost items"
        margin_block = f"""
## Margin & Profit Intelligence (CRITICAL — use the food-cost data above)
This restaurant has entered real food costs. Each menu line shows its cost % and margin %.
- Menu-wide average food cost: {stats["avg_food_cost_pct"]}% of price (avg margin {stats["avg_margin_pct"]}%). {stats["costed_count"]} items costed.
- Cheapest items to give away (lowest food cost — best for "free"/BOGO): {giveaway_text}

Profit rules — every offer must feel BIG to the customer but cost the restaurant LITTLE:
1. BOGO ("buy 1 get 1"): the FREE item only costs the owner its food cost, while the customer feels ~50% off. So make the FREE/cheapest item a LOW-food-cost item (e.g. beverages ~15–20%). Never make a high-cost item the free one.
2. Combo / build-your-own: the combo_price MUST stay comfortably above the total food cost of its items — aim to keep at least ~50% gross margin on the bundle. NEVER set a combo_price below what the items cost to make.
3. Flat / percent discounts: never let the discount exceed the item's margin — a 40%-cost item cannot survive a 40% discount. Prefer discounts well under the avg margin of {stats["avg_margin_pct"]}%.
4. Prefer structured offers (BOGO/combo) over deep flat discounts: they feel huge to the customer (perceived 40–50% off) while only costing food cost. A flat % is real money straight off profit.
5. In each suggestion's "rationale", briefly note the profit logic (e.g. "free chai costs only ₹16 but feels like ₹89 off").
"""
    else:
        margin_block = """
## Margin & Profit Intelligence
No food costs entered yet for this menu. Stay conservative: prefer combos and BOGO on lower-priced items, keep flat discounts modest (≤15%), and use min-order thresholds so no offer can run at a loss.
"""

    # ── Merchant-driven request blocks (NLP prompt / poster image) ──
    request_block = ""
    if from_poster:
        request_block = f"""
## SOURCE: OFFER POSTER IMAGE(S) (highest priority — this OVERRIDES the "{count} suggestions", "Diversity requirement" and any "generate N" instructions below)
One to three images are ATTACHED to this request. They are DIFFERENT screenshots / photos of the SAME single offer — for example a coupon tile, the offer's detail screen after tapping it, and its terms & conditions (like a Zomato/Swiggy coupon). Read ALL the attached images TOGETHER as one offer.

STRICT RULES:
- Produce EXACTLY ONE offer that matches what the images show. Return an array containing EXACTLY ONE object. Do NOT create one offer per image — the images describe the SAME offer.
- Combine details across the images: take the headline/discount from one screen, the minimum order / code / validity / terms from the others, and merge them into that single offer.
- Use the EXACT discount value, code, minimum order, item names, days/times and validity SHOWN in the images. Do not change or invent values that contradict what is shown.
- If a field is not shown anywhere in the images (e.g. no code, no min order), fill only that field in sensibly for this restaurant. If a code is shown, use that exact code.
- Match the offer_type to what the images describe (percent/flat coupon, BOGO, combo, auto/time-based).
- If the images contain NO readable offer at all, return an empty array [].
- Still respect the profit guardrails below; if the offer would run at a loss, keep its headline but adjust thresholds minimally to stay safe and note it in the rationale.

FIELD MAPPING (aggregator-style coupons like Swiggy/Zomato — map EXACTLY):
- "N% off upto ₹M" / "N% off, Maximum discount ₹M"  → discount_type="percent", discount_value=N, max_discount_cap=M.  (e.g. "70% off upto ₹130" → percent, 70, cap 130)
- "Flat ₹N off"                                      → discount_type="flat", discount_value=N, max_discount_cap=null.
- "on orders above ₹X" / "above ₹X" / "min order ₹X" → min_order_amount=X.  (e.g. "above ₹179" → 179)
- "USE CODE XXXX" / "Use code XXXX"                  → offer_type="coupon", code="XXXX" EXACTLY as printed (keep case-insensitive letters, do not translate/localize it).
- "valid till <date>" / "expires <date>"            → valid_until as "YYYY-MM-DD".  (e.g. "valid till Jul 31, 2026 11:59 PM" → "2026-07-31")
- IGNORE aggregator-platform-only terms that do not apply on Flamezo (e.g. "valid only on selected restaurants", "not applicable on pre-discounted items", "other TnCs may apply") — do NOT copy these into the offer.
- Put a short customer-facing line in `description` (e.g. "70% off up to ₹130 on orders above ₹179").
"""
    # Poster & prompt modes must return ONLY the requested offers — suppress the "add a mix" push.
    diversity_block = "" if (from_poster or user_prompt) else f"""## Diversity requirement
Among the {count} suggestions, include a MIX unless offer_type_filter is set:
- At least 1 auto offer (time or day restricted — no code needed)
- At least 1 combo offer (vary combo_type — use real item names from the menu above)
- Remaining: coupon codes (require customer to enter a code)
"""

    if user_prompt and not from_poster:
        request_block = f"""
## MERCHANT'S SPECIFIC REQUEST (highest priority — this OVERRIDES the "{count} suggestions", "Diversity requirement" and any "generate N" instructions below)
The restaurant owner typed this request in their own words:
"{user_prompt.strip()}"

STRICT RULES:
- Create ONLY the offer(s) the owner described — nothing else. If they describe a single offer, return an array with EXACTLY ONE object. If they clearly describe several distinct offers, return exactly one per offer they described.
- Do NOT invent, add, pad, or "also suggest" any extra offer, variant, auto/combo, or complementary deal they did not ask for. Ignore the {count} target and the Diversity requirement entirely.
- Use the EXACT discount value, items, conditions, occasion, days/times and wording the owner specified. Only fill in a field they left unspecified (e.g. a code) sensibly for this restaurant.
- If the request is too vague to build even one concrete offer, make your single best interpretation of it — still only one offer.
- Keep the offer profit-safe per the guardrails below; if their ask would run at a loss, keep its headline but adjust thresholds minimally and note it in the rationale.
"""

    prompt = f"""You are a world-class restaurant growth consultant and promotions strategist specializing in Indian restaurants.
Your job: generate {count} highly specific, immediately actionable coupon/offer suggestions for THIS restaurant.
{request_block}
## Restaurant Profile
- Name: {restaurant.outlet_name}
- Location: {restaurant.city or "India"}{", " + restaurant.state if restaurant.state else ""}
- Cuisine: {stats["cuisine"]}
- Price Tier: {stats["price_tier"]}
- Service Modes: {modes_text}
- Estimated Average Order Value (AOV): ₹{stats["estimated_aov"]}
- Today: {current_day} {"(WEEKEND — great for urgency offers)" if is_weekend else "(weekday)"}
- Current time: {current_time} {"(EVENING PEAK — perfect for time-limited offers)" if is_evening else ""}
{city_culture_block}

## Menu ({stats["total_items"]} active items)
Price range: ₹{stats["min_item_price"]} – ₹{stats["max_item_price"]} | Avg: ₹{stats["avg_item_price"]}
Categories: {", ".join(stats["categories"])}

Top items (by price):
{menu_text}

Good combo pairings to consider: {combo_text}
{margin_block}
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

{diversity_block}
## Make every offer HOT (Flamezo is "India's hottest app")
- Lead with the BIG perceived number: "Buy 1 Get 1", "50% OFF", "Flat ₹X" — never bury the value.
- Add urgency + scarcity: prefer time/day windows and set a believable max_uses (e.g. 50–200) so it feels limited, not infinite. Tonight/this-weekend framing wins.
- Use the structured offers that feel huge but cost little (BOGO on the low-cost beverages above, combos that bundle a high-margin drink with a main).
- Punchy, share-worthy copy in `description`; the customer should *want* to screenshot it.

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


def _validate_and_clean_suggestion(s: dict, tone: str, cost_map: dict | None = None) -> dict | None:
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
        if discount_type not in ("flat", "percent"):
            discount_type = "flat"

        if offer_type == "combo":
            discount_type = "flat"
            discount_value = 0.0
        else:
            discount_value = flt(s.get("discount_value") or 0)
            # A coupon/auto offer with a zero (or negative) discount is invalid — the
            # Coupon doctype rejects it ("Discount Value must be greater than zero"),
            # so it can never be saved. Drop it rather than surface an unsaveable card.
            if discount_value <= 0:
                logger.warning(
                    f"[coupon_generator] Dropping non-combo offer with zero discount: {code}"
                )
                return None

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

        # Validate validity dates (accept YYYY-MM-DD; ignore anything else). These are
        # only populated when a poster/prompt actually states a date.
        def clean_date(d: Any) -> str | None:
            if not d:
                return None
            d = str(d).strip()[:10]
            return d if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else None

        valid_from = clean_date(s.get("valid_from"))
        valid_until = clean_date(s.get("valid_until"))

        # auto offers without time/day restrictions lose their purpose — add a sensible default
        if offer_type == "auto" and not valid_days and not valid_time_start:
            valid_time_start = "12:00:00"
            valid_time_end = "15:00:00"

        # combo_items_hint: strip to reasonable length, keep as string (not saved to DB)
        combo_items_hint = str(s.get("combo_items_hint") or "")[:200] or None
        if offer_type != "combo":
            combo_items_hint = None

        # ── Loss protection: never let a priced combo sell below what it costs to make ──
        # Best-effort: resolve hinted item names against the food-cost map. If we can match
        # 2+ items and their combined food cost meets/exceeds the combo_price, it's a money-
        # losing offer — drop it so it never reaches the owner.
        if (
            cost_map
            and offer_type == "combo"
            and combo_type in ("fixed_bundle", "build_your_own")
            and combo_price
            and combo_items_hint
        ):
            hint_lc = combo_items_hint.lower()
            matched_costs = [c for name, c in cost_map.items() if name and name in hint_lc]
            if len(matched_costs) >= 2:
                total_cogs = sum(matched_costs)
                if combo_price <= total_cogs:
                    logger.warning(
                        f"[coupon_generator] Dropping loss-making combo "
                        f"(price ₹{combo_price} <= food cost ₹{total_cogs:.0f}): {combo_name}"
                    )
                    return None

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
            "valid_from": valid_from,
            "valid_until": valid_until,
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
    if end != -1:
        try:
            result = json.loads(text[start:end])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass  # fall through to salvage

    # 4. Salvage a TRUNCATED array (token-limit cut-off): parse each complete
    #    top-level {...} object individually and keep the ones that parse.
    objs = []
    depth = 0
    obj_start = -1
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
        if ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                try:
                    o = json.loads(text[obj_start:i + 1])
                    if isinstance(o, dict):
                        objs.append(o)
                except json.JSONDecodeError:
                    pass
                obj_start = -1
    return objs or None


def _compute_offer_economics(s: dict, econ_map: dict | None, avg_margin_pct: float = 0.0) -> dict:
    """
    Estimate how an offer FEELS to the customer vs what it really costs the owner.
    Powers the owner-facing "feels like X% off / profit-safe" badge AND acts as the
    final safety net (the caller drops anything that lands below a healthy margin).
    Best-effort: resolves combo_items_hint against real per-item economics.
    """
    offer_type = s.get("offer_type")
    discount_type = s.get("discount_type")
    discount_value = flt(s.get("discount_value"))
    combo_type = s.get("combo_type")
    combo_price = s.get("combo_price")
    items_to_select = int(s.get("items_to_select") or 2)
    hint = (s.get("combo_items_hint") or "").lower()

    def verdict(m):
        return "safe" if m >= 35 else ("ok" if m >= 20 else "thin")

    matched = []
    if econ_map and hint:
        matched = [e for name, e in econ_map.items() if name and name in hint]
        matched.sort(key=lambda e: e["price"])

    # BOGO — cheapest item free; revenue = paid item, cost = both items' COGS
    if offer_type == "combo" and combo_type == "bogo" and matched:
        free = matched[0]
        paid = matched[1] if len(matched) >= 2 else matched[0]
        revenue = paid["price"]
        margin = ((revenue - paid["cost"] - free["cost"]) / revenue * 100) if revenue > 0 else 0
        denom = paid["price"] + free["price"]
        perceived = (free["price"] / denom * 100) if denom > 0 else 50
        return {"perceived_discount_pct": round(perceived), "est_margin_pct": round(margin),
                "real_cost": round(free["cost"]), "verdict": verdict(margin),
                "headline": f"Feels like {round(perceived)}% off · the free item costs you only ₹{free['cost']:.0f}",
                "resolved": True}

    # priced combo — bundle margin
    if offer_type == "combo" and combo_price and matched:
        if combo_type == "build_your_own":
            chosen = matched[:max(items_to_select, 2)]   # customer picks cheapest = worst case for owner
        else:
            chosen = matched
        normal = sum(e["price"] for e in chosen)
        cost = sum(e["cost"] for e in chosen)
        cp = flt(combo_price)
        margin = ((cp - cost) / cp * 100) if cp > 0 else 0
        perceived = ((normal - cp) / normal * 100) if normal > 0 else 0
        return {"perceived_discount_pct": round(max(perceived, 0)), "est_margin_pct": round(margin),
                "real_cost": round(max(normal - cp, 0)), "verdict": verdict(margin),
                "headline": f"Feels like {round(max(perceived, 0))}% off · keeps {round(margin)}% margin",
                "resolved": True}

    # percent coupon — discount comes straight off margin
    if discount_type == "percent" and discount_value > 0:
        margin_after = avg_margin_pct - discount_value
        return {"perceived_discount_pct": round(discount_value), "est_margin_pct": round(margin_after),
                "real_cost": None, "verdict": verdict(margin_after),
                "headline": f"{round(discount_value)}% off · ~{round(margin_after)}% margin left",
                "resolved": bool(avg_margin_pct)}

    # flat coupon — perceived against the min order
    if discount_type == "flat" and discount_value > 0:
        min_o = flt(s.get("min_order_amount")) or discount_value * 2.5
        perceived = (discount_value / min_o * 100) if min_o > 0 else 0
        margin_after = avg_margin_pct - perceived
        return {"perceived_discount_pct": round(perceived), "est_margin_pct": round(margin_after),
                "real_cost": round(discount_value), "verdict": verdict(margin_after),
                "headline": f"₹{discount_value:.0f} off · ~{round(margin_after)}% margin on the min order",
                "resolved": bool(avg_margin_pct)}

    return {"perceived_discount_pct": None, "est_margin_pct": None, "real_cost": None,
            "verdict": "ok", "headline": "", "resolved": False}


def generate_suggestions(
    outlet_id: str,
    tone: str = "attractive",
    offer_type_filter: str | None = None,
    count: int = 6,
    user_prompt: str | None = None,
    poster_base64: str | None = None,
    require_food_cost: bool = True,
) -> dict[str, Any]:
    """
    Main entry point. Generates coupon suggestions using Gemini 2.5 Flash.

    Args:
        outlet_id: Frappe outlet (Restaurant doctype) name/ID
        tone: "calm" | "attractive" | "aggressive"
        offer_type_filter: Optional — restrict to one offer_type
        count: Number of suggestions to generate (3–8)
        user_prompt: Optional merchant free-text request (NLP offer creation)
        poster_base64: Optional base64 poster image — read the offer(s) off it (vision)
        require_food_cost: Gate AI generation behind complete menu food-cost data
            (default True, for the merchant-facing Manage Offers/Coupons flow,
            where the AI is inventing the discount amount and needs real margins
            to keep it profit-safe). Pass False for callers that already supply
            their own discount amount and only want the naming/copy — e.g. Boost
            campaigns — where that economics-safety reason doesn't apply.
    """
    tone = tone if tone in TONE_DESCRIPTIONS else "attractive"
    count = max(3, min(count, 8))
    if offer_type_filter and offer_type_filter not in OFFER_TYPES:
        offer_type_filter = None

    # Gate: AI generation requires food cost on every active menu item so the
    # AI can compute real margins and generate profit-safe offers. Skipped when
    # require_food_cost=False (caller already fixed the discount amount).
    if require_food_cost:
        try:
            total_active = frappe.db.count("Menu Product", {"outlet": outlet_id, "is_active": 1})
            costed = (
                frappe.db.count(
                    "Menu Product",
                    {"outlet": outlet_id, "is_active": 1, "food_cost": [">", 0]},
                )
                if total_active > 0
                else 0
            )
        except Exception:
            # food_cost column not yet migrated — treat as fully uncovered
            total_active = frappe.db.count("Menu Product", {"outlet": outlet_id, "is_active": 1})
            costed = 0

        if total_active > 0 and costed < total_active:
            missing = total_active - costed
            plural = "s are" if missing != 1 else " is"
            return {
                "success": False,
                "error_code": "FOOD_COST_REQUIRED",
                "message": (
                    f"{missing} menu item{plural} missing food cost. "
                    f"Please set food cost for all {total_active} items in the Food Cost page before using AI generation."
                ),
            }

    # Quota check + increment
    quota = _check_and_increment_quota(outlet_id)
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

    # Normalize poster input → list of up to 3 base64 images (same offer, different screens).
    # The client may send a single data-URL string or a JSON array of them.
    poster_list: list[str] = []
    if poster_base64:
        if isinstance(poster_base64, (list, tuple)):
            poster_list = list(poster_base64)
        else:
            s = str(poster_base64).strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    poster_list = parsed if isinstance(parsed, list) else [s]
                except Exception:
                    poster_list = [s]
            else:
                poster_list = [s]
        poster_list = [p for p in poster_list if p][:3]  # cap at 3 images

    context = _get_outlet_context(outlet_id)
    prompt = _build_prompt(
        context, tone, offer_type_filter, count,
        user_prompt=user_prompt, from_poster=bool(poster_list),
    )

    # Call Gemini — text prompt, or vision when offer poster image(s) are attached
    try:
        model = get_gemini_client()
        generation_config = {
            "temperature": 0.75,
            "top_p": 0.95,
            # 2.5-flash is a thinking model; thinking shares the output budget, so a
            # higher ceiling prevents the JSON array from being truncated mid-object.
            "max_output_tokens": 16384,
            # Force clean JSON (no markdown fences / preamble) → reliable parsing.
            "response_mime_type": "application/json",
        }
        if poster_list:
            parts: list = [prompt]
            for img in poster_list:
                # Strip data-URL prefix if the client sent one (data:image/...;base64,)
                b64 = img.split("base64,")[1] if "base64," in img else img
                parts.append({"mime_type": "image/jpeg", "data": b64})
            content = parts
        else:
            content = prompt
        response = model.generate_content(content, generation_config=generation_config)
        raw_text = response.text.strip()
    except Exception as e:
        # Roll back quota increment since generation failed
        used = int(frappe.db.get_value("Outlet", outlet_id, "ai_coupon_generations_this_month") or 1)
        frappe.db.set_value("Outlet", outlet_id,
            {"ai_coupon_generations_this_month": max(used - 1, 0)}, update_modified=False)
        frappe.db.commit()
        return handle_ai_error(e)

    # Parse JSON
    suggestions_raw = _extract_json_array(raw_text)
    if suggestions_raw is None:
        logger.error(f"[coupon_generator] JSON parse failed for {outlet_id}. Raw snippet: {raw_text[:300]}")
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
        cleaned = _validate_and_clean_suggestion(raw, tone, cost_map=context.get("cost_map"))
        if not cleaned:
            continue
        if cleaned["code"] in seen_codes:
            continue

        # Per-offer economics + final profit net: drop any resolvable money-loser
        # (margin < 15%) — this also closes the BOGO "expensive free item" gap.
        econ = _compute_offer_economics(
            cleaned,
            context.get("econ_map"),
            avg_margin_pct=context["stats"].get("avg_margin_pct", 0),
        )
        if econ.get("resolved") and econ.get("est_margin_pct") is not None and econ["est_margin_pct"] < 15:
            logger.warning(
                f"[coupon_generator] Dropping thin/loss offer "
                f"(margin {econ['est_margin_pct']}%): {cleaned['code']}"
            )
            continue

        # Attractiveness gate: a combo priced at/above the item sum gives the customer no
        # real saving ("feels like 0% off") — boring, so drop it. (BOGO always feels ~50%.)
        if (
            cleaned.get("offer_type") == "combo"
            and cleaned.get("combo_type") in ("fixed_bundle", "build_your_own")
            and econ.get("resolved")
            and econ.get("perceived_discount_pct") is not None
            and econ["perceived_discount_pct"] < 10
        ):
            logger.warning(
                f"[coupon_generator] Dropping unattractive combo "
                f"(only {econ['perceived_discount_pct']}% perceived off): {cleaned['code']}"
            )
            continue
        cleaned["economics"] = econ

        seen_codes.add(cleaned["code"])
        suggestions.append(cleaned)

    if not suggestions:
        logger.error(f"[coupon_generator] All suggestions invalid for {outlet_id}. Raw: {raw_text[:300]}")
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
