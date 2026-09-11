# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""E2E tests for api/creator_rate_cards.py — Phase 1 of the marketplace build."""

import unittest
from unittest.mock import patch

import frappe

from flamezo_backend.flamezo.api import creator_rate_cards as rate_cards

_PHONE = "9300000801"


def _cleanup():
	frappe.db.sql(
		"DELETE FROM `tabCreator Rate Card` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)",
		_PHONE,
	)
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestCreatorRateCards(unittest.TestCase):
	def setUp(self):
		_cleanup()
		self._session_patch = patch(
			"flamezo_backend.flamezo.api.creator_rate_cards.has_active_customer_session", return_value=True
		)
		self._session_patch.start()

		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator",
			"customer_phone": _PHONE,
			"display_name": "RateCardTestCreator",
			"status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		self._session_patch.stop()
		_cleanup()

	# ── set / upsert ─────────────────────────────────────────────────────

	def test_set_creates_new_card(self):
		result = rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=800)
		self.assertTrue(result["success"])
		card = frappe.get_doc("Creator Rate Card", result["data"]["rate_card_id"])
		self.assertEqual(card.price_inr, 800)
		self.assertEqual(card.creator, self.creator.name)

	def test_set_upserts_not_duplicates(self):
		first = rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=800)
		second = rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=1200)
		self.assertEqual(first["data"]["rate_card_id"], second["data"]["rate_card_id"])
		count = frappe.db.count("Creator Rate Card", {"creator": self.creator.name, "deliverable_type": "native_chills"})
		self.assertEqual(count, 1)
		self.assertEqual(frappe.db.get_value("Creator Rate Card", second["data"]["rate_card_id"], "price_inr"), 1200)

	def test_set_barter_only_with_zero_price_succeeds(self):
		result = rate_cards.set_my_rate_card(_PHONE, "instagram_story", price_inr=0, accepts_barter=1, barter_min_value_inr=300)
		self.assertTrue(result["success"])

	def test_set_neither_price_nor_barter_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=0, accepts_barter=0)

	def test_set_negative_price_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=-100)

	def test_set_unknown_deliverable_type_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			rate_cards.set_my_rate_card(_PHONE, "carrier_pigeon", price_inr=100)

	def test_set_without_verified_session_throws(self):
		self._session_patch.stop()
		with self.assertRaises(frappe.exceptions.AuthenticationError):
			rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=100)
		self._session_patch.start()

	# ── get_my_rate_cards ────────────────────────────────────────────────

	def test_get_my_rate_cards_returns_only_own(self):
		other_phone = "9300000802"
		other = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": other_phone,
			"display_name": "Other", "status": "approved",
		})
		other.insert(ignore_permissions=True)
		frappe.get_doc({
			"doctype": "Creator Rate Card", "creator": other.name,
			"deliverable_type": "native_chills", "price_inr": 500,
		}).insert(ignore_permissions=True)

		rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=800)
		result = rate_cards.get_my_rate_cards(_PHONE)

		self.assertEqual(len(result["data"]["rate_cards"]), 1)
		self.assertEqual(result["data"]["rate_cards"][0]["price_inr"], 800)

		frappe.db.sql("DELETE FROM `tabCreator Rate Card` WHERE creator=%s", other.name)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", other.name)
		frappe.db.commit()

	# ── get_creator_rate_cards (public) ──────────────────────────────────

	def test_get_creator_rate_cards_public_no_session_needed(self):
		rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=800)
		result = rate_cards.get_creator_rate_cards(self.creator.name)
		self.assertTrue(result["success"])
		self.assertEqual(len(result["data"]["rate_cards"]), 1)

	def test_get_creator_rate_cards_excludes_inactive(self):
		rate_cards.set_my_rate_card(_PHONE, "native_chills", price_inr=800)
		frappe.db.set_value(
			"Creator Rate Card", {"creator": self.creator.name, "deliverable_type": "native_chills"}, "is_active", 0
		)
		result = rate_cards.get_creator_rate_cards(self.creator.name)
		self.assertEqual(len(result["data"]["rate_cards"]), 0)

	def test_get_creator_rate_cards_unknown_creator_throws(self):
		with self.assertRaises(frappe.exceptions.DoesNotExistError):
			rate_cards.get_creator_rate_cards("NOT-A-REAL-CREATOR")


if __name__ == "__main__":
	unittest.main()
