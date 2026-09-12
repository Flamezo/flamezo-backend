"""
Real DB-backed tests for the agreement-signing flow: Agreement Template
versioning, Signed Agreement state machine + immutability, clickwrap
acceptance, the webhook handler (against a fake adapter — no live SignYu
credentials in CI), and the stalled-request reconciliation job.
"""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime

from flamezo_backend.flamezo.esign.base import (
	EsignProviderError,
	SigningRequestResult,
	StatusResult,
	WebhookEvent,
)

_PREFIX = "TEST-ESIGN"
_PHONE_MERCHANT_OWNER = "9500000001"
_PHONE_CREATOR = "9500000002"
_PHONE_OTHER = "9500000003"


def _cleanup():
	frappe.db.sql("DELETE FROM `tabSigned Agreement` WHERE agreement_version LIKE %s", [f"{_PREFIX}%"])
	frappe.db.sql("DELETE FROM `tabAgreement Template` WHERE version LIKE %s", [f"{_PREFIX}%"])
	frappe.db.sql("DELETE FROM `tabOutlet` WHERE name LIKE %s", [f"{_PREFIX}%"])
	frappe.db.sql("DELETE FROM `tabFlamezo Creator` WHERE customer_phone IN (%s, %s)",
		[_PHONE_CREATOR, _PHONE_OTHER])
	frappe.db.sql("DELETE FROM `tabOutlet User` WHERE user = %s", [f"{_PREFIX}-user@test.com"])
	frappe.db.commit()


def _verified_session():
	return patch(
		"flamezo_backend.flamezo.api.esign.has_active_customer_session", return_value=True
	)


def _make_test_file(content=b"fake agreement content for hashing/pipeline tests only"):
	# .txt, not .pdf — Frappe's File doctype runs a real PDF-malware/JS scan
	# on anything named *.pdf, which our fixture bytes (not a real PDF
	# structure) would fail. These tests exercise the hashing/upload
	# pipeline, not actual PDF rendering, so the extension doesn't matter.
	f = frappe.get_doc({
		"doctype": "File",
		"file_name": f"{_PREFIX}-template.txt",
		"is_private": 0,
		"content": content,
	})
	f.insert(ignore_permissions=True)
	return f.file_url


def _make_test_outlet(suffix):
	outlet = frappe.get_doc({
		"doctype": "Outlet",
		"outlet_name": f"{_PREFIX} Outlet {suffix}",
		"legal_name": f"{_PREFIX} Legal {suffix}",
		"owner_phone": _PHONE_MERCHANT_OWNER,
		"outlet_type": "dining",
		"city": "Surat",
	})
	outlet.insert(ignore_permissions=True)
	frappe.db.commit()
	return outlet


def _make_template(agreement_type, version=None, requires_esign=True, provider="signyu", type_code="MERCH-AGR"):
	version = version or f"{_PREFIX}-v1.0"
	doc = frappe.get_doc({
		"doctype": "Agreement Template",
		"agreement_type": agreement_type,
		"agreement_type_code": type_code,
		"version": version,
		"is_active": 1,
		"requires_esign": requires_esign,
		"effective_from": now_datetime(),
		"template_file": _make_test_file(),
		"esign_provider": provider if requires_esign else "",
		"review_period_days": 5,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


class TestAgreementTemplate(unittest.TestCase):
	def setUp(self):
		_cleanup()

	def tearDown(self):
		_cleanup()

	def test_activating_new_version_deactivates_old(self):
		v1 = _make_template("Merchant Partnership Agreement", version=f"{_PREFIX}-v1.0")
		self.assertEqual(frappe.db.get_value("Agreement Template", v1.name, "is_active"), 1)

		v2 = _make_template("Merchant Partnership Agreement", version=f"{_PREFIX}-v2.0")
		self.assertEqual(frappe.db.get_value("Agreement Template", v1.name, "is_active"), 0)
		self.assertEqual(frappe.db.get_value("Agreement Template", v1.name, "superseded_by"), v2.name)
		self.assertEqual(frappe.db.get_value("Agreement Template", v2.name, "is_active"), 1)

	def test_template_file_hash_computed_on_save(self):
		v1 = _make_template("Merchant Partnership Agreement", version=f"{_PREFIX}-v1.0")
		self.assertTrue(v1.template_file_hash)
		self.assertEqual(len(v1.template_file_hash), 64)  # sha256 hex digest


class TestSignedAgreementStateMachine(unittest.TestCase):
	def setUp(self):
		_cleanup()
		self.template = _make_template("Merchant Partnership Agreement")
		self.outlet = _make_test_outlet("StateMachine")

	def tearDown(self):
		_cleanup()

	def _make_row(self, status="Draft"):
		row = frappe.get_doc({
			"doctype": "Signed Agreement",
			"agreement_template": self.template.name,
			"agreement_type": self.template.agreement_type,
			"agreement_version": self.template.version,
			"party_doctype": "Outlet",
			"party": self.outlet.name,
			"status": "Draft",
			"esign_provider": "signyu",
			"agreement_document_hash": "a" * 64,
		})
		row.insert(ignore_permissions=True)
		if status != "Draft":
			row.status = status
			row.save(ignore_permissions=True)
		return row

	def test_valid_transition_allowed(self):
		row = self._make_row()
		row.status = "Link Sent"
		row.save(ignore_permissions=True)  # must not raise
		self.assertEqual(frappe.db.get_value("Signed Agreement", row.name, "status"), "Link Sent")

	def test_invalid_transition_rejected(self):
		row = self._make_row()
		row.status = "Viewed"  # Draft -> Viewed skips Link Sent, not legal
		with self.assertRaises(frappe.exceptions.ValidationError):
			row.save(ignore_permissions=True)

	def test_draft_to_signed_direct_allowed_for_clickwrap(self):
		row = self._make_row()
		row.status = "Signed"  # legal ONLY as the clickwrap shortcut
		row.save(ignore_permissions=True)  # must not raise
		self.assertEqual(frappe.db.get_value("Signed Agreement", row.name, "status"), "Signed")

	def test_signed_row_is_immutable(self):
		row = self._make_row(status="Link Sent")
		row.status = "Signed"
		row.signed_pdf = "/files/whatever.pdf"
		row.save(ignore_permissions=True)

		row.reload()
		row.signer_ip = "1.2.3.4"  # attempting to edit a frozen field
		with self.assertRaises(frappe.exceptions.ValidationError):
			row.save(ignore_permissions=True)

	def test_signed_row_can_move_to_superseded(self):
		row = self._make_row(status="Link Sent")
		row.status = "Signed"
		row.save(ignore_permissions=True)

		row.reload()
		row.status = "Superseded"
		row.save(ignore_permissions=True)  # must not raise
		self.assertEqual(frappe.db.get_value("Signed Agreement", row.name, "status"), "Superseded")

	def test_terminal_states_reject_any_further_transition(self):
		row = self._make_row(status="Failed")
		row.status = "Link Sent"
		with self.assertRaises(frappe.exceptions.ValidationError):
			row.save(ignore_permissions=True)


class TestInitiateAgreementSigning(unittest.TestCase):
	def setUp(self):
		_cleanup()
		self.template = _make_template("Merchant Partnership Agreement")
		self.outlet = frappe.get_doc({
			"doctype": "Outlet",
			"outlet_name": f"{_PREFIX} Test Outlet",
			"legal_name": f"{_PREFIX} Legal Pvt Ltd",
			"owner_phone": _PHONE_MERCHANT_OWNER,
			"outlet_type": "dining",
			"city": "Surat",
		})
		self.outlet.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		_cleanup()

	@patch("flamezo_backend.flamezo.api.esign.get_adapter")
	def test_initiate_creates_signed_agreement_and_calls_adapter(self, mock_get_adapter):
		from flamezo_backend.flamezo.api import esign as esign_api

		fake_adapter = mock_get_adapter.return_value
		fake_adapter.create_signing_request.return_value = SigningRequestResult(
			provider_request_id="prov-123", signing_url=None, raw={}
		)

		with patch("frappe.session") as mock_session:
			mock_session.user = "Administrator"
			result = esign_api.initiate_agreement_signing(
				party_doctype="Outlet",
				party_name=self.outlet.name,
				agreement_type=self.template.agreement_type,
			)

		self.assertTrue(result["success"])
		row_name = result["data"]["signed_agreement"]
		row = frappe.get_doc("Signed Agreement", row_name)
		self.assertEqual(row.status, "Link Sent")
		self.assertEqual(row.provider_request_id, "prov-123")
		self.assertTrue(row.agreement_document_hash)
		snapshot = json.loads(row.schedule_snapshot)
		self.assertEqual(snapshot["success_share_app_pct"], 7)
		fake_adapter.create_signing_request.assert_called_once()

	@patch("flamezo_backend.flamezo.api.esign.get_adapter")
	def test_initiate_is_idempotent_for_pending_request(self, mock_get_adapter):
		from flamezo_backend.flamezo.api import esign as esign_api

		fake_adapter = mock_get_adapter.return_value
		fake_adapter.create_signing_request.return_value = SigningRequestResult(
			provider_request_id="prov-abc", signing_url=None, raw={}
		)

		with patch("frappe.session") as mock_session:
			mock_session.user = "Administrator"
			first = esign_api.initiate_agreement_signing(
				party_doctype="Outlet",
				party_name=self.outlet.name,
				agreement_type=self.template.agreement_type,
			)
			second = esign_api.initiate_agreement_signing(
				party_doctype="Outlet",
				party_name=self.outlet.name,
				agreement_type=self.template.agreement_type,
			)

		self.assertEqual(first["data"]["signed_agreement"], second["data"]["signed_agreement"])
		self.assertTrue(second["data"].get("already_exists"))
		fake_adapter.create_signing_request.assert_called_once()

	@patch("flamezo_backend.flamezo.api.esign.get_adapter")
	def test_provider_failure_marks_row_failed_not_silent(self, mock_get_adapter):
		from flamezo_backend.flamezo.api import esign as esign_api

		fake_adapter = mock_get_adapter.return_value
		fake_adapter.create_signing_request.side_effect = EsignProviderError("boom")

		with patch("frappe.session") as mock_session:
			mock_session.user = "Administrator"
			with self.assertRaises(frappe.exceptions.ValidationError):
				esign_api.initiate_agreement_signing(
					party_doctype="Outlet",
					party_name=self.outlet.name,
					agreement_type=self.template.agreement_type,
				)

		row_name = frappe.db.get_value(
			"Signed Agreement", {"party": self.outlet.name}, "name"
		)
		self.assertEqual(frappe.db.get_value("Signed Agreement", row_name, "status"), "Failed")

	def test_non_mapped_user_cannot_sign_for_outlet(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		with patch("frappe.session") as mock_session:
			mock_session.user = "random-unmapped-user@test.com"
			with self.assertRaises(frappe.exceptions.PermissionError):
				esign_api.initiate_agreement_signing(
					party_doctype="Outlet",
					party_name=self.outlet.name,
					agreement_type=self.template.agreement_type,
				)


class TestAdminInitiateAgreementSigning(unittest.TestCase):
	"""Merchant Management's admin-triggered path — a FlameZO staff member
	(System Manager), not the merchant, sends the agreement for signing."""

	def setUp(self):
		_cleanup()
		self.template = _make_template("Merchant Partnership Agreement")
		self.outlet = _make_test_outlet("AdminInitiate")

	def tearDown(self):
		_cleanup()

	@patch("flamezo_backend.flamezo.api.esign.get_adapter")
	def test_system_manager_can_trigger(self, mock_get_adapter):
		from flamezo_backend.flamezo.api import esign as esign_api

		fake_adapter = mock_get_adapter.return_value
		fake_adapter.create_signing_request.return_value = SigningRequestResult(
			provider_request_id="prov-admin-1", signing_url="https://app1.leegality.com/sign/abc", raw={}
		)

		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = esign_api.admin_initiate_agreement_signing(
				outlet_id=self.outlet.name, agreement_type=self.template.agreement_type
			)

		self.assertTrue(result["success"])
		row = frappe.get_doc("Signed Agreement", result["data"]["signed_agreement"])
		self.assertEqual(row.status, "Link Sent")
		self.assertEqual(row.party_doctype, "Outlet")
		self.assertEqual(row.party, self.outlet.name)

	def test_non_admin_rejected(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		with patch("frappe.get_roles", return_value=["Outlet User"]):
			with self.assertRaises(frappe.exceptions.PermissionError):
				esign_api.admin_initiate_agreement_signing(
					outlet_id=self.outlet.name, agreement_type=self.template.agreement_type
				)

	def test_unknown_outlet_rejected_clearly(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		with patch("frappe.get_roles", return_value=["System Manager"]):
			with self.assertRaises(frappe.exceptions.ValidationError):
				esign_api.admin_initiate_agreement_signing(
					outlet_id="no-such-outlet", agreement_type=self.template.agreement_type
				)

	@patch("flamezo_backend.flamezo.api.esign.get_adapter")
	def test_idempotent_same_as_self_service_path(self, mock_get_adapter):
		# Admin re-clicking "Send for Signing" on an already-pending request
		# must not fire a second signing request to Leegality.
		from flamezo_backend.flamezo.api import esign as esign_api

		fake_adapter = mock_get_adapter.return_value
		fake_adapter.create_signing_request.return_value = SigningRequestResult(
			provider_request_id="prov-admin-2", signing_url=None, raw={}
		)

		with patch("frappe.get_roles", return_value=["System Manager"]):
			first = esign_api.admin_initiate_agreement_signing(
				outlet_id=self.outlet.name, agreement_type=self.template.agreement_type
			)
			second = esign_api.admin_initiate_agreement_signing(
				outlet_id=self.outlet.name, agreement_type=self.template.agreement_type
			)

		self.assertEqual(first["data"]["signed_agreement"], second["data"]["signed_agreement"])
		self.assertTrue(second["data"].get("already_exists"))
		fake_adapter.create_signing_request.assert_called_once()


class TestAdminGetAgreementStatus(unittest.TestCase):
	def setUp(self):
		_cleanup()
		self.template = _make_template("Merchant Partnership Agreement")
		self.outlet = _make_test_outlet("AdminStatus")

	def tearDown(self):
		_cleanup()

	def test_no_agreement_yet_returns_none_not_error(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = esign_api.admin_get_agreement_status(outlet_id=self.outlet.name)

		self.assertTrue(result["success"])
		self.assertIsNone(result["data"])

	def test_returns_latest_status_for_this_outlet_and_type(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		row = frappe.get_doc({
			"doctype": "Signed Agreement",
			"agreement_template": self.template.name,
			"agreement_type": self.template.agreement_type,
			"agreement_version": self.template.version,
			"party_doctype": "Outlet",
			"party": self.outlet.name,
			"status": "Link Sent",
			"agreement_document_hash": "deadbeef",
			"esign_provider": "leegality",
			"provider_request_id": "prov-status-1",
			"signing_url": "https://app1.leegality.com/sign/xyz",
		})
		row.insert(ignore_permissions=True)
		frappe.db.commit()

		with patch("frappe.get_roles", return_value=["System Manager"]):
			result = esign_api.admin_get_agreement_status(outlet_id=self.outlet.name)

		self.assertTrue(result["success"])
		self.assertEqual(result["data"]["name"], row.name)
		self.assertEqual(result["data"]["status"], "Link Sent")
		self.assertEqual(result["data"]["signing_url"], "https://app1.leegality.com/sign/xyz")

	def test_non_admin_rejected(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		with patch("frappe.get_roles", return_value=["Outlet User"]):
			with self.assertRaises(frappe.exceptions.PermissionError):
				esign_api.admin_get_agreement_status(outlet_id=self.outlet.name)


class TestClickwrapAcceptance(unittest.TestCase):
	def setUp(self):
		_cleanup()
		self.template = _make_template(
			"Customer Terms of Service", requires_esign=False, provider="",
			type_code="CUST-TOS",
		)
		from flamezo_backend.flamezo.tests.utils import make_customer

		self.customer = make_customer(phone=_PHONE_CREATOR, name="Test Clickwrap Customer")

	def tearDown(self):
		_cleanup()
		frappe.db.sql("DELETE FROM `tabCustomer` WHERE phone=%s", [_PHONE_CREATOR])
		frappe.db.commit()

	def test_clickwrap_records_signed_immediately_no_provider_call(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		with _verified_session():
			result = esign_api.record_clickwrap_acceptance(phone=_PHONE_CREATOR)

		row = frappe.get_doc("Signed Agreement", result["data"]["signed_agreement"])
		self.assertEqual(row.status, "Signed")
		self.assertEqual(row.esign_provider, "clickwrap")
		self.assertIsNotNone(row.signed_at)

	def test_clickwrap_is_idempotent(self):
		from flamezo_backend.flamezo.api import esign as esign_api

		with _verified_session():
			first = esign_api.record_clickwrap_acceptance(phone=_PHONE_CREATOR)
			second = esign_api.record_clickwrap_acceptance(phone=_PHONE_CREATOR)

		self.assertEqual(first["data"]["signed_agreement"], second["data"]["signed_agreement"])
		self.assertTrue(second["data"].get("already_accepted"))


class FakeSignedWebhookAdapter:
	provider_key = "signyu"

	def verify_and_parse_webhook(self, headers, raw_body):
		payload = json.loads(raw_body)
		if payload.get("bad_signature"):
			return None
		return WebhookEvent(
			provider_request_id=payload["provider_request_id"],
			event_type=payload["event_type"],
			signer_phone_masked="95****01",
			signer_ip="1.2.3.4",
			aadhaar_last4="1234",
			raw=payload,
		)

	def download_signed_document(self, provider_request_id):
		return b"%PDF-1.4 signed content"


class TestEsignWebhook(unittest.TestCase):
	def setUp(self):
		_cleanup()
		self.template = _make_template("Merchant Partnership Agreement")
		self.outlet = _make_test_outlet("Webhook")
		self.row = frappe.get_doc({
			"doctype": "Signed Agreement",
			"agreement_template": self.template.name,
			"agreement_type": self.template.agreement_type,
			"agreement_version": self.template.version,
			"party_doctype": "Outlet",
			"party": self.outlet.name,
			"status": "Draft",
			"esign_provider": "signyu",
			"provider_request_id": "prov-webhook-1",
			"agreement_document_hash": "b" * 64,
		})
		self.row.insert(ignore_permissions=True)
		self.row.status = "Link Sent"
		self.row.save(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		_cleanup()

	def _post_webhook(self, body: dict):
		from flamezo_backend.flamezo.api import esign as esign_api

		class _FakeRequest:
			def __init__(self, data):
				self._data = data
				self.headers = {}

			def get_data(self):
				return self._data

		fake_request = _FakeRequest(json.dumps(body).encode())
		with patch.object(frappe.local, "request", fake_request, create=True):
			with patch(
				"flamezo_backend.flamezo.api.esign.get_adapter",
				return_value=FakeSignedWebhookAdapter(),
			):
				return esign_api.esign_webhook(provider="signyu")

	@patch("flamezo_backend.flamezo.media.storage.upload_bytes")
	def test_signed_event_uploads_pdf_and_marks_signed(self, mock_upload):
		mock_upload.return_value = "https://cdn.example.com/agreements/test.pdf"

		self._post_webhook({
			"provider_request_id": "prov-webhook-1",
			"event_type": "signed",
		})

		row = frappe.get_doc("Signed Agreement", self.row.name)
		self.assertEqual(row.status, "Signed")
		self.assertEqual(row.signed_pdf, "https://cdn.example.com/agreements/test.pdf")
		self.assertTrue(row.signed_pdf_hash)
		mock_upload.assert_called_once()

	@patch("flamezo_backend.flamezo.media.storage.upload_bytes")
	def test_redelivered_signed_event_is_idempotent_noop(self, mock_upload):
		mock_upload.return_value = "https://cdn.example.com/agreements/test.pdf"

		self._post_webhook({"provider_request_id": "prov-webhook-1", "event_type": "signed"})
		self._post_webhook({"provider_request_id": "prov-webhook-1", "event_type": "signed"})

		# Only the first delivery should have actually uploaded/downloaded.
		self.assertEqual(mock_upload.call_count, 1)

	def test_unknown_provider_request_id_is_silently_acked(self):
		result = self._post_webhook({
			"provider_request_id": "does-not-exist",
			"event_type": "signed",
		})
		self.assertTrue(result["success"])
		# original row untouched
		self.assertEqual(
			frappe.db.get_value("Signed Agreement", self.row.name, "status"), "Link Sent"
		)

	def test_bad_signature_is_silently_acked_and_ignored(self):
		result = self._post_webhook({
			"provider_request_id": "prov-webhook-1",
			"event_type": "signed",
			"bad_signature": True,
		})
		self.assertTrue(result["success"])
		self.assertEqual(
			frappe.db.get_value("Signed Agreement", self.row.name, "status"), "Link Sent"
		)
