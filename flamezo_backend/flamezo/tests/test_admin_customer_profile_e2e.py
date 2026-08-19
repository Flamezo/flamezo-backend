# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for admin_get_customer_full_profile (Customer 360 admin view).

Covers:
  - Permission gate (non-supervisor blocked, missing customer handled)
  - Orders surfaced with correct totals/spend aggregation
  - Outlets-visited breakdown (visit_count, last_visited, total_spent per outlet,
    across Orders + Table/Banquet/Court Bookings + Service Appointments)
  - stats.restaurants_visited / total_spend / avg_order_value correctness
  - Loyalty ledger, referral relationships (both directions)
  - UGC submissions, vouchers, redemptions, fraud flags
  - Coupon usage & offer claims
  - Saved addresses & sessions (session_token never exposed)
  - Social/community engagement counts
  - Guest/phone-only doctypes (Court Booking, Service Appointment, Offer Claim
    via phone) correctly attributed to the platform customer
"""

import unittest
import random
import string

import frappe
from frappe.utils import now_datetime, add_to_date, today, add_days

from flamezo_backend.flamezo.tests.utils import make_restaurant, make_customer, make_loyalty_entry

_PREFIX = "TEST-CP"


def _rand(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _make_restaurant(suffix="01", **kwargs):
    name = f"{_PREFIX}-{suffix}"
    r = make_restaurant(name, outlet_type="dining", **kwargs)
    return r.name


def _make_order(restaurant, customer_id, phone, total=500.0, payment_status="completed"):
    order_id = _rand(10)
    doc = frappe.get_doc({
        "doctype": "Order",
        "order_id": order_id,
        "order_number": f"FZ-{order_id[:4].upper()}",
        "restaurant": restaurant,
        "status": "completed",
        "payment_status": payment_status,
        "payment_method": "online",
        "order_type": "dine_in",
        "customer_name": "Test Customer",
        "customer_phone": phone,
        "platform_customer": customer_id,
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
                "product_name": "Test Dish",
                "quantity": 1,
                "unit_price": total,
                "original_price": total,
                "total_price": total,
            },
        ],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_table_booking(restaurant, customer_id, phone, status="completed"):
    doc = frappe.get_doc({
        "doctype": "Table Booking",
        "restaurant": restaurant,
        "platform_customer": customer_id,
        "customer_name": "Test Customer",
        "customer_phone": phone,
        "number_of_diners": 2,
        "date": today(),
        "time_slot": "19:00",
        "status": status,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_banquet_booking(restaurant, customer_id, phone, status="completed"):
    doc = frappe.get_doc({
        "doctype": "Banquet Booking",
        "restaurant": restaurant,
        "platform_customer": customer_id,
        "customer_name": "Test Customer",
        "customer_phone": phone,
        "number_of_guests": 20,
        "event_type": "Birthday",
        "date": today(),
        "time_slot": "18:00",
        "status": status,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_court(restaurant, suffix="1"):
    doc = frappe.get_doc({
        "doctype": "Court",
        "restaurant": restaurant,
        "court_name": f"Court {suffix}",
        "sport_type": "Badminton",
        "slot_duration_minutes": 60,
        "price_per_slot": 400,
        "consumer_fee": 20,
        "opening_time": "08:00:00",
        "closing_time": "22:00:00",
        "available_days": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_court_booking(restaurant, phone):
    court = _make_court(restaurant, suffix=_rand(4))
    doc = frappe.get_doc({
        "doctype": "Court Booking",
        "restaurant": restaurant,
        "court": court,
        "court_name": "Court Test",
        "customer_name": "Test Customer",
        "customer_phone": phone,
        "booking_date": today(),
        "start_time": "10:00:00",
        "end_time": "11:00:00",
        "slot_price": 400,
        "consumer_fee": 20,
        "payment_status": "Paid",
        "status": "Confirmed",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_service_appointment(restaurant, phone):
    doc = frappe.get_doc({
        "doctype": "Service Appointment",
        "restaurant": restaurant,
        "customer_name": "Test Customer",
        "customer_phone": phone,
        "appointment_date": today(),
        "appointment_time": "15:00:00",
        "duration_minutes": 60,
        "status": "Completed",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_coupon(restaurant, code):
    existing = frappe.db.get_value("Coupon", {"restaurant": restaurant, "code": code}, "name")
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Coupon",
        "restaurant": restaurant,
        "offer_type": "coupon",
        "code": code,
        "discount_type": "flat",
        "discount_value": 50,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_ugc_submission(restaurant, customer_id, phone, order_amount=800.0, status="story_verified"):
    order = _make_order(restaurant, customer_id, phone, total=order_amount)
    doc = frappe.get_doc({
        "doctype": "UGC Story Submission",
        "restaurant": restaurant,
        "customer": customer_id,
        "order": order,
        "status": status,
        "order_amount": order_amount,
        "cashback_coins": 40,
        "submission_date": today(),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _make_ugc_voucher(restaurant, customer_id, balance=200.0, status="active"):
    doc = frappe.get_doc({
        "doctype": "UGC Voucher",
        "voucher_code": _rand(8).upper(),
        "restaurant": restaurant,
        "customer": customer_id,
        "status": status,
        "original_amount": 200.0,
        "balance": balance,
        "issued_at": now_datetime(),
        "expires_at": add_to_date(now_datetime(), days=30),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _cleanup(restaurant, customer_id=None, phone=None):
    frappe.db.delete("Order", {"restaurant": restaurant})
    frappe.db.delete("Table Booking", {"restaurant": restaurant})
    frappe.db.delete("Banquet Booking", {"restaurant": restaurant})
    frappe.db.delete("Court Booking", {"restaurant": restaurant})
    frappe.db.delete("Court", {"restaurant": restaurant})
    frappe.db.delete("Service Appointment", {"restaurant": restaurant})
    frappe.db.delete("Restaurant Loyalty Entry", {"restaurant": restaurant})
    frappe.db.delete("UGC Story Submission", {"restaurant": restaurant})
    frappe.db.delete("UGC Voucher Redemption", {"restaurant": restaurant})
    frappe.db.delete("UGC Voucher", {"restaurant": restaurant})
    frappe.db.delete("UGC Fraud Flag", {"restaurant": restaurant})
    frappe.db.delete("Coupon Usage", {"restaurant": restaurant})
    frappe.db.delete("Offer Claim", {"restaurant": restaurant})
    frappe.db.delete("Coupon", {"restaurant": restaurant})
    if customer_id:
        frappe.db.delete("Customer Referral", {"referrer": customer_id})
        frappe.db.delete("Customer Referral", {"referee": customer_id})
        frappe.db.delete("Customer Address", {"customer": customer_id})
        frappe.db.delete("Customer Session", {"customer": customer_id})
    if phone:
        frappe.db.delete("Chills Like", {"customer_phone": phone})
        frappe.db.delete("Chills Save", {"customer_phone": phone})
        frappe.db.delete("Chills Outlet Follow", {"customer_phone": phone})
        frappe.db.delete("Creator Club Member", {"customer_phone": phone})
        frappe.db.delete("Crowd Chat Message", {"sender_phone": phone})
        frappe.db.delete("Crowd Request Member", {"customer_phone": phone})
        frappe.db.delete("Crowd Report", {"reporter_phone": phone})
        frappe.db.delete("Crowd Report", {"reported_phone": phone})
    frappe.db.delete("Restaurant", restaurant)
    frappe.db.commit()


class TestAdminCustomerFullProfilePermissions(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.restaurant = _make_restaurant("PERM01")
        self.customer = make_customer(phone="9811100001", name="Perm Test Customer")

    def tearDown(self):
        _cleanup(self.restaurant, self.customer.name, self.customer.phone)
        frappe.set_user("Administrator")

    def test_non_supervisor_blocked(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            admin_get_customer_full_profile(self.customer.name)

    def test_missing_customer_returns_error(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        result = admin_get_customer_full_profile("TEST-CP-DOES-NOT-EXIST")
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class TestAdminCustomerFullProfileOrdersAndSpend(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("ORD01")
        self.r2 = _make_restaurant("ORD02")
        self.customer = make_customer(phone="9811100002", name="Order Test Customer")

    def tearDown(self):
        _cleanup(self.r1, self.customer.name, self.customer.phone)
        _cleanup(self.r2)

    def test_orders_surfaced_and_scoped_to_customer(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        other_customer = make_customer(phone="9811199999", name="Someone Else")
        _make_order(self.r1, self.customer.name, self.customer.phone, total=500)
        _make_order(self.r1, other_customer.name, other_customer.phone, total=999)

        result = admin_get_customer_full_profile(self.customer.name)
        self.assertTrue(result["success"])
        orders = result["data"]["orders"]
        self.assertEqual(len(orders), 1)
        self.assertEqual(float(orders[0]["total"]), 500)
        self.assertEqual(orders[0]["outlet_name"], f"Test Restaurant {self.r1}")

        frappe.db.delete("Order", {"restaurant": self.r1, "platform_customer": other_customer.name})
        frappe.db.delete("Customer", other_customer.name)
        frappe.db.commit()

    def test_total_spend_only_counts_completed_orders(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        _make_order(self.r1, self.customer.name, self.customer.phone, total=500, payment_status="completed")
        _make_order(self.r1, self.customer.name, self.customer.phone, total=300, payment_status="completed")
        _make_order(self.r1, self.customer.name, self.customer.phone, total=1000, payment_status="pending")

        result = admin_get_customer_full_profile(self.customer.name)
        stats = result["data"]["stats"]
        self.assertEqual(stats["total_orders"], 3)
        self.assertEqual(float(stats["total_spend"]), 800)
        self.assertAlmostEqual(float(stats["avg_order_value"]), 400.0)

    def test_stats_zero_when_no_orders(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        result = admin_get_customer_full_profile(self.customer.name)
        stats = result["data"]["stats"]
        self.assertEqual(stats["total_orders"], 0)
        self.assertEqual(float(stats["total_spend"]), 0)
        self.assertEqual(float(stats["avg_order_value"]), 0)
        self.assertEqual(stats["restaurants_visited"], 0)
        self.assertEqual(result["data"]["outlets_visited"], [])


class TestAdminCustomerFullProfileOutletsVisited(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("OUT01")
        self.r2 = _make_restaurant("OUT02")
        self.customer = make_customer(phone="9811100003", name="Outlets Test Customer")

    def tearDown(self):
        _cleanup(self.r1, self.customer.name, self.customer.phone)
        _cleanup(self.r2)

    def test_two_distinct_outlets_both_reported(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        _make_order(self.r1, self.customer.name, self.customer.phone, total=500)
        _make_order(self.r2, self.customer.name, self.customer.phone, total=700)

        result = admin_get_customer_full_profile(self.customer.name)
        outlets = {o["restaurant"]: o for o in result["data"]["outlets_visited"]}
        self.assertEqual(result["data"]["stats"]["restaurants_visited"], 2)
        self.assertEqual(len(outlets), 2)
        self.assertEqual(outlets[self.r1]["visit_count"], 1)
        self.assertEqual(float(outlets[self.r1]["total_spent"]), 500)
        self.assertEqual(outlets[self.r2]["visit_count"], 1)
        self.assertEqual(float(outlets[self.r2]["total_spent"]), 700)

    def test_multiple_visit_types_at_same_outlet_aggregate(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        _make_order(self.r1, self.customer.name, self.customer.phone, total=500)
        _make_table_booking(self.r1, self.customer.name, self.customer.phone)
        _make_court_booking(self.r1, self.customer.phone)
        _make_service_appointment(self.r1, self.customer.phone)

        result = admin_get_customer_full_profile(self.customer.name)
        outlets = {o["restaurant"]: o for o in result["data"]["outlets_visited"]}
        self.assertEqual(len(outlets), 1)
        stat = outlets[self.r1]
        self.assertEqual(stat["visit_count"], 4)
        self.assertEqual(stat["orders"], 1)
        self.assertEqual(stat["table_bookings"], 1)
        self.assertEqual(stat["court_bookings"], 1)
        self.assertEqual(stat["service_appointments"], 1)
        self.assertEqual(float(stat["total_spent"]), 500)  # only Order contributes spend
        self.assertIsNotNone(stat["last_visited"])

    def test_court_booking_and_service_appointment_are_phone_scoped_correctly(self):
        """Court Booking / Service Appointment have no Customer link — must be
        matched purely by phone, and must NOT leak to a different customer."""
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        other = make_customer(phone="9811188888", name="Phone Scope Other")
        _make_court_booking(self.r1, self.customer.phone)
        _make_court_booking(self.r2, other.phone)

        result = admin_get_customer_full_profile(self.customer.name)
        court_bookings = result["data"]["court_bookings"]
        self.assertEqual(len(court_bookings), 1)
        self.assertEqual(court_bookings[0]["restaurant"], self.r1)

        frappe.db.delete("Court Booking", {"restaurant": self.r2})
        frappe.db.delete("Customer", other.name)
        frappe.db.commit()


class TestAdminCustomerFullProfileLoyaltyAndReferral(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("LOY01")
        self.customer = make_customer(phone="9811100004", name="Loyalty Test Customer")
        self.referee = make_customer(phone="9811100005", name="Referred Friend")

    def tearDown(self):
        _cleanup(self.r1, self.customer.name, self.customer.phone)
        frappe.db.delete("Customer", self.referee.name)
        frappe.db.commit()

    def test_loyalty_balance_and_ledger(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        make_loyalty_entry(self.customer.name, self.r1, 100, txn_type="Earn")
        make_loyalty_entry(self.customer.name, self.r1, 30, txn_type="Redeem")

        result = admin_get_customer_full_profile(self.customer.name)
        loyalty = result["data"]["loyalty"]
        self.assertEqual(loyalty["balance"], 70)
        self.assertEqual(loyalty["lifetime_earned"], 100)
        self.assertEqual(len(loyalty["entries"]), 2)
        self.assertEqual(result["data"]["stats"]["total_redeemed"], 30)

    def test_referral_made_direction(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        frappe.get_doc({
            "doctype": "Customer Referral",
            "referrer": self.customer.name,
            "referee": self.referee.name,
            "orders_credited": 1,
            "cashback_total": 50,
            "status": "active",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        made = result["data"]["referral"]["referrals_made"]
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0]["referee"], self.referee.name)
        self.assertEqual(made[0]["referee_phone"], self.referee.phone)

    def test_referred_by_direction(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        frappe.get_doc({
            "doctype": "Customer Referral",
            "referrer": self.referee.name,
            "referee": self.customer.name,
            "orders_credited": 2,
            "cashback_total": 100,
            "status": "active",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        referred_by = result["data"]["referral"]["referred_by"]
        self.assertIsNotNone(referred_by)
        self.assertEqual(referred_by["referrer_id"], self.referee.name)
        self.assertEqual(float(referred_by["cashback_total"]), 100)


class TestAdminCustomerFullProfileUGC(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("UGC01")
        self.customer = make_customer(phone="9811100006", name="UGC Test Customer")

    def tearDown(self):
        _cleanup(self.r1, self.customer.name, self.customer.phone)

    def test_ugc_submission_surfaced(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        _make_ugc_submission(self.r1, self.customer.name, self.customer.phone)

        result = admin_get_customer_full_profile(self.customer.name)
        ugc = result["data"]["ugc"]
        self.assertEqual(len(ugc), 1)
        self.assertEqual(ugc[0]["outlet_name"], f"Test Restaurant {self.r1}")

    def test_ugc_wallet_balance_only_counts_active_vouchers(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        _make_ugc_voucher(self.r1, self.customer.name, balance=150, status="active")
        _make_ugc_voucher(self.r1, self.customer.name, balance=999, status="exhausted")

        result = admin_get_customer_full_profile(self.customer.name)
        self.assertEqual(len(result["data"]["ugc_vouchers"]), 2)
        self.assertEqual(float(result["data"]["stats"]["ugc_wallet_balance"]), 150)

    def test_ugc_voucher_redemption_surfaced(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        voucher = _make_ugc_voucher(self.r1, self.customer.name, balance=100)
        frappe.get_doc({
            "doctype": "UGC Voucher Redemption",
            "voucher": voucher,
            "customer": self.customer.name,
            "restaurant": self.r1,
            "redeemed_at": now_datetime(),
            "bill_amount": 300,
            "amount_used": 100,
            "balance_before": 200,
            "balance_after": 100,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        self.assertEqual(len(result["data"]["ugc_voucher_redemptions"]), 1)
        self.assertEqual(float(result["data"]["ugc_voucher_redemptions"][0]["amount_used"]), 100)

    def test_fraud_flag_surfaced_and_flips_stat(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        result_before = admin_get_customer_full_profile(self.customer.name)
        self.assertFalse(result_before["data"]["stats"]["fraud_flagged"])

        frappe.get_doc({
            "doctype": "UGC Fraud Flag",
            "customer": self.customer.name,
            "restaurant": self.r1,
            "is_active": 1,
            "reason": "Duplicate video reused across submissions",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result_after = admin_get_customer_full_profile(self.customer.name)
        self.assertTrue(result_after["data"]["stats"]["fraud_flagged"])
        self.assertEqual(len(result_after["data"]["ugc_fraud_flags"]), 1)


class TestAdminCustomerFullProfileCouponsAndOffers(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("CPN01")
        self.customer = make_customer(phone="9811100007", name="Coupon Test Customer")

    def tearDown(self):
        _cleanup(self.r1, self.customer.name, self.customer.phone)

    def test_coupon_usage_surfaced_and_savings_summed(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        coupon = _make_coupon(self.r1, "SAVE50")
        order = _make_order(self.r1, self.customer.name, self.customer.phone, total=450)
        frappe.get_doc({
            "doctype": "Coupon Usage",
            "coupon": coupon,
            "customer": self.customer.name,
            "order": order,
            "usage_date": now_datetime(),
            "discount_amount": 50,
            "restaurant": self.r1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        self.assertEqual(len(result["data"]["coupon_usage"]), 1)
        self.assertEqual(result["data"]["stats"]["coupons_used"], 1)
        self.assertEqual(float(result["data"]["stats"]["total_coupon_savings"]), 50)

    def test_offer_claim_surfaced_via_phone_fallback(self):
        """Offer Claim rows may only have customer_phone set (no Customer link
        yet, e.g. claimed pre-verification) — must still be attributed."""
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        coupon = _make_coupon(self.r1, "HOTDROP1")
        frappe.get_doc({
            "doctype": "Offer Claim",
            "restaurant": self.r1,
            "coupon": coupon,
            "coupon_code": "HOTDROP1",
            "customer_phone": self.customer.phone,
            "claimed_at": now_datetime(),
            "locked_until": add_to_date(now_datetime(), hours=1),
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        self.assertEqual(len(result["data"]["offer_claims"]), 1)
        self.assertEqual(result["data"]["offer_claims"][0]["coupon_code"], "HOTDROP1")


class TestAdminCustomerFullProfileAddressesSessionsEngagement(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.r1 = _make_restaurant("MISC01")
        self.customer = make_customer(phone="9811100008", name="Misc Test Customer")

    def tearDown(self):
        _cleanup(self.r1, self.customer.name, self.customer.phone)

    def test_saved_address_surfaced(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        frappe.get_doc({
            "doctype": "Customer Address",
            "customer": self.customer.name,
            "label": "Home",
            "address_type": "home",
            "is_default": 1,
            "address_line_1": "221B Baker Street",
            "area": "Bandra West",
            "city": "Mumbai",
            "pincode": "400001",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        addresses = result["data"]["addresses"]
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0]["city"], "Mumbai")

    def test_session_surfaced_without_leaking_token(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        frappe.get_doc({
            "doctype": "Customer Session",
            "session_token": "super-secret-token-should-never-leak",
            "customer": self.customer.name,
            "phone": self.customer.phone,
            "device_info": "iPhone 15 Pro / iOS 18",
            "ip_address": "203.0.113.5",
            "last_used_at": now_datetime(),
            "expires_at": add_to_date(now_datetime(), days=30),
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        sessions = result["data"]["sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["device_info"], "iPhone 15 Pro / iOS 18")
        self.assertNotIn("session_token", sessions[0])

    def test_engagement_counts(self):
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        phone = self.customer.phone
        frappe.get_doc({"doctype": "Chills Outlet Follow", "outlet": self.r1, "customer_phone": phone}).insert(ignore_permissions=True)
        frappe.get_doc({
            "doctype": "Crowd Report", "reporter_phone": "9811100099", "reported_phone": phone,
            "message_id": "msg-1", "request_id": "req-1", "reason": "spam", "status": "pending",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

        result = admin_get_customer_full_profile(self.customer.name)
        eng = result["data"]["engagement"]
        self.assertEqual(eng["chills_outlet_follows"], 1)
        self.assertEqual(eng["crowd_reports_against"], 1)
        self.assertEqual(eng["crowd_reports_filed"], 0)

    def test_engagement_zero_when_no_phone(self):
        """A customer with no phone on file must not crash the phone-scoped
        engagement/court-booking/session queries."""
        from flamezo_backend.flamezo.api.admin import admin_get_customer_full_profile
        no_phone_customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "No Phone Customer",
            "customer_type": "Individual",
            "customer_group": "Individual",
        })
        no_phone_customer.insert(ignore_permissions=True)
        frappe.db.commit()
        try:
            result = admin_get_customer_full_profile(no_phone_customer.name)
            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["engagement"]["chills_likes"], 0)
            self.assertEqual(result["data"]["court_bookings"], [])
        finally:
            frappe.delete_doc("Customer", no_phone_customer.name, ignore_permissions=True)
            frappe.db.commit()


if __name__ == "__main__":
    unittest.main()
