"""
eSign provider adapter interface.

Every Aadhaar-eSign vendor (SignYu, Leegality, Digio, ...) has its own wire
format, but the platform only ever needs the five operations below. New
provider = one new adapter file implementing this interface; nothing in
`api/esign.py` or the `Signed Agreement` doctype changes.

This is deliberate, not over-engineering: we're deploying against SignYu
first (cheapest, pay-per-use, zero commitment — see the vendor comparison
in project notes) but expect to move to a negotiated Leegality/Digio
contract once signing volume justifies it, per the "start cheap, graduate
to enterprise" plan. Nothing downstream should need to know which one is
live at any given time.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from typing import Optional


@dataclasses.dataclass
class SigningRequestResult:
	"""Returned by create_signing_request()."""

	provider_request_id: str
	# None when the provider pushes the signing link directly to the
	# signer (e.g. over WhatsApp) rather than handing us a URL to embed —
	# that's the delivery mode we use, per the no-email requirement.
	signing_url: Optional[str]
	raw: dict


@dataclasses.dataclass
class StatusResult:
	provider_request_id: str
	# Normalized onto the same values as Signed Agreement.status:
	# "Link Sent" | "Viewed" | "Signed" | "Failed" | "Expired"
	status: str
	signed_at: Optional[str] = None
	raw: Optional[dict] = None


@dataclasses.dataclass
class WebhookEvent:
	provider_request_id: str
	event_type: str  # normalized: "viewed" | "signed" | "failed" | "expired"
	signer_phone_masked: Optional[str] = None
	signer_ip: Optional[str] = None
	aadhaar_last4: Optional[str] = None
	e_stamp_certificate_number: Optional[str] = None
	e_stamp_duty_amount: Optional[float] = None
	raw: Optional[dict] = None


class EsignProviderError(Exception):
	"""Raised for any provider-side failure — network, auth, rejected
	request. Callers (api/esign.py) catch this and flip the Signed
	Agreement row to Failed rather than letting a provider outage surface
	as an unhandled 500 on a customer/merchant-facing endpoint."""


class EsignAdapter(ABC):
	"""One instance per provider. `flamezo/esign/__init__.py::get_adapter()`
	is the only place that should construct one."""

	#: Must match one of Agreement Template.esign_provider's options.
	provider_key: str

	@abstractmethod
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
		"""Upload the rendered agreement PDF and register a signer against
		it. The provider is expected to deliver the signing link to
		`signer_phone` over WhatsApp — never email. Must raise
		EsignProviderError on any failure; must never return a partial/
		ambiguous result.

		`profile_id` is Leegality's Workflow ID (their WhatsApp-delivery +
		Aadhaar-signature-type + webhook-URL configuration lives on the
		Workflow, not per-request — see Agreement Template.leegality_profile_id).
		Adapters that don't need it (e.g. SignYu) simply ignore it."""

	@abstractmethod
	def get_request_status(self, provider_request_id: str) -> StatusResult:
		"""Polled by the reconciliation job (see tasks/esign_tasks.py) for
		any request that's been sitting in Link Sent/Viewed longer than
		expected — the same self-heal pattern used elsewhere in this
		codebase for stuck jobs, rather than trusting webhooks alone."""

	@abstractmethod
	def download_signed_document(self, provider_request_id: str) -> bytes:
		"""Returns the final signed (and e-stamped, if requested) PDF
		bytes. Only valid once get_request_status() reports "Signed"."""

	@abstractmethod
	def verify_and_parse_webhook(
		self, headers: dict, raw_body: bytes
	) -> Optional[WebhookEvent]:
		"""Verify the request actually came from the provider (HMAC or
		equivalent) and normalize its payload. Returns None — never raises
		— for a signature that fails verification, so the caller can log
		and 200-ack without processing it (never leak *why* verification
		failed to the caller)."""
