# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Scheduled safety net for the agreement-signing flow.

Webhooks are the primary signal, but a provider outage, a missed delivery,
or a signer who opens the link and never finishes leaves a Signed Agreement
sitting in Link Sent/Viewed indefinitely with no event ever arriving. This
sweep polls the provider directly for anything stale — same self-heal
pattern as tasks/extraction_recovery.py — rather than trusting webhooks
alone to eventually show up.
"""

import frappe
from frappe.utils import now_datetime

from flamezo_backend.flamezo.esign import get_adapter
from flamezo_backend.flamezo.esign.base import EsignProviderError

# Anything still Link Sent/Viewed and untouched for this long gets an
# active status check instead of waiting further on a webhook.
_STALE_AFTER_MINUTES = 60


def reconcile_stalled_esign_requests():
	stale_cutoff = frappe.utils.add_to_date(now_datetime(), minutes=-_STALE_AFTER_MINUTES)

	stalled = frappe.get_all(
		"Signed Agreement",
		filters={
			"status": ["in", ["Link Sent", "Viewed"]],
			"modified": ["<", stale_cutoff],
			"esign_provider": ["!=", "clickwrap"],
		},
		fields=["name", "esign_provider", "provider_request_id", "expires_at"],
	)

	for row in stalled:
		if not row.provider_request_id:
			continue
		try:
			adapter = get_adapter(row.esign_provider)
			result = adapter.get_request_status(row.provider_request_id)
		except (EsignProviderError, ValueError) as e:
			frappe.log_error(
				title="esign.reconcile",
				message=f"esign reconcile: status check failed for {row.name}: {e}",
			)
			continue

		if result.status == frappe.db.get_value("Signed Agreement", row.name, "status"):
			# No change — but if the link has also hard-expired by our own
			# clock, flip it so it stops being swept every cycle.
			if row.expires_at and row.expires_at < now_datetime():
				frappe.db.set_value("Signed Agreement", row.name, "status", "Expired")
				frappe.db.commit()
			continue

		if result.status == "Signed":
			# Route through the same webhook handler logic (download +
			# upload + hash + immutability), don't duplicate it here.
			_apply_signed_via_status_poll(row.name, adapter, row.provider_request_id)
		else:
			frappe.db.set_value("Signed Agreement", row.name, "status", result.status)
			frappe.db.commit()


def _apply_signed_via_status_poll(signed_agreement_name, adapter, provider_request_id):
	import hashlib

	from flamezo_backend.flamezo.media import storage as r2_storage

	try:
		signed_pdf_bytes = adapter.download_signed_document(provider_request_id)
	except EsignProviderError as e:
		frappe.log_error(
			title="esign.reconcile",
			message=f"esign reconcile: signed doc download failed for {signed_agreement_name}: {e}",
		)
		return

	row = frappe.get_doc("Signed Agreement", signed_agreement_name)
	object_key = f"agreements/{row.party_doctype}/{row.party}/{row.name}.pdf"
	cdn_url = r2_storage.upload_bytes(object_key, signed_pdf_bytes, content_type="application/pdf")
	row.signed_pdf = cdn_url
	row.signed_pdf_hash = hashlib.sha256(signed_pdf_bytes).hexdigest()
	row.status = "Signed"
	row.signed_at = now_datetime()
	row.last_webhook_event = "reconciled_via_poll"
	row.last_webhook_at = now_datetime()
	row.save(ignore_permissions=True)
	frappe.db.commit()
