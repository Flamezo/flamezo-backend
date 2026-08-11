# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for FLAMEZO consumer wallet APIs (flamezo.py).

Covers:
  get_flamezo_member:
    - new customer has zero balance, Bronze tier, next_tier=Silver
    - Silver tier when lifetime earned >= 500
    - Gold tier when lifetime earned >= 2000
    - Platinum tier has next_tier=None, progress_pct=100
    - lifetime_earned counts only settled Earn entries
    - expiring_soon is capped at current balance
    - required response keys are always present
    - no phone + no token → AUTH_REQUIRED
    - invalid phone → INVALID_PHONE

  get_points_ledger:
    - returns empty entries for new customer
    - entries returned newest-first
    - Earn with "Welcome Bonus" reason maps to type="bonus"
    - Redeem entry maps to type="redeem"
    - current_balance matches actual computed balance
    - pagination: has_more=True when more entries exist
    - pagination: has_more=False on last page
    - limit is capped at 50 regardless of request
    - no phone + no token → AUTH_REQUIRED
    - invalid phone → INVALID_PHONE
"""

import unittest
import unittest.mock as mock
from frappe.utils import today, add_days, flt

import frappe
from flamezo_backend.flamezo.tests.utils import (
    make_restaurant,
    make_customer,
    make_loyalty_entry,
    cleanup_restaurant,
)

_PREFIX = "TEST-WLT"
_PHONE  = "9100000001"
_PHONE_B = "9100000002"

# ── Patch target (module-level import in flamezo.py) ─────────────────────────
_TOKEN_PATCH = "flamezo_backend.flamezo.api.flamezo.get_customer_token"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_rest(suffix="01"):
    return make_restaurant(f"{_PREFIX}-R{suffix}", plan="GOLD")


def _make_cust(phone=_PHONE):
    return make_customer(phone=phone, name=f"Test Wallet {phone[-4:]}")


def _earn(customer_name, restaurant, coins, reason="Order",
          days_until_expiry=60, is_settled=1):
    return make_loyalty_entry(
        customer_name, restaurant, coins,
        txn_type="Earn", reason=reason,
        is_settled=is_settled, days_until_expiry=days_until_expiry,
    )


def _redeem(customer_name, restaurant, coins, reason="Redemption"):
    return make_loyalty_entry(
        customer_name, restaurant, coins,
        txn_type="Redeem", reason=reason,
        is_settled=1, days_until_expiry=0,
    )


def _cleanup(phone=_PHONE):
    cust = frappe.db.get_value("Customer", {"phone": phone}, "name")
    if cust:
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cust})
        frappe.db.delete("Customer", {"name": cust})
    frappe.db.commit()


def _cleanup_all():
    for ph in [_PHONE, _PHONE_B]:
        _cleanup(ph)
    frappe.db.sql("DELETE FROM `tabRestaurant` WHERE name LIKE %s", [f"{_PREFIX}%"])
    frappe.db.commit()


# ── Import API functions ───────────────────────────────────────────────────────
from flamezo_backend.flamezo.api.flamezo import get_flamezo_member, get_points_ledger


# ═══════════════════════════════════════════════════════════════════════════════
# get_flamezo_member
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetFlamezoMember(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        _cleanup_all()
        self.rest = _make_rest()
        self.cust = _make_cust()

    def tearDown(self):
        _cleanup_all()

    def _call(self, phone=_PHONE, **kwargs):
        """Call get_flamezo_member with no live session token."""
        with mock.patch(_TOKEN_PATCH, return_value=None):
            return get_flamezo_member(phone=phone, **kwargs)

    # ── baseline ──────────────────────────────────────────────────────────────

    def test_new_member_has_zero_balance_bronze_tier(self):
        res = self._call()
        self.assertTrue(res["success"], res)
        d = res["data"]
        self.assertEqual(d["flamezo_points_balance"], 0.0)
        self.assertEqual(d["tier"], "Bronze")
        self.assertEqual(d["next_tier"], "Silver")
        self.assertEqual(d["lifetime_earned"], 0.0)
        self.assertEqual(d["expiring_soon"], 0.0)

    def test_required_keys_always_present(self):
        res = self._call()
        self.assertTrue(res["success"])
        expected = {
            "phone", "full_name", "flamezo_points_balance", "tier",
            "next_tier", "tier_progress_pct", "next_tier_threshold",
            "lifetime_earned", "lifetime_redeemed", "expiring_soon",
            "restaurants_visited", "referral_code", "joined_on",
        }
        self.assertEqual(expected, expected & set(res["data"].keys()))

    # ── tiers ─────────────────────────────────────────────────────────────────

    def test_silver_tier_at_500_lifetime_earned(self):
        _earn(self.cust.name, self.rest.name, 500)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["tier"], "Silver")
        self.assertEqual(res["data"]["next_tier"], "Gold")
        self.assertEqual(res["data"]["lifetime_earned"], 500.0)

    def test_gold_tier_at_2000_lifetime_earned(self):
        _earn(self.cust.name, self.rest.name, 2000)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["tier"], "Gold")
        self.assertEqual(res["data"]["next_tier"], "Platinum")

    def test_platinum_tier_has_no_next_tier(self):
        _earn(self.cust.name, self.rest.name, 5000)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["tier"], "Platinum")
        self.assertIsNone(res["data"]["next_tier"])
        # progress_pct stays 0 when next_threshold is None (already at max tier)
        self.assertEqual(res["data"]["tier_progress_pct"], 0)

    def test_progress_pct_within_silver_range(self):
        # Bronze→Silver span = 500 coins. 250 earned = 50% progress.
        _earn(self.cust.name, self.rest.name, 250)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["tier"], "Bronze")
        self.assertEqual(res["data"]["tier_progress_pct"], 50)

    # ── lifetime vs settled ───────────────────────────────────────────────────

    def test_lifetime_earned_excludes_unsettled_entries(self):
        _earn(self.cust.name, self.rest.name, 300, is_settled=1)
        _earn(self.cust.name, self.rest.name, 200, is_settled=0)  # unsettled
        res = self._call()
        self.assertTrue(res["success"])
        # Only settled 300 counts toward lifetime_earned
        self.assertEqual(res["data"]["lifetime_earned"], 300.0)

    def test_lifetime_redeemed_accumulates_redeem_entries(self):
        _earn(self.cust.name, self.rest.name, 500)
        _redeem(self.cust.name, self.rest.name, 100)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["lifetime_redeemed"], 100.0)

    # ── expiring_soon ─────────────────────────────────────────────────────────

    def test_expiring_soon_coins_within_30_days(self):
        _earn(self.cust.name, self.rest.name, 150, days_until_expiry=10)
        _earn(self.cust.name, self.rest.name, 200, days_until_expiry=60)
        res = self._call()
        self.assertTrue(res["success"])
        # Only the 150-coin entry expires within 30 days
        self.assertEqual(res["data"]["expiring_soon"], 150.0)

    def test_expiring_soon_capped_at_current_balance(self):
        # Earn 300, redeem 250 → balance = 50. 300 coins expire soon → capped at 50.
        _earn(self.cust.name, self.rest.name, 300, days_until_expiry=5)
        _redeem(self.cust.name, self.rest.name, 250)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["flamezo_points_balance"], 50.0)
        self.assertEqual(res["data"]["expiring_soon"], 50.0)

    # ── restaurants_visited ───────────────────────────────────────────────────

    def test_restaurants_visited_counts_distinct_restaurants(self):
        r2 = _make_rest(suffix="02")
        _earn(self.cust.name, self.rest.name, 100)
        _earn(self.cust.name, r2.name, 100)
        _earn(self.cust.name, r2.name, 50)  # duplicate restaurant
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["restaurants_visited"], 2)

    # ── auth errors ───────────────────────────────────────────────────────────

    def test_no_phone_no_token_returns_auth_required(self):
        with mock.patch(_TOKEN_PATCH, return_value=None):
            res = get_flamezo_member(phone=None)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "AUTH_REQUIRED")

    def test_invalid_phone_returns_invalid_phone_error(self):
        res = self._call(phone="abc")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_PHONE")

    def test_non_numeric_phone_returns_invalid_phone_error(self):
        # "abc" is non-empty so passes the `not phone` gate, but normalize_phone
        # strips non-digits → empty → INVALID_PHONE
        res = self._call(phone="abc")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_PHONE")

    # ── cross-customer isolation ──────────────────────────────────────────────

    def test_other_customer_entries_not_included(self):
        cust_b = _make_cust(_PHONE_B)
        _earn(cust_b.name, self.rest.name, 9000)  # should not affect cust A
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["flamezo_points_balance"], 0.0)
        self.assertEqual(res["data"]["tier"], "Bronze")


# ═══════════════════════════════════════════════════════════════════════════════
# get_points_ledger
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetPointsLedger(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        _cleanup_all()
        self.rest = _make_rest()
        self.cust = _make_cust()

    def tearDown(self):
        _cleanup_all()

    def _call(self, phone=_PHONE, **kwargs):
        with mock.patch(_TOKEN_PATCH, return_value=None):
            return get_points_ledger(phone=phone, **kwargs)

    # ── baseline ──────────────────────────────────────────────────────────────

    def test_empty_ledger_for_new_customer(self):
        res = self._call()
        self.assertTrue(res["success"], res)
        d = res["data"]
        self.assertEqual(d["entries"], [])
        self.assertEqual(d["current_balance"], 0.0)
        self.assertEqual(d["total"], 0)
        self.assertFalse(d["has_more"])

    def test_required_keys_in_response(self):
        res = self._call()
        self.assertTrue(res["success"])
        for key in ("entries", "page", "limit", "total", "has_more", "current_balance"):
            self.assertIn(key, res["data"], f"Missing key: {key}")

    # ── entry type mapping ────────────────────────────────────────────────────

    def test_earn_entry_maps_to_type_earn(self):
        _earn(self.cust.name, self.rest.name, 100, reason="Order")
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(len(res["data"]["entries"]), 1)
        self.assertEqual(res["data"]["entries"][0]["type"], "earn")

    def test_earn_with_bonus_reason_maps_to_type_bonus(self):
        _earn(self.cust.name, self.rest.name, 75, reason="Welcome Bonus")
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["entries"][0]["type"], "bonus")

    def test_redeem_entry_maps_to_type_redeem(self):
        _earn(self.cust.name, self.rest.name, 200)
        _redeem(self.cust.name, self.rest.name, 100)
        res = self._call()
        self.assertTrue(res["success"])
        types = {e["type"] for e in res["data"]["entries"]}
        self.assertIn("redeem", types)

    # ── entry fields ──────────────────────────────────────────────────────────

    def test_entry_has_required_fields(self):
        _earn(self.cust.name, self.rest.name, 100)
        res = self._call()
        self.assertTrue(res["success"])
        e = res["data"]["entries"][0]
        for key in ("outlet_name", "outlet_id", "points", "type",
                    "reason", "is_settled", "posting_date", "timestamp"):
            self.assertIn(key, e, f"Missing field: {key}")

    def test_entry_points_value_matches_inserted_coins(self):
        _earn(self.cust.name, self.rest.name, 350)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["entries"][0]["points"], 350.0)

    # ── current_balance correctness ───────────────────────────────────────────

    def test_current_balance_matches_earn_minus_redeem(self):
        _earn(self.cust.name, self.rest.name, 500)
        _redeem(self.cust.name, self.rest.name, 150)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["current_balance"], 350.0)

    def test_current_balance_reflects_redemption(self):
        # Earn 200, redeem all 200 → balance 0
        _earn(self.cust.name, self.rest.name, 200)
        _redeem(self.cust.name, self.rest.name, 200)
        res = self._call()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["current_balance"], 0.0)

    # ── ordering ─────────────────────────────────────────────────────────────

    def test_entries_returned_newest_first(self):
        _earn(self.cust.name, self.rest.name, 100)
        _earn(self.cust.name, self.rest.name, 200)
        res = self._call()
        self.assertTrue(res["success"])
        entries = res["data"]["entries"]
        self.assertEqual(len(entries), 2)
        # Newest creation first → second entry was inserted last
        self.assertEqual(entries[0]["points"], 200.0)
        self.assertEqual(entries[1]["points"], 100.0)

    # ── pagination ────────────────────────────────────────────────────────────

    def test_has_more_true_when_entries_exceed_limit(self):
        _earn(self.cust.name, self.rest.name, 10)
        _earn(self.cust.name, self.rest.name, 20)
        _earn(self.cust.name, self.rest.name, 30)
        res = self._call(limit=2)
        self.assertTrue(res["success"])
        d = res["data"]
        self.assertEqual(len(d["entries"]), 2)
        self.assertTrue(d["has_more"])
        self.assertEqual(d["total"], 3)

    def test_has_more_false_on_last_page(self):
        _earn(self.cust.name, self.rest.name, 10)
        _earn(self.cust.name, self.rest.name, 20)
        res = self._call(page=2, limit=1)
        self.assertTrue(res["success"])
        d = res["data"]
        self.assertEqual(len(d["entries"]), 1)
        self.assertFalse(d["has_more"])

    def test_page_number_reflected_in_response(self):
        res = self._call(page=3, limit=5)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["page"], 3)
        self.assertEqual(res["data"]["limit"], 5)

    def test_limit_capped_at_50(self):
        res = self._call(limit=200)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["limit"], 50)

    # ── auth errors ───────────────────────────────────────────────────────────

    def test_no_phone_no_token_returns_auth_required(self):
        with mock.patch(_TOKEN_PATCH, return_value=None):
            res = get_points_ledger(phone=None)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "AUTH_REQUIRED")

    def test_invalid_phone_returns_invalid_phone_error(self):
        res = self._call(phone="notaphone")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_PHONE")

    # ── cross-customer isolation ──────────────────────────────────────────────

    def test_entries_isolated_to_phone(self):
        cust_b = _make_cust(_PHONE_B)
        _earn(cust_b.name, self.rest.name, 9999)
        res = self._call()  # phone A
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["entries"], [])
        self.assertEqual(res["data"]["current_balance"], 0.0)


if __name__ == "__main__":
    unittest.main()
