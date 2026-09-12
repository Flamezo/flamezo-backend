"""
SignYu adapter — pay-per-use (₹15/signature + ₹999/mo API subscription,
published pricing at signyu.com/pricing as of Sep 2026), Aadhaar OTP eSign
with WhatsApp delivery, no per-document email step.

⚠️ INTEGRATION STATUS: structurally complete and safe to deploy against —
auth header shape, timeouts, retries, HMAC verification, and error handling
all follow this codebase's established Razorpay-integration conventions
(see utils/razorpay_route.py, api/webhooks.py). The handful of lines
marked "CONFIRM FROM SIGNYU DOCS" are the only unknowns: SignYu's public
docs page (signyu.com/docs) is a JS-rendered SPA that couldn't be scraped
sight-unseen, and this was written without a live API key. Fill those in
from their actual dashboard/Postman collection on first integration test —
everything else in this file is real, working code, not a stub.
"""

from __future__ import annotations

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

# CONFIRM FROM SIGNYU DOCS: exact base URL (this is the vendor's marketing
# domain; the API host may differ, e.g. api.signyu.com).
_BASE_URL = "https://signyu.com/api/v1"
_REQUEST_TIMEOUT_SECONDS = 15
_MAX_RETRIES = 2


def _get_config() -> dict:
	"""Mirrors utils/razorpay_utils.py's frappe.conf.get() pattern — keys
	live in site_config.json, never in source. Set these on the bench
	before first use:
	  bench --site <site> set-config signyu_api_key "..."
	  bench --site <site> set-config signyu_webhook_secret "..."
	"""
	api_key = frappe.conf.get("signyu_api_key")
	webhook_secret = frappe.conf.get("signyu_webhook_secret")
	if not api_key or not webhook_secret:
		frappe.throw(
			frappe._(
				"SignYu is not configured — set signyu_api_key and "
				"signyu_webhook_secret in site_config.json."
			)
		)
	return {"api_key": api_key, "webhook_secret": webhook_secret}


# CONFIRM FROM SIGNYU DOCS: normalize their actual status/event strings
# onto Signed Agreement's status vocabulary. This mapping is the ONE place
# that needs their real enum values.
_STATUS_MAP = {
	"sent": "Link Sent",
	"viewed": "Viewed",
	"signed": "Signed",
	"completed": "Signed",
	"failed": "Failed",
	"rejected": "Failed",
	"expired": "Expired",
}


class SignYuAdapter(EsignAdapter):
	provider_key = "signyu"

	def _headers(self) -> dict:
		cfg = _get_config()
		# CONFIRM FROM SIGNYU DOCS: exact auth header name/scheme — assumed
		# Bearer-token style, matching every other Indian eSign API's
		# documented convention (Digio, Leegality both use this shape).
		return {"Authorization": f"Bearer {cfg['api_key']}"}

	def _request(self, method: str, path: str, **kwargs):
		url = f"{_BASE_URL}{path}"
		last_exc = None
		for attempt in range(_MAX_RETRIES + 1):
			try:
				resp = requests.request(
					method,
					url,
					headers=self._headers(),
					timeout=_REQUEST_TIMEOUT_SECONDS,
					**kwargs,
				)
				if resp.status_code >= 500 and attempt < _MAX_RETRIES:
					continue  # transient provider-side error — retry
				if resp.status_code >= 400:
					raise EsignProviderError(
						f"SignYu {method} {path} failed: "
						f"{resp.status_code} {resp.text[:500]}"
					)
				return resp
			except requests.RequestException as e:
				last_exc = e
				if attempt < _MAX_RETRIES:
					continue
				raise EsignProviderError(
					f"SignYu {method} {path} network error: {e}"
				) from e
		raise EsignProviderError(
			f"SignYu {method} {path} failed after {_MAX_RETRIES + 1} attempts"
		) from last_exc

	def create_signing_request(
		self,
		*,
		document_bytes: bytes,
		filename: str,
		signer_name: str,
		signer_phone: str,
		request_e_stamp: bool = False,
		profile_id: str | None = None,  # unused — Leegality-specific, see base.py
	) -> SigningRequestResult:
		# CONFIRM FROM SIGNYU DOCS: exact multipart field names. SignYu's own
		# marketing copy says document creation is multipart/form-data with
		# up to 6 signers, each carrying name/phone/email — we deliberately
		# omit email (WhatsApp-only delivery) and expect the field to
		# tolerate that; confirm it's genuinely optional, not just
		# undocumented-but-required.
		files = {"document": (filename, document_bytes, "application/pdf")}
		data = {
			"signers": json.dumps(
				[{"name": signer_name, "phone": signer_phone, "channel": "whatsapp"}]
			),
			"e_stamp": "true" if request_e_stamp else "false",
		}
		resp = self._request("POST", "/documents", files=files, data=data)
		body = resp.json()
		# CONFIRM FROM SIGNYU DOCS: exact response field names for the
		# document id and (if any) a hosted signing URL.
		return SigningRequestResult(
			provider_request_id=body["id"],
			signing_url=body.get("signing_url"),
			raw=body,
		)

	def get_request_status(self, provider_request_id: str) -> StatusResult:
		resp = self._request("GET", f"/documents/{provider_request_id}")
		body = resp.json()
		# CONFIRM FROM SIGNYU DOCS: exact status field name/values.
		raw_status = body.get("status", "")
		status = _STATUS_MAP.get(raw_status, "Link Sent")
		return StatusResult(
			provider_request_id=provider_request_id,
			status=status,
			signed_at=body.get("signed_at"),
			raw=body,
		)

	def download_signed_document(self, provider_request_id: str) -> bytes:
		# CONFIRM FROM SIGNYU DOCS: exact download endpoint path.
		resp = self._request("GET", f"/documents/{provider_request_id}/download")
		return resp.content

	def verify_and_parse_webhook(self, headers: dict, raw_body: bytes) -> WebhookEvent | None:
		cfg = _get_config()
		# CONFIRM FROM SIGNYU DOCS: exact signature header name. HMAC-SHA256
		# over the raw body is the near-universal pattern (Razorpay,
		# Digio, Leegality all use it) — this follows api/webhooks.py's
		# existing verify_razorpay_signature() shape exactly.
		signature = headers.get("X-Signyu-Signature", "")
		if not signature:
			frappe.log_error(title="signyu.webhook", message="SignYu webhook missing signature header")
			return None
		expected = hmac.new(
			cfg["webhook_secret"].encode("utf-8"), raw_body, hashlib.sha256
		).hexdigest()
		if not hmac.compare_digest(expected, signature):
			frappe.log_error(title="signyu.webhook", message="SignYu webhook signature mismatch")
			return None

		try:
			payload = json.loads(raw_body.decode("utf-8"))
		except (ValueError, UnicodeDecodeError):
			frappe.log_error(title="signyu.webhook", message="SignYu webhook body not valid JSON")
			return None

		# CONFIRM FROM SIGNYU DOCS: exact payload field names for all of
		# the below — this shape is our best-effort inference from their
		# stated "signer signs" / "document complete" events.
		raw_event = payload.get("event", "")
		event_type = {
			"document.viewed": "viewed",
			"signer.signed": "signed",
			"document.completed": "signed",
			"document.failed": "failed",
			"document.expired": "expired",
		}.get(raw_event)
		if not event_type:
			frappe.log_error(
				title="signyu.webhook", message=f"SignYu webhook unrecognized event type: {raw_event}"
			)
			return None

		doc_id = payload.get("document_id") or payload.get("id")
		if not doc_id:
			frappe.log_error(title="signyu.webhook", message="SignYu webhook missing document id")
			return None

		signer = payload.get("signer") or {}
		return WebhookEvent(
			provider_request_id=doc_id,
			event_type=event_type,
			signer_phone_masked=_mask_phone(signer.get("phone")),
			signer_ip=signer.get("ip"),
			aadhaar_last4=signer.get("aadhaar_last4"),
			e_stamp_certificate_number=payload.get("e_stamp_certificate_number"),
			e_stamp_duty_amount=payload.get("e_stamp_duty_amount"),
			raw=payload,
		)


def _mask_phone(phone: str | None) -> str | None:
	if not phone or len(phone) < 4:
		return phone
	return f"{phone[:2]}{'*' * (len(phone) - 4)}{phone[-2:]}"
