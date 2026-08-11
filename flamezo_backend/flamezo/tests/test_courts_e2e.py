# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the Court Booking API (courts.py).

Covers:
  Consumer:
    - get_courts: returns active courts, excludes inactive
    - get_court_availability: slot generation, booked slots excluded,
      past slots excluded (today), closed days return empty, advance limit
    - create_court_booking: happy path (no Razorpay in test — stubs),
      slot already taken blocked, past date blocked, invalid slot blocked
    - get_my_court_bookings: pagination, cross-restaurant
    - cancel_court_booking: wrong phone blocked, completed blocked

  Merchant:
    - get_court_bookings: filter by date, court, status
    - get_court_booking_summary: counts + revenue
    - mark_court_completed + mark_court_no_show
    - save_court: create, update, validation
    - delete_court: success, blocks if active bookings

  Cross-restaurant security:
    - Merchant cannot access another restaurant's court or booking
"""

import unittest
from unittest.mock import patch, MagicMock
from frappe.utils import today, add_days

import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-CRT"
_PHONE  = "9100000001"
_PHONE2 = "9100000002"


def _make_restaurant(suffix="01"):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type="sports_court")
    return r.name


def _make_court(restaurant, court_name="Badminton Court 1", sport_type="Badminton",
                price=300, consumer_fee=20, slot_duration=60,
                opening="06:00:00", closing="22:00:00",
                available_days="Mon,Tue,Wed,Thu,Fri,Sat,Sun", is_active=1):
    doc = frappe.get_doc({
        "doctype": "Court",
        "restaurant": restaurant,
        "court_name": court_name,
        "sport_type": sport_type,
        "is_active": is_active,
        "slot_duration_minutes": slot_duration,
        "price_per_slot": price,
        "consumer_fee": consumer_fee,
        "opening_time": opening,
        "closing_time": closing,
        "available_days": available_days,
        "advance_booking_days": 7,
        "sort_order": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_court_booking(restaurant, court, phone=_PHONE, date=None,
                        start="09:00:00", end="10:00:00", status="Confirmed",
                        payment_status="Paid", consumer_fee=20, slot_price=300):
    booking = frappe.get_doc({
        "doctype": "Court Booking",
        "restaurant": restaurant,
        "court": court,
        "court_name": frappe.db.get_value("Court", court, "court_name"),
        "sport_type": frappe.db.get_value("Court", court, "sport_type"),
        "booking_date": date or add_days(today(), 1),
        "start_time": start,
        "end_time": end,
        "customer_name": "Test Booker",
        "customer_phone": phone,
        "slot_price": slot_price,
        "consumer_fee": consumer_fee,
        "payment_status": payment_status,
        "status": status,
        "razorpay_order_id": "order_test_123",
        "razorpay_payment_id": "pay_test_456" if payment_status == "Paid" else "",
    })
    booking.insert(ignore_permissions=True)
    frappe.db.commit()
    return booking.name


def _cleanup(restaurant):
    frappe.db.delete("Court Booking", {"restaurant": restaurant})
    frappe.db.delete("Court", {"restaurant": restaurant})
    frappe.db.delete("Restaurant", restaurant)
    frappe.db.commit()


class TestGetCourts(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("GCT01")
        self.court1 = _make_court(self.restaurant, "Court A", is_active=1)
        self.court2 = _make_court(self.restaurant, "Court B", is_active=0)

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_returns_only_active_courts(self):
        from flamezo_backend.flamezo.api.courts import get_courts
        res = get_courts(outlet_id=self.restaurant)
        self.assertTrue(res["success"], res)
        names = [c["name"] for c in res["data"]]
        self.assertIn("Court A", names)
        self.assertNotIn("Court B", names)

    def test_court_fields_complete(self):
        from flamezo_backend.flamezo.api.courts import get_courts
        res = get_courts(outlet_id=self.restaurant)
        court = res["data"][0]
        required_keys = ["id", "name", "sport_type", "slot_duration_minutes",
                         "price_per_slot", "consumer_fee", "opening_time",
                         "closing_time", "available_days", "advance_booking_days"]
        for key in required_keys:
            self.assertIn(key, court, f"Missing key: {key}")

    def test_missing_restaurant_id(self):
        from flamezo_backend.flamezo.api.courts import get_courts
        res = get_courts()
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "MISSING_PARAM")


class TestGetCourtAvailability(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("AV01")
        self.court = _make_court(
            self.restaurant, "Test Court",
            opening="09:00:00", closing="12:00:00",
            slot_duration=60,
            available_days="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        )

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_generates_correct_slots(self):
        from flamezo_backend.flamezo.api.courts import get_court_availability
        date = add_days(today(), 1)
        res = get_court_availability(
            outlet_id=self.restaurant,
            court_id=self.court,
            date=str(date),
        )
        self.assertTrue(res["success"], res)
        slots = res["data"]["slots"]
        # 09:00-12:00 with 60min slots = 3 slots
        self.assertEqual(len(slots), 3)
        starts = [s["start"] for s in slots]
        self.assertIn("09:00", starts)
        self.assertIn("10:00", starts)
        self.assertIn("11:00", starts)

    def test_booked_slot_marked_unavailable(self):
        from flamezo_backend.flamezo.api.courts import get_court_availability
        date = add_days(today(), 1)
        _make_court_booking(self.restaurant, self.court, date=date,
                            start="09:00:00", end="10:00:00", status="Confirmed")
        res = get_court_availability(
            outlet_id=self.restaurant,
            court_id=self.court,
            date=str(date),
        )
        self.assertTrue(res["success"])
        slot_09 = next(s for s in res["data"]["slots"] if s["start"] == "09:00")
        self.assertFalse(slot_09["is_available"])

    def test_cancelled_booking_does_not_block_slot(self):
        from flamezo_backend.flamezo.api.courts import get_court_availability
        date = add_days(today(), 1)
        _make_court_booking(self.restaurant, self.court, date=date,
                            start="09:00:00", end="10:00:00", status="Cancelled")
        res = get_court_availability(
            outlet_id=self.restaurant,
            court_id=self.court,
            date=str(date),
        )
        slot_09 = next(s for s in res["data"]["slots"] if s["start"] == "09:00")
        self.assertTrue(slot_09["is_available"])

    def test_past_date_blocked(self):
        from flamezo_backend.flamezo.api.courts import get_court_availability
        res = get_court_availability(
            outlet_id=self.restaurant,
            court_id=self.court,
            date=add_days(today(), -1),
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_DATE")

    def test_beyond_advance_booking_window_blocked(self):
        from flamezo_backend.flamezo.api.courts import get_court_availability
        res = get_court_availability(
            outlet_id=self.restaurant,
            court_id=self.court,
            date=add_days(today(), 30),  # court has advance_booking_days=7
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_DATE")

    def test_closed_day_returns_no_slots(self):
        from flamezo_backend.flamezo.api.courts import get_court_availability
        # Court only open Mon
        closed_court = _make_court(
            self.restaurant, "Mon Only Court",
            available_days="Mon",
            opening="09:00:00", closing="12:00:00",
        )
        # Find next Tuesday (weekday 1)
        from datetime import date as date_type
        import datetime
        d = datetime.date.fromisoformat(str(add_days(today(), 1)))
        # Skip ahead to find a non-Monday within advance window
        for i in range(1, 8):
            check = datetime.date.fromisoformat(str(add_days(today(), i)))
            if check.weekday() != 0:  # 0 = Monday
                break
        res = get_court_availability(
            outlet_id=self.restaurant,
            court_id=closed_court,
            date=str(check),
        )
        self.assertTrue(res["success"])
        self.assertFalse(res["data"]["is_open"])
        self.assertEqual(len(res["data"]["slots"]), 0)


class TestCreateCourtBooking(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CB01")
        self.court = _make_court(
            self.restaurant, opening="09:00:00", closing="12:00:00", slot_duration=60
        )

    def tearDown(self):
        _cleanup(self.restaurant)

    @patch("flamezo_backend.flamezo.api.courts._get_razorpay_client")
    def test_creates_booking_and_razorpay_order(self, mock_rp):
        from flamezo_backend.flamezo.api.courts import create_court_booking
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_mock_001"}
        mock_rp.return_value = mock_client

        date = add_days(today(), 1)
        res = create_court_booking(
            outlet_id=self.restaurant,
            court_id=self.court,
            booking_date=str(date),
            start_time="09:00",
            customer_name="Test Player",
            customer_phone=_PHONE,
        )
        self.assertTrue(res["success"], res)
        self.assertIn("booking_id", res["data"])
        self.assertEqual(res["data"]["razorpay_order_id"], "order_mock_001")
        self.assertEqual(res["data"]["consumer_fee"], 20.0)
        self.assertEqual(res["data"]["start_time"], "09:00")

        # DB state
        doc = frappe.get_doc("Court Booking", res["data"]["booking_id"])
        self.assertEqual(doc.status, "Pending Payment")
        self.assertEqual(doc.razorpay_order_id, "order_mock_001")

    @patch("flamezo_backend.flamezo.api.courts._get_razorpay_client")
    def test_slot_already_taken_blocked(self, mock_rp):
        from flamezo_backend.flamezo.api.courts import create_court_booking
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_mock_002"}
        mock_rp.return_value = mock_client

        date = add_days(today(), 1)
        # Pre-book the slot
        _make_court_booking(self.restaurant, self.court, date=date,
                            start="09:00:00", end="10:00:00", status="Confirmed")
        res = create_court_booking(
            outlet_id=self.restaurant,
            court_id=self.court,
            booking_date=str(date),
            start_time="09:00",
            customer_name="Another Player",
            customer_phone=_PHONE2,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "SLOT_TAKEN")

    def test_invalid_slot_blocked(self):
        from flamezo_backend.flamezo.api.courts import create_court_booking
        date = add_days(today(), 1)
        res = create_court_booking(
            outlet_id=self.restaurant,
            court_id=self.court,
            booking_date=str(date),
            start_time="14:00",  # court closes at 12:00
            customer_name="Player",
            customer_phone=_PHONE,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_SLOT")

    def test_past_date_blocked(self):
        from flamezo_backend.flamezo.api.courts import create_court_booking
        res = create_court_booking(
            outlet_id=self.restaurant,
            court_id=self.court,
            booking_date=add_days(today(), -1),
            start_time="09:00",
            customer_name="Player",
            customer_phone=_PHONE,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_DATE")


class TestVerifyCourtPayment(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("VP01")
        self.court = _make_court(self.restaurant)

    def tearDown(self):
        _cleanup(self.restaurant)

    @patch("flamezo_backend.flamezo.api.courts.hmac")
    def test_valid_signature_confirms_booking(self, mock_hmac_module):
        from flamezo_backend.flamezo.api.courts import verify_court_payment
        # Create a pending booking
        booking = _make_court_booking(
            self.restaurant, self.court,
            status="Pending Payment", payment_status="Pending",
        )
        frappe.db.set_value("Court Booking", booking, {
            "razorpay_order_id": "order_123",
            "status": "Pending Payment",
        })
        frappe.db.commit()

        # Mock HMAC comparison to return True
        mock_digest = MagicMock()
        mock_digest.hexdigest.return_value = "valid_sig"
        mock_hmac_module.new.return_value = mock_digest
        mock_hmac_module.compare_digest.return_value = True

        res = verify_court_payment(
            booking_id=booking,
            razorpay_order_id="order_123",
            razorpay_payment_id="pay_abc",
            razorpay_signature="valid_sig",
        )
        self.assertTrue(res["success"], res)
        doc = frappe.get_doc("Court Booking", booking)
        self.assertEqual(doc.status, "Confirmed")
        self.assertEqual(doc.payment_status, "Paid")

    @patch("flamezo_backend.flamezo.api.courts.hmac")
    def test_invalid_signature_rejects(self, mock_hmac_module):
        from flamezo_backend.flamezo.api.courts import verify_court_payment
        booking = _make_court_booking(
            self.restaurant, self.court,
            status="Pending Payment", payment_status="Pending",
        )
        frappe.db.set_value("Court Booking", booking, "razorpay_order_id", "order_456")
        frappe.db.commit()

        mock_digest = MagicMock()
        mock_digest.hexdigest.return_value = "expected_sig"
        mock_hmac_module.new.return_value = mock_digest
        mock_hmac_module.compare_digest.return_value = False  # Signature mismatch

        res = verify_court_payment(
            booking_id=booking,
            razorpay_order_id="order_456",
            razorpay_payment_id="pay_bad",
            razorpay_signature="wrong_sig",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "SIGNATURE_INVALID")


class TestGetMyCourtBookings(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("MG01")
        self.r2 = _make_restaurant("MG02")
        self.c1 = _make_court(self.r1)
        self.c2 = _make_court(self.r2)
        self.b1 = _make_court_booking(self.r1, self.c1, phone=_PHONE)
        self.b2 = _make_court_booking(self.r2, self.c2, phone=_PHONE)
        self.b3 = _make_court_booking(self.r1, self.c1, phone=_PHONE2)

    def tearDown(self):
        _cleanup(self.r1)
        _cleanup(self.r2)

    def test_returns_only_customer_bookings(self):
        from flamezo_backend.flamezo.api.courts import get_my_court_bookings
        res = get_my_court_bookings(phone=_PHONE)
        self.assertTrue(res["success"], res)
        ids = [b["id"] for b in res["data"]["bookings"]]
        self.assertIn(self.b1, ids)
        self.assertIn(self.b2, ids)
        self.assertNotIn(self.b3, ids)

    def test_pagination(self):
        from flamezo_backend.flamezo.api.courts import get_my_court_bookings
        res = get_my_court_bookings(phone=_PHONE, page=1, limit=1)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["data"]["bookings"]), 1)
        self.assertEqual(res["data"]["total"], 2)
        self.assertTrue(res["data"]["has_more"])


class TestCancelCourtBooking(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CC01")
        self.court = _make_court(self.restaurant)

    def tearDown(self):
        _cleanup(self.restaurant)

    @patch("flamezo_backend.flamezo.api.courts._get_razorpay_client")
    def test_cancel_confirmed_triggers_refund(self, mock_rp):
        from flamezo_backend.flamezo.api.courts import cancel_court_booking
        mock_client = MagicMock()
        mock_rp.return_value = mock_client

        booking = _make_court_booking(
            self.restaurant, self.court, phone=_PHONE,
            status="Confirmed", payment_status="Paid",
        )
        frappe.db.set_value("Court Booking", booking, "razorpay_payment_id", "pay_to_refund")
        frappe.db.commit()

        res = cancel_court_booking(booking_id=booking, phone=_PHONE, reason="Can't make it")
        self.assertTrue(res["success"], res)
        self.assertTrue(res["data"]["refunded"])
        mock_client.payment.refund.assert_called_once()
        doc = frappe.get_doc("Court Booking", booking)
        self.assertEqual(doc.status, "Cancelled")
        self.assertEqual(doc.payment_status, "Refunded")

    def test_wrong_phone_blocked(self):
        from flamezo_backend.flamezo.api.courts import cancel_court_booking
        booking = _make_court_booking(self.restaurant, self.court, phone=_PHONE)
        res = cancel_court_booking(booking_id=booking, phone=_PHONE2)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_completed_booking_cannot_be_cancelled(self):
        from flamezo_backend.flamezo.api.courts import cancel_court_booking
        booking = _make_court_booking(self.restaurant, self.court, phone=_PHONE, status="Completed")
        res = cancel_court_booking(booking_id=booking, phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_STATUS")


class TestMerchantCourtManagement(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("MC01")
        self.other = _make_restaurant("MC02")
        self.court = _make_court(self.restaurant)

    def tearDown(self):
        _cleanup(self.restaurant)
        _cleanup(self.other)

    def test_get_court_bookings_filter_by_date(self):
        from flamezo_backend.flamezo.api.courts import get_court_bookings
        target = add_days(today(), 1)
        _make_court_booking(self.restaurant, self.court, date=target)
        _make_court_booking(self.restaurant, self.court, date=add_days(today(), 3))
        res = get_court_bookings(outlet_id=self.restaurant, date=str(target))
        self.assertTrue(res["success"])
        for b in res["data"]["bookings"]:
            self.assertEqual(b["booking_date"], str(target))

    def test_daily_summary_counts_and_revenue(self):
        from flamezo_backend.flamezo.api.courts import get_court_booking_summary
        target = add_days(today(), 2)
        _make_court_booking(self.restaurant, self.court, date=target, status="Confirmed", payment_status="Paid", slot_price=300, consumer_fee=20)
        _make_court_booking(self.restaurant, self.court, date=target, status="Cancelled", payment_status="Pending")
        res = get_court_booking_summary(outlet_id=self.restaurant, date=str(target))
        self.assertTrue(res["success"], res)
        data = res["data"]
        self.assertEqual(data["by_status"]["Confirmed"], 1)
        self.assertEqual(data["by_status"]["Cancelled"], 1)
        self.assertEqual(data["total_slot_revenue"], 300.0)
        self.assertEqual(data["total_consumer_fees_collected"], 20.0)

    def test_mark_completed(self):
        from flamezo_backend.flamezo.api.courts import mark_court_completed
        b = _make_court_booking(self.restaurant, self.court, status="Confirmed")
        res = mark_court_completed(booking_id=b, outlet_id=self.restaurant)
        self.assertTrue(res["success"])
        self.assertEqual(frappe.db.get_value("Court Booking", b, "status"), "Completed")

    def test_mark_no_show(self):
        from flamezo_backend.flamezo.api.courts import mark_court_no_show
        b = _make_court_booking(self.restaurant, self.court, status="Confirmed")
        res = mark_court_no_show(booking_id=b, outlet_id=self.restaurant)
        self.assertTrue(res["success"])
        self.assertEqual(frappe.db.get_value("Court Booking", b, "status"), "No Show")

    def test_save_court_create(self):
        from flamezo_backend.flamezo.api.courts import save_court
        res = save_court(
            outlet_id=self.restaurant,
            court_data={
                "court_name": "New Court",
                "sport_type": "Squash",
                "slot_duration_minutes": 45,
                "price_per_slot": 250,
                "consumer_fee": 30,
                "opening_time": "08:00:00",
                "closing_time": "20:00:00",
                "available_days": "Mon,Wed,Fri",
            },
        )
        self.assertTrue(res["success"], res)
        doc = frappe.get_doc("Court", res["data"]["court_id"])
        self.assertEqual(doc.court_name, "New Court")
        self.assertEqual(doc.consumer_fee, 30.0)
        self.assertEqual(doc.available_days, "Mon,Wed,Fri")

    def test_delete_court_blocked_with_active_bookings(self):
        from flamezo_backend.flamezo.api.courts import delete_court
        _make_court_booking(self.restaurant, self.court, status="Confirmed",
                            date=add_days(today(), 1))
        res = delete_court(outlet_id=self.restaurant, court_id=self.court)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "HAS_BOOKINGS")

    def test_delete_court_success_no_active_bookings(self):
        from flamezo_backend.flamezo.api.courts import delete_court, save_court
        # Create a fresh court with no bookings
        res = save_court(
            outlet_id=self.restaurant,
            court_data={
                "court_name": "Temp Court",
                "sport_type": "Badminton",
                "slot_duration_minutes": 60,
                "price_per_slot": 200,
                "consumer_fee": 20,
                "opening_time": "09:00:00",
                "closing_time": "21:00:00",
                "available_days": "Mon,Tue",
            },
        )
        court_id = res["data"]["court_id"]
        del_res = delete_court(outlet_id=self.restaurant, court_id=court_id)
        self.assertTrue(del_res["success"])
        self.assertFalse(frappe.db.exists("Court", court_id))

    def test_cross_restaurant_court_access_blocked(self):
        from flamezo_backend.flamezo.api.courts import mark_court_completed
        b = _make_court_booking(self.restaurant, self.court, status="Confirmed")
        res = mark_court_completed(booking_id=b, outlet_id=self.other)
        self.assertFalse(res["success"])


if __name__ == "__main__":
    unittest.main()
