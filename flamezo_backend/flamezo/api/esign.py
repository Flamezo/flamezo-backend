"""
Agreement signing — Merchant Partnership Agreement, Creator Marketplace
Agreement (Aadhaar eSign via a pluggable provider, WhatsApp delivery, no
email anywhere in the flow) and Customer Terms of Service (in-app
clickwrap, no external provider at all).

Every party type authenticates the way the rest of this codebase already
authenticates it — Outlet via a real Frappe session + Outlet User mapping
(merchant dashboard), Flamezo Creator / Customer via the X-Customer-Token
session (mirrors crowd.py/chills.py's _require_session pattern) — this
module doesn't invent a new auth model.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from flamezo_backend.flamezo.esign import get_adapter
from flamezo_backend.flamezo.esign.base import EsignProviderError
from flamezo_backend.flamezo.media import storage as r2_storage
from flamezo_backend.flamezo.utils.customer_helpers import has_active_customer_session

_VALID_PARTY_DOCTYPES = {"Customer", "Outlet", "Flamezo Creator"}

# How long a Link Sent/Viewed request is given before the reconciliation
# job (tasks/esign_tasks.py) treats it as stalled and polls the provider
# directly instead of waiting on a webhook that may never arrive.
_LINK_EXPIRY_DAYS = 7


# ── auth ─────────────────────────────────────────────────────────────────

def _authorize_party(party_doctype, party_name, phone=None):
	"""Confirms the caller is actually allowed to act on this party record.
	Raises frappe.PermissionError otherwise. Never trust a client-supplied
	party_name without checking it against who's actually calling."""
	if party_doctype not in _VALID_PARTY_DOCTYPES:
		frappe.throw(_("Invalid party_doctype: {0}").format(party_doctype))

	if party_doctype == "Outlet":
		if frappe.session.user in ("Guest", None):
			frappe.throw(_("Sign in required"), frappe.AuthenticationError)
		if frappe.session.user == "Administrator":
			return
		is_mapped = frappe.db.exists(
			"Outlet User",
			{"outlet": party_name, "user": frappe.session.user, "is_active": 1},
		)
		if not is_mapped:
			frappe.throw(
				_("You are not authorized to sign for this outlet."),
				frappe.PermissionError,
			)
		return

	# Customer / Flamezo Creator — X-Customer-Token session, keyed by phone.
	if not phone:
		frappe.throw(_("phone is required"), frappe.AuthenticationError)
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)

	phone_field = "phone" if party_doctype == "Customer" else "customer_phone"
	owner_phone = frappe.db.get_value(party_doctype, party_name, phone_field)
	if owner_phone != phone:
		frappe.throw(
			_("You are not authorized to sign for this account."),
			frappe.PermissionError,
		)


def _signer_display_name(party_doctype, party_name):
	field = {
		"Outlet": "legal_name",
		"Flamezo Creator": "display_name",
		"Customer": "customer_name",
	}[party_doctype]
	name = frappe.db.get_value(party_doctype, party_name, field)
	return name or party_name


def _signer_phone(party_doctype, party_name):
	field = "owner_phone" if party_doctype == "Outlet" else (
		"customer_phone" if party_doctype == "Flamezo Creator" else "phone"
	)
	return frappe.db.get_value(party_doctype, party_name, field) or ""


# ── template rendering & commercial-terms snapshot ──────────────────────

def _build_schedule_snapshot(party_doctype, party_name):
	"""Freezes the commercial values that matter for this specific document
	at the moment of signing — Schedule A/B can change later under
	Section 4.4 / 24.5 of the Agreement, but this snapshot must remain
	provable as exactly what this party agreed to."""
	if party_doctype == "Outlet":
		from flamezo_backend.flamezo.utils.ifsc_lookup import format_bank_name_branch

		row = frappe.db.get_value(
			"Outlet",
			party_name,
			["legal_name", "outlet_name", "address", "gst_number", "pan_number",
				"bank_account_number", "bank_ifsc"],
			as_dict=True,
		) or {}
		return {
			"success_share_web_pct": 0,
			"success_share_app_pct": 7,
			"tcs_pct": 0.5,
			**row,
			# Merge-field names used in the Schedule A template — mapped from
			# the Outlet fields actually captured today. bank_name_branch is
			# auto-derived from the IFSC the merchant already gave during
			# Route KYC (see utils/ifsc_lookup.py) rather than asking for a
			# second input — blank only if the lookup genuinely fails.
			"trade_name": row.get("outlet_name"),
			"registered_address": row.get("address"),
			"bank_name_branch": format_bank_name_branch(row.get("bank_ifsc")),
		}
	if party_doctype == "Flamezo Creator":
		return {"marketplace_fee_pct": 10, "review_period_days": 5, "auto_release": True}
	return {}


def _render_agreement_pdf(template_doc, party_doctype, party_name):
	"""Merges party-specific fields into the active Agreement Template's
	source and renders a fresh PDF. Returns (pdf_bytes, sha256_hex).

	template_file is Markdown source with {{merge_field}} placeholders (the
	same source FlameZO_Merchant_Agreement_v2.2.pdf was hand-built from) —
	not a pre-rendered PDF/DOCX. Pipeline: merge -> Markdown -> HTML ->
	wkhtmltopdf, via utils/agreement_pdf.py (wkhtmltopdf is a core Frappe
	dependency already present on every bench, no extra install needed).
	"""
	from flamezo_backend.flamezo.utils.agreement_pdf import (
		embed_static_stamps,
		merge_fields,
		render_markdown_to_pdf,
	)

	file_doc = frappe.get_doc("File", {"file_url": template_doc.template_file})
	content = file_doc.get_content()
	if isinstance(content, bytes):
		content = content.decode("utf-8")
	content = embed_static_stamps(content)

	values = _build_schedule_snapshot(party_doctype, party_name)
	values.setdefault("signer_name", _signer_display_name(party_doctype, party_name))
	merged_text, unresolved = merge_fields(content, values)
	if unresolved:
		# Not fatal — a genuinely unregistered dealer has no GST number,
		# for instance — but worth a visible trail per document rather than
		# silently shipping blanks. title= is capped at 140 chars and comes
		# FIRST in this Frappe version's log_error(title, message) — the
		# unbounded dynamic text must go in message=, not title=.
		frappe.log_error(
			title="esign.render: unresolved merge fields",
			message=f"Agreement merge for {party_doctype} {party_name}: unresolved "
			f"fields left blank: {sorted(set(unresolved))}",
		)

	pdf_bytes = render_markdown_to_pdf(merged_text)
	digest = hashlib.sha256(pdf_bytes).hexdigest()
	return pdf_bytes, digest


# ── initiate signing ─────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["POST"])
def initiate_agreement_signing(party_doctype, party_name, agreement_type, phone=None):
	"""Entry point for the app (Flamezo Creator) or a future merchant
	self-service flow. Merchant-side signing today is admin-triggered from
	Merchant Management (see admin_initiate_agreement_signing) — the
	Outlet auth branch of _authorize_party stays in place below since a
	future merchant-facing "Sign Agreement" screen would need it, but
	nothing calls this for Outlet yet."""
	_authorize_party(party_doctype, party_name, phone)
	return _initiate_agreement_signing_core(party_doctype, party_name, agreement_type)


def _initiate_agreement_signing_core(party_doctype, party_name, agreement_type):
	"""Shared by the (future) self-service entry point above and the
	admin-triggered one below — renders the active Agreement Template,
	sends it to the configured eSign provider, and returns the new Signed
	Agreement's name for the caller to poll. Caller is responsible for
	authorization before calling this."""
	template_doc = frappe.db.get_value(
		"Agreement Template",
		{"agreement_type": agreement_type, "is_active": 1},
		"name",
	)
	if not template_doc:
		frappe.throw(_("No active Agreement Template for {0}").format(agreement_type))
	template_doc = frappe.get_doc("Agreement Template", template_doc)

	existing = frappe.db.get_value(
		"Signed Agreement",
		{
			"party_doctype": party_doctype,
			"party": party_name,
			"agreement_template": template_doc.name,
			"status": ["in", ["Link Sent", "Viewed", "Signed"]],
		},
		"name",
	)
	if existing:
		return {"success": True, "data": {"signed_agreement": existing, "already_exists": True}}

	if not template_doc.requires_esign:
		frappe.throw(
			_("{0} does not require eSign — use record_clickwrap_acceptance instead.").format(
				agreement_type
			)
		)

	pdf_bytes, doc_hash = _render_agreement_pdf(template_doc, party_doctype, party_name)
	snapshot = _build_schedule_snapshot(party_doctype, party_name)
	signer_name = _signer_display_name(party_doctype, party_name)
	signer_phone = _signer_phone(party_doctype, party_name)
	if not signer_phone:
		frappe.throw(_("No phone number on file for {0} {1}").format(party_doctype, party_name))

	row = frappe.get_doc({
		"doctype": "Signed Agreement",
		"agreement_template": template_doc.name,
		"agreement_type": agreement_type,
		"agreement_version": template_doc.version,
		"party_doctype": party_doctype,
		"party": party_name,
		"status": "Draft",
		"agreement_document_hash": doc_hash,
		"schedule_snapshot": json.dumps(snapshot),
		"esign_provider": template_doc.esign_provider,
		"expires_at": add_days(now_datetime(), _LINK_EXPIRY_DAYS),
	})
	row.insert(ignore_permissions=True)

	adapter = get_adapter(template_doc.esign_provider)
	try:
		result = adapter.create_signing_request(
			document_bytes=pdf_bytes,
			filename=f"{agreement_type}-{party_name}.pdf",
			signer_name=signer_name,
			signer_phone=signer_phone,
			request_e_stamp=bool(template_doc.e_stamp_required),
			profile_id=template_doc.get("leegality_profile_id"),
		)
	except EsignProviderError as e:
		row.status = "Failed"
		row.save(ignore_permissions=True)
		frappe.log_error(title="esign.initiate", message=f"eSign initiate failed for {row.name}: {e}")
		frappe.throw(_("Could not start the signing process. Please try again shortly."))

	row.provider_request_id = result.provider_request_id
	row.signing_url = result.signing_url
	row.status = "Link Sent"
	row.initiated_at = now_datetime()
	row.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"success": True,
		"data": {
			"signed_agreement": row.name,
			"status": row.status,
			"signing_url": row.signing_url,  # None for pure WhatsApp-push delivery
		},
	}


@frappe.whitelist(allow_guest=True)
def get_agreement_status(signed_agreement):
	doc = frappe.db.get_value(
		"Signed Agreement",
		signed_agreement,
		["status", "agreement_type", "agreement_version", "signed_at"],
		as_dict=True,
	)
	if not doc:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	return {"success": True, "data": doc}


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


# ── admin-triggered signing (Merchant Management) ────────────────────────

@frappe.whitelist(methods=["POST"])
def admin_initiate_agreement_signing(outlet_id, agreement_type="Merchant Partnership Agreement"):
	"""Merchant Management's "Send for Signing" action. FlameZO staff, not
	the merchant, triggers this — the merchant only ever sees the Leegality
	Aadhaar eSign link that arrives by SMS. Requires System Manager, same
	gate as the other admin-only actions in api/commission.py."""
	_require_system_manager()
	if not frappe.db.exists("Outlet", outlet_id):
		frappe.throw(_("Outlet {0} not found").format(outlet_id))
	return _initiate_agreement_signing_core("Outlet", outlet_id, agreement_type)


@frappe.whitelist()
def admin_get_agreement_status(outlet_id, agreement_type="Merchant Partnership Agreement"):
	"""Latest Signed Agreement (if any) for this Outlet + agreement type —
	lets Merchant Management show current status without the frontend
	needing to already know a specific Signed Agreement name."""
	_require_system_manager()
	doc = frappe.db.get_value(
		"Signed Agreement",
		{"party_doctype": "Outlet", "party": outlet_id, "agreement_type": agreement_type},
		["name", "status", "agreement_version", "signing_url", "initiated_at", "signed_at", "expires_at"],
		as_dict=True,
		order_by="creation desc",
	)
	return {"success": True, "data": doc}


# ── clickwrap (Customer Terms of Service) ────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["POST"])
def record_clickwrap_acceptance(phone):
	"""Customer ToS acceptance — no provider call, no PDF, no signature.
	Just an immutable, timestamped, versioned acceptance record. This is
	deliberately the cheap tier — see project notes on why clickwrap is
	legally sufficient here and eSign is reserved for Merchant/Creator."""
	if not has_active_customer_session(phone):
		frappe.throw(_("Please verify your phone to continue."), frappe.AuthenticationError)

	template_name = frappe.db.get_value(
		"Agreement Template",
		{"agreement_type": "Customer Terms of Service", "is_active": 1},
		"name",
	)
	if not template_name:
		frappe.throw(_("No active Customer Terms of Service template configured"))
	template_doc = frappe.get_doc("Agreement Template", template_name)

	customer_id = frappe.db.get_value("Customer", {"phone": phone}, "name")
	if not customer_id:
		frappe.throw(_("Customer record not found"), frappe.DoesNotExistError)

	existing = frappe.db.exists(
		"Signed Agreement",
		{
			"party_doctype": "Customer",
			"party": customer_id,
			"agreement_template": template_name,
			"status": "Signed",
		},
	)
	if existing:
		return {"success": True, "data": {"signed_agreement": existing, "already_accepted": True}}

	try:
		signer_ip = frappe.request.remote_addr
	except Exception:
		signer_ip = None

	row = frappe.get_doc({
		"doctype": "Signed Agreement",
		"agreement_template": template_name,
		"agreement_type": "Customer Terms of Service",
		"agreement_version": template_doc.version,
		"party_doctype": "Customer",
		"party": customer_id,
		"status": "Draft",
		"agreement_document_hash": template_doc.template_file_hash,
		"esign_provider": "clickwrap",
		"signer_phone_masked": f"{phone[:2]}{'*' * max(len(phone) - 4, 0)}{phone[-2:]}",
		"signer_ip": signer_ip,
	})
	row.insert(ignore_permissions=True)
	row.status = "Signed"
	row.signed_at = now_datetime()
	row.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"signed_agreement": row.name}}


# ── webhook ──────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["POST"])
def esign_webhook(provider):
	"""One URL per provider: /api/method/flamezo_backend.flamezo.api.esign.esign_webhook?provider=signyu
	Idempotent on (provider_request_id, event_type) — a redelivered webhook
	for an event already applied is a silent no-op, matching the
	Razorpay Webhook Log pattern already used elsewhere in this codebase."""
	request = frappe.local.request
	raw_body = request.get_data()
	headers = dict(request.headers)

	try:
		adapter = get_adapter(provider)
	except ValueError:
		frappe.log_error(title="esign.webhook", message=f"eSign webhook for unknown provider: {provider}")
		# 200 regardless — never give an unauthenticated caller a signal
		# about which provider keys are/aren't configured.
		return {"success": True}

	event = adapter.verify_and_parse_webhook(headers, raw_body)
	if not event:
		return {"success": True}

	row_name = frappe.db.get_value(
		"Signed Agreement", {"provider_request_id": event.provider_request_id}, "name"
	)
	if not row_name:
		frappe.log_error(
			title="esign.webhook",
			message=f"eSign webhook for unknown provider_request_id: {event.provider_request_id}",
		)
		return {"success": True}

	row = frappe.get_doc("Signed Agreement", row_name)

	# Idempotency guard: a re-delivered "signed" event for an already-Signed
	# row is a no-op, not an error — webhook redelivery is normal, expected
	# provider behaviour, not a bug.
	if row.status == "Signed" and event.event_type == "signed":
		return {"success": True}

	if event.event_type == "viewed" and row.status == "Link Sent":
		row.status = "Viewed"
		row.viewed_at = now_datetime()

	elif event.event_type == "signed":
		try:
			signed_pdf_bytes = adapter.download_signed_document(event.provider_request_id)
		except EsignProviderError as e:
			frappe.log_error(
				title="esign.webhook", message=f"Could not download signed PDF for {row.name}: {e}"
			)
			# Don't flip to Signed without the durable copy in hand — leave
			# status as-is; the reconciliation job will retry the download.
			return {"success": True}

		object_key = f"agreements/{row.party_doctype}/{row.party}/{row.name}.pdf"
		cdn_url = r2_storage.upload_bytes(object_key, signed_pdf_bytes, content_type="application/pdf")
		row.signed_pdf = cdn_url
		row.signed_pdf_hash = hashlib.sha256(signed_pdf_bytes).hexdigest()
		row.signer_phone_masked = event.signer_phone_masked
		row.signer_ip = event.signer_ip
		row.aadhaar_last4 = event.aadhaar_last4
		row.e_stamp_certificate_number = event.e_stamp_certificate_number
		row.e_stamp_duty_amount = event.e_stamp_duty_amount
		row.status = "Signed"
		row.signed_at = now_datetime()

	elif event.event_type in ("failed", "expired"):
		row.status = "Failed" if event.event_type == "failed" else "Expired"

	row.last_webhook_event = event.event_type
	row.last_webhook_at = now_datetime()
	row.webhook_raw_payload = json.dumps(_redact(event.raw or {}))
	row.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True}


def _redact(payload: dict) -> dict:
	"""Defence-in-depth: strip any key that looks like it could carry a raw
	Aadhaar number or other high-sensitivity PII before this payload is
	persisted for audit purposes. Never trust a provider to have already
	redacted its own webhook body."""
	_DENY_KEYS = {"aadhaar", "aadhaar_number", "uid", "otp", "biometric"}
	if not isinstance(payload, dict):
		return payload
	return {
		k: (_redact(v) if isinstance(v, dict) else v)
		for k, v in payload.items()
		if k.lower() not in _DENY_KEYS
	}
