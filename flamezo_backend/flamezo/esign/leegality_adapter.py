"""
Leegality adapter — Basic Plan, Aadhaar eSign at ₹25/signature, no monthly
API toll (unlike SignYu). Live account, real credentials already in
site_config.json (leegality_auth_token, leegality_private_salt).

Every endpoint/field name below is taken directly from Leegality's own
docs (knowledge.leegality.com), not guessed:
  - Create request:   POST /v3.0/sign/request
  - Status check:      GET /v3.3/document/details
  - Download signed:   GET /v3.1/document/fetchDocument
  - Webhook verify:    mac = HMAC-SHA1(documentId, privateSalt)  -- SHA1,
    not SHA256; that's genuinely what Leegality documents, not a typo.

WhatsApp delivery and the Aadhaar signature requirement are configured
ONCE per Workflow in the Leegality dashboard (Settings > that workflow's
"More Options" > notification channel + webhook URLs + Webhook Version
v2.5) — NOT passed per API call. That workflow's ID is `profileId`, one
per Agreement Template (see Agreement Template.leegality_profile_id).
Before this adapter can be used for a given Agreement Template:
  1. Create a Workflow in the Leegality dashboard for that agreement type.
  2. Set its notification channel to WhatsApp (confirm this is available
     on the Basic Plan when setting it up — flagged as unverified earlier).
  3. Set signature type to Aadhaar eSign.
  4. Add this app's webhook URL (both Webhook URL and Error Webhook URL)
     and set Webhook Version to v2.5.
  5. Copy that workflow's profileId into the Agreement Template row.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import frappe
import requests

from .base import (
	EsignAdapter,
	EsignProviderError,
	SigningRequestResult,
	StatusResult,
	WebhookEvent,
)

_REQUEST_TIMEOUT_SECONDS = 20
_MAX_RETRIES = 2

# data.document.status values per check-document-details
_STATUS_MAP = {
	"DRAFT": "Draft",
	"SENT": "Link Sent",
	"COMPLETED": "Signed",
}


def _get_config() -> dict:
	auth_token = frappe.conf.get("leegality_auth_token")
	private_salt = frappe.conf.get("leegality_private_salt")
	base_url = frappe.conf.get("leegality_base_url") or "https://sandbox.leegality.com/api"
	if not auth_token or not private_salt:
		frappe.throw(
			frappe._(
				"Leegality is not configured — set leegality_auth_token and "
				"leegality_private_salt in site_config.json."
			)
		)
	return {"auth_token": auth_token, "private_salt": private_salt, "base_url": base_url}


class LeegalityAdapter(EsignAdapter):
	provider_key = "leegality"

	def _headers(self) -> dict:
		cfg = _get_config()
		return {"X-Auth-Token": cfg["auth_token"], "Content-Type": "application/json"}

	def _request(self, method: str, path: str, base_url: str, **kwargs):
		url = f"{base_url}{path}"
		last_exc = None
		for attempt in range(_MAX_RETRIES + 1):
			try:
				resp = requests.request(
					method, url, headers=self._headers(), timeout=_REQUEST_TIMEOUT_SECONDS, **kwargs
				)
				if resp.status_code >= 500 and attempt < _MAX_RETRIES:
					continue
				if resp.status_code >= 400:
					raise EsignProviderError(
						f"Leegality {method} {path} failed: {resp.status_code} {resp.text[:500]}"
					)
				return resp
			except requests.RequestException as e:
				last_exc = e
				if attempt < _MAX_RETRIES:
					continue
				raise EsignProviderError(f"Leegality {method} {path} network error: {e}") from e
		raise EsignProviderError(
			f"Leegality {method} {path} failed after {_MAX_RETRIES + 1} attempts"
		) from last_exc

	def create_signing_request(
		self,
		*,
		document_bytes: bytes,
		filename: str,
		signer_name: str,
		signer_phone: str,
		request_e_stamp: bool = False,
		profile_id: str | None = None,
	) -> SigningRequestResult:
		if not profile_id:
			raise EsignProviderError(
				"Leegality requires a profileId (Workflow ID) — set "
				"Agreement Template.leegality_profile_id for this agreement type."
			)
		cfg = _get_config()
		body = {
			"profileId": profile_id,
			"file": {
				"name": filename,
				"file": base64.b64encode(document_bytes).decode("ascii"),
			},
			"invitees": [
				{
					"name": signer_name,
					"phone": signer_phone,
					# WhatsApp delivery + signature type are workflow-level
					# settings (see module docstring), not passed here.
					"aadhaarConfig": {"verifyName": False},
				}
			],
		}
		resp = self._request("POST", "/v3.0/sign/request", cfg["base_url"], json=body)
		payload = resp.json()
		if payload.get("status") != 1:
			raise EsignProviderError(f"Leegality create request rejected: {payload}")

		data = payload.get("data") or {}
		invitees = data.get("invitees") or []
		signing_url = invitees[0].get("signUrl") if invitees else None
		return SigningRequestResult(
			provider_request_id=data["documentId"], signing_url=signing_url, raw=payload
		)

	def get_request_status(self, provider_request_id: str) -> StatusResult:
		cfg = _get_config()
		resp = self._request(
			"GET",
			"/v3.3/document/details",
			cfg["base_url"],
			params={"documentId": provider_request_id},
		)
		payload = resp.json()
		raw_status = ((payload.get("data") or {}).get("document") or {}).get("status", "")
		status = _STATUS_MAP.get(raw_status, "Link Sent")
		return StatusResult(provider_request_id=provider_request_id, status=status, raw=payload)

	def download_signed_document(self, provider_request_id: str) -> bytes:
		cfg = _get_config()
		resp = self._request(
			"GET",
			"/v3.1/document/fetchDocument",
			cfg["base_url"],
			params={"documentId": provider_request_id, "documentDownloadType": "DOCUMENT"},
		)
		content_type = resp.headers.get("Content-Type", "")
		if "application/pdf" not in content_type:
			# Leegality returns HTTP 200 with a JSON error body on failure
			# instead of a real error status — never treat a 200 as success
			# without checking the content type first.
			raise EsignProviderError(
				f"Leegality fetchDocument did not return a PDF for {provider_request_id}: "
				f"{resp.text[:500]}"
			)
		return resp.content

	def verify_and_parse_webhook(self, headers: dict, raw_body: bytes) -> WebhookEvent | None:
		cfg = _get_config()
		try:
			payload = json.loads(raw_body.decode("utf-8"))
		except (ValueError, UnicodeDecodeError):
			frappe.log_error("Leegality webhook body not valid JSON", "leegality.webhook")
			return None

		# documentId can be top-level (older/error-webhook shape) or nested
		# under document.documentId (v2.5 success-webhook shape) — handle
		# both rather than assume one schema, since Leegality's own example
		# payloads use different shapes for success vs. error webhooks.
		doc_id = payload.get("documentId") or (payload.get("document") or {}).get("documentId")
		mac = payload.get("mac")
		if not doc_id or not mac:
			frappe.log_error(
				"Leegality webhook missing documentId or mac", "leegality.webhook"
			)
			return None

		expected_mac = hmac.new(
			cfg["private_salt"].encode("utf-8"), doc_id.encode("utf-8"), hashlib.sha1
		).hexdigest()
		if not hmac.compare_digest(expected_mac, mac):
			frappe.log_error("Leegality webhook mac mismatch", "leegality.webhook")
			return None

		event_type = self._normalize_event(payload)
		if not event_type:
			frappe.log_error(
				f"Leegality webhook unrecognized shape: {json.dumps(payload)[:300]}",
				"leegality.webhook",
			)
			return None

		invitee = payload.get("invitee") or payload.get("request") or {}
		return WebhookEvent(
			provider_request_id=doc_id,
			event_type=event_type,
			signer_phone_masked=_mask_phone(invitee.get("inviteeMobile") or invitee.get("phone")),
			raw=payload,
		)

	@staticmethod
	def _normalize_event(payload: dict) -> str | None:
		# v2.5 success shape: {"eventType": "SIGNED", ...}
		event_type = payload.get("eventType")
		if event_type == "SIGNED":
			return "signed"
		if event_type in ("SIGNER_REJECTED", "REVIEWER_REJECTED"):
			return "failed"

		# Error-webhook shape (document-expired.txt example): no eventType,
		# but request.expired / webhookType: "Error" instead.
		if payload.get("webhookType") == "Error":
			request = payload.get("request") or {}
			if request.get("expired"):
				return "expired"
			return "failed"

		return None


def _mask_phone(phone: str | None) -> str | None:
	if not phone or len(phone) < 4:
		return phone
	return f"{phone[:2]}{'*' * (len(phone) - 4)}{phone[-2:]}"
