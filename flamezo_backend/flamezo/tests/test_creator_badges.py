# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Tests for utils/creator_badges.py's Phase 5 additions — the stored
Creator Badge history (sync_creator_badge / sync_all_creator_badges /
get_creator_badge_history) and the doctype controller's single-current
invariant. The live-tier computation itself (_compute_badge_details)
is already covered indirectly via test_collab_disputes.py's badge
integration tests — this file focuses on what's new: persistence.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from flamezo_backend.flamezo.api import collab_deals as deals
from flamezo_backend.flamezo.tests.utils import make_restaurant
from flamezo_backend.flamezo.utils import creator_badges

_PREFIX = "TEST-BADGE"
_PHONE = "9300000951"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabCreator Badge` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone=%s)", _PHONE)
	frappe.db.sql(f"DELETE FROM `tabCreator Collab Invite` WHERE outlet LIKE '{_PREFIX}%%'")
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone=%s", _PHONE)
	frappe.db.commit()


class TestCreatorBadgesPersistence(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.outlet = f"{_PREFIX}-OUTLET"
		if not frappe.db.exists("Outlet", cls.outlet):
			make_restaurant(cls.outlet, outlet_type="dining", city="Surat")

	def setUp(self):
		_cleanup()
		self.creator = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": _PHONE,
			"display_name": "BadgeTestCreator", "status": "approved",
		})
		self.creator.insert(ignore_permissions=True)
		self.invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name,
		})
		self.invite.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		_cleanup()

	def _released_deal(self, deadline_offset=0):
		deal = frappe.get_doc({
			"doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
			"direct_invite": self.invite.name, "deal_type": "barter", "fair_value_inr": 50,
			"terms_json": "{}", "deadline": add_days(today(), deadline_offset or 7),
		})
		deal.insert(ignore_permissions=True)
		deal.status = "accepted"
		deal.save(ignore_permissions=True)
		deal.status = "delivered"
		deal.save(ignore_permissions=True)
		deal.status = "released"
		deal.save(ignore_permissions=True)
		return deal

	# ── sync_creator_badge — no-op / new earn ────────────────────────────

	def test_sync_no_deals_is_new_creator_no_row_written(self):
		result = creator_badges.sync_creator_badge(self.creator.name)
		self.assertFalse(result["changed"])
		self.assertEqual(result["tier"], "new_creator")
		self.assertEqual(frappe.db.count("Creator Badge", {"creator": self.creator.name}), 0)

	def test_sync_writes_verified_creator_on_first_qualifying_state(self):
		for _ in range(3):
			self._released_deal()
		result = creator_badges.sync_creator_badge(self.creator.name)
		self.assertTrue(result["changed"])
		self.assertEqual(result["tier"], "verified_creator")

		row = frappe.db.get_value(
			"Creator Badge", {"creator": self.creator.name, "is_current": 1},
			["badge_type", "earned_at", "lost_at"], as_dict=True,
		)
		self.assertEqual(row.badge_type, "verified_creator")
		self.assertIsNotNone(row.earned_at)
		self.assertIsNone(row.lost_at)

	def test_sync_is_idempotent_when_tier_unchanged(self):
		for _ in range(3):
			self._released_deal()
		creator_badges.sync_creator_badge(self.creator.name)
		result = creator_badges.sync_creator_badge(self.creator.name)  # same tier again
		self.assertFalse(result["changed"])
		self.assertEqual(frappe.db.count("Creator Badge", {"creator": self.creator.name}), 1)

	def test_sync_criteria_snapshot_records_real_numbers(self):
		for _ in range(3):
			self._released_deal()
		creator_badges.sync_creator_badge(self.creator.name)
		import json
		snapshot = json.loads(
			frappe.db.get_value("Creator Badge", {"creator": self.creator.name, "is_current": 1}, "criteria_snapshot_json")
		)
		self.assertEqual(snapshot["released_count"], 3)

	# ── tier transitions supersede the previous row ──────────────────────

	def test_sync_upgrade_supersedes_previous_row(self):
		for _ in range(3):
			self._released_deal()
		creator_badges.sync_creator_badge(self.creator.name)  # verified_creator

		self.invite.merchant_rating = 5
		self.invite.save(ignore_permissions=True)
		for _ in range(12):  # 15 total, plus the rating -> top_rated territory
			self._released_deal()
		frappe.db.set_value(
			"Collab Deal", {"creator": self.creator.name}, "creation",
			frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-200),
		)
		result = creator_badges.sync_creator_badge(self.creator.name)
		self.assertTrue(result["changed"])
		self.assertIn(result["tier"], ("top_rated", "elite_creator"))

		old_row = frappe.db.get_value(
			"Creator Badge", {"creator": self.creator.name, "badge_type": "verified_creator"},
			["is_current", "lost_at"], as_dict=True,
		)
		self.assertEqual(old_row.is_current, 0)
		self.assertIsNotNone(old_row.lost_at)

		current = frappe.db.get_value("Creator Badge", {"creator": self.creator.name, "is_current": 1}, "badge_type")
		self.assertEqual(current, result["tier"])

	def test_sync_downgrade_to_new_creator_leaves_no_current_row(self):
		"""A creator who drops back to new_creator (e.g. an anomaly flag
		right after their 3rd deal, within the 90-day verified window)
		should have their old badge marked not-current with no new row
		written — new_creator is the absence state, not an earned tier."""
		for _ in range(3):
			self._released_deal()
		creator_badges.sync_creator_badge(self.creator.name)
		self.assertEqual(frappe.db.count("Creator Badge", {"creator": self.creator.name, "is_current": 1}), 1)

		with patch(
			"flamezo_backend.flamezo.utils.creator_badges._compute_badge_details",
			return_value=("new_creator", {"released_count": 3}),
		):
			result = creator_badges.sync_creator_badge(self.creator.name)
		self.assertTrue(result["changed"])
		self.assertEqual(result["tier"], "new_creator")
		self.assertEqual(frappe.db.count("Creator Badge", {"creator": self.creator.name, "is_current": 1}), 0)

	# ── doctype controller invariant ─────────────────────────────────────

	def test_controller_rejects_second_current_row_for_same_creator(self):
		frappe.get_doc({
			"doctype": "Creator Badge", "creator": self.creator.name,
			"badge_type": "verified_creator", "is_current": 1,
		}).insert(ignore_permissions=True)
		with self.assertRaises(frappe.exceptions.ValidationError):
			frappe.get_doc({
				"doctype": "Creator Badge", "creator": self.creator.name,
				"badge_type": "top_rated", "is_current": 1,
			}).insert(ignore_permissions=True)

	# ── sync_all_creator_badges ───────────────────────────────────────────

	def test_sync_all_scans_creators_with_released_deals(self):
		self._released_deal()
		other = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": "9300000952",
			"display_name": "OtherBadgeCreator", "status": "approved",
		})
		other.insert(ignore_permissions=True)
		# a creator with zero released deals must not appear in the scan
		result = creator_badges.sync_all_creator_badges()
		self.assertGreaterEqual(result["scanned"], 1)
		self.assertEqual(result["errors"], 0)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", other.name)
		frappe.db.commit()

	def test_sync_all_one_bad_creator_does_not_block_others(self):
		"""One creator's sync raising must not stop the rest from being
		reconciled — scoped to this test's own creator via a real deal
		plus a side-effect keyed off that specific name, so leftover
		Collab Deal rows from other test modules sharing this DB don't
		make the assertion flaky."""
		self._released_deal()
		other = frappe.get_doc({
			"doctype": "Flamezo Creator", "customer_phone": "9300000953",
			"display_name": "OtherOkCreator", "status": "approved",
		})
		other.insert(ignore_permissions=True)
		other_invite = frappe.get_doc({
			"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": other.name,
		})
		other_invite.insert(ignore_permissions=True)
		other_deals = []
		for _ in range(3):  # clears the verified_creator floor (>= 3 released)
			d = frappe.get_doc({
				"doctype": "Collab Deal", "creator": other.name, "outlet": self.outlet,
				"direct_invite": other_invite.name, "deal_type": "barter", "fair_value_inr": 50,
				"terms_json": "{}", "deadline": add_days(today(), 7),
			})
			d.insert(ignore_permissions=True)
			d.status = "accepted"; d.save(ignore_permissions=True)
			d.status = "delivered"; d.save(ignore_permissions=True)
			d.status = "released"; d.save(ignore_permissions=True)
			other_deals.append(d.name)

		real_sync = creator_badges.sync_creator_badge

		def _boom_for_this_creator_only(creator_name):
			if creator_name == self.creator.name:
				raise Exception("boom")
			return real_sync(creator_name)

		with patch(
			"flamezo_backend.flamezo.utils.creator_badges.sync_creator_badge",
			side_effect=_boom_for_this_creator_only,
		):
			result = creator_badges.sync_all_creator_badges()

		self.assertGreaterEqual(result["errors"], 1)
		# The other, healthy creator still got reconciled despite the failure.
		self.assertTrue(frappe.db.exists("Creator Badge", {"creator": other.name, "is_current": 1}))

		frappe.db.sql("DELETE FROM `tabCreator Badge` WHERE creator=%s", other.name)
		frappe.db.sql("DELETE FROM `tabCollab Deal` WHERE creator=%s", other.name)
		frappe.db.sql("DELETE FROM `tabCreator Collab Invite` WHERE name=%s", other_invite.name)
		frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE name=%s", other.name)
		frappe.db.commit()

	# ── get_creator_badge_history ─────────────────────────────────────────

	def test_get_creator_badge_history_empty_for_new_creator(self):
		self.assertEqual(creator_badges.get_creator_badge_history(self.creator.name), [])

	def test_get_creator_badge_history_newest_first_with_parsed_snapshot(self):
		for _ in range(3):
			self._released_deal()
		creator_badges.sync_creator_badge(self.creator.name)
		history = creator_badges.get_creator_badge_history(self.creator.name)
		self.assertEqual(len(history), 1)
		self.assertEqual(history[0]["badge_type"], "verified_creator")
		self.assertEqual(history[0]["criteria_snapshot"]["released_count"], 3)

	# ── enforcement stays live, unaffected by the stored table ───────────

	def test_meets_minimum_tier_unaffected_by_stale_stored_row(self):
		"""Regression guard for the module's own design principle: even
		if a stored Creator Badge row is stale (sync hasn't run yet),
		meets_minimum_tier must answer from the live computation, never
		the stored table — a creator who just qualified shouldn't be
		locked out of a gig until next Monday's job runs."""
		for _ in range(3):
			self._released_deal()
		# No sync_creator_badge call — the stored table is deliberately
		# left empty/stale here.
		self.assertTrue(creator_badges.meets_minimum_tier(self.creator.name, "verified_creator"))
		self.assertEqual(frappe.db.count("Creator Badge", {"creator": self.creator.name}), 0)


if __name__ == "__main__":
	unittest.main()
