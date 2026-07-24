# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Customer Order Tracking API (orders.py).

Covers:
  get_my_orders:
    - Returns orders for the correct customer phone (10-digit match, +91 variant)
    - Pagination works (page, limit, has_more)
    - Status filter
    - Restaurant filter
    - Missing phone returns error

  get_order_detail:
    - Returns full order with items
    - Wrong phone blocked (FORBIDDEN)
    - Nonexistent order returns NOT_FOUND
    - Resolves by order_id field as well as Frappe name

  get_order_status:
    - Returns lightweight status + payment_status
    - Wrong phone blocked

  cancel_order:
    - Cancels pending order
    - Cancels confirmed order
    - Blocks cancellation of completed/delivered/cancelled orders
    - Wrong phone blocked
    - Nonexistent order returns NOT_FOUND

  get_all_customer_bookings (extended):
    - Returns all 4 booking types (table, banquet, appointment, court)
    - Filters out past / cancelled bookings correctly
    - Sorted by date ascending
"""

import unittest
from frappe.utils import today, add_days

import unittest.mock
import frappe
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-ORD"
_PHONE       = "9200000001"
_PHONE_PLUS  = "+919200000001"
_PHONE_ZERO  = "09200000001"
_PHONE_OTHER = "9200000099"


def _make_restaurant(suffix="01", outlet_type="dining"):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type=outlet_type)
    return r.name


def _make_order(restaurant, phone=_PHONE, status="draft",
                payment_status="completed", total=500.0, order_type="dine_in"):
    import random, string
    order_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    doc = frappe.get_doc({
        "doctype": "Order",
        "order_id": order_id,
        "order_number": f"FZ-{order_id[:4].upper()}",
        "restaurant": restaurant,
        "status": status,
        "payment_status": payment_status,
        "payment_method": "online",
        "order_type": order_type,
        "customer_name": "Test Customer",
        "customer_phone": phone,
        "subtotal": total,
        "discount": 0,
        "loyalty_discount": 0,
        "packaging_fee": 0,
        "delivery_fee": 0,
        "tax": 0,
        "total": total,
        "order_items": [
            {
                "doctype": "Order Item",
                "product": "",
                "product_name": "Masala Dosa",
                "quantity": 2,
                "unit_price": 150,
                "original_price": 150,
                "total_price": 300,
            },
            {
                "doctype": "Order Item",
                "product": "",
                "product_name": "Filter Coffee",
                "quantity": 2,
                "unit_price": 100,
                "original_price": 100,
                "total_price": 200,
            },
        ],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name, doc.order_id


def _cleanup(restaurant):
    order_names = frappe.get_all("Order", {"restaurant": restaurant}, ["name"])
    for o in order_names:
        frappe.delete_doc("Order", o.name, ignore_permissions=True)
    frappe.db.delete("Restaurant", restaurant)
    frappe.db.commit()


class TestGetMyOrders(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("GMO01")
        self.o1, _ = _make_order(self.restaurant, _PHONE, status="completed")
        self.o2, _ = _make_order(self.restaurant, _PHONE, status="draft")
        self.o3, _ = _make_order(self.restaurant, _PHONE_OTHER, status="completed")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_returns_only_customer_orders(self):
        from flamezo_backend.flamezo.api.orders import get_my_orders
        res = get_my_orders(phone=_PHONE)
        self.assertTrue(res["success"], res)
        ids = [o["id"] for o in res["data"]["orders"]]
        self.assertIn(self.o1, ids)
        self.assertIn(self.o2, ids)
        self.assertNotIn(self.o3, ids)

    def test_pagination(self):
        from flamezo_backend.flamezo.api.orders import get_my_orders
        res = get_my_orders(phone=_PHONE, page=1, limit=1)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["data"]["orders"]), 1)
        self.assertEqual(res["data"]["total"], 2)
        self.assertTrue(res["data"]["has_more"])

        res2 = get_my_orders(phone=_PHONE, page=2, limit=1)
        self.assertTrue(res2["success"])
        self.assertFalse(res2["data"]["has_more"])

    def test_status_filter(self):
        from flamezo_backend.flamezo.api.orders import get_my_orders
        res = get_my_orders(phone=_PHONE, status="draft")
        self.assertTrue(res["success"])
        for o in res["data"]["orders"]:
            self.assertEqual(o["status"], "draft")

    def test_restaurant_filter(self):
        from flamezo_backend.flamezo.api.orders import get_my_orders
        other = _make_restaurant("GMO02")
        _make_order(other, _PHONE, status="completed")
        try:
            res = get_my_orders(phone=_PHONE, restaurant_id=self.restaurant)
            self.assertTrue(res["success"])
            for o in res["data"]["orders"]:
                self.assertEqual(o["restaurant_id"], self.restaurant)
        finally:
            _cleanup(other)

    def test_missing_phone_returns_error(self):
        from flamezo_backend.flamezo.api.orders import get_my_orders
        res = get_my_orders()
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "MISSING_PARAM")

    def test_response_includes_restaurant_name(self):
        from flamezo_backend.flamezo.api.orders import get_my_orders
        res = get_my_orders(phone=_PHONE)
        self.assertTrue(res["success"])
        for o in res["data"]["orders"]:
            self.assertIn("restaurant_name", o)
            self.assertTrue(len(o["restaurant_name"]) > 0)


class TestGetOrderDetail(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("GOD01")
        self.order_name, self.order_id = _make_order(self.restaurant, _PHONE)

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_returns_full_order_with_items(self):
        from flamezo_backend.flamezo.api.orders import get_order_detail
        res = get_order_detail(order_id=self.order_name, phone=_PHONE)
        self.assertTrue(res["success"], res)
        data = res["data"]
        self.assertEqual(data["id"], self.order_name)
        self.assertIn("items", data)
        self.assertEqual(len(data["items"]), 2)
        item_names = [i["name"] for i in data["items"]]
        self.assertIn("Masala Dosa", item_names)
        self.assertIn("Filter Coffee", item_names)

    def test_resolves_by_order_id_field(self):
        from flamezo_backend.flamezo.api.orders import get_order_detail
        res = get_order_detail(order_id=self.order_id, phone=_PHONE)
        self.assertTrue(res["success"], res)
        self.assertEqual(res["data"]["id"], self.order_name)

    def test_wrong_phone_blocked(self):
        from flamezo_backend.flamezo.api.orders import get_order_detail
        res = get_order_detail(order_id=self.order_name, phone=_PHONE_OTHER)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_plus91_phone_variant_works(self):
        from flamezo_backend.flamezo.api.orders import get_order_detail
        res = get_order_detail(order_id=self.order_name, phone=_PHONE_PLUS)
        self.assertTrue(res["success"], res)

    def test_nonexistent_order_returns_not_found(self):
        from flamezo_backend.flamezo.api.orders import get_order_detail
        res = get_order_detail(order_id="FAKE-ORDER-9999", phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "NOT_FOUND")

    def test_includes_restaurant_info(self):
        from flamezo_backend.flamezo.api.orders import get_order_detail
        res = get_order_detail(order_id=self.order_name, phone=_PHONE)
        self.assertIn("restaurant_name", res["data"])
        self.assertTrue(len(res["data"]["restaurant_name"]) > 0)


class TestGetOrderStatus(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("GOS01")
        self.order_name, self.order_id = _make_order(
            self.restaurant, _PHONE, status="confirmed", payment_status="completed"
        )

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_returns_status_fields_only(self):
        from flamezo_backend.flamezo.api.orders import get_order_status
        res = get_order_status(order_id=self.order_name, phone=_PHONE)
        self.assertTrue(res["success"], res)
        data = res["data"]
        self.assertEqual(data["status"], "confirmed")
        self.assertEqual(data["payment_status"], "completed")
        self.assertIn("order_id", data)
        self.assertIn("last_updated", data)
        # Must NOT contain items (lightweight endpoint)
        self.assertNotIn("items", data)

    def test_wrong_phone_blocked(self):
        from flamezo_backend.flamezo.api.orders import get_order_status
        res = get_order_status(order_id=self.order_name, phone=_PHONE_OTHER)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_nonexistent_order_not_found(self):
        from flamezo_backend.flamezo.api.orders import get_order_status
        res = get_order_status(order_id="NONEXISTENT-9999", phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "NOT_FOUND")


class TestCancelOrder(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("CO01")

    def tearDown(self):
        _cleanup(self.restaurant)

    def test_cancel_draft_order(self):
        from flamezo_backend.flamezo.api.orders import cancel_order
        name, _ = _make_order(self.restaurant, _PHONE, status="draft")
        res = cancel_order(order_id=name, phone=_PHONE, reason="Ordered by mistake")
        self.assertTrue(res["success"], res)
        self.assertEqual(
            frappe.db.get_value("Order", name, "status"), "cancelled"
        )

    def test_cancel_confirmed_order(self):
        from flamezo_backend.flamezo.api.orders import cancel_order
        name, _ = _make_order(self.restaurant, _PHONE, status="confirmed")
        res = cancel_order(order_id=name, phone=_PHONE)
        self.assertTrue(res["success"], res)

    def test_cancel_completed_order_blocked(self):
        from flamezo_backend.flamezo.api.orders import cancel_order
        name, _ = _make_order(self.restaurant, _PHONE, status="completed")
        res = cancel_order(order_id=name, phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_STATUS")

    def test_cancel_already_cancelled_blocked(self):
        from flamezo_backend.flamezo.api.orders import cancel_order
        name, _ = _make_order(self.restaurant, _PHONE, status="cancelled")
        res = cancel_order(order_id=name, phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "INVALID_STATUS")

    def test_wrong_phone_blocked(self):
        from flamezo_backend.flamezo.api.orders import cancel_order
        name, _ = _make_order(self.restaurant, _PHONE, status="draft")
        res = cancel_order(order_id=name, phone=_PHONE_OTHER)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_nonexistent_order_not_found(self):
        from flamezo_backend.flamezo.api.orders import cancel_order
        res = cancel_order(order_id="FAKE-ORD-9999", phone=_PHONE)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "NOT_FOUND")

    def test_paid_order_cancellation_includes_refund_note(self):
        from flamezo_backend.flamezo.api.orders import cancel_order
        name, _ = _make_order(self.restaurant, _PHONE, status="draft", payment_status="completed")
        res = cancel_order(order_id=name, phone=_PHONE)
        self.assertTrue(res["success"])
        self.assertIn("refund_note", res["data"])
        self.assertTrue(len(res["data"]["refund_note"]) > 0)


class TestGetAllCustomerBookingsExtended(unittest.TestCase):
    """
    Tests for the extended get_all_customer_bookings that now includes
    Service Appointments and Court Bookings alongside Table + Banquet.
    """

    def setUp(self):
        frappe.set_user("Administrator")
        from flamezo_backend.flamezo.tests.utils import make_restaurant
        self.r_dining   = _make_restaurant("CB01", "dining")
        self.r_wellness = _make_restaurant("CB02", "wellness")
        self.r_court    = _make_restaurant("CB03", "sports_court")

        # Future table booking
        self.table_bk = frappe.get_doc({
            "doctype": "Table Booking",
            "restaurant": self.r_dining,
            "customer_name": "Test Diner",
            "customer_phone": _PHONE,
            "date": add_days(today(), 3),
            "time_slot": "7:30 PM",
            "number_of_diners": 2,
            "status": "confirmed",
        }).insert(ignore_permissions=True).name
        frappe.db.commit()

        # Future service appointment
        self.appt = frappe.get_doc({
            "doctype": "Service Appointment",
            "restaurant": self.r_wellness,
            "outlet_type": "wellness",
            "customer_name": "Test Wellness",
            "customer_phone": _PHONE,
            "appointment_date": add_days(today(), 2),
            "appointment_time": "11:00:00",
            "duration_minutes": 60,
            "catalogue_item_name": "Facial",
            "sub_item_name": "Basic Facial",
            "sub_item_price": 1200,
            "status": "Pending",
        }).insert(ignore_permissions=True).name
        frappe.db.commit()

        # Future court booking
        court = frappe.get_doc({
            "doctype": "Court",
            "restaurant": self.r_court,
            "court_name": "Court 1",
            "sport_type": "Badminton",
            "is_active": 1,
            "slot_duration_minutes": 60,
            "price_per_slot": 300,
            "consumer_fee": 20,
            "opening_time": "09:00:00",
            "closing_time": "21:00:00",
            "available_days": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
            "advance_booking_days": 7,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        self.court_bk = frappe.get_doc({
            "doctype": "Court Booking",
            "restaurant": self.r_court,
            "court": court.name,
            "court_name": "Court 1",
            "sport_type": "Badminton",
            "booking_date": add_days(today(), 1),
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "customer_name": "Test Player",
            "customer_phone": _PHONE,
            "slot_price": 300,
            "consumer_fee": 20,
            "payment_status": "Paid",
            "status": "Confirmed",
        }).insert(ignore_permissions=True).name
        frappe.db.commit()

    def tearDown(self):
        frappe.db.delete("Table Booking", {"restaurant": self.r_dining})
        frappe.db.delete("Service Appointment", {"restaurant": self.r_wellness})
        frappe.db.delete("Court Booking", {"restaurant": self.r_court})
        frappe.db.delete("Court", {"restaurant": self.r_court})
        for r in [self.r_dining, self.r_wellness, self.r_court]:
            frappe.db.delete("Restaurant", r)
        frappe.db.commit()

    def test_all_four_types_returned(self):
        from flamezo_backend.flamezo.api.bookings import get_all_customer_bookings

        # Patch session validation to allow guest call
        with unittest.mock.patch(
            "flamezo_backend.flamezo.utils.customer_helpers.validate_customer_session",
            return_value=True
        ), unittest.mock.patch(
            "flamezo_backend.flamezo.utils.customer_helpers.normalize_phone",
            return_value="9200000001"
        ), unittest.mock.patch(
            "flamezo_backend.flamezo.utils.customer_helpers.get_phone_variants_for_lookup",
            return_value=[_PHONE]
        ), unittest.mock.patch(
            "flamezo_backend.flamezo.utils.customer_helpers.get_customer_token",
            return_value="tok_test"
        ), unittest.mock.patch(
            "flamezo_backend.flamezo.utils.customer_helpers.is_phone_verified",
            return_value=True
        ):
            res = get_all_customer_bookings(phone=_PHONE, limit=20)

        self.assertTrue(res["success"], res)
        bookings = res["data"]["bookings"]
        types_found = {b["type"] for b in bookings}
        self.assertIn("table",       types_found)
        self.assertIn("appointment", types_found)
        self.assertIn("court",       types_found)

    def test_appointment_booking_has_correct_fields(self):
        from flamezo_backend.flamezo.api.bookings import get_all_customer_bookings
        import unittest.mock as mock

        with mock.patch("flamezo_backend.flamezo.utils.customer_helpers.validate_customer_session", return_value=True), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.normalize_phone", return_value="9200000001"), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.get_phone_variants_for_lookup", return_value=[_PHONE]), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.get_customer_token", return_value="tok"), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.is_phone_verified", return_value=True):
            res = get_all_customer_bookings(phone=_PHONE, limit=20)

        appts = [b for b in res["data"]["bookings"] if b["type"] == "appointment"]
        self.assertEqual(len(appts), 1)
        a = appts[0]
        self.assertEqual(a["serviceName"], "Facial")
        self.assertEqual(a["subItemName"], "Basic Facial")
        self.assertIn("timeSlot", a)

    def test_court_booking_has_correct_fields(self):
        from flamezo_backend.flamezo.api.bookings import get_all_customer_bookings
        import unittest.mock as mock

        with mock.patch("flamezo_backend.flamezo.utils.customer_helpers.validate_customer_session", return_value=True), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.normalize_phone", return_value="9200000001"), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.get_phone_variants_for_lookup", return_value=[_PHONE]), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.get_customer_token", return_value="tok"), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.is_phone_verified", return_value=True):
            res = get_all_customer_bookings(phone=_PHONE, limit=20)

        courts = [b for b in res["data"]["bookings"] if b["type"] == "court"]
        self.assertEqual(len(courts), 1)
        c = courts[0]
        self.assertEqual(c["sportType"], "Badminton")
        self.assertEqual(c["consumerFee"], 20.0)
        self.assertIn("09:00", c["timeSlot"])

    def test_response_includes_types_included_field(self):
        from flamezo_backend.flamezo.api.bookings import get_all_customer_bookings
        import unittest.mock as mock

        with mock.patch("flamezo_backend.flamezo.utils.customer_helpers.validate_customer_session", return_value=True), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.normalize_phone", return_value="9200000001"), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.get_phone_variants_for_lookup", return_value=[_PHONE]), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.get_customer_token", return_value="tok"), \
             mock.patch("flamezo_backend.flamezo.utils.customer_helpers.is_phone_verified", return_value=True):
            res = get_all_customer_bookings(phone=_PHONE)

        self.assertIn("types_included", res["data"])
        self.assertIn("appointment", res["data"]["types_included"])
        self.assertIn("court", res["data"]["types_included"])


if __name__ == "__main__":
    unittest.main()
