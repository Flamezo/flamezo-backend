# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Service Appointment API (appointments.py).

Covers:
  Consumer:
    - create_appointment: happy path, past date blocked, missing params
    - get_my_appointments: pagination, cross-restaurant
    - cancel_appointment: by customer, wrong phone blocked,
      already-cancelled idempotent guard, completed blocks cancel

  Merchant:
    - get_appointment_requests: filter by status, filter by date
    - confirm_appointment: status transition
    - reject_appointment: status + cancellation fields
    - mark_appointment_completed: status transition
    - mark_appointment_no_show: status transition
    - get_appointment_summary: counts by status
    - Cross-restaurant access: merchant cannot act on another restaurant's appointment
"""

import unittest
from frappe.utils import today, add_days

import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-APPT"
_PHONE  = "9000000001"
_PHONE2 = "9000000002"


def _make_restaurant(suffix="01", outlet_type="wellness"):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type=outlet_type)
    return r.name


def _make_appointment(restaurant, phone=_PHONE, date=None, status="Pending",
                      catalogue_item_name="Haircut", sub_item_name="Men Haircut",
                      sub_item_price=350, time="10:00:00"):
    doc = frappe.get_doc({
        "doctype": "Service Appointment",
        "restaurant": restaurant,
        "outlet_type": frappe.db.get_value("Restaurant", restaurant, "outlet_type") or "wellness",
        "catalogue_item_name": catalogue_item_name,
        "sub_item_name": sub_item_name,
        "sub_item_price": sub_item_price,
        "customer_name": "Test Customer",
        "customer_phone": phone,
        "appointment_date": date or add_days(today(), 2),
        "appointment_time": time,
        "duration_minutes": 60,
        "notes": "Test appointment",
        "status": status,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _cleanup(restaurant):
    frappe.db.delete("Service Appointment", {"restaurant": restaurant})
    frappe.db.delete("Restaurant", restaurant)
    frappe.db.commit()


class TestCreateAppointment(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CA01", "wellness")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_create_happy_path(self):
        from flamezo_backend.flamezo.api.appointments import create_appointment
        res = create_appointment(
            outlet_id=self.restaurant,
            customer_name="Jane Doe",
            customer_phone=_PHONE,
            appointment_date=add_days(today(), 3),
            appointment_time="11:00:00",
            sub_item_name="Men Haircut",
            sub_item_price=350,
            duration_minutes=60,
            notes="First visit",
        )
        self.assertTrue(res["success"], res)
        self.assertIn("appointment_id", res["data"])
        self.assertEqual(res["data"]["status"], "Pending")
        # Verify in DB
        doc = frappe.get_doc("Service Appointment", res["data"]["appointment_id"])
        self.assertEqual(doc.customer_name, "Jane Doe")
        self.assertEqual(doc.restaurant, self.restaurant)
        self.assertEqual(doc.outlet_type, "wellness")

    def test_past_date_blocked(self):
        from flamezo_backend.flamezo.api.appointments import create_appointment
        res = create_appointment(
            outlet_id=self.restaurant,
            customer_name="Jane Doe",
            customer_phone=_PHONE,
            appointment_date=add_days(today(), -1),
            appointment_time="10:00:00",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_DATE")

    def test_missing_required_params(self):
        from flamezo_backend.flamezo.api.appointments import create_appointment
        res = create_appointment(outlet_id=self.restaurant)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "MISSING_PARAM")

    def test_nonexistent_restaurant(self):
        from flamezo_backend.flamezo.api.appointments import create_appointment
        res = create_appointment(
            outlet_id="FAKE-9999",
            customer_name="Jane",
            customer_phone=_PHONE,
            appointment_date=add_days(today(), 1),
            appointment_time="10:00:00",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "NOT_FOUND")


class TestGetMyAppointments(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("GM01", "wellness")
        self.r2 = _make_restaurant("GM02", "fitness")
        self.a1 = _make_appointment(self.r1, _PHONE)
        self.a2 = _make_appointment(self.r2, _PHONE)
        self.a3 = _make_appointment(self.r1, _PHONE2)  # different customer

    def tearDown(self):
        _cleanup(self.r1)
        _cleanup(self.r2)

    def test_returns_only_customer_appointments(self):
        from flamezo_backend.flamezo.api.appointments import get_my_appointments
        res = get_my_appointments(phone=_PHONE)
        self.assertTrue(res["success"], res)
        ids = [a["id"] for a in res["data"]["appointments"]]
        self.assertIn(self.a1, ids)
        self.assertIn(self.a2, ids)
        self.assertNotIn(self.a3, ids)

    def test_pagination(self):
        from flamezo_backend.flamezo.api.appointments import get_my_appointments
        res = get_my_appointments(phone=_PHONE, page=1, limit=1)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["data"]["appointments"]), 1)
        self.assertEqual(res["data"]["total"], 2)
        self.assertTrue(res["data"]["has_more"])

    def test_missing_phone_returns_error(self):
        from flamezo_backend.flamezo.api.appointments import get_my_appointments
        res = get_my_appointments()
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "MISSING_PARAM")


class TestCancelAppointment(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CX01", "wellness")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_customer_can_cancel_pending(self):
        from flamezo_backend.flamezo.api.appointments import cancel_appointment
        appt = _make_appointment(self.restaurant, _PHONE, status="Pending")
        res = cancel_appointment(appointment_id=appt, phone=_PHONE, reason="Changed plans")
        self.assertTrue(res["success"], res)
        self.assertEqual(res["data"]["status"], "Cancelled")
        doc = frappe.get_doc("Service Appointment", appt)
        self.assertEqual(doc.status, "Cancelled")
        self.assertEqual(doc.cancelled_by, "customer")
        self.assertEqual(doc.cancellation_reason, "Changed plans")

    def test_customer_can_cancel_confirmed(self):
        from flamezo_backend.flamezo.api.appointments import cancel_appointment
        appt = _make_appointment(self.restaurant, _PHONE, status="Confirmed")
        res = cancel_appointment(appointment_id=appt, phone=_PHONE)
        self.assertTrue(res["success"])

    def test_wrong_phone_blocked(self):
        from flamezo_backend.flamezo.api.appointments import cancel_appointment
        appt = _make_appointment(self.restaurant, _PHONE, status="Pending")
        res = cancel_appointment(appointment_id=appt, phone=_PHONE2)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_completed_appointment_cannot_be_cancelled(self):
        from flamezo_backend.flamezo.api.appointments import cancel_appointment
        appt = _make_appointment(self.restaurant, _PHONE, status="Completed")
        res = cancel_appointment(appointment_id=appt, phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_STATUS")

    def test_already_cancelled_blocked(self):
        from flamezo_backend.flamezo.api.appointments import cancel_appointment
        appt = _make_appointment(self.restaurant, _PHONE, status="Cancelled")
        res = cancel_appointment(appointment_id=appt, phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_STATUS")


class TestMerchantAppointmentManagement(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("MA01", "wellness")
        self.other_rest = _make_restaurant("MA02", "fitness")
        self.appt = _make_appointment(self.restaurant, _PHONE, status="Pending")

    def tearDown(self):
        _cleanup(self.restaurant)
        _cleanup(self.other_rest)

    def test_confirm_appointment(self):
        from flamezo_backend.flamezo.api.appointments import confirm_appointment
        res = confirm_appointment(appointment_id=self.appt, outlet_id=self.restaurant)
        self.assertTrue(res["success"], res)
        doc = frappe.get_doc("Service Appointment", self.appt)
        self.assertEqual(doc.status, "Confirmed")
        self.assertIsNotNone(doc.confirmed_at)

    def test_reject_appointment(self):
        from flamezo_backend.flamezo.api.appointments import reject_appointment
        res = reject_appointment(
            appointment_id=self.appt,
            outlet_id=self.restaurant,
            reason="Fully booked that day",
        )
        self.assertTrue(res["success"], res)
        doc = frappe.get_doc("Service Appointment", self.appt)
        self.assertEqual(doc.status, "Cancelled")
        self.assertEqual(doc.cancelled_by, "merchant")
        self.assertEqual(doc.cancellation_reason, "Fully booked that day")

    def test_mark_completed(self):
        from flamezo_backend.flamezo.api.appointments import confirm_appointment, mark_appointment_completed
        confirm_appointment(appointment_id=self.appt, outlet_id=self.restaurant)
        res = mark_appointment_completed(appointment_id=self.appt, outlet_id=self.restaurant)
        self.assertTrue(res["success"], res)
        doc = frappe.get_doc("Service Appointment", self.appt)
        self.assertEqual(doc.status, "Completed")
        self.assertIsNotNone(doc.completed_at)

    def test_mark_no_show(self):
        from flamezo_backend.flamezo.api.appointments import confirm_appointment, mark_appointment_no_show
        confirm_appointment(appointment_id=self.appt, outlet_id=self.restaurant)
        res = mark_appointment_no_show(appointment_id=self.appt, outlet_id=self.restaurant)
        self.assertTrue(res["success"], res)
        self.assertEqual(
            frappe.db.get_value("Service Appointment", self.appt, "status"),
            "No Show",
        )

    def test_cross_restaurant_access_blocked(self):
        from flamezo_backend.flamezo.api.appointments import confirm_appointment
        res = confirm_appointment(appointment_id=self.appt, outlet_id=self.other_rest)
        self.assertFalse(res["success"])

    def test_get_appointment_requests_filter_by_status(self):
        from flamezo_backend.flamezo.api.appointments import get_appointment_requests
        _make_appointment(self.restaurant, _PHONE, status="Confirmed")
        res = get_appointment_requests(outlet_id=self.restaurant, status="Pending")
        self.assertTrue(res["success"])
        for a in res["data"]["appointments"]:
            self.assertEqual(a["status"], "Pending")

    def test_get_appointment_requests_filter_by_date(self):
        from flamezo_backend.flamezo.api.appointments import get_appointment_requests
        target = add_days(today(), 2)
        _make_appointment(self.restaurant, _PHONE, date=add_days(today(), 5))
        res = get_appointment_requests(outlet_id=self.restaurant, date=target)
        self.assertTrue(res["success"])
        for a in res["data"]["appointments"]:
            self.assertEqual(a["appointment_date"], str(target))

    def test_get_appointment_summary(self):
        from flamezo_backend.flamezo.api.appointments import get_appointment_summary
        target_date = add_days(today(), 2)
        _make_appointment(self.restaurant, _PHONE2, date=target_date, status="Confirmed")
        res = get_appointment_summary(outlet_id=self.restaurant, date=str(target_date))
        self.assertTrue(res["success"], res)
        summary = res["data"]
        self.assertGreaterEqual(summary["by_status"]["Pending"], 1)
        self.assertGreaterEqual(summary["by_status"]["Confirmed"], 1)
        self.assertEqual(summary["date"], str(target_date))


if __name__ == "__main__":
    unittest.main()
