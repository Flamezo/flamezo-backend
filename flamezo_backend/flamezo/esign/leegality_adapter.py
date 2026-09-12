"""
Leegality adapter — Basic Plan, Aadhaar eSign at ₹25/signature, no monthly
API toll (unlike SignYu). Live account, real credentials already in
site_config.json (leegality_auth_token, leegality_private_salt).

Every endpoint/field name below is taken directly from Leegality's own
docs (knowledge.leegality.com), not guessed:
  - Create request:   POST /v3.0/sign/request
  - Status check:      GET /v3.3/document/details
  - Download signed:   GET /v3.3/document/fetchDocument -- returns JSON with
    data.file = a temporary CDN URL that expires in 15 seconds, NOT the PDF
    bytes directly. Must be fetched immediately, with no auth header (it's a
    signed CDN link, not a Leegality API call).
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

	def _headers(self, has_json_body: bool) -> dict:
		cfg = _get_config()
		headers = {"X-Auth-Token": cfg["auth_token"]}
		if has_json_body:
			# Confirmed against the live production API: sending
			# Content-Type: application/json on a GET request with no body
			# breaks Leegality's server-side query-param parsing entirely
			# (every query param comes back as if it were never sent — e.g.
			# "Property documentId cannot be null" even though it's plainly
			# in the URL). Only ever send this header on requests that
			# actually carry a JSON body.
			headers["Content-Type"] = "application/json"
		return headers

	def _request(self, method: str, path: str, base_url: str, **kwargs):
		url = f"{base_url}{path}"
		last_exc = None
		headers = self._headers(has_json_body="json" in kwargs)
		for attempt in range(_MAX_RETRIES + 1):
			try:
				resp = requests.request(
					method, url, headers=headers, timeout=_REQUEST_TIMEOUT_SECONDS, **kwargs
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
			# Trailing slash before the query string is required — Leegality's
			# router silently drops all query params without it, returning
			# "Property documentId cannot be null" even though it's plainly
			# present. Confirmed against the live production API, not a typo.
			"/v3.3/document/details/",
			cfg["base_url"],
			params={"documentId": provider_request_id},
		)
		payload = resp.json()
		raw_status = ((payload.get("data") or {}).get("document") or {}).get("status", "")
		status = _STATUS_MAP.get(raw_status, "Link Sent")
		return StatusResult(provider_request_id=provider_request_id, status=status, raw=payload)

	def download_signed_document(self, provider_request_id: str) -> bytes:
		cfg = _get_config()
		# fetchDocument itself never returns the PDF bytes — it returns a
		# JSON body with a temporary CDN URL (data.file) that expires in
		# 15 seconds, so it must be fetched immediately, in the same call.
		resp = self._request(
			"GET",
			# Same trailing-slash-before-query-string quirk as document/details.
			"/v3.3/document/fetchDocument/",
			cfg["base_url"],
			params={"documentId": provider_request_id, "documentDownloadType": "DOCUMENT"},
		)
		payload = resp.json()
		if payload.get("status") != 1:
			# Leegality returns HTTP 200 with a JSON error body (status: 0)
			# on failure instead of a real error status code — e.g.
			# "no.document.found" if signing isn't complete yet.
			raise EsignProviderError(
				f"Leegality fetchDocument rejected for {provider_request_id}: {payload}"
			)
		cdn_url = (payload.get("data") or {}).get("file")
		if not cdn_url:
			raise EsignProviderError(
				f"Leegality fetchDocument response missing data.file for {provider_request_id}: {payload}"
			)
		# The CDN URL is itself pre-signed — no X-Auth-Token needed/wanted here.
		cdn_resp = requests.get(cdn_url, timeout=_REQUEST_TIMEOUT_SECONDS)
		if cdn_resp.status_code >= 400:
			raise EsignProviderError(
				f"Leegality CDN download failed for {provider_request_id} "
				f"(likely expired 15s URL): {cdn_resp.status_code}"
			)
		return cdn_resp.content

	def verify_and_parse_webhook(self, headers: dict, raw_body: bytes) -> WebhookEvent | None:
		cfg = _get_config()
		try:
			payload = json.loads(raw_body.decode("utf-8"))
		except (ValueError, UnicodeDecodeError):
			frappe.log_error(title="leegality.webhook", message="Leegality webhook body not valid JSON")
			return None

		# documentId can be top-level (older/error-webhook shape) or nested
		# under document.documentId (v2.5 success-webhook shape) — handle
		# both rather than assume one schema, since Leegality's own example
		# payloads use different shapes for success vs. error webhooks.
		doc_id = payload.get("documentId") or (payload.get("document") or {}).get("documentId")
		mac = payload.get("mac")
		if not doc_id or not mac:
			frappe.log_error(
				title="leegality.webhook", message="Leegality webhook missing documentId or mac"
			)
			return None

		expected_mac = hmac.new(
			cfg["private_salt"].encode("utf-8"), doc_id.encode("utf-8"), hashlib.sha1
		).hexdigest()
		if not hmac.compare_digest(expected_mac, mac):
			frappe.log_error(title="leegality.webhook", message="Leegality webhook mac mismatch")
			return None

		event_type = self._normalize_event(payload)
		if not event_type:
			# 300 chars previously truncated a real unrecognized shape mid-way,
			# during a live signature, before it could be diagnosed — this
			# genuinely cost a wasted signing fee. message has no length cap.
			frappe.log_error(
				title="leegality.webhook",
				message=f"Leegality webhook unrecognized shape: {json.dumps(payload)[:3000]}",
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

		# Third real shape, confirmed live against an actual completed
		# Aadhaar eSign on this Workflow (not in Leegality's own example
		# docs — their examples don't cover every shape they actually
		# send): no top-level eventType/webhookType at all, just
		# request.action as a capitalized human-readable string.
		request = payload.get("request") or {}
		action = (request.get("action") or "").strip().lower()
		if action == "signed":
			return "signed"
		if action in ("rejected", "declined"):
			return "failed"
		if request.get("expired") or action == "expired":
			return "expired"

		return None


def _mask_phone(phone: str | None) -> str | None:
	if not phone or len(phone) < 4:
		return phone
	return f"{phone[:2]}{'*' * (len(phone) - 4)}{phone[-2:]}"
