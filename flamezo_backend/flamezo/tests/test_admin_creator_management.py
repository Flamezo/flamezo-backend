# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
E2E tests for the admin Creator Management endpoints — admin.py's
admin_get_all_creators / admin_get_creator_full_profile /
admin_update_creator_status. This is the first admin surface with any
manual override for creator status (approve/reject/suspend/reinstate);
creator_onboarding.py's Instagram-connect flow only ever sets it
automatically.
"""

import unittest

import frappe
from frappe.utils import add_days, now_datetime

from flamezo_backend.flamezo.api import admin
from flamezo_backend.flamezo.tests.utils import make_restaurant

_PREFIX = "TEST-ADMINCREATOR"
_PHONE = "9300000801"
_PHONE2 = "9300000802"


def _cleanup():
    frappe.db.sql(
        "DELETE FROM `tabEscrow Transaction` WHERE deal IN (SELECT name FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s, %s)))",
        (_PHONE, _PHONE2),
    )
    frappe.db.sql(
        "DELETE FROM `tabCollab Deal` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s, %s))",
        (_PHONE, _PHONE2),
    )
    frappe.db.sql(
        "DELETE FROM `tabCreator Rate Card` WHERE creator IN (SELECT name FROM `tabFlamezo Creator` WHERE customer_phone IN (%s, %s))",
        (_PHONE, _PHONE2),
    )
    frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone IN (%s, %s)", (_PHONE, _PHONE2))
    frappe.db.commit()


class TestAdminCreatorManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outlet = f"{_PREFIX}-OUTLET"
        if not frappe.db.exists("Outlet", cls.outlet):
            make_restaurant(cls.outlet, outlet_type="dining")

    def setUp(self):
        _cleanup()
        self.creator = frappe.get_doc({
            "doctype": "Flamezo Creator",
            "customer_phone": _PHONE,
            "display_name": "AdminMgmtTestCreator",
            "instagram_handle": "admin_mgmt_test",
            "meta_followers": 12000,
            "city": "Surat",
            "status": "approved",
            "razorpay_kyc_status": "under_review",
            "legal_name": "Test Legal Name",
            "bank_account_number": "1234567890123",
        })
        self.creator.insert(ignore_permissions=True)

    def tearDown(self):
        _cleanup()

    # ── list ──────────────────────────────────────────────────────────

    def test_list_creators_includes_stats_and_kyc(self):
        invite = frappe.get_doc({"doctype": "Creator Collab Invite", "outlet": self.outlet, "creator": self.creator.name})
        invite.insert(ignore_permissions=True)
        deal = frappe.get_doc({
            "doctype": "Collab Deal", "creator": self.creator.name, "outlet": self.outlet,
            "deal_type": "cash", "status": "offered", "deadline": add_days(now_datetime(), 5).date(),
            "price_inr": 500, "commission_pct": 10, "terms_json": "{}", "direct_invite": invite.name,
        })
        deal.insert(ignore_permissions=True)
        deal.status = "accepted"; deal.save(ignore_permissions=True)
        deal.status = "funded"; deal.save(ignore_permissions=True)
        deal.status = "delivered"; deal.save(ignore_permissions=True)
        escrow = frappe.get_doc({
            "doctype": "Escrow Transaction", "deal": deal.name, "state": "released",
            "amount_inr": 500, "platform_fee_inr": 50, "creator_net_inr": 450,
        })
        escrow.insert(ignore_permissions=True)
        deal.status = "released"; deal.save(ignore_permissions=True)

        res = admin.admin_get_all_creators(search="AdminMgmtTestCreator")
        self.assertTrue(res["success"])
        rows = res["data"]["creators"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], self.creator.name)
        self.assertEqual(row["kyc_status"], "under_review")
        self.assertEqual(row["collabs_done"], 1)
        self.assertEqual(row["total_earned_inr"], 450)
        self.assertEqual(row["open_disputes"], 0)

    def test_list_creators_status_filter(self):
        frappe.db.set_value("Flamezo Creator", self.creator.name, "status", "suspended")
        res = admin.admin_get_all_creators(search="AdminMgmtTestCreator", status="suspended")
        self.assertEqual(len(res["data"]["creators"]), 1)
        res2 = admin.admin_get_all_creators(search="AdminMgmtTestCreator", status="approved")
        self.assertEqual(len(res2["data"]["creators"]), 0)

    def test_list_creators_search_by_phone_and_instagram(self):
        res = admin.admin_get_all_creators(search=_PHONE)
        self.assertEqual(len(res["data"]["creators"]), 1)
        res2 = admin.admin_get_all_creators(search="admin_mgmt_test")
        self.assertEqual(len(res2["data"]["creators"]), 1)

    # ── detail ────────────────────────────────────────────────────────

    def test_get_creator_full_profile_masks_bank_account(self):
        res = admin.admin_get_creator_full_profile(self.creator.name)
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["id"], self.creator.name)
        self.assertEqual(data["kyc"]["bank_account_masked"], "••••0123")
        self.assertNotIn("1234567890123", str(data))  # full account number never leaves the server

    def test_get_creator_full_profile_includes_rate_cards(self):
        card = frappe.get_doc({
            "doctype": "Creator Rate Card", "creator": self.creator.name,
            "deliverable_type": "native_chills", "price_inr": 800, "accepts_barter": 1, "is_active": 1,
        })
        card.insert(ignore_permissions=True)
        res = admin.admin_get_creator_full_profile(self.creator.name)
        self.assertEqual(len(res["data"]["rate_cards"]), 1)
        self.assertEqual(res["data"]["rate_cards"][0]["price_inr"], 800)

    def test_get_creator_full_profile_nonexistent_returns_not_found(self):
        res = admin.admin_get_creator_full_profile("CREATOR-DOES-NOT-EXIST")
        self.assertFalse(res["success"])

    # ── status transitions ────────────────────────────────────────────

    def test_update_creator_status_suspend_and_reinstate(self):
        res = admin.admin_update_creator_status(self.creator.name, "suspended", reason="Policy violation test")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["status"], "suspended")
        self.assertEqual(frappe.db.get_value("Flamezo Creator", self.creator.name, "status"), "suspended")

        res2 = admin.admin_update_creator_status(self.creator.name, "approved", reason="Reinstated after review")
        self.assertTrue(res2["success"])
        self.assertEqual(frappe.db.get_value("Flamezo Creator", self.creator.name, "status"), "approved")

    def test_update_creator_status_sets_approved_at_on_first_approval(self):
        frappe.db.set_value("Flamezo Creator", self.creator.name, "status", "pending")
        frappe.db.set_value("Flamezo Creator", self.creator.name, "approved_at", None)
        admin.admin_update_creator_status(self.creator.name, "approved")
        self.assertIsNotNone(frappe.db.get_value("Flamezo Creator", self.creator.name, "approved_at"))

    def test_update_creator_status_invalid_status_throws(self):
        with self.assertRaises(frappe.ValidationError):
            admin.admin_update_creator_status(self.creator.name, "banned_forever")

    def test_update_creator_status_same_status_returns_error_not_exception(self):
        res = admin.admin_update_creator_status(self.creator.name, "approved")
        self.assertFalse(res["success"])

    def test_update_creator_status_logs_audit_comment(self):
        admin.admin_update_creator_status(self.creator.name, "rejected", reason="Fake follower count")
        comments = frappe.db.get_all(
            "Comment", filters={"reference_doctype": "Flamezo Creator", "reference_name": self.creator.name},
            fields=["content"], order_by="creation desc", limit_page_length=1,
        )
        self.assertEqual(len(comments), 1)
        self.assertIn("approved", comments[0].content)
        self.assertIn("rejected", comments[0].content)
        self.assertIn("Fake follower count", comments[0].content)

    def test_update_creator_status_nonexistent_creator_returns_not_found(self):
        res = admin.admin_update_creator_status("CREATOR-DOES-NOT-EXIST", "approved")
        self.assertFalse(res["success"])
