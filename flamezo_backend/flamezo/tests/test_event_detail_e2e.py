# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for get_event_detail API (events.py).

Covers:
  Happy path:
    - returns full event fields for active event
    - includes restaurant_name and restaurantCity in response
    - recurring event includes recurring block with weekdays
    - non-recurring event recurring block is {repeatThisEvent: False}

  Access control:
    - inactive event (is_active=0) returns NOT_FOUND error
    - non-existent event_id returns NOT_FOUND error

  Validation:
    - missing event_id throws / returns error
"""

import unittest

import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-EVT-DETAIL"


def _make_rest():
    name = f"{_PREFIX}-R01"
    r = make_restaurant(name, outlet_type="dining")
    return r


def _make_event(restaurant_name, is_active=1, title="Test Event Detail", featured=0,
                recurring=False, status="upcoming"):
    doc = frappe.get_doc({
        "doctype": "Event",
        "restaurant": restaurant_name,
        "title": title,
        "image_src": "https://r2.example.com/events/test.jpg",
        "description": "Test event description",
        "date": frappe.utils.add_days(frappe.utils.today(), 5),
        "time": "19:00:00",
        "location": "Surat, Gujarat",
        "category": "dining",
        "featured": featured,
        "status": status,
        "is_active": is_active,
        "repeat_this_event": 1 if recurring else 0,
        "repeat_on": "Weekly" if recurring else "",
        "monday": 1 if recurring else 0,
        "wednesday": 1 if recurring else 0,
        "friday": 1 if recurring else 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _cleanup():
    frappe.db.sql("DELETE FROM `tabEvent` WHERE title LIKE 'Test Event Detail%'")
    frappe.db.sql("DELETE FROM `tabRestaurant` WHERE name LIKE %s", [f"{_PREFIX}%"])
    frappe.db.commit()


from flamezo_backend.flamezo.api import events as events_api


class TestGetEventDetail(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.event = _make_event(self.rest.name)

    def tearDown(self):
        _cleanup()

    def test_returns_correct_event(self):
        result = events_api.get_event_detail(self.event.name)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["event"]["id"], self.event.name)

    def test_all_fields_present(self):
        result = events_api.get_event_detail(self.event.name)
        evt = result["data"]["event"]
        for field in ("id", "title", "description", "date", "time", "location",
                      "category", "status", "restaurantName"):
            self.assertIn(field, evt)

    def test_includes_restaurant_name(self):
        result = events_api.get_event_detail(self.event.name)
        evt = result["data"]["event"]
        self.assertTrue(len(evt.get("restaurantName", "")) > 0)

    def test_non_recurring_block(self):
        result = events_api.get_event_detail(self.event.name)
        evt = result["data"]["event"]
        self.assertIn("recurring", evt)
        self.assertFalse(evt["recurring"]["repeatThisEvent"])

    def test_recurring_event_includes_weekdays(self):
        rec = _make_event(self.rest.name, title="Test Event Detail Recurring", recurring=True, status="recurring")
        result = events_api.get_event_detail(rec.name)
        evt = result["data"]["event"]
        self.assertTrue(evt["recurring"]["repeatThisEvent"])
        weekdays = evt["recurring"].get("weekdays", [])
        self.assertIn("Monday", weekdays)
        self.assertIn("Wednesday", weekdays)
        self.assertIn("Friday", weekdays)

    def test_inactive_event_returns_not_found(self):
        inactive = _make_event(self.rest.name, title="Test Event Detail Inactive", is_active=0)
        result = events_api.get_event_detail(inactive.name)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NOT_FOUND")

    def test_nonexistent_event_returns_not_found(self):
        result = events_api.get_event_detail("EVENT-FAKE-99999")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NOT_FOUND")

    def test_missing_event_id_returns_error(self):
        result = events_api.get_event_detail(None)
        self.assertFalse(result["success"])

    def test_featured_field_present(self):
        feat = _make_event(self.rest.name, title="Test Event Detail Featured", featured=1)
        result = events_api.get_event_detail(feat.name)
        evt = result["data"]["event"]
        self.assertTrue(evt.get("featured"))
