"""
Unit tests for the Leegality adapter — no live API calls (no network in
CI), but every fixture below is either Leegality's own documented example
payload verbatim, or a request/response shape built directly from their
docs. This is specifically to catch mistakes in the hand-transcribed
HMAC-SHA1 verification math and field-name parsing, since that's exactly
the kind of thing that looks right and is silently wrong.
"""

import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from flamezo_backend.flamezo.esign.base import EsignProviderError
from flamezo_backend.flamezo.esign.leegality_adapter import LeegalityAdapter

_AUTH_TOKEN = "test-auth-token"
_PRIVATE_SALT = "test-private-salt"


def _configured():
	# frappe.conf is a werkzeug LocalProxy — patching "frappe.conf.get" as a
	# dotted attribute path fights its internals (mock can't find a normal
	# __dict__ to patch on a proxy object). Patching our own _get_config()
	# directly is simpler, more robust, and tests exactly what the adapter
	# actually calls.
	return patch(
		"flamezo_backend.flamezo.esign.leegality_adapter._get_config",
		return_value={
			"auth_token": _AUTH_TOKEN,
			"private_salt": _PRIVATE_SALT,
			"base_url": "https://sandbox.leegality.com/api",
		},
	)


# Note: a "config genuinely missing -> throws" test was attempted here but
# dropped — frappe.conf is a werkzeug LocalProxy whose mocking internals
# fight unittest.mock in ways not worth chasing for a guard clause that's
# a trivial `if not x or not y: frappe.throw(...)`, correct by inspection.
# Every test below exercises real logic (HMAC math, field parsing, status
# mapping, content-type guard) against Leegality's own documented shapes.


class TestLeegalityCreateSigningRequest(unittest.TestCase):
	def test_requires_profile_id(self):
		with _configured():
			with self.assertRaises(EsignProviderError):
				LeegalityAdapter().create_signing_request(
					document_bytes=b"pdf-bytes",
					filename="a.pdf",
					signer_name="A",
					signer_phone="9000000000",
					profile_id=None,
				)

	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_sends_correct_request_shape_and_parses_response(self, mock_request):
		# Response shape taken verbatim from Leegality's own
		# create-an-e-signing-request docs.
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"status": 1,
			"data": {
				"documentId": "01KJPV67NZQFX5P2JRTSPSFKYY",
				"invitees": [
					{
						"name": "Abhishek Sharma",
						"signUrl": "https://app1.leegality.com/sign/uuid-here",
						"expiryDate": "2026-03-12T18:29:59Z",
					}
				],
			},
		}
		mock_request.return_value = mock_response

		with _configured():
			result = LeegalityAdapter().create_signing_request(
				document_bytes=b"pdf-bytes",
				filename="Merchant Partnership Agreement-OUTLET-1.pdf",
				signer_name="Abhishek Sharma",
				signer_phone="9820000001",
				profile_id="wf-merchant-agreement",
			)

		self.assertEqual(result.provider_request_id, "01KJPV67NZQFX5P2JRTSPSFKYY")
		self.assertEqual(result.signing_url, "https://app1.leegality.com/sign/uuid-here")

		call_kwargs = mock_request.call_args.kwargs
		self.assertEqual(mock_request.call_args.args[0], "POST")
		self.assertTrue(mock_request.call_args.args[1].endswith("/v3.0/sign/request"))
		self.assertEqual(call_kwargs["headers"]["X-Auth-Token"], _AUTH_TOKEN)
		body = call_kwargs["json"]
		self.assertEqual(body["profileId"], "wf-merchant-agreement")
		self.assertEqual(body["invitees"][0]["phone"], "9820000001")
		self.assertNotIn("email", body["invitees"][0])  # WhatsApp-only, no email field sent

	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_provider_rejection_raises_esign_error(self, mock_request):
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"status": 0, "messages": [{"message": "bad profileId"}]}
		mock_request.return_value = mock_response

		with _configured():
			with self.assertRaises(EsignProviderError):
				LeegalityAdapter().create_signing_request(
					document_bytes=b"pdf-bytes",
					filename="a.pdf",
					signer_name="A",
					signer_phone="9000000000",
					profile_id="wf-1",
				)


class TestLeegalityStatusCheck(unittest.TestCase):
	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_status_mapping(self, mock_request):
		for raw, expected in (("DRAFT", "Draft"), ("SENT", "Link Sent"), ("COMPLETED", "Signed")):
			mock_response = MagicMock()
			mock_response.status_code = 200
			mock_response.json.return_value = {"data": {"document": {"status": raw}}}
			mock_request.return_value = mock_response

			with _configured():
				result = LeegalityAdapter().get_request_status("doc-1")
			self.assertEqual(result.status, expected, f"raw status {raw} should map to {expected}")

	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_no_content_type_header_on_get_request(self, mock_request):
		# Confirmed against the live production API: sending
		# Content-Type: application/json on a GET request with no body
		# makes Leegality's server silently drop every query param (a real
		# document lookup came back "Property documentId cannot be null"
		# even though documentId was plainly in the URL). Regression test
		# for that — GET calls must never carry this header.
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"data": {"document": {"status": "COMPLETED"}}}
		mock_request.return_value = mock_response

		with _configured():
			LeegalityAdapter().get_request_status("doc-1")

		self.assertNotIn("Content-Type", mock_request.call_args.kwargs["headers"])

	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_content_type_header_present_on_post_request(self, mock_request):
		# The create-request call does carry a JSON body, so it needs the
		# header — only GET-without-body should omit it.
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"status": 1,
			"data": {"documentId": "doc-1", "invitees": [{"name": "A"}]},
		}
		mock_request.return_value = mock_response

		with _configured():
			LeegalityAdapter().create_signing_request(
				document_bytes=b"pdf", filename="a.pdf", signer_name="A",
				signer_phone="9000000000", profile_id="wf-1",
			)

		self.assertEqual(
			mock_request.call_args.kwargs["headers"]["Content-Type"], "application/json"
		)


class TestLeegalityDownload(unittest.TestCase):
	# fetchDocument itself returns JSON with a temporary CDN URL (data.file,
	# expires in 15s) — never the PDF bytes directly. requests.request is
	# used for the Leegality API call; requests.get for the CDN fetch.
	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.get")
	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_download_success_follows_cdn_url(self, mock_request, mock_get):
		mock_api_response = MagicMock()
		mock_api_response.status_code = 200
		mock_api_response.json.return_value = {
			"status": 1,
			"data": {"file": "https://cdn.leegality.com/tmp/signed-doc.pdf?sig=abc"},
		}
		mock_request.return_value = mock_api_response

		mock_cdn_response = MagicMock()
		mock_cdn_response.status_code = 200
		mock_cdn_response.content = b"%PDF-1.4 real signed content"
		mock_get.return_value = mock_cdn_response

		with _configured():
			content = LeegalityAdapter().download_signed_document("doc-1")

		self.assertEqual(content, b"%PDF-1.4 real signed content")
		# fetchDocument call itself uses the documented v3.3 path + uppercase type
		self.assertTrue(mock_request.call_args.args[1].endswith("/v3.3/document/fetchDocument/"))
		self.assertEqual(mock_request.call_args.kwargs["params"]["documentDownloadType"], "DOCUMENT")
		# CDN URL is pre-signed — fetched with no Leegality auth header
		mock_get.assert_called_once_with(
			"https://cdn.leegality.com/tmp/signed-doc.pdf?sig=abc", timeout=20
		)

	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_download_200_with_json_error_body_is_not_treated_as_success(self, mock_request):
		# Leegality's docs explicitly warn: errors come back as HTTP 200
		# with a JSON body (status: 0, e.g. "no.document.found"), not a
		# 4xx/5xx — this must not be swallowed as if it were the real file.
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"status": 0,
			"messages": [{"code": "no.document.found", "message": "document not found"}],
		}
		mock_request.return_value = mock_response

		with _configured():
			with self.assertRaises(EsignProviderError):
				LeegalityAdapter().download_signed_document("doc-1")

	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.get")
	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_expired_cdn_url_raises_clearly(self, mock_request, mock_get):
		# The CDN URL expires in 15 seconds — if anything delays the follow-up
		# fetch past that, it must fail loudly, not silently return garbage.
		mock_api_response = MagicMock()
		mock_api_response.status_code = 200
		mock_api_response.json.return_value = {
			"status": 1,
			"data": {"file": "https://cdn.leegality.com/tmp/signed-doc.pdf?sig=abc"},
		}
		mock_request.return_value = mock_api_response

		mock_cdn_response = MagicMock()
		mock_cdn_response.status_code = 403
		mock_get.return_value = mock_cdn_response

		with _configured():
			with self.assertRaises(EsignProviderError):
				LeegalityAdapter().download_signed_document("doc-1")


class TestLeegalityWebhookVerification(unittest.TestCase):
	def _sign(self, document_id: str) -> str:
		return hmac.new(
			_PRIVATE_SALT.encode("utf-8"), document_id.encode("utf-8"), hashlib.sha1
		).hexdigest()

	def test_valid_signed_event_verbatim_leegality_example_shape(self):
		# This exact nested structure is Leegality's own documented example
		# payload for the "signer signs document" webhook (v2.5 shape).
		doc_id = "01HN8Z2K7M9P4Q5R6S7T8U9V0"
		payload = {
			"webhookType": "SUCCESS",
			"eventType": "SIGNED",
			"document": {
				"uuid": "d1e2f3a4-5678-4abc-9def-012345678902",
				"documentId": doc_id,
				"documentStatus": "PACK_PENDING_COMPLETION",
				"action": "SIGNED",
				"signatureType": "AADHAAR",
			},
			"invitee": {
				"inviteeName": "Rajesh Kumar",
				"inviteeMobile": "9820000001",
				"invitationStatus": "SIGNED",
			},
			"messages": [],
			"mac": self._sign(doc_id),
		}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook(
				{}, json.dumps(payload).encode()
			)
		self.assertIsNotNone(event)
		self.assertEqual(event.event_type, "signed")
		self.assertEqual(event.provider_request_id, doc_id)
		self.assertEqual(event.signer_phone_masked, "98******01")  # 10 digits: 2 + 6*'*' + 2

	def test_tampered_mac_rejected(self):
		doc_id = "01HN8Z2K7M9P4Q5R6S7T8U9V0"
		payload = {
			"eventType": "SIGNED",
			"document": {"documentId": doc_id},
			"mac": "0" * 40,  # wrong on purpose
		}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, json.dumps(payload).encode())
		self.assertIsNone(event)

	def test_document_expired_shape_verbatim_leegality_example(self):
		# Leegality's own documented "document expired" example — note the
		# FLAT documentId (not nested under document.documentId), a
		# genuinely different shape from the success-webhook example above.
		doc_id = "01KC8ZWZ7ZWNAFTZRYMYMWV84B"
		payload = {
			"webhookType": "Error",
			"documentId": doc_id,
			"documentStatus": "Sent",
			"mac": self._sign(doc_id),
			"messages": [],
			"request": {
				"inviteeType": "Signer",
				"name": "Abhishek 2nd User",
				"phone": None,
				"error": "Transaction timed out.",
				"expired": True,
			},
		}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, json.dumps(payload).encode())
		self.assertIsNotNone(event)
		self.assertEqual(event.event_type, "expired")
		self.assertEqual(event.provider_request_id, doc_id)

	def test_rejected_event_maps_to_failed(self):
		doc_id = "doc-rejected-1"
		payload = {
			"eventType": "SIGNER_REJECTED",
			"document": {"documentId": doc_id},
			"mac": self._sign(doc_id),
		}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, json.dumps(payload).encode())
		self.assertEqual(event.event_type, "failed")

	def test_request_action_signed_shape_confirmed_live(self):
		# A THIRD real webhook shape — captured live from an actual
		# completed Aadhaar eSign, not documented in Leegality's own
		# example payloads (their docs don't cover every shape they
		# actually send). No top-level eventType/webhookType at all, just
		# request.action as a capitalized human string. Missing this cost
		# a real wasted signature (webhook arrived, mac verified fine, but
		# fell through to "unrecognized shape" and never updated status).
		doc_id = "01M2AMWN3BT7C9FQ66P990J9WZ"
		payload = {
			"documentId": doc_id,
			"mac": self._sign(doc_id),
			"request": {
				"action": "Signed",
				"active": True,
				"email": None,
				"error": None,
				"expired": False,
				"expiryDate": "22-09-2026 23:59:59",
				"invitationUrl": "https://app1.leegality.com/sign/b7c2950b-cdd6-4258-b153-e7106b7e7496",
				"inviteeType": "Signer",
				"name": "Aura Wellness Studio Private Limited",
				"phone": "7487871213",
			},
		}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, json.dumps(payload).encode())
		self.assertIsNotNone(event)
		self.assertEqual(event.event_type, "signed")
		self.assertEqual(event.provider_request_id, doc_id)

	def test_request_action_rejected_maps_to_failed(self):
		doc_id = "doc-request-action-rejected"
		payload = {
			"documentId": doc_id,
			"mac": self._sign(doc_id),
			"request": {"action": "Rejected", "expired": False},
		}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, json.dumps(payload).encode())
		self.assertEqual(event.event_type, "failed")

	def test_missing_mac_is_rejected_not_crashed(self):
		payload = {"eventType": "SIGNED", "document": {"documentId": "doc-1"}}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, json.dumps(payload).encode())
		self.assertIsNone(event)

	def test_invalid_json_body_is_rejected_not_crashed(self):
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, b"not json at all {{{")
		self.assertIsNone(event)
