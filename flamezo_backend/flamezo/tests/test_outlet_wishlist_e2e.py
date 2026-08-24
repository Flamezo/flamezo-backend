# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the Outlet Wishlist ("save"/heart) feature (api/outlet.py).

Unlike Chills likes/saves, this is a plain synchronous DB toggle on the
`Outlet Save` doctype — outlet saves are a low-frequency personal-list
action, so there's no Redis-buffered hot path here (see the docstring on
save_outlet in outlet.py). Response shape: every endpoint returns
{"success": True, "data": {...}} — all assertions read through result["data"].

DocTypes under test:
  Outlet Save — per-phone save record

Covers:
  save_outlet:
    - toggle on -> saved=True, row exists, saves_count updated
    - toggle off -> saved=False, row deleted, saves_count back down
    - phone isolation (two phones independent)
    - missing phone / outlet_id / nonexistent outlet throws
    - requires a verified session (unverified phone throws)

  is_outlet_saved:
    - true after save, false before/after unsave
    - guest (no phone) / unverified phone -> always False, never throws

  get_my_saved_outlet_ids:
    - returns exactly the ids this phone saved, none from another phone
    - requires a verified session

  get_saved_outlets:
    - returns full outlet cards, most-recently-saved first
    - cursor pagination (two pages, no overlap, no duplicates)
    - phone isolation
    - excludes inactive outlets
    - isSaved=True on every item (definitionally)
    - requires a verified session
"""

import unittest
from unittest.mock import patch

import frappe
from flamezo_backend.flamezo.api import outlet as outlet_api
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-WISHLIST"
_PHONE_A = "9800000101"
_PHONE_B = "9800000102"


def _verified_session():
    """save_outlet/get_saved_outlets require a real verified session —
    outlet.py imports has_active_customer_session by name, so the patch
    target is outlet.py's own bound reference (same gotcha documented in
    test_chills_e2e.py / test_clubs_e2e.py)."""
    return patch("flamezo_backend.flamezo.api.outlet.has_active_customer_session", return_value=True)


def _make_rest(suffix="01", **kwargs):
    name = f"{_PREFIX}-R{suffix}"
    return make_restaurant(name, outlet_type="dining", **kwargs)


def _cleanup():
    frappe.db.sql("DELETE FROM `tabOutlet Save` WHERE customer_phone IN (%s, %s)", [_PHONE_A, _PHONE_B])
    frappe.db.sql("DELETE FROM `tabOutlet` WHERE name LIKE %s", [f"{_PREFIX}%"])
    frappe.db.commit()


class TestSaveOutlet(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()

    def tearDown(self):
        _cleanup()

    def test_save_sets_true(self):
        with _verified_session():
            result = outlet_api.save_outlet(self.rest.name, _PHONE_A)["data"]
        self.assertTrue(result["saved"])
        self.assertEqual(result["saves_count"], 1)
        self.assertTrue(frappe.db.exists("Outlet Save", {"outlet": self.rest.name, "customer_phone": _PHONE_A}))

    def test_unsave_sets_false(self):
        with _verified_session():
            outlet_api.save_outlet(self.rest.name, _PHONE_A)
            result = outlet_api.save_outlet(self.rest.name, _PHONE_A)["data"]
        self.assertFalse(result["saved"])
        self.assertEqual(result["saves_count"], 0)
        self.assertFalse(frappe.db.exists("Outlet Save", {"outlet": self.rest.name, "customer_phone": _PHONE_A}))

    def test_phone_isolation(self):
        with _verified_session():
            outlet_api.save_outlet(self.rest.name, _PHONE_A)
            result_b = outlet_api.save_outlet(self.rest.name, _PHONE_B)["data"]
        self.assertTrue(result_b["saved"])
        self.assertEqual(result_b["saves_count"], 2)
        with _verified_session():
            outlet_api.save_outlet(self.rest.name, _PHONE_A)  # unsave A
        self.assertTrue(frappe.db.exists("Outlet Save", {"outlet": self.rest.name, "customer_phone": _PHONE_B}))
        self.assertFalse(frappe.db.exists("Outlet Save", {"outlet": self.rest.name, "customer_phone": _PHONE_A}))

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            outlet_api.save_outlet(self.rest.name, None)

    def test_missing_outlet_id_throws(self):
        with _verified_session():
            with self.assertRaises(Exception):
                outlet_api.save_outlet(None, _PHONE_A)

    def test_nonexistent_outlet_throws(self):
        with _verified_session():
            with self.assertRaises(frappe.exceptions.DoesNotExistError):
                outlet_api.save_outlet("OUTLET-DOES-NOT-EXIST", _PHONE_A)

    def test_unverified_session_throws(self):
        with patch("flamezo_backend.flamezo.api.outlet.has_active_customer_session", return_value=False):
            with self.assertRaises(frappe.exceptions.AuthenticationError):
                outlet_api.save_outlet(self.rest.name, _PHONE_A)


class TestIsOutletSaved(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()

    def tearDown(self):
        _cleanup()

    def test_true_after_save(self):
        with _verified_session():
            outlet_api.save_outlet(self.rest.name, _PHONE_A)
            result = outlet_api.is_outlet_saved(self.rest.name, _PHONE_A)["data"]
        self.assertTrue(result["saved"])

    def test_false_before_save(self):
        with _verified_session():
            result = outlet_api.is_outlet_saved(self.rest.name, _PHONE_A)["data"]
        self.assertFalse(result["saved"])

    def test_false_after_unsave(self):
        with _verified_session():
            outlet_api.save_outlet(self.rest.name, _PHONE_A)
            outlet_api.save_outlet(self.rest.name, _PHONE_A)
            result = outlet_api.is_outlet_saved(self.rest.name, _PHONE_A)["data"]
        self.assertFalse(result["saved"])

    def test_guest_never_throws_and_is_false(self):
        result = outlet_api.is_outlet_saved(self.rest.name, None)["data"]
        self.assertFalse(result["saved"])

    def test_unverified_phone_is_false_not_throw(self):
        with patch("flamezo_backend.flamezo.api.outlet.has_active_customer_session", return_value=False):
            result = outlet_api.is_outlet_saved(self.rest.name, _PHONE_A)["data"]
        self.assertFalse(result["saved"])

    def test_missing_outlet_id_returns_false_not_throw(self):
        result = outlet_api.is_outlet_saved(None, _PHONE_A)["data"]
        self.assertFalse(result["saved"])


class TestGetMySavedOutletIds(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest1 = _make_rest("01")
        self.rest2 = _make_rest("02")

    def tearDown(self):
        _cleanup()

    def test_returns_only_this_phones_saves(self):
        with _verified_session():
            outlet_api.save_outlet(self.rest1.name, _PHONE_A)
            outlet_api.save_outlet(self.rest2.name, _PHONE_A)
            outlet_api.save_outlet(self.rest1.name, _PHONE_B)
            result = outlet_api.get_my_saved_outlet_ids(_PHONE_A)["data"]
        self.assertEqual(set(result["outlet_ids"]), {self.rest1.name, self.rest2.name})

    def test_empty_when_nothing_saved(self):
        with _verified_session():
            result = outlet_api.get_my_saved_outlet_ids(_PHONE_A)["data"]
        self.assertEqual(result["outlet_ids"], [])

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            outlet_api.get_my_saved_outlet_ids(None)

    def test_unverified_session_throws(self):
        with patch("flamezo_backend.flamezo.api.outlet.has_active_customer_session", return_value=False):
            with self.assertRaises(frappe.exceptions.AuthenticationError):
                outlet_api.get_my_saved_outlet_ids(_PHONE_A)


class TestGetSavedOutlets(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rests = [_make_rest(f"{i:02d}") for i in range(1, 6)]

    def tearDown(self):
        _cleanup()

    def test_returns_saved_outlets_newest_first(self):
        with _verified_session():
            for r in self.rests[:3]:
                outlet_api.save_outlet(r.name, _PHONE_A)
            result = outlet_api.get_saved_outlets(_PHONE_A)["data"]
        ids = [o["id"] for o in result["outlets"]]
        self.assertEqual(ids, [self.rests[2].name, self.rests[1].name, self.rests[0].name])
        self.assertTrue(all(o["isSaved"] is True for o in result["outlets"]))

    def test_pagination_two_pages_no_overlap(self):
        with _verified_session():
            for r in self.rests:
                outlet_api.save_outlet(r.name, _PHONE_A)
            page1 = outlet_api.get_saved_outlets(_PHONE_A, limit=3)["data"]
            self.assertTrue(page1["has_more"])
            self.assertEqual(len(page1["outlets"]), 3)
            page2 = outlet_api.get_saved_outlets(_PHONE_A, cursor=page1["next_cursor"], limit=3)["data"]
        ids1 = {o["id"] for o in page1["outlets"]}
        ids2 = {o["id"] for o in page2["outlets"]}
        self.assertEqual(len(ids1 & ids2), 0)
        self.assertEqual(len(ids1) + len(ids2), 5)
        self.assertFalse(page2["has_more"])

    def test_phone_isolation(self):
        with _verified_session():
            outlet_api.save_outlet(self.rests[0].name, _PHONE_A)
            outlet_api.save_outlet(self.rests[1].name, _PHONE_B)
            result_a = outlet_api.get_saved_outlets(_PHONE_A)["data"]
        ids = [o["id"] for o in result_a["outlets"]]
        self.assertEqual(ids, [self.rests[0].name])

    def test_excludes_inactive_outlets(self):
        inactive = _make_rest("99", is_active=0)
        with _verified_session():
            outlet_api.save_outlet(inactive.name, _PHONE_A)
            outlet_api.save_outlet(self.rests[0].name, _PHONE_A)
            result = outlet_api.get_saved_outlets(_PHONE_A)["data"]
        ids = [o["id"] for o in result["outlets"]]
        self.assertNotIn(inactive.name, ids)
        self.assertIn(self.rests[0].name, ids)

    def test_unsaving_removes_from_list(self):
        with _verified_session():
            outlet_api.save_outlet(self.rests[0].name, _PHONE_A)
            outlet_api.save_outlet(self.rests[0].name, _PHONE_A)  # unsave
            result = outlet_api.get_saved_outlets(_PHONE_A)["data"]
        self.assertEqual(result["outlets"], [])

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            outlet_api.get_saved_outlets(None)

    def test_unverified_session_throws(self):
        with patch("flamezo_backend.flamezo.api.outlet.has_active_customer_session", return_value=False):
            with self.assertRaises(frappe.exceptions.AuthenticationError):
                outlet_api.get_saved_outlets(_PHONE_A)
