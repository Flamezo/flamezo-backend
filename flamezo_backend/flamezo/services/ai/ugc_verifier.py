# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
UGC proof verifier
==================
Reads the Instagram/Facebook story view-count from the diner's uploaded
screen-recording and decides whether to auto-credit cashback or route the
claim to staff review.

Pipeline (per submission):
  1. Guard       — only run on freshly `proof_submitted` claims.
  2. Dedup       — reject claims whose proof video re-uses an already-seen hash.
  3. Template    — fetch the restaurant's story template image for visual comparison.
  4. AI verify   — send BOTH the proof video AND the template image to Gemini:
                     a) Real-phone check   (status bar, time, battery, carrier)
                     b) Template match     (story shown ≈ restaurant's template)
                     c) View-count OCR     (highest clearly-visible "Seen by" count)
                     d) Tamper detection   (editing, duplication, desktop UI, etc.)
  5. Decision    — confident & clean & real-phone & template-match → auto-credit
                   otherwise → flag for staff review.
"""

import os
import json
import time
import tempfile
import urllib.request

import frappe
from frappe.utils import cint, flt

# ── Prompts ──────────────────────────────────────────────────────────────────

# Sent when we have BOTH the proof video AND the restaurant's template image.
_OCR_PROMPT_WITH_TEMPLATE = """You are a fraud-prevention AI verifying a diner's UGC cashback claim for a restaurant.

You have been given TWO inputs:
  1. A PROOF VIDEO — a screen recording uploaded by the diner showing their Instagram or Facebook story's view count.
  2. A TEMPLATE IMAGE — the official story graphic the restaurant gave the diner to share.

Analyse both carefully and return STRICT JSON only (no prose, no markdown):

{
  "view_count": <integer — the HIGHEST clearly-readable story "Seen by" / viewer count shown in the video. 0 if unreadable.>,
  "confidence": <float 0.0-1.0 — how certain you are of the view_count number>,
  "is_story_insights": <true only if the video clearly shows a story's own "Seen by" / viewer list screen — NOT a feed post, NOT a reel, NOT a follower list>,
  "is_real_phone_recording": <true only if the video looks like a genuine phone screen recording — a phone status bar (clock, battery, signal/carrier) must be visible at some point>,
  "has_phone_status_bar": <true if a phone status bar with time AND at least one of battery/signal/carrier is clearly visible>,
  "story_matches_template": <true if the story content visible in the proof video clearly resembles the provided template image — same branding, colours, or graphic layout>,
  "tamper_signals": [
    <include zero or more of these exact strings if detected:
      "edited_number"           — the view count looks digitally altered or pasted in,
      "screenshot_of_screenshot"— the video appears to be a recording of another screen or image rather than a live phone,
      "not_a_story"             — content is not an Instagram/Facebook story (e.g. a feed post, reel, or profile page),
      "feed_post_not_story"     — the content is clearly a feed post rather than a story,
      "number_unreadable"       — view count digits cannot be read clearly,
      "inconsistent_numbers"    — multiple conflicting numbers shown with no clear winner,
      "no_status_bar"           — no phone status bar (time/battery/signal) is visible at any point,
      "desktop_ui"              — the recording appears to be from a desktop browser rather than a mobile device,
      "template_mismatch"       — the story shown does NOT visually match the provided restaurant template,
      "wrong_story_account"     — the insights shown appear to belong to a different story or account than the restaurant's
    >
  ]
}

Rules:
- Be CONSERVATIVE. If you cannot clearly read a genuine story view count, set view_count to 0 and confidence below 0.5.
- A real phone recording MUST show a status bar with clock + battery or signal at some point. If absent, add "no_status_bar".
- If the story content has clearly different branding, colours, or layout from the template, add "template_mismatch".
- Watch the ENTIRE video before deciding. The view count screen may appear briefly.
- Read the HIGHEST clearly-visible view/seen count. Do not invent or round numbers.
"""

# Fallback prompt — used when the restaurant's template is unavailable (no visual comparison possible).
_OCR_PROMPT_NO_TEMPLATE = """You are a fraud-prevention AI verifying a diner's UGC cashback claim for a restaurant.

You have been given a PROOF VIDEO — a screen recording uploaded by the diner showing their Instagram or Facebook story's view count.

Analyse the video carefully and return STRICT JSON only (no prose, no markdown):

{
  "view_count": <integer — the HIGHEST clearly-readable story "Seen by" / viewer count shown in the video. 0 if unreadable.>,
  "confidence": <float 0.0-1.0 — how certain you are of the view_count number>,
  "is_story_insights": <true only if the video clearly shows a story's own "Seen by" / viewer list screen — NOT a feed post, NOT a reel, NOT a follower list>,
  "is_real_phone_recording": <true only if the video looks like a genuine phone screen recording — a phone status bar (clock, battery, signal/carrier) must be visible at some point>,
  "has_phone_status_bar": <true if a phone status bar with time AND at least one of battery/signal/carrier is clearly visible>,
  "story_matches_template": null,
  "tamper_signals": [
    <include zero or more of these exact strings if detected:
      "edited_number", "screenshot_of_screenshot", "not_a_story", "feed_post_not_story",
      "number_unreadable", "inconsistent_numbers", "no_status_bar", "desktop_ui", "wrong_story_account"
    >
  ]
}

Rules:
- Be CONSERVATIVE. If you cannot clearly read a genuine story view count, set view_count to 0 and confidence below 0.5.
- A real phone recording MUST show a status bar with clock + battery or signal at some point. If absent, add "no_status_bar".
- Watch the ENTIRE video before deciding. The view count screen may appear briefly.
- Read the HIGHEST clearly-visible view/seen count. Do not invent or round numbers.
"""


def verify_submission(submission_name):
	"""Entry point — enqueued after the proof video is processed by the media pipeline."""
	try:
		sub = frappe.get_doc("UGC Story Submission", submission_name)
	except frappe.DoesNotExistError:
		return

	# 1. Guard — idempotent: only process claims awaiting verification.
	if sub.status != "proof_submitted":
		return

	from flamezo_backend.flamezo.api.ugc import (
		credit_ugc_cashback, PLATFORM_AI_PROVIDER, PLATFORM_AI_CONFIDENCE,
	)

	provider = PLATFORM_AI_PROVIDER
	threshold = PLATFORM_AI_CONFIDENCE
	sub.ai_provider = provider

	# 2. Dedup — same proof video hash on another live/credited claim = fraud.
	if sub.proof_video_hash:
		dup = frappe.db.exists(
			"UGC Story Submission",
			{
				"name": ["!=", sub.name],
				"proof_video_hash": sub.proof_video_hash,
				"status": ["in", ("credited", "proof_submitted", "flagged")],
			},
		)
		if dup:
			sub.status = "rejected"
			sub.rejection_reason = "Duplicate proof video (already used on another claim)."
			sub.ai_tamper_signals = "duplicate_video_hash"
			sub.save(ignore_permissions=True)
			frappe.db.commit()
			return

	# 3. Fetch the restaurant's story template for visual comparison.
	template_bytes, template_mime = _fetch_template(sub)

	# 4. AI OCR — read the view count, check real-phone + template match.
	result = _read_view_count(sub, provider, template_bytes, template_mime)

	sub.ai_view_count = cint(result.get("view_count"))
	sub.ai_confidence = flt(result.get("confidence"))
	sub.ai_tamper_signals = result.get("tamper_signals") or ""
	sub.ai_raw = result.get("raw") or ""

	# 5. Decision — ALL gates must pass for auto-credit.
	clean = not result.get("tamper_signals")
	confident = flt(result.get("confidence")) >= threshold
	has_views = cint(result.get("view_count")) > 0
	real_phone = result.get("is_real_phone_recording", False)
	# template_match is None when no template was available — don't block on it then.
	template_match = result.get("story_matches_template")
	template_ok = (template_match is True) or (template_match is None)

	if result.get("ready") and clean and confident and has_views and real_phone and template_ok:
		sub.save(ignore_permissions=True)
		frappe.db.commit()
		credit_ugc_cashback(sub, view_count=cint(result["view_count"]), source="ai")
	else:
		sub.status = "flagged"
		sub.save(ignore_permissions=True)
		frappe.db.commit()


def _fetch_template(submission):
	"""
	Return (bytes, mime_type) for the restaurant's story template image.
	Tries submission.template_used first, then the restaurant's UGC config.
	Returns (None, None) if unavailable or if the template is a video (can't
	do inline visual comparison for video templates).
	"""
	# Try submission.template_used (set when diner calls mark_story_shared).
	asset_name = submission.template_used
	if not asset_name:
		# Fall back to the restaurant's config first template.
		config_name = frappe.db.get_value(
			"UGC Cashback Config", {"restaurant": submission.restaurant}, "name"
		)
		if config_name:
			config = frappe.get_doc("UGC Cashback Config", config_name)
			if config.template_assets:
				asset_name = config.template_assets[0].media_asset

	if not asset_name:
		return None, None

	asset = frappe.db.get_value(
		"Media Asset", asset_name,
		["primary_url", "media_kind", "raw_object_key", "primary_object_key"],
		as_dict=True,
	)
	if not asset:
		return None, None

	# Only do inline comparison for images — video templates need a Files API upload
	# which adds latency and cost; skip for now, staff will compare manually.
	if asset.get("media_kind") == "video":
		return None, None

	cdn_url = asset.get("primary_url")
	if not cdn_url:
		return None, None

	try:
		req = urllib.request.Request(cdn_url, headers={"User-Agent": "Flamezo-UGC-Verifier/1.0"})
		with urllib.request.urlopen(req, timeout=15) as resp:
			image_bytes = resp.read()
		content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
		# Normalise to a Gemini-supported mime.
		if "png" in content_type:
			mime = "image/png"
		elif "webp" in content_type:
			mime = "image/webp"
		else:
			mime = "image/jpeg"
		return image_bytes, mime
	except Exception as e:
		frappe.log_error(f"UGC template fetch failed for {asset_name}: {e}", "UGC")
		return None, None


def _read_view_count(submission, provider, template_bytes=None, template_mime=None):
	"""
	Download the proof video, upload it to the Gemini Files API along with the
	restaurant's template image (when available), and ask Gemini to verify the
	claim in one pass.

	Returns {ready, view_count, confidence, is_real_phone_recording,
	         story_matches_template, tamper_signals, raw}.
	``ready=False`` routes to the staff queue — used whenever anything errors
	or the AI can't process the video, so auto-credit never fires unverified.
	"""
	if (provider or "Gemini") != "Gemini":
		return _not_ready("Provider has no video reader — manual review.")

	# Locate the proof video object key (primary after processing, raw as fallback).
	object_key = None
	if submission.proof_video:
		asset_dict = frappe.db.get_value(
			"Media Asset", submission.proof_video,
			["primary_object_key", "raw_object_key"], as_dict=True,
		)
		if asset_dict:
			object_key = asset_dict.get("primary_object_key") or asset_dict.get("raw_object_key")
	if not object_key:
		return _not_ready("Proof video object not found — manual review.")

	tmp_path = None
	uploaded_video = None
	try:
		import google.generativeai as genai
		from flamezo_backend.flamezo.media.storage import download_object
		from flamezo_backend.flamezo.services.ai.base import get_gemini_client

		# Download the proof video to a temp file.
		fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
		os.close(fd)
		download_object(object_key, tmp_path)

		# Configure Gemini and upload the video via the Files API.
		model = get_gemini_client()  # also calls genai.configure(api_key=...)
		uploaded_video = genai.upload_file(path=tmp_path, mime_type="video/mp4")

		for _ in range(30):  # poll up to ~60 s
			if uploaded_video.state.name == "ACTIVE":
				break
			if uploaded_video.state.name == "FAILED":
				return _not_ready("Gemini could not process the proof video — manual review.")
			time.sleep(2)
			uploaded_video = genai.get_file(uploaded_video.name)

		if uploaded_video.state.name != "ACTIVE":
			return _not_ready("Gemini video processing timed out — manual review.")

		# Build the content parts: [prompt, video, template_image (optional)].
		if template_bytes:
			prompt = _OCR_PROMPT_WITH_TEMPLATE
			content_parts = [
				prompt,
				uploaded_video,
				{"mime_type": template_mime, "data": template_bytes},
			]
		else:
			prompt = _OCR_PROMPT_NO_TEMPLATE
			content_parts = [prompt, uploaded_video]

		resp = model.generate_content(
			content_parts,
			generation_config={"response_mime_type": "application/json", "temperature": 0},
		)
		raw = (resp.text or "").strip()
		parsed = json.loads(raw)

		# Collect tamper signals from Gemini + our own derived checks.
		tamper = list(parsed.get("tamper_signals") or [])

		if not parsed.get("is_story_insights", False):
			if "not_a_story" not in tamper:
				tamper.append("not_story_insights")

		if not parsed.get("is_real_phone_recording", False):
			if "no_status_bar" not in tamper:
				tamper.append("no_status_bar")

		if not parsed.get("has_phone_status_bar", False):
			if "no_status_bar" not in tamper:
				tamper.append("no_status_bar")

		# template_mismatch is only meaningful when a template was provided.
		if template_bytes and parsed.get("story_matches_template") is False:
			if "template_mismatch" not in tamper:
				tamper.append("template_mismatch")

		return {
			"ready": True,
			"view_count": cint(parsed.get("view_count")),
			"confidence": flt(parsed.get("confidence")),
			"is_real_phone_recording": bool(parsed.get("is_real_phone_recording")),
			"story_matches_template": parsed.get("story_matches_template"),
			"tamper_signals": ",".join(sorted(set(tamper))),
			"raw": raw[:2000],
		}

	except Exception as e:
		frappe.log_error(f"UGC view-count OCR failed for {submission.name}: {e}", "UGC")
		return _not_ready(f"OCR error — manual review. ({str(e)[:120]})")

	finally:
		# Always clean up: delete the uploaded Gemini file + the temp video.
		try:
			if uploaded_video is not None:
				import google.generativeai as genai
				genai.delete_file(uploaded_video.name)
		except Exception:
			pass
		if tmp_path and os.path.exists(tmp_path):
			try:
				os.remove(tmp_path)
			except Exception:
				pass


def _not_ready(reason):
	return {
		"ready": False,
		"view_count": 0,
		"confidence": 0.0,
		"is_real_phone_recording": False,
		"story_matches_template": None,
		"tamper_signals": "",
		"raw": reason,
	}
