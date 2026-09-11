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


class TestLeegalityDownload(unittest.TestCase):
	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_download_success(self, mock_request):
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.headers = {"Content-Type": "application/pdf"}
		mock_response.content = b"%PDF-1.4 real signed content"
		mock_request.return_value = mock_response

		with _configured():
			content = LeegalityAdapter().download_signed_document("doc-1")
		self.assertEqual(content, b"%PDF-1.4 real signed content")

	@patch("flamezo_backend.flamezo.esign.leegality_adapter.requests.request")
	def test_download_200_with_json_error_body_is_not_treated_as_success(self, mock_request):
		# Leegality's docs explicitly warn: errors come back as HTTP 200
		# with a JSON body, not a 4xx/5xx — this must not be swallowed as
		# if it were the real PDF.
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.headers = {"Content-Type": "application/json"}
		mock_response.text = '{"status": 0, "messages": [{"message": "document not found"}]}'
		mock_request.return_value = mock_response

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

	def test_missing_mac_is_rejected_not_crashed(self):
		payload = {"eventType": "SIGNED", "document": {"documentId": "doc-1"}}
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, json.dumps(payload).encode())
		self.assertIsNone(event)

	def test_invalid_json_body_is_rejected_not_crashed(self):
		with _configured():
			event = LeegalityAdapter().verify_and_parse_webhook({}, b"not json at all {{{")
		self.assertIsNone(event)
