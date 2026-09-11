"""
Real Instagram delivery verification (creator-marketplace-blueprint.html
§06). Closes the gap `api/collab_deals.py::mark_delivered` deliberately
left open — an Instagram deliverable claim is recorded as
`Delivery Proof(verification_method="manual")` and the deal stays put;
this module is the polling job that actually confirms it, the same way
`_verify_native_deliverable` confirms a native one synchronously.

Uses "Instagram API with Instagram Login" (graph.instagram.com) — same
API family already live in api/creator_onboarding.py, not the older
Facebook-Graph-API Business Discovery (which needs a linked FB Page on
the OUTLET's side that nothing in this codebase collects). Fetches the
SPECIFIC media the creator already claimed (the `instagram_media_id`
mark_delivered stored) by ID, rather than paging /me/media and pattern
-matching — precise, and avoids missing a claim that's fallen off the
first page of recent media by the time the job runs.

Verified against real 2026 API behaviour before writing this (not
assumed): `instagram_business_basic` is sufficient for `GET
/{media-id}?fields=caption,timestamp,permalink,username`
on a Business/Creator account's own media — no extra scope needed
beyond what onboarding already requires. Genuinely cannot be
live-tested without a real Meta Developer App + real connected
creator/outlet accounts (same honest limitation every other Graph API
call in this codebase has) — the HTTP call shape and response parsing
are real; only live credentials are pending.
"""

import re

import requests

import frappe
from frappe.utils import add_days, getdate, now_datetime

from flamezo_backend.flamezo.api.creator_onboarding import get_valid_access_token

MEDIA_URL = "https://graph.instagram.com/{media_id}"
DISCLOSURE_TAGS = {"#ad", "#sponsored", "#promotion", "#paidpartnership"}
# How far past a deal's acceptance a claimed post is still considered
# plausible for — generous on purpose (a creator might post the day
# before their formal deadline, or a few days after visiting); this is
# a sanity check against a wildly mismatched/reused claim, not a tight
# SLA window (the deal's own `deadline` field already enforces timing
# at the mark_delivered step).
CLAIM_WINDOW_DAYS_BEFORE = 3
CLAIM_WINDOW_DAYS_AFTER = 14


def _extract_handle(instagram_url: str) -> str:
	"""'https://instagram.com/spice.route.cafe/' / '@spice.route.cafe' /
	'spice.route.cafe' all resolve to the bare handle, lowercased."""
	if not instagram_url:
		return ""
	handle = instagram_url.strip()
	handle = re.sub(r"^https?://(www\.)?instagram\.com/", "", handle, flags=re.IGNORECASE)
	handle = handle.strip("/").lstrip("@")
	handle = handle.split("/")[0].split("?")[0]
	return handle.lower()


def caption_mentions_handle(caption: str, handle: str) -> bool:
	if not caption or not handle:
		return False
	return f"@{handle}".lower() in caption.lower()


def caption_has_disclosure_tag(caption: str) -> bool:
	"""ASCI-required paid-content disclosure (blueprint §06's table) — a
	tag word anywhere in the caption, not required to be a specific
	position (Instagram captions don't support the same auto-injected
	overlay the native upload flow uses, so this is the best available
	check on this platform)."""
	if not caption:
		return False
	lowered = caption.lower()
	return any(tag in lowered for tag in DISCLOSURE_TAGS)


def fetch_media_detail(access_token: str, media_id: str) -> dict:
	"""Real Graph API call. Returns the raw response dict — caller checks
	for an 'error' key (Meta's error shape) rather than this function
	raising, since 'the post was deleted' / 'token expired mid-flight' are
	expected outcomes a polling job must handle gracefully, not crash on."""
	url = MEDIA_URL.format(media_id=media_id)
	resp = requests.get(
		url, params={"fields": "caption,timestamp,permalink,username", "access_token": access_token}, timeout=20,
	)
	return resp.json()


def verify_pending_instagram_proof(proof) -> dict:
	"""Attempts to confirm one pending Delivery Proof row. Returns
	{"verified": bool, "reason": str}. Never raises — every failure mode
	(no token, deleted post, caption doesn't qualify yet) is a normal,
	expected outcome for a polling job to log and retry next run, not an
	exception."""
	proof = proof if hasattr(proof, "name") else frappe.get_doc("Delivery Proof", proof)
	deal = frappe.get_doc("Collab Deal", proof.deal)

	token = get_valid_access_token(deal.creator)
	if not token:
		return {"verified": False, "reason": "no_valid_creator_token"}

	outlet_ig_url = frappe.db.get_value("Outlet", deal.outlet, "instagram_url")
	handle = _extract_handle(outlet_ig_url)
	if not handle:
		return {"verified": False, "reason": "outlet_has_no_instagram_handle_on_file"}

	try:
		media = fetch_media_detail(token, proof.instagram_media_id)
	except Exception as e:
		frappe.log_error(f"Instagram media fetch failed for proof {proof.name}: {e}", "instagram_verification.fetch")
		return {"verified": False, "reason": "fetch_failed"}

	if media.get("error"):
		return {"verified": False, "reason": f"graph_api_error: {media['error'].get('message', media['error'])}"}

	caption = media.get("caption") or ""
	timestamp = media.get("timestamp")

	if timestamp:
		posted_date = getdate(timestamp[:10])
		window_start = add_days(getdate(deal.accepted_at or deal.creation), -CLAIM_WINDOW_DAYS_BEFORE)
		window_end = add_days(getdate(deal.accepted_at or deal.creation), CLAIM_WINDOW_DAYS_AFTER)
		if not (window_start <= posted_date <= window_end):
			return {"verified": False, "reason": "posted_outside_plausible_window"}

	if not caption_mentions_handle(caption, handle):
		return {"verified": False, "reason": "caption_does_not_mention_outlet"}
	if not caption_has_disclosure_tag(caption):
		# Blueprint §06: "No match → deliverable is not marked complete...
		# the creator gets asked to fix the caption and repost" — never
		# silently pass an undisclosed paid post.
		return {"verified": False, "reason": "missing_disclosure_tag"}

	proof.verification_method = "graph_api"
	proof.disclosure_verified = 1
	proof.verified_at = now_datetime()
	proof.save(ignore_permissions=True)

	deal.status = "delivered"
	deal.save(ignore_permissions=True)
	frappe.db.commit()

	return {"verified": True, "reason": "matched"}


def poll_pending_instagram_deliveries() -> dict:
	"""Scheduled job (see hooks.py) — every Delivery Proof still sitting
	as an unverified Instagram claim on a deal that hasn't moved on
	(cancelled/expired deals are skipped, nothing to confirm there)."""
	rows = frappe.db.sql(
		"""
		SELECT dp.name
		FROM `tabDelivery Proof` dp
		JOIN `tabCollab Deal` d ON d.name = dp.deal
		WHERE dp.verification_method = 'manual'
		  AND dp.deliverable_type IN ('instagram_reel', 'instagram_story')
		  AND d.status IN ('accepted', 'funded')
		""",
		as_dict=True,
	)
	verified = 0
	errors = 0
	for row in rows:
		try:
			result = verify_pending_instagram_proof(row.name)
			if result["verified"]:
				verified += 1
		except Exception:
			errors += 1
			frappe.log_error(title="instagram_verification.poll_pending", message=frappe.get_traceback())
	return {"scanned": len(rows), "verified": verified, "errors": errors}
