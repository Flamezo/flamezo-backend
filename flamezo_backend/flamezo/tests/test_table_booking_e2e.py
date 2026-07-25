# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Consumer Table Booking API (table_booking_consumer.py).

Covers:
  create_table_booking:
    - valid creation returns booking_id + Pending status
    - restaurant not found → DoesNotExistError
    - inactive restaurant rejected
    - past date rejected
    - malformed date rejected
    - missing restaurant_id rejected
    - missing date rejected
    - missing time_slot rejected
    - number_of_diners < 1 rejected
    - missing phone rejected

  get_my_table_bookings:
    - returns only this phone's bookings
    - other phone's bookings excluded
    - status filter (Pending / Confirmed)
    - pagination (has_more, page)
    - missing phone rejected

  get_table_booking_detail:
    - returns correct booking fields
    - wrong phone → PermissionError
    - non-existent booking → DoesNotExistError
    - missing booking_id rejected

  cancel_table_booking:
    - Pending booking → Cancelled, sets cancelled_at
    - Confirmed booking → Cancelled
    - Completed booking → not cancellable (ValidationError)
    - Rejected booking → not cancellable (ValidationError)
    - already Cancelled → not cancellable
    - wrong phone → PermissionError
    - non-existent booking → DoesNotExistError
    - missing phone rejected
    - missing booking_id rejected
"""

import unittest
from frappe.utils import add_days, today

import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-TBK"
_PHONE_A = "9600000001"
_PHONE_B = "9600000002"


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_rest(suffix="01", is_active=1):
    name = f"{_PREFIX}-R{suffix}"
    r = make_restaurant(name, outlet_type="dining")
    frappe.db.set_value("Restaurant", r.name, "is_active", is_active)
    frappe.db.commit()
    return r


def _make_booking(restaurant, phone=_PHONE_A, date=None, time_slot="19:00 – 21:00",
                  diners=2, status="pending"):
    date = date or add_days(today(), 2)
    doc = frappe.get_doc({
        "doctype": "Table Booking",
        "restaurant": restaurant,
        "customer_phone": phone,
        "customer_name": f"Guest {phone[-4:]}",
        "date": date,
        "time_slot": time_slot,
        "number_of_diners": diners,
        "status": status,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _cleanup():
    frappe.db.sql("DELETE FROM `tabTable Booking` WHERE customer_phone IN (%s, %s)", [_PHONE_A, _PHONE_B])
    frappe.db.sql("DELETE FROM `tabRestaurant` WHERE name LIKE %s", [f"{_PREFIX}%"])
    frappe.db.commit()


from flamezo_backend.flamezo.api import table_booking_consumer as tbc


class TestCreateTableBooking(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()

    def tearDown(self):
        _cleanup()

    def test_valid_booking_created(self):
        result = tbc.create_table_booking(
            phone=_PHONE_A,
            restaurant_id=self.rest.name,
            date=add_days(today(), 3),
            time_slot="19:00 – 21:00",
            number_of_diners=2,
        )
        self.assertTrue(result["success"])
        self.assertIn("booking_id", result["data"])
        self.assertEqual(result["data"]["status"], "pending")

    def test_booking_persisted_with_correct_fields(self):
        result = tbc.create_table_booking(
            phone=_PHONE_A,
            restaurant_id=self.rest.name,
            date=add_days(today(), 3),
            time_slot="19:00 – 21:00",
            number_of_diners=4,
            notes="Window seat please",
        )
        doc = frappe.get_doc("Table Booking", result["data"]["booking_id"])
        self.assertEqual(doc.customer_phone, _PHONE_A)
        self.assertEqual(doc.number_of_diners, 4)
        self.assertEqual(doc.notes, "Window seat please")
        self.assertEqual(doc.restaurant, self.rest.name)

    def test_nonexistent_restaurant_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            tbc.create_table_booking(
                phone=_PHONE_A,
                restaurant_id="REST-FAKE-9999",
                date=add_days(today(), 2),
                time_slot="18:00 – 20:00",
                number_of_diners=2,
            )

    def test_inactive_restaurant_rejected(self):
        inactive = _make_rest("02", is_active=0)
        with self.assertRaises(frappe.exceptions.ValidationError):
            tbc.create_table_booking(
                phone=_PHONE_A,
                restaurant_id=inactive.name,
                date=add_days(today(), 2),
                time_slot="18:00 – 20:00",
                number_of_diners=2,
            )

    def test_past_date_rejected(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            tbc.create_table_booking(
                phone=_PHONE_A,
                restaurant_id=self.rest.name,
                date=add_days(today(), -1),
                time_slot="18:00 – 20:00",
                number_of_diners=2,
            )

    def test_malformed_date_rejected(self):
        with self.assertRaises(Exception):
            tbc.create_table_booking(
                phone=_PHONE_A,
                restaurant_id=self.rest.name,
                date="not-a-date",
                time_slot="18:00 – 20:00",
                number_of_diners=2,
            )

    def test_missing_restaurant_throws(self):
        with self.assertRaises(Exception):
            tbc.create_table_booking(
                phone=_PHONE_A, restaurant_id=None,
                date=add_days(today(), 2), time_slot="18:00", number_of_diners=2,
            )

    def test_missing_date_throws(self):
        with self.assertRaises(Exception):
            tbc.create_table_booking(
                phone=_PHONE_A, restaurant_id=self.rest.name,
                date=None, time_slot="18:00", number_of_diners=2,
            )

    def test_missing_time_slot_throws(self):
        with self.assertRaises(Exception):
            tbc.create_table_booking(
                phone=_PHONE_A, restaurant_id=self.rest.name,
                date=add_days(today(), 2), time_slot=None, number_of_diners=2,
            )

    def test_zero_diners_rejected(self):
        with self.assertRaises(Exception):
            tbc.create_table_booking(
                phone=_PHONE_A, restaurant_id=self.rest.name,
                date=add_days(today(), 2), time_slot="18:00", number_of_diners=0,
            )

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            tbc.create_table_booking(
                phone=None, restaurant_id=self.rest.name,
                date=add_days(today(), 2), time_slot="18:00", number_of_diners=2,
            )


class TestGetMyTableBookings(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.b1 = _make_booking(self.rest.name, phone=_PHONE_A, status="pending")
        self.b2 = _make_booking(self.rest.name, phone=_PHONE_A, status="confirmed")
        self.b_other = _make_booking(self.rest.name, phone=_PHONE_B, status="pending")

    def tearDown(self):
        _cleanup()

    def test_returns_only_own_bookings(self):
        result = tbc.get_my_table_bookings(_PHONE_A)
        self.assertTrue(result["success"])
        ids = [b["id"] for b in result["data"]["bookings"]]
        self.assertIn(self.b1.name, ids)
        self.assertIn(self.b2.name, ids)
        self.assertNotIn(self.b_other.name, ids)

    def test_other_phone_excluded(self):
        result = tbc.get_my_table_bookings(_PHONE_B)
        ids = [b["id"] for b in result["data"]["bookings"]]
        self.assertNotIn(self.b1.name, ids)
        self.assertIn(self.b_other.name, ids)

    def test_status_filter_pending(self):
        result = tbc.get_my_table_bookings(_PHONE_A, status="pending")
        ids = [b["id"] for b in result["data"]["bookings"]]
        self.assertIn(self.b1.name, ids)
        self.assertNotIn(self.b2.name, ids)

    def test_status_filter_confirmed(self):
        result = tbc.get_my_table_bookings(_PHONE_A, status="confirmed")
        ids = [b["id"] for b in result["data"]["bookings"]]
        self.assertIn(self.b2.name, ids)
        self.assertNotIn(self.b1.name, ids)

    def test_pagination(self):
        # Use a unique phone to avoid the 3-active-booking limit
        page_phone = "9600000099"
        frappe.db.sql("DELETE FROM `tabTable Booking` WHERE customer_phone=%s", page_phone)
        for i in range(3):
            _make_booking(self.rest.name, phone=page_phone, status="cancelled")
        result = tbc.get_my_table_bookings(page_phone, limit=2)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["data"]["bookings"]), 2)
        self.assertTrue(result["data"]["has_more"])
        frappe.db.sql("DELETE FROM `tabTable Booking` WHERE customer_phone=%s", page_phone)
        frappe.db.commit()

    def test_booking_fields_present(self):
        result = tbc.get_my_table_bookings(_PHONE_A)
        b = result["data"]["bookings"][0]
        for field in ("id", "restaurant_name", "date", "time_slot", "number_of_diners", "status"):
            self.assertIn(field, b)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            tbc.get_my_table_bookings(None)


class TestGetTableBookingDetail(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()
        self.booking = _make_booking(self.rest.name, phone=_PHONE_A)

    def tearDown(self):
        _cleanup()

    def test_returns_correct_booking(self):
        result = tbc.get_table_booking_detail(self.booking.name, _PHONE_A)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["booking"]["id"], self.booking.name)

    def test_all_fields_present(self):
        result = tbc.get_table_booking_detail(self.booking.name, _PHONE_A)
        b = result["data"]["booking"]
        for field in ("id", "restaurant_name", "date", "time_slot",
                      "number_of_diners", "status", "customer_name"):
            self.assertIn(field, b)

    def test_wrong_phone_throws_permission_error(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            tbc.get_table_booking_detail(self.booking.name, _PHONE_B)

    def test_nonexistent_booking_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            tbc.get_table_booking_detail("TBK-FAKE-9999", _PHONE_A)

    def test_missing_booking_id_throws(self):
        with self.assertRaises(Exception):
            tbc.get_table_booking_detail(None, _PHONE_A)


class TestCancelTableBooking(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.rest = _make_rest()

    def tearDown(self):
        _cleanup()

    def test_cancel_pending_booking(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="pending")
        result = tbc.cancel_table_booking(b.name, _PHONE_A)
        self.assertTrue(result["success"])
        status = frappe.db.get_value("Table Booking", b.name, "status")
        self.assertEqual(status, "cancelled")

    def test_cancel_sets_cancelled_at(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="pending")
        tbc.cancel_table_booking(b.name, _PHONE_A)
        cancelled_at = frappe.db.get_value("Table Booking", b.name, "cancelled_at")
        self.assertIsNotNone(cancelled_at)

    def test_cancel_confirmed_booking(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="confirmed")
        result = tbc.cancel_table_booking(b.name, _PHONE_A)
        self.assertTrue(result["success"])

    def test_cannot_cancel_completed(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="completed")
        with self.assertRaises(frappe.exceptions.ValidationError):
            tbc.cancel_table_booking(b.name, _PHONE_A)

    def test_cannot_cancel_rejected(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="rejected")
        with self.assertRaises(frappe.exceptions.ValidationError):
            tbc.cancel_table_booking(b.name, _PHONE_A)

    def test_cannot_cancel_already_cancelled(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="cancelled")
        with self.assertRaises(frappe.exceptions.ValidationError):
            tbc.cancel_table_booking(b.name, _PHONE_A)

    def test_wrong_phone_throws_permission_error(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="pending")
        with self.assertRaises(frappe.exceptions.PermissionError):
            tbc.cancel_table_booking(b.name, _PHONE_B)

    def test_nonexistent_booking_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            tbc.cancel_table_booking("TBK-FAKE-9999", _PHONE_A)

    def test_missing_booking_id_throws(self):
        with self.assertRaises(Exception):
            tbc.cancel_table_booking(None, _PHONE_A)

    def test_missing_phone_throws(self):
        b = _make_booking(self.rest.name, phone=_PHONE_A, status="pending")
        with self.assertRaises(Exception):
            tbc.cancel_table_booking(b.name, None)
