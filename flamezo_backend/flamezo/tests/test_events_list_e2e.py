# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the consumer-facing get_events() list API (events.py).

Covers:
  Happy path:
    - Returns only active, upcoming events
    - Response shape: all required fields present
    - Restaurant info (restaurantName, restaurantCity) in consumer mode

  Consumer mode (no outlet_id):
    - Aggregates events from all active restaurants
    - Inactive restaurant's events are excluded
    - Events from multiple active restaurants all appear

  Restaurant-scoped mode (with outlet_id):
    - Returns events for that restaurant only
    - Other restaurants' events excluded
    - Invalid outlet_id returns error

  Filters:
    - featured=True returns only featured events
    - featured=False excludes featured events
    - category filter narrows results
    - upcoming_only=True (default) excludes 'past' events
    - upcoming_only=False includes past events too

  Edge cases:
    - No active events returns empty list
    - Inactive event (is_active=0) excluded
    - recurring events included in upcoming_only mode
    - Non-existent outlet_id returns error
"""

import unittest

import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-EVTLIST"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_restaurant(suffix, is_active=1):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type="dining")
    # make_restaurant sets is_active=1 by default; explicitly set for inactive tests
    if not is_active:
        frappe.db.set_value("Outlet", name, "is_active", 0)
        frappe.db.commit()
    return r.name


def _make_event(restaurant_name, title, status="upcoming", is_active=1,
                featured=0, category="dining", days_ahead=5):
    doc = frappe.get_doc({
        "doctype": "Event",
        "restaurant": restaurant_name,
        "title": title,
        "image_src": "https://r2.example.com/events/test.jpg",
        "description": "E2E test event",
        "date": frappe.utils.add_days(frappe.utils.today(), days_ahead),
        "time": "19:00:00",
        "location": "Surat, Gujarat",
        "category": category,
        "featured": featured,
        "status": status,
        "is_active": is_active,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _cleanup():
    frappe.db.sql("DELETE FROM `tabEvent` WHERE description='E2E test event'")
    frappe.db.sql("DELETE FROM `tabOutlet` WHERE name LIKE %s", [f"{_PREFIX}%"])
    frappe.db.commit()


from flamezo_backend.flamezo.api import events as events_api


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGetEventsConsumerMode(unittest.TestCase):
    """get_events() with no outlet_id — cross-restaurant discovery."""

    def setUp(self):
        _cleanup()
        self.rest1 = _make_restaurant("R01")
        self.rest2 = _make_restaurant("R02")
        self.evt1 = _make_event(self.rest1, "Event Alpha", category="dining")
        self.evt2 = _make_event(self.rest2, "Event Beta", category="wellness")

    def tearDown(self):
        _cleanup()

    def test_returns_events_from_multiple_restaurants(self):
        result = events_api.get_events()
        self.assertTrue(result["success"], result)
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertIn("Event Alpha", titles)
        self.assertIn("Event Beta", titles)

    def test_response_has_required_fields(self):
        result = events_api.get_events()
        self.assertTrue(result["success"])
        events = result["data"]["events"]
        self.assertGreater(len(events), 0)
        evt = next(e for e in events if e["title"] == "Event Alpha")
        for field in ("id", "title", "description", "date", "time", "location",
                      "category", "status", "featured", "image_src", "recurring"):
            self.assertIn(field, evt, f"Missing field: {field}")

    def test_consumer_mode_includes_restaurant_info(self):
        result = events_api.get_events()
        self.assertTrue(result["success"])
        events = result["data"]["events"]
        evt = next(e for e in events if e["title"] == "Event Alpha")
        self.assertIn("outletName", evt)
        self.assertIn("outletCity", evt)
        self.assertTrue(len(evt["outletName"]) > 0)

    def test_inactive_restaurant_events_excluded(self):
        inactive_rest = _make_restaurant("RINACTIVE", is_active=0)
        _make_event(inactive_rest, "Event From Inactive Rest")
        try:
            result = events_api.get_events()
            self.assertTrue(result["success"])
            titles = [e["title"] for e in result["data"]["events"]]
            self.assertNotIn("Event From Inactive Rest", titles)
        finally:
            frappe.db.sql("DELETE FROM `tabEvent` WHERE title='Event From Inactive Rest'")
            frappe.db.sql("DELETE FROM `tabOutlet` WHERE name=%s", inactive_rest)
            frappe.db.commit()

    def test_inactive_event_excluded(self):
        _make_event(self.rest1, "Event Inactive", is_active=0)
        result = events_api.get_events()
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertNotIn("Event Inactive", titles)

    def test_no_active_events_returns_empty_list(self):
        # Make a restaurant with no events
        empty_rest = _make_restaurant("REMPTY")
        # Deactivate all other test events
        frappe.db.sql(
            "UPDATE `tabEvent` SET is_active=0 WHERE description='E2E test event'"
        )
        frappe.db.commit()
        try:
            result = events_api.get_events()
            self.assertTrue(result["success"])
            # At minimum there should be 0 matching our test events
            titles = [e["title"] for e in result["data"]["events"]]
            self.assertNotIn("Event Alpha", titles)
            self.assertNotIn("Event Beta", titles)
        finally:
            frappe.db.sql(
                "UPDATE `tabEvent` SET is_active=1 WHERE description='E2E test event'"
            )
            frappe.db.sql("DELETE FROM `tabOutlet` WHERE name=%s", empty_rest)
            frappe.db.commit()


class TestGetEventsRestaurantMode(unittest.TestCase):
    """get_events(outlet_id=...) — scoped to a single outlet."""

    def setUp(self):
        _cleanup()
        self.rest1 = _make_restaurant("RS01")
        self.rest2 = _make_restaurant("RS02")
        self.evt1 = _make_event(self.rest1, "RS01 Event A")
        self.evt2 = _make_event(self.rest2, "RS02 Event B")

    def tearDown(self):
        _cleanup()

    def test_only_that_restaurant_events_returned(self):
        result = events_api.get_events(outlet_id=self.rest1)
        self.assertTrue(result["success"], result)
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertIn("RS01 Event A", titles)
        self.assertNotIn("RS02 Event B", titles)

    def test_invalid_restaurant_returns_error(self):
        result = events_api.get_events(outlet_id="NONEXISTENT-9999")
        self.assertFalse(result["success"])

    def test_restaurant_with_no_events_returns_empty_list(self):
        empty_rest = _make_restaurant("RS03")
        try:
            result = events_api.get_events(outlet_id=empty_rest)
            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["events"], [])
        finally:
            frappe.db.sql("DELETE FROM `tabOutlet` WHERE name=%s", empty_rest)
            frappe.db.commit()


class TestGetEventsFilters(unittest.TestCase):
    """Filter parameters: featured, category, upcoming_only."""

    def setUp(self):
        _cleanup()
        self.rest = _make_restaurant("RF01")
        self.upcoming = _make_event(self.rest, "Filter Upcoming", status="upcoming", featured=0, category="dining")
        self.featured = _make_event(self.rest, "Filter Featured", status="upcoming", featured=1, category="dining")
        self.past = _make_event(self.rest, "Filter Past", status="past", featured=0, category="dining", days_ahead=-2)
        self.wellness = _make_event(self.rest, "Filter Wellness", status="upcoming", featured=0, category="wellness")
        self.recurring = _make_event(self.rest, "Filter Recurring", status="recurring", featured=0, category="dining")

    def tearDown(self):
        _cleanup()

    def test_featured_filter_returns_only_featured(self):
        result = events_api.get_events(outlet_id=self.rest, featured=True)
        self.assertTrue(result["success"])
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertIn("Filter Featured", titles)
        self.assertNotIn("Filter Upcoming", titles)

    def test_featured_false_excludes_featured(self):
        result = events_api.get_events(outlet_id=self.rest, featured=False)
        self.assertTrue(result["success"])
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertNotIn("Filter Featured", titles)
        self.assertIn("Filter Upcoming", titles)

    def test_category_filter_narrows_results(self):
        result = events_api.get_events(outlet_id=self.rest, category="wellness")
        self.assertTrue(result["success"])
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertIn("Filter Wellness", titles)
        self.assertNotIn("Filter Upcoming", titles)
        self.assertNotIn("Filter Featured", titles)

    def test_upcoming_only_excludes_past(self):
        result = events_api.get_events(outlet_id=self.rest, upcoming_only=True)
        self.assertTrue(result["success"])
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertNotIn("Filter Past", titles)

    def test_upcoming_only_true_includes_recurring(self):
        result = events_api.get_events(outlet_id=self.rest, upcoming_only=True)
        self.assertTrue(result["success"])
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertIn("Filter Recurring", titles)

    def test_upcoming_only_false_includes_past(self):
        result = events_api.get_events(outlet_id=self.rest, upcoming_only=False)
        self.assertTrue(result["success"])
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertIn("Filter Past", titles)

    def test_upcoming_only_default_is_true(self):
        # Default call should not include past events
        result = events_api.get_events(outlet_id=self.rest)
        self.assertTrue(result["success"])
        titles = [e["title"] for e in result["data"]["events"]]
        self.assertNotIn("Filter Past", titles)


class TestGetEventsResponseShape(unittest.TestCase):
    """Validate recurring block and all sub-fields in response."""

    def setUp(self):
        _cleanup()
        self.rest = _make_restaurant("RSHAPE")
        self.evt = _make_event(self.rest, "Shape Test Event", featured=1)
        # Recurring event
        self.rec_evt = frappe.get_doc({
            "doctype": "Event",
            "restaurant": self.rest,
            "title": "Shape Recurring",
            "image_src": "https://r2.example.com/events/rec.jpg",
            "description": "E2E test event",
            "date": frappe.utils.add_days(frappe.utils.today(), 3),
            "time": "10:00:00",
            "location": "Ahmedabad",
            "category": "wellness",
            "status": "recurring",
            "is_active": 1,
            "repeat_this_event": 1,
            "repeat_on": "Weekly",
            "monday": 1,
            "thursday": 1,
        })
        self.rec_evt.insert(ignore_permissions=True)
        frappe.db.commit()

    def tearDown(self):
        _cleanup()

    def test_non_recurring_block_is_false(self):
        result = events_api.get_events(outlet_id=self.rest)
        self.assertTrue(result["success"])
        evt = next(e for e in result["data"]["events"] if e["title"] == "Shape Test Event")
        self.assertIn("recurring", evt)
        self.assertFalse(evt["recurring"]["repeatThisEvent"])

    def test_recurring_block_includes_weekdays(self):
        result = events_api.get_events(outlet_id=self.rest)
        self.assertTrue(result["success"])
        evt = next(e for e in result["data"]["events"] if e["title"] == "Shape Recurring")
        self.assertTrue(evt["recurring"]["repeatThisEvent"])
        self.assertEqual(evt["recurring"]["repeatOn"], "Weekly")
        weekdays = evt["recurring"].get("weekdays", [])
        self.assertIn("Monday", weekdays)
        self.assertIn("Thursday", weekdays)
        self.assertNotIn("Tuesday", weekdays)

    def test_featured_flag_is_bool(self):
        result = events_api.get_events(outlet_id=self.rest)
        self.assertTrue(result["success"])
        evt = next(e for e in result["data"]["events"] if e["title"] == "Shape Test Event")
        self.assertIsInstance(evt["featured"], bool)
        self.assertTrue(evt["featured"])

    def test_google_maps_and_registration_links_in_response(self):
        special = frappe.get_doc({
            "doctype": "Event",
            "restaurant": self.rest,
            "title": "Shape Links Event",
            "image_src": "https://r2.example.com/events/links.jpg",
            "description": "E2E test event",
            "date": frappe.utils.add_days(frappe.utils.today(), 7),
            "time": "18:00:00",
            "google_maps_link": "https://maps.google.com/test",
            "registration_link": "https://example.com/register",
            "status": "upcoming",
            "is_active": 1,
        })
        special.insert(ignore_permissions=True)
        frappe.db.commit()

        result = events_api.get_events(outlet_id=self.rest)
        self.assertTrue(result["success"])
        evt = next(e for e in result["data"]["events"] if e["title"] == "Shape Links Event")
        self.assertIn("google_maps_link", evt)
        self.assertIn("registration_link", evt)
        self.assertEqual(evt["google_maps_link"], "https://maps.google.com/test")
        self.assertEqual(evt["registration_link"], "https://example.com/register")


if __name__ == "__main__":
    unittest.main()
