# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt
#
# ── Flamezo Platform-Wide Loyalty Constants ───────────────────────────────
#
# These values are FIXED by Flamezo and are NOT configurable by restaurants.
# The settlement model is: restaurants pay nothing in cash — instead, the cross-
# network customer discovery IS the settlement. A customer who earned cash at
# Restaurant A and redeems at Restaurant B is a net-new customer for Restaurant B.
# That's the Flamezo value proposition.
#
# To change these values, update them here only. The backend (loyalty.py) and
# the API (api/loyalty.py) both import from this single source of truth.
# ─────────────────────────────────────────────────────────────────────────────

PLATFORM_LOYALTY = {
    # ── Earning ───────────────────────────────────────────────────────────────
    "earn_type":                    "Percentage of Bill",
    "earn_percentage":              9.0,   # 9% earn rate (₹1000 order → ₹90 cash)
    "min_order_to_earn":            100,   # Orders below ₹100 earn nothing
    "max_coins_per_order":          900,   # Max cap: 9% of ₹10,000

    # ── Redemption ────────────────────────────────────────────────────────────
    "min_redemption_threshold":     100,   # Need ₹100 in wallet to redeem
    "min_billing_for_redemption":   200,   # Order must be ≥ ₹200 to allow redemption
    "max_redemption_percent":       30,    # Up to 30% of order value per redemption
    "max_daily_redemption_inr":     1000,  # Max ₹1,000/day across all restaurants
    "max_manual_adjustment_coins":  500,   # Max adjustment cap

    # ── Coin Value (non-negotiable) ───────────────────────────────────────────
    "coin_value_in_inr":  1,         # 1 Flamezo Cash = ₹1. Always.

    # ── Expiry ───────────────────────────────────────────────────────────────
    "loyalty_expiry_days":          45,    # ALL Cash expires 45 days after earned

    # ── Growth & Bonuses ──────────────────────────────────────────────────────
    "birthday_bonus_coins":         100,   # ₹100 birthday bonus
    "welcome_reward_coins":         150,   # Referee gets ₹150 welcome cash on first claim

    # ── Referral Cashback (platform-level, order-triggered) ───────────────────
    # Referrer earns: ₹50 flat when referee places first order, then 1% of
    # each of the next 15 orders, capped at ₹500 total per referred customer.
    "referral_flat_first_order":    50,    # ₹50 flat on referee's first order
    "referral_cashback_percent":    1.0,   # 1% of each subsequent order
    "referral_cashback_orders":     15,    # Number of orders after first that earn cashback
    "referral_max_cashback":        500,   # Hard cap: max ₹500 earned per referred customer

    # ── Platform Tiers (Global, based on lifetime earned cash) ────────────────
    "tier": {
        "silver":   500,    # ₹500+ lifetime earnings → Silver
        "gold":     2000,   # ₹2,000+ lifetime earnings → Gold
        "platinum": 5000,   # ₹5,000+ lifetime earnings → Platinum
    },
}


# Convenience helpers so callers don't have to dig into the dict

def get_earn_percentage(plan_type=None) -> float:
    return float(PLATFORM_LOYALTY["earn_percentage"])

def get_max_coins_per_order(plan_type=None) -> int:
    return int(PLATFORM_LOYALTY["max_coins_per_order"])

def get_max_redemption_percent(plan_type=None) -> int:
    return int(PLATFORM_LOYALTY["max_redemption_percent"])

def get_expiry_days(plan_type=None) -> int:
    return int(PLATFORM_LOYALTY["loyalty_expiry_days"])

def get_expiry_months(plan_type=None) -> int:
    # Deprecated: Cash expiry is day-based now. Kept so any legacy caller still works.
    return max(1, round(get_expiry_days() / 30))

def get_birthday_bonus_coins(plan_type=None) -> int:
    return int(PLATFORM_LOYALTY["birthday_bonus_coins"])

def get_tier_threshold(tier_name="silver") -> int:
    """Returns the global lifetime earning threshold for a specific tier."""
    tiers: dict = PLATFORM_LOYALTY.get("tier", {})  # type: ignore
    return int(tiers.get(tier_name.lower(), 500))

def get_min_order_to_earn() -> int:
    return PLATFORM_LOYALTY["min_order_to_earn"]  # type: ignore

def get_min_redemption_threshold() -> int:
    return PLATFORM_LOYALTY["min_redemption_threshold"]  # type: ignore

def get_min_billing_for_redemption() -> int:
    return PLATFORM_LOYALTY["min_billing_for_redemption"]  # type: ignore

def get_welcome_reward_coins() -> int:
    return PLATFORM_LOYALTY["welcome_reward_coins"]  # type: ignore

def get_referral_flat_first_order() -> int:
    return int(PLATFORM_LOYALTY["referral_flat_first_order"])  # type: ignore

def get_referral_cashback_percent() -> float:
    return float(PLATFORM_LOYALTY["referral_cashback_percent"])  # type: ignore

def get_referral_cashback_orders() -> int:
    return int(PLATFORM_LOYALTY["referral_cashback_orders"])  # type: ignore

def get_referral_max_cashback() -> int:
    return int(PLATFORM_LOYALTY["referral_max_cashback"])  # type: ignore

def get_max_opens_rewarded_per_share() -> int:
    # Kept for backward-compat; monthly cycle cap is now derived from referral_max_cashback
    return 10
