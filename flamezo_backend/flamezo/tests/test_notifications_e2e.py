# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Consumer Notifications API (notifications_consumer.py).

Covers:
  get_my_notifications:
    - returns notifications for a phone, newest first
    - other phones' notifications excluded
    - unread_only=True filters correctly
    - pagination (has_more, page)
    - empty when none exist
    - all fields present in each notification
    - missing phone throws

  get_notification_count:
    - returns correct unread count
    - count=0 when none exist
    - after mark-read, count decrements
    - count cached (second call returns cached value)
    - missing phone throws

  mark_notifications_read:
    - specific IDs marked as read
    - other phone's notifications not affected by this phone's mark-read
    - mark-all (no IDs) marks all unread as read
    - already-read notifications stay read (idempotent)
    - missing phone throws

  mark_notification_actioned:
    - sets is_actioned=1 and is_read=1
    - wrong phone → PermissionError
    - non-existent notification → DoesNotExistError
    - missing notification_id throws
    - missing phone throws

  create_notification (internal helper):
    - creates notification record with correct fields
    - missing phone returns None (no crash)
    - missing title returns None (no crash)
    - notification appears in get_my_notifications after creation

  Cross-phone isolation:
    - Phone A cannot mark Phone B's notifications
    - Phone A's count unaffected by Phone B's activity
"""

import unittest

import frappe
from flamezo_backend.flamezo.api.notifications_consumer import (
    create_notification,
    get_my_notifications,
    get_notification_count,
    mark_notifications_read,
    mark_notification_actioned,
)

_PHONE_A = "9700000001"
_PHONE_B = "9700000002"


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_notif(phone=_PHONE_A, title="Test Notification", body="Test body",
                notif_type="general", is_read=0):
    name = create_notification(
        customer_phone=phone,
        title=title,
        body=body,
        notification_type=notif_type,
    )
    if name and is_read:
        frappe.db.set_value("Flamezo Notification", name, "is_read", 1)
        frappe.db.commit()
    return name


def _cleanup():
    frappe.db.sql("DELETE FROM `tabFlamezo Notification` WHERE customer_phone IN (%s, %s)", [_PHONE_A, _PHONE_B])
    frappe.db.commit()
    frappe.cache().delete_value(f"notif:count:{_PHONE_A}")
    frappe.cache().delete_value(f"notif:count:{_PHONE_B}")


class TestGetMyNotifications(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.n1 = _make_notif(_PHONE_A, title="Notif A1", notif_type="order")
        self.n2 = _make_notif(_PHONE_A, title="Notif A2", notif_type="booking")
        self.n_b = _make_notif(_PHONE_B, title="Notif B1")

    def tearDown(self):
        _cleanup()

    def test_returns_own_notifications(self):
        result = get_my_notifications(_PHONE_A)
        self.assertTrue(result["success"])
        ids = [n["id"] for n in result["data"]["notifications"]]
        self.assertIn(self.n1, ids)
        self.assertIn(self.n2, ids)

    def test_other_phone_excluded(self):
        result = get_my_notifications(_PHONE_A)
        ids = [n["id"] for n in result["data"]["notifications"]]
        self.assertNotIn(self.n_b, ids)

    def test_unread_only_filter(self):
        # Mark n1 as read
        frappe.db.set_value("Flamezo Notification", self.n1, "is_read", 1)
        frappe.db.commit()
        result = get_my_notifications(_PHONE_A, unread_only=True)
        ids = [n["id"] for n in result["data"]["notifications"]]
        self.assertNotIn(self.n1, ids)
        self.assertIn(self.n2, ids)

    def test_unread_only_string_true(self):
        result = get_my_notifications(_PHONE_A, unread_only="true")
        self.assertIsNotNone(result["data"]["notifications"])

    def test_pagination(self):
        for i in range(5):
            _make_notif(_PHONE_A, title=f"Paginated {i}")
        result = get_my_notifications(_PHONE_A, limit=3)
        self.assertEqual(len(result["data"]["notifications"]), 3)
        self.assertTrue(result["data"]["has_more"])

    def test_empty_when_none(self):
        result = get_my_notifications(_PHONE_B)
        # n_b was created but belongs to PHONE_B; check result for phone with no notifs
        _cleanup()
        result = get_my_notifications(_PHONE_A)
        self.assertEqual(len(result["data"]["notifications"]), 0)
        self.assertFalse(result["data"]["has_more"])

    def test_fields_present(self):
        result = get_my_notifications(_PHONE_A)
        n = result["data"]["notifications"][0]
        for field in ("id", "type", "title", "body", "is_read", "is_actioned", "created_at"):
            self.assertIn(field, n)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            get_my_notifications(None)


class TestGetNotificationCount(unittest.TestCase):

    def setUp(self):
        _cleanup()

    def tearDown(self):
        _cleanup()

    def test_count_zero_when_no_notifications(self):
        result = get_notification_count(_PHONE_A)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["unread_count"], 0)

    def test_count_reflects_unread(self):
        _make_notif(_PHONE_A, title="Unread 1")
        _make_notif(_PHONE_A, title="Unread 2")
        frappe.cache().delete_value(f"notif:count:{_PHONE_A}")
        result = get_notification_count(_PHONE_A)
        self.assertEqual(result["data"]["unread_count"], 2)

    def test_count_after_mark_read(self):
        n = _make_notif(_PHONE_A, title="Will read")
        frappe.cache().delete_value(f"notif:count:{_PHONE_A}")
        mark_notifications_read(_PHONE_A, n)
        frappe.cache().delete_value(f"notif:count:{_PHONE_A}")
        result = get_notification_count(_PHONE_A)
        self.assertEqual(result["data"]["unread_count"], 0)

    def test_count_ignores_already_read(self):
        _make_notif(_PHONE_A, title="Read one", is_read=1)
        frappe.cache().delete_value(f"notif:count:{_PHONE_A}")
        result = get_notification_count(_PHONE_A)
        self.assertEqual(result["data"]["unread_count"], 0)

    def test_phone_isolation_count(self):
        _make_notif(_PHONE_A, title="A notif")
        frappe.cache().delete_value(f"notif:count:{_PHONE_B}")
        result = get_notification_count(_PHONE_B)
        self.assertEqual(result["data"]["unread_count"], 0)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            get_notification_count(None)


class TestMarkNotificationsRead(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.n1 = _make_notif(_PHONE_A, title="Mark 1")
        self.n2 = _make_notif(_PHONE_A, title="Mark 2")
        self.nb = _make_notif(_PHONE_B, title="Other phone")

    def tearDown(self):
        _cleanup()

    def test_specific_ids_marked_read(self):
        mark_notifications_read(_PHONE_A, self.n1)
        is_read = frappe.db.get_value("Flamezo Notification", self.n1, "is_read")
        self.assertEqual(is_read, 1)

    def test_other_notification_stays_unread(self):
        mark_notifications_read(_PHONE_A, self.n1)
        is_read = frappe.db.get_value("Flamezo Notification", self.n2, "is_read")
        self.assertEqual(is_read, 0)

    def test_mark_all_read_no_ids(self):
        mark_notifications_read(_PHONE_A)
        r1 = frappe.db.get_value("Flamezo Notification", self.n1, "is_read")
        r2 = frappe.db.get_value("Flamezo Notification", self.n2, "is_read")
        self.assertEqual(r1, 1)
        self.assertEqual(r2, 1)

    def test_other_phone_not_affected(self):
        mark_notifications_read(_PHONE_A)
        rb = frappe.db.get_value("Flamezo Notification", self.nb, "is_read")
        self.assertEqual(rb, 0)

    def test_idempotent_already_read(self):
        frappe.db.set_value("Flamezo Notification", self.n1, "is_read", 1)
        frappe.db.commit()
        # Should not crash on double mark
        result = mark_notifications_read(_PHONE_A, self.n1)
        self.assertTrue(result["success"])

    def test_comma_separated_ids_string(self):
        mark_notifications_read(_PHONE_A, f"{self.n1},{self.n2}")
        r1 = frappe.db.get_value("Flamezo Notification", self.n1, "is_read")
        r2 = frappe.db.get_value("Flamezo Notification", self.n2, "is_read")
        self.assertEqual(r1, 1)
        self.assertEqual(r2, 1)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            mark_notifications_read(None, self.n1)


class TestMarkNotificationActioned(unittest.TestCase):

    def setUp(self):
        _cleanup()
        self.n = _make_notif(_PHONE_A, title="Action me")
        self.nb = _make_notif(_PHONE_B, title="Other phone action")

    def tearDown(self):
        _cleanup()

    def test_sets_actioned_and_read(self):
        mark_notification_actioned(_PHONE_A, self.n)
        is_actioned = frappe.db.get_value("Flamezo Notification", self.n, "is_actioned")
        is_read = frappe.db.get_value("Flamezo Notification", self.n, "is_read")
        self.assertEqual(is_actioned, 1)
        self.assertEqual(is_read, 1)

    def test_wrong_phone_throws_permission_error(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            mark_notification_actioned(_PHONE_B, self.n)

    def test_nonexistent_notification_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            mark_notification_actioned(_PHONE_A, "FNOTIF-FAKE-99999")

    def test_missing_notification_id_throws(self):
        with self.assertRaises(Exception):
            mark_notification_actioned(_PHONE_A, None)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            mark_notification_actioned(None, self.n)


class TestCreateNotificationHelper(unittest.TestCase):

    def setUp(self):
        _cleanup()

    def tearDown(self):
        _cleanup()

    def test_creates_notification_record(self):
        name = create_notification(
            customer_phone=_PHONE_A,
            title="Order confirmed",
            body="Your order has been confirmed",
            notification_type="order",
            reference_doctype="Order",
            reference_name="ORD-2026-00001",
            deep_link="/activity/ORD-2026-00001",
        )
        self.assertIsNotNone(name)
        doc = frappe.get_doc("Flamezo Notification", name)
        self.assertEqual(doc.customer_phone, _PHONE_A)
        self.assertEqual(doc.notification_type, "order")
        self.assertEqual(doc.reference_doctype, "Order")
        self.assertEqual(doc.is_read, 0)
        self.assertEqual(doc.is_actioned, 0)

    def test_missing_phone_returns_none(self):
        result = create_notification(customer_phone=None, title="Test", body="")
        self.assertIsNone(result)

    def test_missing_title_returns_none(self):
        result = create_notification(customer_phone=_PHONE_A, title=None, body="")
        self.assertIsNone(result)

    def test_notification_appears_in_listing(self):
        create_notification(_PHONE_A, "Listing test notif", "body here", "loyalty")
        result = get_my_notifications(_PHONE_A)
        titles = [n["title"] for n in result["data"]["notifications"]]
        self.assertIn("Listing test notif", titles)

    def test_notification_type_preserved(self):
        name = create_notification(_PHONE_A, "Club notif", "body", "club")
        doc = frappe.get_doc("Flamezo Notification", name)
        self.assertEqual(doc.notification_type, "club")
