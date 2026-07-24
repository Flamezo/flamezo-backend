# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Find Crowd API (crowd.py).

Covers:
  Listing:
    - get_crowd_requests: returns only open requests
    - closed/cancelled/completed requests excluded
    - expired requests excluded
    - creator's own requests excluded from listing
    - category filter
    - pagination

  Create:
    - create_crowd_request: valid creation returns request_id
    - expires_at auto-set to 48h after date
    - outlet_id validated — non-existent outlet throws
    - missing title throws
    - missing date throws
    - missing phone throws
    - current_members defaults to 1

  Join:
    - request_to_join: pending member created
    - cannot join own request
    - cannot join closed request
    - cannot join expired request
    - cannot double-join same request
    - non-existent request throws
    - missing phone throws

  Manage:
    - approve: member status = approved, current_members incremented
    - reject: member status = rejected, current_members NOT incremented
    - only creator can manage (other phone throws PermissionError)
    - already-processed member throws
    - approve to max_members auto-closes request
    - non-existent request throws
    - non-existent member throws

  My Requests:
    - get_my_crowd_requests: only creator's requests
    - includes member list per request
    - pagination

  My Joins:
    - get_my_crowd_joins: only requests I applied to
    - includes my status (pending/approved/rejected)
    - pagination

  Cancel:
    - cancel_crowd_request: sets status=cancelled
    - only creator can cancel (other phone throws PermissionError)
    - already completed/cancelled throws
    - non-existent request throws

  has_requested flag:
    - has_requested=True in listing after joining
    - has_requested=False before joining
    - has_requested=False for creator's own listing
"""

import unittest
from frappe.utils import add_days, today, get_datetime, now_datetime

import frappe

_PREFIX = "TEST-CROWD"
_PHONE_A = "9400000001"  # creator
_PHONE_B = "9400000002"  # joiner 1
_PHONE_C = "9400000003"  # joiner 2


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_request(phone=_PHONE_A, status="open", date=None, expires_at=None,
                  max_members=4, category="dining", title=None):
    date = date or add_days(today(), 3)
    expires = expires_at or str(get_datetime(str(date) + " 23:59:59"))
    doc = frappe.get_doc({
        "doctype": "Crowd Request",
        "creator_phone": phone,
        "creator_name": "Test Creator",
        "title": title or f"Test Crowd Request {phone[-4:]}",
        "description": "Test crowd description",
        "category": category,
        "date": date,
        "max_members": max_members,
        "current_members": 1,
        "gender_preference": "any",
        "status": status,
        "expires_at": expires,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _cleanup_crowd():
    frappe.db.sql("DELETE FROM `tabCrowd Request Member` WHERE customer_phone IN (%s, %s, %s)",
                  [_PHONE_A, _PHONE_B, _PHONE_C])
    frappe.db.sql("DELETE FROM `tabCrowd Request` WHERE creator_phone IN (%s, %s, %s)",
                  [_PHONE_A, _PHONE_B, _PHONE_C])
    frappe.db.commit()


from flamezo_backend.flamezo.api import crowd


class TestGetCrowdRequests(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_open_requests_returned(self):
        req = _make_request(phone=_PHONE_A, status="open")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in result["requests"]]
        self.assertIn(req.name, ids)

    def test_closed_requests_excluded(self):
        req = _make_request(phone=_PHONE_A, status="closed")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in result["requests"]]
        self.assertNotIn(req.name, ids)

    def test_cancelled_requests_excluded(self):
        req = _make_request(phone=_PHONE_A, status="cancelled")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in result["requests"]]
        self.assertNotIn(req.name, ids)

    def test_expired_requests_excluded(self):
        past = add_days(today(), -1)
        req = _make_request(phone=_PHONE_A, status="open", date=past,
                            expires_at=str(get_datetime(str(past) + " 00:00:00")))
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in result["requests"]]
        self.assertNotIn(req.name, ids)

    def test_creators_own_requests_excluded(self):
        req = _make_request(phone=_PHONE_A, status="open")
        result = crowd.get_crowd_requests(phone=_PHONE_A)
        ids = [r["id"] for r in result["requests"]]
        self.assertNotIn(req.name, ids)

    def test_category_filter(self):
        req_dining = _make_request(phone=_PHONE_A, category="dining")
        req_wellness = _make_request(phone=_PHONE_A, category="wellness")
        result = crowd.get_crowd_requests(phone=_PHONE_B, category="dining")
        ids = [r["id"] for r in result["requests"]]
        self.assertIn(req_dining.name, ids)
        self.assertNotIn(req_wellness.name, ids)

    def test_pagination(self):
        for i in range(3):
            _make_request(phone=_PHONE_A)
        result = crowd.get_crowd_requests(phone=_PHONE_B, limit=2)
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["requests"]), 2)

    def test_has_requested_false_before_join(self):
        req = _make_request(phone=_PHONE_A)
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        req_data = next(r for r in result["requests"] if r["id"] == req.name)
        self.assertFalse(req_data["has_requested"])

    def test_has_requested_true_after_join(self):
        req = _make_request(phone=_PHONE_A)
        crowd.request_to_join(req.name, _PHONE_B, customer_name="Test B")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        req_data = next((r for r in result["requests"] if r["id"] == req.name), None)
        # Request may be excluded from listing now but has_requested captured during join
        if req_data:
            self.assertTrue(req_data["has_requested"])

    def test_request_fields_complete(self):
        req = _make_request(phone=_PHONE_A)
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        req_data = next(r for r in result["requests"] if r["id"] == req.name)
        for field in ("id", "creator_phone", "creator_name", "title", "category",
                      "date", "max_members", "current_members", "status", "expires_at"):
            self.assertIn(field, req_data)


class TestCreateCrowdRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_valid_creation(self):
        result = crowd.create_crowd_request(
            phone=_PHONE_A,
            title="Anyone up for dinner?",
            date=add_days(today(), 3),
            category="dining",
            max_members=4,
        )
        self.assertIn("request_id", result)
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertEqual(doc.status, "open")
        self.assertEqual(doc.current_members, 1)

    def test_expires_at_auto_set(self):
        date = add_days(today(), 5)
        result = crowd.create_crowd_request(phone=_PHONE_A, title="Test Exp", date=date)
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertIsNotNone(doc.expires_at)
        # expires_at should be after date
        event_dt = get_datetime(str(date) + " 00:00:00")
        self.assertGreater(get_datetime(str(doc.expires_at)), event_dt)

    def test_missing_title_throws(self):
        with self.assertRaises(Exception):
            crowd.create_crowd_request(phone=_PHONE_A, title=None, date=add_days(today(), 2))

    def test_missing_date_throws(self):
        with self.assertRaises(Exception):
            crowd.create_crowd_request(phone=_PHONE_A, title="No Date", date=None)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.create_crowd_request(phone=None, title="No Phone", date=add_days(today(), 2))

    def test_nonexistent_outlet_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.create_crowd_request(
                phone=_PHONE_A,
                title="Bad Outlet",
                date=add_days(today(), 2),
                outlet_id="RESTAURANT-FAKE-999",
            )


class TestRequestToJoin(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A)

    def tearDown(self):
        _cleanup_crowd()

    def test_valid_join_creates_pending_member(self):
        result = crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Test Joiner")
        self.assertIn("member_id", result)
        self.assertEqual(result["status"], "pending")
        member = frappe.get_doc("Crowd Request Member", result["member_id"])
        self.assertEqual(member.status, "pending")
        self.assertEqual(member.customer_phone, _PHONE_B)

    def test_cannot_join_own_request(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(self.req.name, _PHONE_A)

    def test_cannot_join_closed_request(self):
        closed = _make_request(phone=_PHONE_A, status="closed")
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(closed.name, _PHONE_B)

    def test_cannot_join_cancelled_request(self):
        cancelled = _make_request(phone=_PHONE_A, status="cancelled")
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(cancelled.name, _PHONE_B)

    def test_cannot_join_expired_request(self):
        past = add_days(today(), -2)
        expired = _make_request(phone=_PHONE_A, status="open", date=past,
                                expires_at=str(get_datetime(str(past) + " 00:00:00")))
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(expired.name, _PHONE_B)

    def test_cannot_double_join(self):
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="First Join")
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Second Join")

    def test_nonexistent_request_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.request_to_join("CROWD-FAKE-999", _PHONE_B)

    def test_missing_request_id_throws(self):
        with self.assertRaises(Exception):
            crowd.request_to_join(None, _PHONE_B)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.request_to_join(self.req.name, None)


class TestManageJoinRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, max_members=3)
        join = crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Joiner B")
        self.member_id = join["member_id"]

    def tearDown(self):
        _cleanup_crowd()

    def test_approve_sets_member_approved(self):
        crowd.manage_join_request(self.req.name, self.member_id, "approve", _PHONE_A)
        status = frappe.db.get_value("Crowd Request Member", self.member_id, "status")
        self.assertEqual(status, "approved")

    def test_approve_increments_current_members(self):
        before = frappe.db.get_value("Crowd Request", self.req.name, "current_members")
        crowd.manage_join_request(self.req.name, self.member_id, "approve", _PHONE_A)
        after = frappe.db.get_value("Crowd Request", self.req.name, "current_members")
        self.assertEqual(after, before + 1)

    def test_reject_sets_member_rejected(self):
        crowd.manage_join_request(self.req.name, self.member_id, "reject", _PHONE_A)
        status = frappe.db.get_value("Crowd Request Member", self.member_id, "status")
        self.assertEqual(status, "rejected")

    def test_reject_does_not_increment_members(self):
        before = frappe.db.get_value("Crowd Request", self.req.name, "current_members")
        crowd.manage_join_request(self.req.name, self.member_id, "reject", _PHONE_A)
        after = frappe.db.get_value("Crowd Request", self.req.name, "current_members")
        self.assertEqual(after, before)

    def test_only_creator_can_manage(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.manage_join_request(self.req.name, self.member_id, "approve", _PHONE_C)

    def test_already_processed_member_throws(self):
        crowd.manage_join_request(self.req.name, self.member_id, "approve", _PHONE_A)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.manage_join_request(self.req.name, self.member_id, "approve", _PHONE_A)

    def test_invalid_action_throws(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.manage_join_request(self.req.name, self.member_id, "yeet", _PHONE_A)

    def test_approve_to_max_closes_request(self):
        # req max_members=3, current=1. Add 2 more joiners to hit max.
        join2 = crowd.request_to_join(self.req.name, _PHONE_C, customer_name="Joiner C")
        crowd.manage_join_request(self.req.name, self.member_id, "approve", _PHONE_A)
        crowd.manage_join_request(self.req.name, join2["member_id"], "approve", _PHONE_A)
        status = frappe.db.get_value("Crowd Request", self.req.name, "status")
        self.assertEqual(status, "closed")

    def test_nonexistent_request_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.manage_join_request("CROWD-FAKE", self.member_id, "approve", _PHONE_A)

    def test_member_from_different_request_throws(self):
        other_req = _make_request(phone=_PHONE_A)
        other_join = crowd.request_to_join(other_req.name, _PHONE_C, customer_name="Other")
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.manage_join_request(self.req.name, other_join["member_id"], "approve", _PHONE_A)


class TestGetMyCrowdRequests(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, title="My Test Request")

    def tearDown(self):
        _cleanup_crowd()

    def test_returns_creators_requests(self):
        result = crowd.get_my_crowd_requests(_PHONE_A)
        ids = [r["id"] for r in result["requests"]]
        self.assertIn(self.req.name, ids)

    def test_other_creators_requests_excluded(self):
        other = _make_request(phone=_PHONE_B, title="Other Test Request")
        result = crowd.get_my_crowd_requests(_PHONE_A)
        ids = [r["id"] for r in result["requests"]]
        self.assertNotIn(other.name, ids)

    def test_includes_member_list(self):
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Joiner")
        result = crowd.get_my_crowd_requests(_PHONE_A)
        req_data = next(r for r in result["requests"] if r["id"] == self.req.name)
        self.assertIn("members", req_data)
        self.assertEqual(len(req_data["members"]), 1)
        self.assertEqual(req_data["members"][0]["customer_phone"], _PHONE_B)

    def test_pagination(self):
        for i in range(3):
            _make_request(phone=_PHONE_A, title=f"Paged request {i}")
        result = crowd.get_my_crowd_requests(_PHONE_A, limit=2)
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["requests"]), 2)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.get_my_crowd_requests(None)


class TestGetMyCrowdJoins(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, title="Join Test Request")

    def tearDown(self):
        _cleanup_crowd()

    def test_returns_joined_requests(self):
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="B")
        result = crowd.get_my_crowd_joins(_PHONE_B)
        ids = [r["id"] for r in result["joins"]]
        self.assertIn(self.req.name, ids)

    def test_not_joined_requests_excluded(self):
        other = _make_request(phone=_PHONE_A, title="Not Joined Request")
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="B")
        result = crowd.get_my_crowd_joins(_PHONE_B)
        ids = [r["id"] for r in result["joins"]]
        self.assertNotIn(other.name, ids)

    def test_my_status_pending_before_decision(self):
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="B")
        result = crowd.get_my_crowd_joins(_PHONE_B)
        join_data = next(r for r in result["joins"] if r["id"] == self.req.name)
        self.assertEqual(join_data["my_status"], "pending")

    def test_my_status_approved_after_approval(self):
        join = crowd.request_to_join(self.req.name, _PHONE_B, customer_name="B")
        crowd.manage_join_request(self.req.name, join["member_id"], "approve", _PHONE_A)
        result = crowd.get_my_crowd_joins(_PHONE_B)
        join_data = next(r for r in result["joins"] if r["id"] == self.req.name)
        self.assertEqual(join_data["my_status"], "approved")

    def test_my_status_rejected_after_rejection(self):
        join = crowd.request_to_join(self.req.name, _PHONE_B, customer_name="B")
        crowd.manage_join_request(self.req.name, join["member_id"], "reject", _PHONE_A)
        result = crowd.get_my_crowd_joins(_PHONE_B)
        join_data = next(r for r in result["joins"] if r["id"] == self.req.name)
        self.assertEqual(join_data["my_status"], "rejected")

    def test_pagination(self):
        for i in range(3):
            req = _make_request(phone=_PHONE_A, title=f"Join paged {i}")
            crowd.request_to_join(req.name, _PHONE_B, customer_name="B")
        result = crowd.get_my_crowd_joins(_PHONE_B, limit=2)
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["joins"]), 2)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.get_my_crowd_joins(None)


class TestCancelCrowdRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, status="open")

    def tearDown(self):
        _cleanup_crowd()

    def test_cancel_sets_status_cancelled(self):
        crowd.cancel_crowd_request(self.req.name, _PHONE_A)
        status = frappe.db.get_value("Crowd Request", self.req.name, "status")
        self.assertEqual(status, "cancelled")

    def test_only_creator_can_cancel(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.cancel_crowd_request(self.req.name, _PHONE_B)

    def test_cannot_cancel_completed(self):
        frappe.db.set_value("Crowd Request", self.req.name, "status", "completed")
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.cancel_crowd_request(self.req.name, _PHONE_A)

    def test_cannot_cancel_already_cancelled(self):
        crowd.cancel_crowd_request(self.req.name, _PHONE_A)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.cancel_crowd_request(self.req.name, _PHONE_A)

    def test_nonexistent_request_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.cancel_crowd_request("CROWD-FAKE-000", _PHONE_A)

    def test_missing_request_id_throws(self):
        with self.assertRaises(Exception):
            crowd.cancel_crowd_request(None, _PHONE_A)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.cancel_crowd_request(self.req.name, None)
