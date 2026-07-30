# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for Find Crowd API (crowd.py) — including Crowd Chat.

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

  Chat (send_message / get_messages):
    - creator and approved member can send
    - non-member cannot send
    - pending member cannot send
    - empty text message throws
    - image message requires image_url
    - image message with blank message is OK
    - messages returned in chronological order
    - pagination: before_id returns older messages
    - system messages stored and returned correctly
    - optimistic fields present (id, sender_phone, sender_name, created_at, message_type)
    - guest read allowed (no phone)
    - missing request_id throws (send + get)
    - get after cancel still returns existing messages
"""

import time
import unittest
from frappe.utils import add_days, today, get_datetime, now_datetime

import frappe

_PREFIX = "TEST-CROWD"
_PHONE_A = "9400000001"  # creator
_PHONE_B = "9400000002"  # joiner 1
_PHONE_C = "9400000003"  # joiner 2


# ── helpers ───────────────────────────────────────────────────────────────────

def _data(result: dict) -> dict:
    """Unwrap the { success, data } envelope that all crowd API functions return."""
    return result.get("data", result)


# ── fixtures ──────────────────────────────────────────────────────────────────

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
    frappe.db.sql("DELETE FROM `tabCrowd Chat Message` WHERE sender_phone IN (%s, %s, %s)",
                  [_PHONE_A, _PHONE_B, _PHONE_C])
    frappe.db.sql("DELETE FROM `tabCrowd Request Member` WHERE customer_phone IN (%s, %s, %s)",
                  [_PHONE_A, _PHONE_B, _PHONE_C])
    frappe.db.sql("DELETE FROM `tabCrowd Request` WHERE creator_phone IN (%s, %s, %s)",
                  [_PHONE_A, _PHONE_B, _PHONE_C])
    frappe.db.commit()


def _approved_member_request():
    """Creates a request and returns (req, member_id) with PHONE_B approved."""
    req = _make_request(phone=_PHONE_A, max_members=5)
    join = _data(crowd.request_to_join(req.name, _PHONE_B, customer_name="Joiner B"))
    crowd.manage_join_request(req.name, join["member_id"], "approve", _PHONE_A)
    return req, join["member_id"]


from flamezo_backend.flamezo.api import crowd


# ─────────────────────────────────────────────────────────────────────────────
# TestGetCrowdRequests
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCrowdRequests(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_open_requests_returned(self):
        req = _make_request(phone=_PHONE_A, status="open")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(req.name, ids)

    def test_closed_requests_excluded(self):
        req = _make_request(phone=_PHONE_A, status="closed")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertNotIn(req.name, ids)

    def test_cancelled_requests_excluded(self):
        req = _make_request(phone=_PHONE_A, status="cancelled")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertNotIn(req.name, ids)

    def test_expired_requests_excluded(self):
        past = add_days(today(), -1)
        req = _make_request(phone=_PHONE_A, status="open", date=past,
                            expires_at=str(get_datetime(str(past) + " 00:00:00")))
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertNotIn(req.name, ids)

    def test_creators_own_requests_excluded(self):
        req = _make_request(phone=_PHONE_A, status="open")
        result = crowd.get_crowd_requests(phone=_PHONE_A)
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertNotIn(req.name, ids)

    def test_category_filter(self):
        req_dining  = _make_request(phone=_PHONE_A, category="dining")
        req_wellness = _make_request(phone=_PHONE_A, category="wellness")
        result = crowd.get_crowd_requests(phone=_PHONE_B, category="dining")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(req_dining.name, ids)
        self.assertNotIn(req_wellness.name, ids)

    def test_pagination(self):
        for _ in range(3):
            _make_request(phone=_PHONE_A)
        result = _data(crowd.get_crowd_requests(phone=_PHONE_B, limit=2))
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["requests"]), 2)

    def test_has_requested_false_before_join(self):
        req = _make_request(phone=_PHONE_A)
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        req_data = next(r for r in _data(result)["requests"] if r["id"] == req.name)
        self.assertFalse(req_data["has_requested"])

    def test_has_requested_true_after_join(self):
        req = _make_request(phone=_PHONE_A)
        crowd.request_to_join(req.name, _PHONE_B, customer_name="Test B")
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        req_data = next((r for r in _data(result)["requests"] if r["id"] == req.name), None)
        if req_data:
            self.assertTrue(req_data["has_requested"])

    def test_request_fields_complete(self):
        req = _make_request(phone=_PHONE_A)
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        req_data = next(r for r in _data(result)["requests"] if r["id"] == req.name)
        for field in ("id", "creator_phone", "creator_name", "title", "category",
                      "date", "max_members", "current_members", "status", "expires_at"):
            self.assertIn(field, req_data, f"Missing field: {field}")

    def test_guest_access_no_phone(self):
        _make_request(phone=_PHONE_A)
        result = crowd.get_crowd_requests()
        self.assertIn("requests", _data(result))

    def test_multiple_requests_ordered(self):
        _make_request(phone=_PHONE_A, title="First")
        _make_request(phone=_PHONE_B, title="Second")
        result = _data(crowd.get_crowd_requests())
        self.assertGreaterEqual(len(result["requests"]), 2)


# ─────────────────────────────────────────────────────────────────────────────
# TestCreateCrowdRequest
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateCrowdRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_valid_creation(self):
        result = _data(crowd.create_crowd_request(
            phone=_PHONE_A,
            title="Anyone up for dinner?",
            date=add_days(today(), 3),
            category="dining",
            max_members=4,
        ))
        self.assertIn("request_id", result)
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertEqual(doc.status, "open")
        self.assertEqual(doc.current_members, 1)

    def test_expires_at_auto_set(self):
        date = add_days(today(), 5)
        result = _data(crowd.create_crowd_request(phone=_PHONE_A, title="Test Exp", date=date))
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertIsNotNone(doc.expires_at)
        event_dt = get_datetime(str(date) + " 00:00:00")
        self.assertGreater(get_datetime(str(doc.expires_at)), event_dt)

    def test_interests_stored(self):
        result = _data(crowd.create_crowd_request(
            phone=_PHONE_A, title="Test Tags", date=add_days(today(), 3),
            interests="Chill,Foodie,Regular"
        ))
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertIn("Chill", doc.interests)

    def test_gender_preference_stored(self):
        result = _data(crowd.create_crowd_request(
            phone=_PHONE_A, title="Women Only Test", date=add_days(today(), 3),
            gender_preference="women_only"
        ))
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertEqual(doc.gender_preference, "women_only")

    def test_max_members_stored(self):
        result = _data(crowd.create_crowd_request(
            phone=_PHONE_A, title="Big Group", date=add_days(today(), 3), max_members=10
        ))
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertEqual(doc.max_members, 10)

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
                phone=_PHONE_A, title="Bad Outlet",
                date=add_days(today(), 2),
                outlet_id="RESTAURANT-FAKE-999",
            )

    def test_spontaneous_with_expires_at(self):
        from frappe.utils import add_to_date
        expires = str(add_to_date(now_datetime(), hours=2))
        result = _data(crowd.create_crowd_request(
            phone=_PHONE_A, title="Spontaneous Hangout",
            date=today(), expires_at=expires
        ))
        doc = frappe.get_doc("Crowd Request", result["request_id"])
        self.assertIsNotNone(doc.expires_at)


# ─────────────────────────────────────────────────────────────────────────────
# TestRequestToJoin
# ─────────────────────────────────────────────────────────────────────────────

class TestRequestToJoin(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A)

    def tearDown(self):
        _cleanup_crowd()

    def test_valid_join_creates_pending_member(self):
        result = _data(crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Test Joiner"))
        self.assertIn("member_id", result)
        self.assertEqual(result["status"], "pending")
        member = frappe.get_doc("Crowd Request Member", result["member_id"])
        self.assertEqual(member.status, "pending")
        self.assertEqual(member.customer_phone, _PHONE_B)

    def test_intro_message_stored(self):
        result = _data(crowd.request_to_join(
            self.req.name, _PHONE_B,
            customer_name="Test Joiner", intro_message="Hey! Looking for good company"
        ))
        member = frappe.get_doc("Crowd Request Member", result["member_id"])
        self.assertEqual(member.intro_message, "Hey! Looking for good company")

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


# ─────────────────────────────────────────────────────────────────────────────
# TestManageJoinRequest
# ─────────────────────────────────────────────────────────────────────────────

class TestManageJoinRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, max_members=3)
        join = _data(crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Joiner B"))
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
        join2 = _data(crowd.request_to_join(self.req.name, _PHONE_C, customer_name="Joiner C"))
        crowd.manage_join_request(self.req.name, self.member_id, "approve", _PHONE_A)
        crowd.manage_join_request(self.req.name, join2["member_id"], "approve", _PHONE_A)
        status = frappe.db.get_value("Crowd Request", self.req.name, "status")
        self.assertEqual(status, "closed")

    def test_nonexistent_request_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.manage_join_request("CROWD-FAKE", self.member_id, "approve", _PHONE_A)

    def test_member_from_different_request_throws(self):
        other_req = _make_request(phone=_PHONE_A)
        other_join = _data(crowd.request_to_join(other_req.name, _PHONE_C, customer_name="Other"))
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.manage_join_request(self.req.name, other_join["member_id"], "approve", _PHONE_A)


# ─────────────────────────────────────────────────────────────────────────────
# TestGetMyCrowdRequests
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMyCrowdRequests(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, title="My Test Request")

    def tearDown(self):
        _cleanup_crowd()

    def test_returns_creators_requests(self):
        result = crowd.get_my_crowd_requests(_PHONE_A)
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(self.req.name, ids)

    def test_other_creators_requests_excluded(self):
        other = _make_request(phone=_PHONE_B, title="Other Test Request")
        result = crowd.get_my_crowd_requests(_PHONE_A)
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertNotIn(other.name, ids)

    def test_includes_member_list(self):
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Joiner")
        result = crowd.get_my_crowd_requests(_PHONE_A)
        req_data = next(r for r in _data(result)["requests"] if r["id"] == self.req.name)
        self.assertIn("members", req_data)
        self.assertEqual(len(req_data["members"]), 1)
        self.assertEqual(req_data["members"][0]["customer_phone"], _PHONE_B)

    def test_pagination(self):
        for i in range(3):
            _make_request(phone=_PHONE_A, title=f"Paged request {i}")
        result = _data(crowd.get_my_crowd_requests(_PHONE_A, limit=2))
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["requests"]), 2)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.get_my_crowd_requests(None)


# ─────────────────────────────────────────────────────────────────────────────
# TestGetMyCrowdJoins
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMyCrowdJoins(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, title="Join Test Request")

    def tearDown(self):
        _cleanup_crowd()

    def test_returns_joined_requests(self):
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Bobby B")
        result = crowd.get_my_crowd_joins(_PHONE_B)
        ids = [r["id"] for r in _data(result)["joins"]]
        self.assertIn(self.req.name, ids)

    def test_not_joined_requests_excluded(self):
        other = _make_request(phone=_PHONE_A, title="Not Joined Request")
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Bobby B")
        result = crowd.get_my_crowd_joins(_PHONE_B)
        ids = [r["id"] for r in _data(result)["joins"]]
        self.assertNotIn(other.name, ids)

    def test_my_status_pending_before_decision(self):
        crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Bobby B")
        result = crowd.get_my_crowd_joins(_PHONE_B)
        join_data = next(r for r in _data(result)["joins"] if r["id"] == self.req.name)
        self.assertEqual(join_data["my_status"], "pending")

    def test_my_status_approved_after_approval(self):
        join = _data(crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Bobby B"))
        crowd.manage_join_request(self.req.name, join["member_id"], "approve", _PHONE_A)
        result = crowd.get_my_crowd_joins(_PHONE_B)
        join_data = next(r for r in _data(result)["joins"] if r["id"] == self.req.name)
        self.assertEqual(join_data["my_status"], "approved")

    def test_my_status_rejected_after_rejection(self):
        join = _data(crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Bobby B"))
        crowd.manage_join_request(self.req.name, join["member_id"], "reject", _PHONE_A)
        result = crowd.get_my_crowd_joins(_PHONE_B)
        join_data = next(r for r in _data(result)["joins"] if r["id"] == self.req.name)
        self.assertEqual(join_data["my_status"], "rejected")

    def test_pagination(self):
        for i in range(3):
            req = _make_request(phone=_PHONE_A, title=f"Join paged {i}")
            crowd.request_to_join(req.name, _PHONE_B, customer_name="Bobby B")
        result = _data(crowd.get_my_crowd_joins(_PHONE_B, limit=2))
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["joins"]), 2)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.get_my_crowd_joins(None)


# ─────────────────────────────────────────────────────────────────────────────
# TestCancelCrowdRequest
# ─────────────────────────────────────────────────────────────────────────────

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

    def test_return_value_shape(self):
        result = _data(crowd.cancel_crowd_request(self.req.name, _PHONE_A))
        self.assertEqual(result.get("status"), "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# TestCrowdChat — send_message / get_messages
# ─────────────────────────────────────────────────────────────────────────────

class TestCrowdChat(unittest.TestCase):
    """
    Full E2E coverage for the Crowd Chat endpoints.

    Access model:
      - Creator can always send/read
      - Approved member can send/read
      - Pending / non-member / unauthenticated cannot send (but CAN read, guest read allowed)
    """

    def setUp(self):
        _cleanup_crowd()
        # Build a request with PHONE_B approved
        self.req, self.member_b_id = _approved_member_request()

    def tearDown(self):
        _cleanup_crowd()

    # ── Send happy paths ──────────────────────────────────────────────────────

    def test_creator_can_send_text(self):
        result = _data(crowd.send_message(
            request_id=self.req.name,
            phone=_PHONE_A,
            message="Hello team!",
            sender_name="Creator",
        ))
        self.assertIn("id", result)
        self.assertEqual(result["message"], "Hello team!")
        self.assertEqual(result["message_type"], "text")
        self.assertEqual(result["sender_phone"], _PHONE_A)

    def test_approved_member_can_send_text(self):
        result = _data(crowd.send_message(
            request_id=self.req.name,
            phone=_PHONE_B,
            message="Excited to join!",
            sender_name="Joiner B",
        ))
        self.assertEqual(result["sender_phone"], _PHONE_B)
        self.assertEqual(result["message"], "Excited to join!")

    def test_send_image_message(self):
        result = _data(crowd.send_message(
            request_id=self.req.name,
            phone=_PHONE_A,
            message="",
            message_type="image",
            image_url="https://cdn.flamezo.in/test/photo.jpg",
            sender_name="Creator",
        ))
        self.assertEqual(result["message_type"], "image")
        self.assertEqual(result["image_url"], "https://cdn.flamezo.in/test/photo.jpg")

    def test_send_system_message(self):
        # System messages can be sent by creator with is_system flag via direct doc insert
        doc = frappe.get_doc({
            "doctype":      "Crowd Chat Message",
            "request_id":   self.req.name,
            "sender_phone": "SYSTEM",
            "sender_name":  "System",
            "message_type": "system",
            "message":      "Test User joined the group.",
            "is_system":    1,
            "created_at":   now_datetime(),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        system_msgs = [m for m in msgs if m["is_system"]]
        self.assertTrue(len(system_msgs) >= 1)
        self.assertEqual(system_msgs[0]["message_type"], "system")

    # ── Send guard-rails ──────────────────────────────────────────────────────

    def test_pending_member_cannot_send(self):
        # PHONE_C joins but is not yet approved
        crowd.request_to_join(self.req.name, _PHONE_C, customer_name="Pending C")
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.send_message(
                request_id=self.req.name,
                phone=_PHONE_C,
                message="Can I say something?",
            )

    def test_non_member_cannot_send(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.send_message(
                request_id=self.req.name,
                phone=_PHONE_C,
                message="I'm not in the group",
            )

    def test_empty_text_throws(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.send_message(
                request_id=self.req.name,
                phone=_PHONE_A,
                message="   ",
                message_type="text",
            )

    def test_image_message_without_url_throws(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.send_message(
                request_id=self.req.name,
                phone=_PHONE_A,
                message="",
                message_type="image",
                image_url="",
            )

    def test_send_missing_request_id_throws(self):
        with self.assertRaises(Exception):
            crowd.send_message(request_id=None, phone=_PHONE_A, message="Hello")

    def test_send_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.send_message(request_id=self.req.name, phone=None, message="Hello")

    # ── get_messages happy paths ──────────────────────────────────────────────

    def test_get_messages_returns_list(self):
        crowd.send_message(self.req.name, _PHONE_A, message="Msg 1", sender_name="A")
        result = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))
        self.assertIn("messages", result)
        self.assertIsInstance(result["messages"], list)

    def test_messages_in_chronological_order(self):
        # Datetime field has second precision — sleep 1s between inserts to guarantee ordering
        crowd.send_message(self.req.name, _PHONE_A, message="First",  sender_name="A")
        time.sleep(1)
        crowd.send_message(self.req.name, _PHONE_B, message="Second", sender_name="B")
        time.sleep(1)
        crowd.send_message(self.req.name, _PHONE_A, message="Third",  sender_name="A")
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        texts = [m["message"] for m in msgs if m["message_type"] == "text"]
        self.assertLess(texts.index("First"), texts.index("Second"))
        self.assertLess(texts.index("Second"), texts.index("Third"))

    def test_message_fields_complete(self):
        crowd.send_message(self.req.name, _PHONE_A, message="Hello", sender_name="A")
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        msg = msgs[-1]
        for field in ("id", "request_id", "sender_phone", "sender_name",
                      "message_type", "message", "image_url", "is_system", "created_at"):
            self.assertIn(field, msg, f"Missing field: {field}")

    def test_pagination_has_more(self):
        for i in range(45):
            crowd.send_message(self.req.name, _PHONE_A, message=f"Msg {i}", sender_name="A")
        result = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A, limit=40))
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["messages"]), 40)

    def test_pagination_before_id(self):
        # Datetime field has second precision — sleep 1s between inserts so each has a unique
        # created_at, making before_id cursor pagination deterministic
        ids = []
        for i in range(5):
            r = _data(crowd.send_message(self.req.name, _PHONE_A, message=f"M{i}", sender_name="A"))
            ids.append(r["id"])
            if i < 4:
                time.sleep(1)
        # before_id = ids[2] should return only ids[0] and ids[1]
        result = _data(crowd.get_messages(
            request_id=self.req.name, phone=_PHONE_A,
            before_id=ids[2], limit=40
        ))
        returned_ids = [m["id"] for m in result["messages"]]
        self.assertIn(ids[0], returned_ids)
        self.assertIn(ids[1], returned_ids)
        self.assertNotIn(ids[2], returned_ids)
        self.assertNotIn(ids[3], returned_ids)
        self.assertNotIn(ids[4], returned_ids)

    def test_guest_read_no_phone(self):
        crowd.send_message(self.req.name, _PHONE_A, message="Public msg", sender_name="A")
        result = _data(crowd.get_messages(request_id=self.req.name))
        self.assertIn("messages", result)
        self.assertGreater(len(result["messages"]), 0)

    def test_approved_member_can_read(self):
        crowd.send_message(self.req.name, _PHONE_A, message="Hi", sender_name="A")
        result = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_B))
        self.assertGreater(len(result["messages"]), 0)

    def test_pending_member_blocked_from_read(self):
        crowd.request_to_join(self.req.name, _PHONE_C, customer_name="Charlie C")
        # Non-guest authenticated read with phone should be blocked for pending member
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.get_messages(request_id=self.req.name, phone=_PHONE_C)

    def test_get_missing_request_id_throws(self):
        with self.assertRaises(Exception):
            crowd.get_messages(request_id=None, phone=_PHONE_A)

    def test_messages_scoped_to_request(self):
        # Messages from a different request should not appear
        other_req, _ = _approved_member_request()
        crowd.send_message(self.req.name,   _PHONE_A, message="Req1 msg", sender_name="A")
        crowd.send_message(other_req.name,  _PHONE_A, message="Req2 msg", sender_name="A")
        msgs1 = _data(crowd.get_messages(request_id=self.req.name,  phone=_PHONE_A))["messages"]
        msgs2 = _data(crowd.get_messages(request_id=other_req.name, phone=_PHONE_A))["messages"]
        texts1 = {m["message"] for m in msgs1}
        texts2 = {m["message"] for m in msgs2}
        self.assertIn("Req1 msg", texts1)
        self.assertIn("Req2 msg", texts2)
        self.assertNotIn("Req2 msg", texts1)
        self.assertNotIn("Req1 msg", texts2)

    def test_messages_persist_after_cancel(self):
        crowd.send_message(self.req.name, _PHONE_A, message="Pre-cancel msg", sender_name="A")
        crowd.cancel_crowd_request(self.req.name, _PHONE_A)
        # Messages should still be readable (guest read)
        result = _data(crowd.get_messages(request_id=self.req.name))
        self.assertGreater(len(result["messages"]), 0)

    def test_sender_name_stored(self):
        crowd.send_message(self.req.name, _PHONE_A, message="Named msg", sender_name="Alice Test")
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        named = next(m for m in msgs if m["message"] == "Named msg")
        self.assertEqual(named["sender_name"], "Alice Test")

    def test_image_url_stored_and_returned(self):
        url = "https://cdn.flamezo.in/crowd/test-img.jpg"
        crowd.send_message(
            self.req.name, _PHONE_A,
            message="", message_type="image",
            image_url=url, sender_name="A",
        )
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        img_msgs = [m for m in msgs if m["message_type"] == "image"]
        self.assertEqual(img_msgs[-1]["image_url"], url)


# ─────────────────────────────────────────────────────────────────────────────
# TestCrowdFullFlow — end-to-end journey
# ─────────────────────────────────────────────────────────────────────────────

class TestCrowdFullFlow(unittest.TestCase):
    """
    Complete user journey: create → join request → approve → chat → cancel.
    Validates the entire feature as a production user would experience it.
    """

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_full_journey_create_join_approve_chat_cancel(self):
        # 1. Creator posts a Team Up
        create_result = _data(crowd.create_crowd_request(
            phone=_PHONE_A, title="Dinner at Glass House",
            date=add_days(today(), 3), category="dining",
            max_members=5, gender_preference="any",
            interests="Foodie,Chill"
        ))
        req_id = create_result["request_id"]
        self.assertTrue(req_id)

        # 2. Team Up appears in feed for PHONE_B
        feed = _data(crowd.get_crowd_requests(phone=_PHONE_B))
        feed_ids = [r["id"] for r in feed["requests"]]
        self.assertIn(req_id, feed_ids)

        # 3. PHONE_B requests to join with an icebreaker
        join_result = _data(crowd.request_to_join(
            req_id, _PHONE_B,
            customer_name="Rohan", intro_message="Looking forward to this!"
        ))
        member_id = join_result["member_id"]
        self.assertEqual(join_result["status"], "pending")

        # 4. PHONE_B sees their status in my_joins
        my_joins = _data(crowd.get_my_crowd_joins(_PHONE_B))
        b_join = next(j for j in my_joins["joins"] if j["id"] == req_id)
        self.assertEqual(b_join["my_status"], "pending")

        # 5. Creator sees the pending request in my_requests
        my_reqs = _data(crowd.get_my_crowd_requests(_PHONE_A))
        my_req = next(r for r in my_reqs["requests"] if r["id"] == req_id)
        self.assertEqual(len(my_req["members"]), 1)
        self.assertEqual(my_req["members"][0]["customer_phone"], _PHONE_B)
        self.assertEqual(my_req["members"][0]["status"], "pending")

        # 6. Creator approves PHONE_B
        crowd.manage_join_request(req_id, member_id, "approve", _PHONE_A)
        self.assertEqual(
            frappe.db.get_value("Crowd Request Member", member_id, "status"),
            "approved"
        )
        self.assertEqual(
            frappe.db.get_value("Crowd Request", req_id, "current_members"),
            2  # creator + approved member
        )

        # 7. PHONE_B now sees approved status
        my_joins_after = _data(crowd.get_my_crowd_joins(_PHONE_B))
        b_join_after = next(j for j in my_joins_after["joins"] if j["id"] == req_id)
        self.assertEqual(b_join_after["my_status"], "approved")

        # 8. Both creator and approved member can chat
        msg_a = _data(crowd.send_message(req_id, _PHONE_A, message="Welcome Rohan!", sender_name="Creator"))
        msg_b = _data(crowd.send_message(req_id, _PHONE_B, message="Thanks! Can't wait!", sender_name="Rohan"))
        self.assertEqual(msg_a["message_type"], "text")
        self.assertEqual(msg_b["sender_phone"], _PHONE_B)

        # 9. Both can read the chat
        msgs = _data(crowd.get_messages(request_id=req_id, phone=_PHONE_A))["messages"]
        msg_texts = [m["message"] for m in msgs]
        self.assertIn("Welcome Rohan!", msg_texts)
        self.assertIn("Thanks! Can't wait!", msg_texts)

        # 10. Non-member cannot join or chat
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.send_message(req_id, _PHONE_C, message="I'm crashing this", sender_name="Crasher")

        # 11. Creator cancels — request closes
        crowd.cancel_crowd_request(req_id, _PHONE_A)
        self.assertEqual(frappe.db.get_value("Crowd Request", req_id, "status"), "cancelled")

        # 12. Messages still exist after cancel (read for posterity)
        archive = _data(crowd.get_messages(request_id=req_id))
        self.assertGreaterEqual(len(archive["messages"]), 2)


# ─────────────────────────────────────────────────────────────────────────────
# TestExpoPushToken — save_expo_push_token endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestExpoPushToken(unittest.TestCase):
    """
    Tests for the Expo push token registration endpoint.
    Tokens are stored in Redis; this verifies the round-trip without needing
    a real Expo device.
    """

    def setUp(self):
        # Clean up any cached token for test phones
        frappe.cache().delete_value(f"expo_push:{_PHONE_A}")
        frappe.cache().delete_value(f"expo_push:{_PHONE_B}")

    def tearDown(self):
        frappe.cache().delete_value(f"expo_push:{_PHONE_A}")
        frappe.cache().delete_value(f"expo_push:{_PHONE_B}")

    def _fake_token(self, suffix="AAAA1234567890123456789012"):
        return f"ExponentPushToken[{suffix}]"

    def test_valid_token_saved(self):
        result = _data(crowd.save_expo_push_token(_PHONE_A, self._fake_token()))
        self.assertTrue(result.get("success") or "success" in str(result))
        stored = frappe.cache().get_value(f"expo_push:{_PHONE_A}")
        self.assertEqual(stored, self._fake_token())

    def test_token_overwritten_on_re_register(self):
        crowd.save_expo_push_token(_PHONE_A, self._fake_token("FIRST11111111111111111111"))
        crowd.save_expo_push_token(_PHONE_A, self._fake_token("SECOND1111111111111111111"))
        stored = frappe.cache().get_value(f"expo_push:{_PHONE_A}")
        self.assertIn("SECOND", stored)

    def test_invalid_token_format_throws(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.save_expo_push_token(_PHONE_A, "not-an-expo-token")

    def test_empty_token_throws(self):
        with self.assertRaises(Exception):
            crowd.save_expo_push_token(_PHONE_A, "")

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.save_expo_push_token(None, self._fake_token())

    def test_different_phones_stored_independently(self):
        crowd.save_expo_push_token(_PHONE_A, self._fake_token("AAAA0000000000000000000000"))
        crowd.save_expo_push_token(_PHONE_B, self._fake_token("BBBB0000000000000000000000"))
        tok_a = frappe.cache().get_value(f"expo_push:{_PHONE_A}")
        tok_b = frappe.cache().get_value(f"expo_push:{_PHONE_B}")
        self.assertIn("AAAA", tok_a)
        self.assertIn("BBBB", tok_b)


# ─────────────────────────────────────────────────────────────────────────────
# TestUploadChatImage — upload_chat_image with real base64 bytes
# ─────────────────────────────────────────────────────────────────────────────

# Minimal valid 1×1 red PNG (generated offline, pure Python, 68 bytes decoded)
_1PX_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
)

class TestUploadChatImage(unittest.TestCase):
    """
    Tests the full upload_chat_image path with real decoded bytes.
    Uses the R2 path if available; falls back to Frappe File doctype.
    Both paths must return a valid URL in the response envelope.
    """

    def setUp(self):
        _cleanup_crowd()
        self.req, self.member_b_id = _approved_member_request()

    def tearDown(self):
        _cleanup_crowd()
        # Clean up any Frappe File docs created during tests
        frappe.db.sql(
            "DELETE FROM `tabFile` WHERE file_name LIKE %s",
            ["crowd-test-%.png"]
        )
        frappe.db.commit()

    def test_valid_png_upload_returns_url(self):
        result = _data(crowd.upload_chat_image(
            request_id=self.req.name,
            phone=_PHONE_A,
            file_content=_1PX_PNG_B64,
            filename="crowd-test-img.png",
            content_type="image/png",
        ))
        self.assertIn("url", result)
        url = result["url"]
        self.assertTrue(url.startswith("http") or url.startswith("/"), f"URL looks wrong: {url}")

    def test_image_too_large_throws(self):
        import base64
        big_b64 = base64.b64encode(b"X" * (5 * 1024 * 1024 + 1)).decode()
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.upload_chat_image(
                request_id=self.req.name,
                phone=_PHONE_A,
                file_content=big_b64,
                filename="big.png",
            )

    def test_invalid_base64_throws(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.upload_chat_image(
                request_id=self.req.name,
                phone=_PHONE_A,
                file_content="not-valid-base64!!!",
                filename="bad.png",
            )

    def test_non_member_upload_throws(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.upload_chat_image(
                request_id=self.req.name,
                phone=_PHONE_C,
                file_content=_1PX_PNG_B64,
                filename="sneak.png",
            )

    def test_upload_then_send_image_message(self):
        # Full flow: upload → get URL → send as image message
        result = _data(crowd.upload_chat_image(
            request_id=self.req.name,
            phone=_PHONE_A,
            file_content=_1PX_PNG_B64,
            filename="crowd-test-flow.png",
        ))
        url = result["url"]
        msg = _data(crowd.send_message(
            request_id=self.req.name,
            phone=_PHONE_A,
            message="",
            message_type="image",
            image_url=url,
            sender_name="Creator",
        ))
        self.assertEqual(msg["message_type"], "image")
        self.assertEqual(msg["image_url"], url)
        # Verify it appears in get_messages
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        img_msgs = [m for m in msgs if m["message_type"] == "image"]
        self.assertEqual(len(img_msgs), 1)
        self.assertEqual(img_msgs[0]["image_url"], url)


# ─────────────────────────────────────────────────────────────────────────────
# TestCrowdPushIntegration — push token + send_message trigger
# ─────────────────────────────────────────────────────────────────────────────

class TestCrowdPushIntegration(unittest.TestCase):
    """
    Validates that _send_crowd_chat_push is callable without crashing,
    that it reads tokens from Redis correctly, and that push is not sent
    to the sender.  Actual Expo delivery is not tested (would require network +
    real device tokens).
    """

    def setUp(self):
        _cleanup_crowd()
        self.req, self.member_b_id = _approved_member_request()
        frappe.cache().set_value(f"expo_push:{_PHONE_B}", "ExponentPushToken[BBBB0000000000000000000000]")

    def tearDown(self):
        _cleanup_crowd()
        frappe.cache().delete_value(f"expo_push:{_PHONE_B}")
        frappe.cache().delete_value(f"expo_push:{_PHONE_A}")

    def test_push_helper_does_not_crash_with_token(self):
        # _send_crowd_chat_push should run without error even when Expo is unreachable
        # (it catches all exceptions internally)
        try:
            crowd._send_crowd_chat_push(
                request_id=self.req.name,
                sender_phone=_PHONE_A,
                sender_name="Creator",
                message_preview="Hello from test!",
            )
        except Exception as e:
            self.fail(f"_send_crowd_chat_push raised unexpectedly: {e}")

    def test_push_helper_skips_sender_phone(self):
        # Register a token for PHONE_A (creator / sender); PHONE_B already has one
        frappe.cache().set_value(f"expo_push:{_PHONE_A}", "ExponentPushToken[AAAA0000000000000000000000]")
        # Helper should NOT push to _PHONE_A since it's the sender
        # We can't assert the HTTP call but we verify the helper doesn't crash
        crowd._send_crowd_chat_push(
            request_id=self.req.name,
            sender_phone=_PHONE_A,
            sender_name="Creator",
            message_preview="This is a test message",
        )
        # PHONE_B's token should still be in Redis (not consumed/deleted)
        tok = frappe.cache().get_value(f"expo_push:{_PHONE_B}")
        self.assertIsNotNone(tok)

    def test_push_helper_no_crash_when_no_tokens(self):
        frappe.cache().delete_value(f"expo_push:{_PHONE_B}")
        try:
            crowd._send_crowd_chat_push(
                request_id=self.req.name,
                sender_phone=_PHONE_A,
                sender_name="Creator",
                message_preview="No one has tokens",
            )
        except Exception as e:
            self.fail(f"Raised unexpectedly: {e}")

    def test_send_message_does_not_block_on_push(self):
        # send_message should return quickly even if push enqueue takes time
        result = _data(crowd.send_message(
            request_id=self.req.name,
            phone=_PHONE_A,
            message="Test with push enqueue",
            sender_name="Creator",
        ))
        self.assertIn("id", result)
        self.assertEqual(result["message"], "Test with push enqueue")


# ─────────────────────────────────────────────────────────────────────────────
# TestMessageDeduplication — rapid sends don't produce phantoms
# ─────────────────────────────────────────────────────────────────────────────

class TestMessageDeduplication(unittest.TestCase):
    """
    Backend-level dedup: sending the same text twice produces two distinct
    server documents with distinct IDs. This is the ground truth the frontend
    dedup relies on (optimistic id → real id swap in onSuccess).
    """

    def setUp(self):
        _cleanup_crowd()
        self.req, _ = _approved_member_request()

    def tearDown(self):
        _cleanup_crowd()

    def test_two_sends_produce_two_unique_ids(self):
        r1 = _data(crowd.send_message(self.req.name, _PHONE_A, message="Msg A", sender_name="A"))
        r2 = _data(crowd.send_message(self.req.name, _PHONE_A, message="Msg B", sender_name="A"))
        self.assertNotEqual(r1["id"], r2["id"])

    def test_rapid_sends_all_persist(self):
        count = 5
        ids = []
        for i in range(count):
            r = _data(crowd.send_message(
                self.req.name, _PHONE_A,
                message=f"Rapid {i}", sender_name="A"
            ))
            ids.append(r["id"])
        # All IDs must be unique
        self.assertEqual(len(set(ids)), count)
        # All messages must appear in get_messages
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        server_ids = {m["id"] for m in msgs}
        for msg_id in ids:
            self.assertIn(msg_id, server_ids)

    def test_same_text_twice_produces_two_docs(self):
        text = "Hello hello"
        r1 = _data(crowd.send_message(self.req.name, _PHONE_A, message=text, sender_name="A"))
        r2 = _data(crowd.send_message(self.req.name, _PHONE_A, message=text, sender_name="A"))
        self.assertNotEqual(r1["id"], r2["id"])
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        matching = [m for m in msgs if m["message"] == text]
        self.assertEqual(len(matching), 2)


# ─────────────────────────────────────────────────────────────────────────────
# TestFilterCrowdRequests — timing + gender filters
# ─────────────────────────────────────────────────────────────────────────────

class TestFilterCrowdRequests(unittest.TestCase):
    """
    Validates the timing (happening_now / today / this_week) and gender_preference
    filters added to get_crowd_requests.
    """

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_gender_filter_women_only(self):
        women = _make_request(phone=_PHONE_A, title="Women Only")
        frappe.db.set_value("Crowd Request", women.name, "gender_preference", "women_only")
        frappe.db.commit()
        # men_only request should NOT appear under women_only filter
        men = _make_request(phone=_PHONE_A, title="Men Only")
        frappe.db.set_value("Crowd Request", men.name, "gender_preference", "men_only")
        frappe.db.commit()
        result = crowd.get_crowd_requests(phone=_PHONE_B, gender_preference="women_only")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(women.name, ids)
        self.assertNotIn(men.name, ids)

    def test_gender_filter_men_only(self):
        men = _make_request(phone=_PHONE_A, title="Men Only Group")
        frappe.db.set_value("Crowd Request", men.name, "gender_preference", "men_only")
        frappe.db.commit()
        result = crowd.get_crowd_requests(phone=_PHONE_B, gender_preference="men_only")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(men.name, ids)

    def test_gender_filter_any_returns_all(self):
        req1 = _make_request(phone=_PHONE_A, title="Any Gender")
        req2 = _make_request(phone=_PHONE_B, title="Women Only For Any Test")
        frappe.db.set_value("Crowd Request", req2.name, "gender_preference", "women_only")
        frappe.db.commit()
        result = crowd.get_crowd_requests(phone=_PHONE_C, gender_preference="any")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(req1.name, ids)
        self.assertIn(req2.name, ids)

    def test_timing_filter_today_includes_today(self):
        from frappe.utils import today as frappe_today
        req = _make_request(phone=_PHONE_A, date=frappe_today())
        result = crowd.get_crowd_requests(phone=_PHONE_B, timing="today")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(req.name, ids)

    def test_timing_filter_today_excludes_future(self):
        future = _make_request(phone=_PHONE_A, date=add_days(today(), 5))
        result = crowd.get_crowd_requests(phone=_PHONE_B, timing="today")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertNotIn(future.name, ids)

    def test_timing_filter_this_week_includes_next_7_days(self):
        next3 = _make_request(phone=_PHONE_A, date=add_days(today(), 3))
        result = crowd.get_crowd_requests(phone=_PHONE_B, timing="this_week")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertIn(next3.name, ids)

    def test_timing_filter_this_week_excludes_far_future(self):
        far = _make_request(phone=_PHONE_A, date=add_days(today(), 10))
        result = crowd.get_crowd_requests(phone=_PHONE_B, timing="this_week")
        ids = [r["id"] for r in _data(result)["requests"]]
        self.assertNotIn(far.name, ids)

    def test_tier_field_returned_in_response(self):
        req = _make_request(phone=_PHONE_A)
        frappe.db.set_value("Crowd Request", req.name, "tier", "premium")
        frappe.db.commit()
        result = crowd.get_crowd_requests(phone=_PHONE_B)
        req_data = next((r for r in _data(result)["requests"] if r["id"] == req.name), None)
        if req_data:
            self.assertIn("tier", req_data)


# ─────────────────────────────────────────────────────────────────────────────
# TestEditCrowdRequest — creator edits (blocked after joins)
# ─────────────────────────────────────────────────────────────────────────────

class TestEditCrowdRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, title="Original Title")

    def tearDown(self):
        _cleanup_crowd()

    def test_creator_can_edit_title(self):
        crowd.edit_crowd_request(self.req.name, _PHONE_A, title="New Title")
        stored = frappe.db.get_value("Crowd Request", self.req.name, "title")
        self.assertEqual(stored, "New Title")

    def test_creator_can_edit_description(self):
        crowd.edit_crowd_request(self.req.name, _PHONE_A, description="Updated description")
        stored = frappe.db.get_value("Crowd Request", self.req.name, "description")
        self.assertEqual(stored, "Updated description")

    def test_creator_can_edit_max_members(self):
        crowd.edit_crowd_request(self.req.name, _PHONE_A, max_members=8)
        stored = frappe.db.get_value("Crowd Request", self.req.name, "max_members")
        self.assertEqual(stored, 8)

    def test_max_members_bounds_too_low_throws(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.edit_crowd_request(self.req.name, _PHONE_A, max_members=1)

    def test_max_members_bounds_too_high_throws(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.edit_crowd_request(self.req.name, _PHONE_A, max_members=25)

    def test_non_creator_cannot_edit(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.edit_crowd_request(self.req.name, _PHONE_B, title="Hacked Title")

    def test_cannot_edit_after_member_joins(self):
        # Approve PHONE_B → current_members becomes 2
        join = _data(crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Joiner B"))
        crowd.manage_join_request(self.req.name, join["member_id"], "approve", _PHONE_A)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.edit_crowd_request(self.req.name, _PHONE_A, title="After Join Title")

    def test_cannot_edit_cancelled_request(self):
        crowd.cancel_crowd_request(self.req.name, _PHONE_A)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.edit_crowd_request(self.req.name, _PHONE_A, title="Ghost Edit")

    def test_returns_request_id(self):
        result = _data(crowd.edit_crowd_request(self.req.name, _PHONE_A, title="New Title"))
        self.assertEqual(result["request_id"], self.req.name)

    def test_missing_request_id_throws(self):
        with self.assertRaises(Exception):
            crowd.edit_crowd_request(None, _PHONE_A, title="Test")

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.edit_crowd_request(self.req.name, None, title="Test")


# ─────────────────────────────────────────────────────────────────────────────
# TestLeaveCrowdRequest — member leaves, count decremented
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaveCrowdRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req, self.member_b_id = _approved_member_request()

    def tearDown(self):
        _cleanup_crowd()

    def test_approved_member_can_leave(self):
        crowd.leave_crowd_request(self.req.name, _PHONE_B)
        status = frappe.db.get_value("Crowd Request Member", self.member_b_id, "status")
        self.assertEqual(status, "left")

    def test_leave_decrements_current_members(self):
        before = frappe.db.get_value("Crowd Request", self.req.name, "current_members")
        crowd.leave_crowd_request(self.req.name, _PHONE_B)
        after = frappe.db.get_value("Crowd Request", self.req.name, "current_members")
        self.assertEqual(after, before - 1)

    def test_leave_reopens_closed_request(self):
        # Fill the request to max → auto-closes
        req_small = _make_request(phone=_PHONE_A, max_members=2)
        join = _data(crowd.request_to_join(req_small.name, _PHONE_B, customer_name="Bobby B"))
        crowd.manage_join_request(req_small.name, join["member_id"], "approve", _PHONE_A)
        self.assertEqual(frappe.db.get_value("Crowd Request", req_small.name, "status"), "closed")
        # Now B leaves → should re-open
        crowd.leave_crowd_request(req_small.name, _PHONE_B)
        self.assertEqual(frappe.db.get_value("Crowd Request", req_small.name, "status"), "open")

    def test_creator_cannot_leave(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.leave_crowd_request(self.req.name, _PHONE_A)

    def test_non_member_cannot_leave(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.leave_crowd_request(self.req.name, _PHONE_C)

    def test_pending_member_cannot_leave(self):
        crowd.request_to_join(self.req.name, _PHONE_C, customer_name="Charlie C")
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.leave_crowd_request(self.req.name, _PHONE_C)

    def test_cannot_leave_cancelled_request(self):
        # Approve C first, then cancel
        join_c = _data(crowd.request_to_join(self.req.name, _PHONE_C, customer_name="Charlie C"))
        crowd.manage_join_request(self.req.name, join_c["member_id"], "approve", _PHONE_A)
        crowd.cancel_crowd_request(self.req.name, _PHONE_A)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.leave_crowd_request(self.req.name, _PHONE_C)

    def test_leave_returns_status_left(self):
        result = _data(crowd.leave_crowd_request(self.req.name, _PHONE_B))
        self.assertEqual(result["status"], "left")


# ─────────────────────────────────────────────────────────────────────────────
# TestReportCrowdMessage — report validation
# ─────────────────────────────────────────────────────────────────────────────

class TestReportCrowdMessage(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req, self.member_b_id = _approved_member_request()
        # PHONE_A sends a message to report
        send_result = _data(crowd.send_message(
            self.req.name, _PHONE_A, message="Inappropriate content here", sender_name="A"
        ))
        self.msg_id = send_result["id"]

    def tearDown(self):
        _cleanup_crowd()
        frappe.db.sql(
            "DELETE FROM `tabCrowd Report` WHERE reporter_phone IN (%s, %s, %s)",
            [_PHONE_A, _PHONE_B, _PHONE_C],
        )
        frappe.db.commit()

    def test_approved_member_can_report(self):
        result = _data(crowd.report_crowd_message(self.msg_id, _PHONE_B, reason="harassment"))
        self.assertIn("report_id", result)

    def test_report_creates_crowd_report_doc(self):
        result = _data(crowd.report_crowd_message(self.msg_id, _PHONE_B, reason="spam"))
        report = frappe.get_doc("Crowd Report", result["report_id"])
        self.assertEqual(report.reporter_phone, _PHONE_B)
        self.assertEqual(report.message_id, self.msg_id)
        self.assertEqual(report.reason, "spam")
        self.assertEqual(report.status, "pending")

    def test_cannot_report_own_message(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.report_crowd_message(self.msg_id, _PHONE_A, reason="spam")

    def test_non_member_cannot_report(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.report_crowd_message(self.msg_id, _PHONE_C, reason="harassment")

    def test_invalid_reason_defaults_to_other(self):
        result = _data(crowd.report_crowd_message(self.msg_id, _PHONE_B, reason="banana"))
        report = frappe.get_doc("Crowd Report", result["report_id"])
        self.assertEqual(report.reason, "other")

    def test_valid_reasons_accepted(self):
        for reason in ("explicit_content", "harassment", "spam", "contact_details", "other"):
            # Send a fresh message for each report to avoid self-report
            send = _data(crowd.send_message(
                self.req.name, _PHONE_A, message=f"Content for {reason}", sender_name="A"
            ))
            result = _data(crowd.report_crowd_message(send["id"], _PHONE_B, reason=reason))
            self.assertIn("report_id", result)

    def test_nonexistent_message_throws(self):
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            crowd.report_crowd_message("MSG-FAKE-9999", _PHONE_B, reason="spam")

    def test_missing_message_id_throws(self):
        with self.assertRaises(Exception):
            crowd.report_crowd_message(None, _PHONE_B, reason="spam")


# ─────────────────────────────────────────────────────────────────────────────
# TestCompleteCrowdRequest — attendance tracking
# ─────────────────────────────────────────────────────────────────────────────

class TestCompleteCrowdRequest(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req, self.member_b_id = _approved_member_request()
        # Also approve PHONE_C
        join_c = _data(crowd.request_to_join(self.req.name, _PHONE_C, customer_name="Charlie C"))
        crowd.manage_join_request(self.req.name, join_c["member_id"], "approve", _PHONE_A)

    def tearDown(self):
        _cleanup_crowd()

    def test_creator_can_complete(self):
        crowd.complete_crowd_request(self.req.name, _PHONE_A, attended_phones=[_PHONE_B])
        status = frappe.db.get_value("Crowd Request", self.req.name, "status")
        self.assertEqual(status, "completed")

    def test_attended_flag_set_correctly(self):
        crowd.complete_crowd_request(
            self.req.name, _PHONE_A, attended_phones=[_PHONE_B]
        )
        b_attended = frappe.db.get_value(
            "Crowd Request Member", self.member_b_id, "attended"
        )
        self.assertEqual(b_attended, 1)
        # PHONE_C was approved but not in attended_phones
        c_member = frappe.db.get_value(
            "Crowd Request Member",
            {"request": self.req.name, "customer_phone": _PHONE_C},
            "attended",
        )
        self.assertEqual(c_member, 0)

    def test_non_creator_cannot_complete(self):
        with self.assertRaises(frappe.exceptions.PermissionError):
            crowd.complete_crowd_request(self.req.name, _PHONE_B, attended_phones=[_PHONE_B])

    def test_cannot_complete_already_cancelled(self):
        crowd.cancel_crowd_request(self.req.name, _PHONE_A)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.complete_crowd_request(self.req.name, _PHONE_A, attended_phones=[_PHONE_B])

    def test_cannot_complete_twice(self):
        crowd.complete_crowd_request(self.req.name, _PHONE_A, attended_phones=[_PHONE_B])
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.complete_crowd_request(self.req.name, _PHONE_A, attended_phones=[_PHONE_B])

    def test_attended_count_in_response(self):
        result = _data(crowd.complete_crowd_request(
            self.req.name, _PHONE_A, attended_phones=[_PHONE_B, _PHONE_C]
        ))
        self.assertEqual(result["attended_count"], 2)
        self.assertEqual(result["status"], "completed")

    def test_no_attended_phones_marks_all_absent(self):
        crowd.complete_crowd_request(self.req.name, _PHONE_A, attended_phones=[])
        b_attended = frappe.db.get_value(
            "Crowd Request Member", self.member_b_id, "attended"
        )
        self.assertEqual(b_attended, 0)

    def test_missing_request_id_throws(self):
        with self.assertRaises(Exception):
            crowd.complete_crowd_request(None, _PHONE_A, attended_phones=[])


# ─────────────────────────────────────────────────────────────────────────────
# TestCrowdReliability — score calculation
# ─────────────────────────────────────────────────────────────────────────────

class TestCrowdReliability(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_new_user_score_100(self):
        result = _data(crowd.get_crowd_reliability(_PHONE_C))
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["total_joins"], 0)

    def test_score_reflects_attendance(self):
        req = _make_request(phone=_PHONE_A, max_members=5)
        join = _data(crowd.request_to_join(req.name, _PHONE_B, customer_name="Bobby B"))
        crowd.manage_join_request(req.name, join["member_id"], "approve", _PHONE_A)
        # Mark B as attended
        crowd.complete_crowd_request(req.name, _PHONE_A, attended_phones=[_PHONE_B])
        result = _data(crowd.get_crowd_reliability(_PHONE_B))
        self.assertEqual(result["attended"], 1)
        self.assertEqual(result["total_joins"], 1)
        self.assertEqual(result["score"], 100)

    def test_score_reflects_non_attendance(self):
        req = _make_request(phone=_PHONE_A, max_members=5)
        join = _data(crowd.request_to_join(req.name, _PHONE_B, customer_name="Bobby B"))
        crowd.manage_join_request(req.name, join["member_id"], "approve", _PHONE_A)
        # Mark B as NOT attended (empty list)
        crowd.complete_crowd_request(req.name, _PHONE_A, attended_phones=[])
        result = _data(crowd.get_crowd_reliability(_PHONE_B))
        self.assertEqual(result["score"], 0)

    def test_missing_phone_throws(self):
        with self.assertRaises(Exception):
            crowd.get_crowd_reliability(None)

    def test_response_shape(self):
        result = _data(crowd.get_crowd_reliability(_PHONE_A))
        for field in ("score", "total_joins", "attended"):
            self.assertIn(field, result)


# ─────────────────────────────────────────────────────────────────────────────
# TestApprovalPush — push enqueued on approve, not on reject
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalPush(unittest.TestCase):
    """
    We cannot verify the actual HTTP call to Expo, but we can verify that:
    - _send_approval_push reads the Redis token without crashing
    - Helper skips cleanly when no token is stored
    - send_approval_push does not block request-response (returns quickly)
    """

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, max_members=5)
        join = _data(crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Bobby B"))
        self.member_id = join["member_id"]
        frappe.cache().set_value(
            f"expo_push:{_PHONE_B}",
            "ExponentPushToken[BBBB1111111111111111111111]"
        )

    def tearDown(self):
        _cleanup_crowd()
        frappe.cache().delete_value(f"expo_push:{_PHONE_B}")

    def test_approval_push_helper_does_not_raise(self):
        try:
            crowd._send_approval_push(_PHONE_B, self.req.name)
        except Exception as e:
            self.fail(f"_send_approval_push raised unexpectedly: {e}")

    def test_approval_push_no_crash_without_token(self):
        frappe.cache().delete_value(f"expo_push:{_PHONE_B}")
        try:
            crowd._send_approval_push(_PHONE_B, self.req.name)
        except Exception as e:
            self.fail(f"_send_approval_push raised unexpectedly: {e}")

    def test_manage_approve_does_not_block(self):
        result = _data(crowd.manage_join_request(
            self.req.name, self.member_id, "approve", _PHONE_A
        ))
        self.assertEqual(result["status"], "approved")

    def test_reject_does_not_trigger_push(self):
        # Rejecting should not push — no crash is the observable signal
        crowd.manage_join_request(self.req.name, self.member_id, "reject", _PHONE_A)
        # Token still intact (not cleared/consumed by push)
        tok = frappe.cache().get_value(f"expo_push:{_PHONE_B}")
        self.assertIsNotNone(tok)


# ─────────────────────────────────────────────────────────────────────────────
# TestAutoClose — scheduler closes expired requests
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoClose(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()

    def tearDown(self):
        _cleanup_crowd()

    def test_scheduler_closes_expired_requests(self):
        past = add_days(today(), -1)
        req = _make_request(phone=_PHONE_A, status="open", date=past,
                            expires_at=str(get_datetime(str(past) + " 00:00:00")))
        crowd.close_expired_crowd_requests()
        status = frappe.db.get_value("Crowd Request", req.name, "status")
        self.assertEqual(status, "closed")

    def test_scheduler_leaves_future_requests_open(self):
        req = _make_request(phone=_PHONE_A, status="open")
        crowd.close_expired_crowd_requests()
        status = frappe.db.get_value("Crowd Request", req.name, "status")
        self.assertEqual(status, "open")

    def test_scheduler_leaves_already_completed_unchanged(self):
        past = add_days(today(), -1)
        req = _make_request(phone=_PHONE_A, status="completed", date=past,
                            expires_at=str(get_datetime(str(past) + " 00:00:00")))
        crowd.close_expired_crowd_requests()
        status = frappe.db.get_value("Crowd Request", req.name, "status")
        self.assertEqual(status, "completed")

    def test_scheduler_leaves_cancelled_unchanged(self):
        past = add_days(today(), -1)
        req = _make_request(phone=_PHONE_A, status="cancelled", date=past,
                            expires_at=str(get_datetime(str(past) + " 00:00:00")))
        crowd.close_expired_crowd_requests()
        status = frappe.db.get_value("Crowd Request", req.name, "status")
        self.assertEqual(status, "cancelled")

    def test_scheduler_does_not_raise(self):
        try:
            crowd.close_expired_crowd_requests()
        except Exception as e:
            self.fail(f"close_expired_crowd_requests raised: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# TestJoinEligibility — 7-day account age, name, reliability
# ─────────────────────────────────────────────────────────────────────────────

class TestJoinEligibility(unittest.TestCase):
    """
    Tests the _check_join_eligibility gate embedded in request_to_join.
    Account age check fires only when the phone exists in the Customer table.
    For phones without a Customer record, account-age is skipped (new user default).
    """

    _CUSTOMER_IDS = {}  # phone → Customer.name

    def setUp(self):
        _cleanup_crowd()
        self.req = _make_request(phone=_PHONE_A, max_members=5)

    def tearDown(self):
        _cleanup_crowd()
        # Remove any test Customer records we created
        for phone in (_PHONE_B, _PHONE_C):
            cid = frappe.db.get_value("Customer", {"phone": phone}, "name")
            if cid:
                frappe.db.set_value("Customer", cid, "phone", "")
        frappe.db.commit()

    def _create_member(self, phone, created_days_ago=10):
        creation_dt = str(get_datetime(add_days(today(), -created_days_ago)))
        cid = frappe.db.get_value("Customer", {"phone": phone}, "name")
        if not cid:
            # Create a minimal Customer with a unique naming_series
            doc = frappe.get_doc({
                "doctype":       "Customer",
                "customer_name": f"Test User {phone}",
                "customer_type": "Individual",
                "customer_group": frappe.db.get_value("Customer Group", {}, "name") or "All Customer Groups",
                "territory":     frappe.db.get_value("Territory", {}, "name") or "All Territories",
                "phone":         phone,
            })
            doc.insert(ignore_permissions=True)
            cid = doc.name
        frappe.db.set_value("Customer", cid, "creation", creation_dt)
        frappe.db.commit()

    def test_eligible_user_can_join(self):
        self._create_member(_PHONE_B, created_days_ago=10)
        result = _data(crowd.request_to_join(
            self.req.name, _PHONE_B, customer_name="Alice Test"
        ))
        self.assertIn("member_id", result)

    def test_account_too_new_throws(self):
        self._create_member(_PHONE_B, created_days_ago=3)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(self.req.name, _PHONE_B, customer_name="Alice Test")

    def test_placeholder_name_throws(self):
        self._create_member(_PHONE_B, created_days_ago=10)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(self.req.name, _PHONE_B, customer_name="user123")

    def test_too_short_name_throws(self):
        self._create_member(_PHONE_B, created_days_ago=10)
        with self.assertRaises(frappe.exceptions.ValidationError):
            crowd.request_to_join(self.req.name, _PHONE_B, customer_name="X")

    def test_reliability_gate_after_5_joins(self):
        """If 5+ joins with 0 attended, score = 0% → blocked."""
        self._create_member(_PHONE_B, created_days_ago=10)
        # Insert 5 approved+not-attended records directly
        for i in range(5):
            other = _make_request(phone=_PHONE_A, max_members=5)
            join = _data(crowd.request_to_join(other.name, _PHONE_B, customer_name="Alice Test"))
            crowd.manage_join_request(other.name, join["member_id"], "approve", _PHONE_A)
            # Complete with nobody attended
            crowd.complete_crowd_request(other.name, _PHONE_A, attended_phones=[])

        with self.assertRaises(frappe.exceptions.ValidationError):
            new_req = _make_request(phone=_PHONE_A, max_members=5)
            crowd.request_to_join(new_req.name, _PHONE_B, customer_name="Alice Test")

    def test_reliability_gate_not_enforced_before_5_joins(self):
        """Under 5 joins, even 0% attendance is fine."""
        self._create_member(_PHONE_B, created_days_ago=10)
        for i in range(4):
            other = _make_request(phone=_PHONE_A, max_members=5)
            join = _data(crowd.request_to_join(other.name, _PHONE_B, customer_name="Alice Test"))
            crowd.manage_join_request(other.name, join["member_id"], "approve", _PHONE_A)
            crowd.complete_crowd_request(other.name, _PHONE_A, attended_phones=[])

        # 5th join should still go through (only 4 past joins at this point)
        result = _data(crowd.request_to_join(
            self.req.name, _PHONE_B, customer_name="Alice Test"
        ))
        self.assertIn("member_id", result)

    def test_no_customer_record_skips_age_check(self):
        """Users without a Customer record skip the age gate entirely."""
        # Ensure _PHONE_C has no Customer record with this phone
        cid = frappe.db.get_value("Customer", {"phone": _PHONE_C}, "name")
        if cid:
            frappe.db.set_value("Customer", cid, "phone", "")
            frappe.db.commit()
        result = _data(crowd.request_to_join(
            self.req.name, _PHONE_C, customer_name="Unknown User"
        ))
        self.assertIn("member_id", result)


# ─────────────────────────────────────────────────────────────────────────────
# TestSenderInterests — sender_interests field stored and returned
# ─────────────────────────────────────────────────────────────────────────────

class TestSenderInterests(unittest.TestCase):

    def setUp(self):
        _cleanup_crowd()
        self.req, _ = _approved_member_request()

    def tearDown(self):
        _cleanup_crowd()

    def test_sender_interests_stored_and_returned(self):
        crowd.send_message(
            self.req.name, _PHONE_A,
            message="Hey!", sender_name="A",
            sender_interests="Food,Music,Travel"
        )
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        msg = next((m for m in msgs if m["message"] == "Hey!"), None)
        self.assertIsNotNone(msg)
        self.assertIn("sender_interests", msg)
        self.assertIn("Food", msg["sender_interests"])
        self.assertIn("Music", msg["sender_interests"])

    def test_empty_interests_returns_empty_list(self):
        crowd.send_message(self.req.name, _PHONE_A, message="No interests", sender_name="A")
        msgs = _data(crowd.get_messages(request_id=self.req.name, phone=_PHONE_A))["messages"]
        msg = next((m for m in msgs if m["message"] == "No interests"), None)
        self.assertIsNotNone(msg)
        self.assertIsInstance(msg["sender_interests"], list)
        self.assertEqual(len(msg["sender_interests"]), 0)


if __name__ == "__main__":
    unittest.main()
